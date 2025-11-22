"""
Module specific to Kraken's spot and margin offerings
"""
import base64
import hashlib
import json
import logging
import os
import time
from typing import TYPE_CHECKING, Literal

import requests
from requests import Response

from rotkehlchen.constants import (
    KRAKEN_BASE_URL,
    KRAKEN_FUTURES_API_VERSION,
)
from rotkehlchen.constants.misc import KRAKEN_FUTURES_BASE_URL, KRAKEN_FUTURES_BASE_URL_PATH
from rotkehlchen.db.settings import CachedSettings
from rotkehlchen.errors.misc import RemoteError
from rotkehlchen.exchanges.data_structures import MarginPosition
from rotkehlchen.exchanges.kraken.kraken import Kraken
from rotkehlchen.exchanges.kraken.kraken_base import KrakenAccountType, KrakenBase
from rotkehlchen.history.events.structures.base import (
    HistoryEvent,
)
from rotkehlchen.history.events.structures.swap import SwapEvent
from rotkehlchen.logging import RotkehlchenLogsAdapter
from rotkehlchen.types import (
    ApiKey,
    ApiSecret,
    Location,
    Timestamp,
)
from rotkehlchen.utils.serialization import jsonloads_dict

if TYPE_CHECKING:
    from rotkehlchen.db.dbhandler import DBHandler
    from rotkehlchen.user_messages import MessagesAggregator


logger = logging.getLogger(__name__)
log = RotkehlchenLogsAdapter(logger)

KRAKEN_QUERY_TRIES = 8
KRAKEN_BACKOFF_DIVIDEND = 15
MAX_CALL_COUNTER_INCREASE = 2  # Trades and Ledger produce the max increase


def _check_and_get_response(response: Response, method: str) -> str | dict:
    """Checks the kraken response and if it's successful returns the result.

    If there is recoverable error a string is returned explaining the error
    May raise:
    - RemoteError if there is an unrecoverable/unexpected remote error
    """
    if response.status_code in {520, 525, 504}:
        log.debug(f'Kraken returned status code {response.status_code}')
        return 'Usual kraken 5xx shenanigans'
    if response.status_code != 200:
        raise RemoteError(
            f'Kraken API request {response.url} for {method} failed with HTTP status '
            f'code: {response.status_code}')

    try:
        log.debug(f'KRAKEN FUTURES RESPONSE: {response}')
        log.debug(f'KRAKEN FUTURES RESPONSE: {response.text}')
        log.debug(f'KRAKEN FUTURES RESPONSE: {response.content}')
        log.debug(f'KRAKEN FUTURES RESPONSE: {response.raw}')
        decoded_json = jsonloads_dict(response.text)
    except json.decoder.JSONDecodeError as e:
        raise RemoteError(f'Invalid JSON in Kraken response. {e}') from e

    error = decoded_json.get('error', None)
    if error:
        if isinstance(error, list) and len(error) != 0:
            error = error[0]

        if 'Rate limit exceeded' in error:
            log.debug(f'Kraken: Got rate limit exceeded error: {error}')
            return 'Rate limited exceeded'

        # else
        raise RemoteError(error)

    result = decoded_json.get('result', None)
    if result is None:
        if method == 'Balance':
            return {}

        raise RemoteError(f'Missing result in kraken response for {method}')

    return result


class KrakenFutures(KrakenBase):
    def __init__(
            self,
            name: str,
            api_key: ApiKey,
            secret: ApiSecret,
            database: 'DBHandler',
            msg_aggregator: 'MessagesAggregator',
            kraken_account_type: KrakenAccountType | None = None,
            base_uri: str = KRAKEN_BASE_URL,
    ):
        super().__init__(
            name=name,
            location=Location.KRAKEN_FUTURES,
            api_key=api_key,
            secret=secret,
            database=database,
            msg_aggregator=msg_aggregator,
            base_uri=base_uri,
            kraken_account_type=kraken_account_type,
        )
        # Kraken provides base64-encoded secrets, decode it for use with mixin methods
        if name == 'demo_kraken':  # TODO: Remove test dependent code from PROD
            self.secret = ApiSecret(self.secret)
        else:  # TODO: See if this is the case for PROD
            self.secret = ApiSecret(base64.b64decode(self.secret))

    def validate_api_key(self) -> tuple[bool, str]:
        """Validates that the Kraken API Key is good for usage in Rotkehlchen

        Makes sure that the following permission are given to the key:
        - Ability to query funds
        - Ability to query open/closed trades
        - Ability to query ledgers
        """
        valid, msg = self._validate_single_api_key_action(KRAKEN_FUTURES_BASE_URL, 'accounts')
        if not valid:
            return False, msg

        return True, ''


    def query_api_method(self, method: str, req: dict | None = None) -> dict | str:
        """API queries that require a valid key/secret pair.

        Arguments:
        method -- API method name (string, no default)
        req    -- additional API request parameters (default: {})

        """
        if req is None:
            req = {}

        urlpath: str = os.path.join(KRAKEN_FUTURES_BASE_URL_PATH, KRAKEN_FUTURES_API_VERSION, method if method is not None else '')
        urlpath_without_prefix = urlpath.removeprefix('/derivatives')  # TODO: Could prob make nicer in setup/constants

        req['nonce'] = str(int(1000 * time.time()))
        # post_data = urlencode(req)
        post_data = ''

        # any unicode strings must be turned to bytes
        hashable = (post_data + req['nonce'] + urlpath_without_prefix).encode()
        message = hashlib.sha256(hashable).digest()
        signature = self.generate_hmac_b64_signature(
            message=message,
            digest_algorithm=hashlib.sha512,
        )
        self.session.headers.update({
            'APIKey': self.api_key,
            'Nonce': req['nonce'],
            'Authent': signature,
        })
        try:
            full_url = KRAKEN_FUTURES_BASE_URL + urlpath
            log.debug(f'Querying Kraken for {method} with {req} at URL: {full_url}')
            response = self.session.get(
                full_url,
                timeout=CachedSettings().get_timeout_tuple(),
            )
        except requests.exceptions.RequestException as e:
            raise RemoteError(f'Kraken API request failed due to {e!s}') from e
        self._manage_call_counter(method)

        return _check_and_get_response(response, method)

    def query_until_finished(
            self,
            endpoint: Literal['Ledgers'],
            keyname: str,
            start_ts: Timestamp,
            end_ts: Timestamp,
            extra_dict: dict | None = None,
    ) -> tuple[list, bool]:
        """ Abstracting away the functionality of querying a kraken endpoint where
        you need to check the 'count' of the returned results and provide sufficient
        calls with enough offset to gather all the data of your query.
        """
        result: list = []

        with_errors = False
        log.debug(
            f'Querying Kraken {endpoint} from {start_ts} to '
            f'{end_ts} with extra_dict {extra_dict}',
        )
        response = self._query_endpoint_for_period(
            endpoint=endpoint,
            start_ts=start_ts,
            end_ts=end_ts,
            extra_dict=extra_dict,
        )
        count = response['count']
        offset = len(response[keyname])
        result.extend(response[keyname].values())

        log.debug(f'Kraken {endpoint} Query Response with count:{count}')

        while offset < count:
            log.debug(
                f'Querying Kraken {endpoint} from {start_ts} to {end_ts} '
                f'with offset {offset} and extra_dict {extra_dict}',
            )
            try:
                response = self._query_endpoint_for_period(
                    endpoint=endpoint,
                    start_ts=start_ts,
                    end_ts=end_ts,
                    offset=offset,
                    extra_dict=extra_dict,
                )
            except RemoteError as e:
                with_errors = True
                log.error(
                    f'One of krakens queries when querying endpoint for period failed '
                    f'with {e!s}. Returning only results we have.',
                )
                break

            if count != response['count']:
                log.error(
                    f'Kraken unexpected response while querying endpoint for period. '
                    f'Original count was {count} and response returned {response["count"]}',
                )
                with_errors = True
                break

            response_length = len(response[keyname])
            offset += response_length
            if response_length == 0 and offset != count:
                # If we have provided specific filtering then this is a known
                # issue documented below, so skip the warning logging
                # https://github.com/rotki/rotki/issues/116
                if extra_dict:
                    break
                # it is possible that kraken misbehaves and either does not
                # send us enough results or thinks it has more than it really does
                log.warning(
                    f'Missing {count - offset} results when querying kraken '
                    f'endpoint {endpoint}',
                )
                with_errors = True
                break

            result.extend(response[keyname].values())

        return result, with_errors


    def query_online_margin_history(
            self,
            start_ts: Timestamp,  # pylint: disable=unused-argument
            end_ts: Timestamp,
    ) -> list[MarginPosition]:
        return []  # noop for kraken futures

    def process_kraken_events_for_trade(
            self,
            trade_parts: list[HistoryEvent],
    ) -> list[SwapEvent]:
        return []  # noop for the moment

    # TODO: Might be other missing no-ops that I removed here