"""
Module specific to Kraken's spot and margin offerings
"""
import hashlib
import logging
import time
from typing import TYPE_CHECKING

import requests

from rotkehlchen.constants import (
    KRAKEN_FUTURES_API_VERSION,
)
from rotkehlchen.constants.misc import KRAKEN_FUTURES_BASE_URL
from rotkehlchen.db.settings import CachedSettings
from rotkehlchen.errors.misc import RemoteError
from rotkehlchen.exchanges.exchange import ExchangeQueryBalances
from rotkehlchen.exchanges.krakenbase import KrakenAccountType, KrakenBase, _check_and_get_response
from rotkehlchen.logging import RotkehlchenLogsAdapter
from rotkehlchen.types import (
    ApiKey,
    ApiSecret,
    Location,
)
from rotkehlchen.utils.mixins.cacheable import cache_response_timewise
from rotkehlchen.utils.mixins.lockable import protect_with_lock

if TYPE_CHECKING:
    from rotkehlchen.db.dbhandler import DBHandler
    from rotkehlchen.user_messages import MessagesAggregator


logger = logging.getLogger(__name__)
log = RotkehlchenLogsAdapter(logger)


class Krakenfutures(KrakenBase):
    def __init__(
            self,
            name: str,
            api_key: ApiKey,
            secret: ApiSecret,
            database: 'DBHandler',
            msg_aggregator: 'MessagesAggregator',
            kraken_account_type: KrakenAccountType | None = None,
            base_uri: str = KRAKEN_FUTURES_BASE_URL,
    ):
        super().__init__(
            name=name,
            location=Location.KRAKENFUTURES,
            api_key=api_key,
            secret=secret,
            database=database,
            msg_aggregator=msg_aggregator,
            base_uri=base_uri,
            kraken_account_type=kraken_account_type,
        )
        self.secret = ApiSecret(self.secret)

    def validate_api_key(self) -> tuple[bool, str]:
        """Validates that the Kraken API Key is good for usage in Rotkehlchen

        Makes sure that the following permission are given to the key:
        - Ability to query funds
        - Ability to query open/closed trades
        - Ability to query ledgers
        """
        valid, msg = self._validate_single_api_key_action(self.base_uri, 'accounts')
        if not valid:
            return False, msg

        return True, ''

    # ---- General exchanges interface ----
    @protect_with_lock()
    @cache_response_timewise()
    def query_balances(self) -> ExchangeQueryBalances:
        return self.query_balances_base('accounts')


    def query_private_api_method(self, method: str, req: dict | None = None) -> dict | str:
        """API queries that require a valid key/secret pair.

        Arguments:
        method -- API method name (string, no default)
        req    -- additional API request parameters (default: {})

        """
        if req is None:
            req = {}

        urlpath: str = '/derivatives/api/' + KRAKEN_FUTURES_API_VERSION + '/' + method if method is not None else ''
        urlpath_without_prefix = urlpath.removeprefix('/derivatives')
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
            full_url = self.base_uri + urlpath
            log.debug(f'Querying Kraken for {method} with {req} at URL: {full_url}')
            response = self.session.get(
                full_url,
                timeout=CachedSettings().get_timeout_tuple(),
            )
        except requests.exceptions.RequestException as e:
            raise RemoteError(f'Kraken API request failed due to {e!s}') from e
        self._manage_call_counter(method)

        decoded_json = _check_and_get_response(response, method)

        if isinstance(decoded_json, str):
            return decoded_json

        accounts: dict | None = self._get_inner_dict(decoded_json, 'accounts', method)
        cash: dict | None = self._get_inner_dict(accounts, 'cash', method)
        cash_balances: dict | None = self._get_inner_dict(cash, 'balances', method)

        # Make asset tickers all uppercase before returning to allign them with Kraken spot
        return {k.upper(): v for k, v in cash_balances.items()}

    @staticmethod
    def _get_inner_dict(dictionary, inner_dict_keyname, method) -> dict | None:
        result: dict | None = dictionary.get(inner_dict_keyname, None)
        if result is None:
            if method == 'accounts':
                return {}

            raise RemoteError(f'Missing result in kraken futures response for {method}')

        return result