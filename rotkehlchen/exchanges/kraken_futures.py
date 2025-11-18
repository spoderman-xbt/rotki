# Good kraken and python resource:
# https://github.com/zertrin/clikraken/tree/master/src/clikraken
import base64
import hashlib
import itertools
import json
import logging
import operator
import os
import time
from collections import defaultdict
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, Literal
from urllib.parse import urlencode

import gevent
import requests
from requests import Response

from rotkehlchen.accounting.structures.balance import Balance
from rotkehlchen.assets.converters import asset_from_kraken
from rotkehlchen.constants import (
    KRAKEN_API_VERSION,
    KRAKEN_BASE_URL,
    KRAKEN_FUTURES_API_VERSION,
    ZERO,
)
from rotkehlchen.constants.assets import A_ETH2, A_KFEE, A_USD
from rotkehlchen.constants.misc import KRAKEN_FUTURES_BASE_URL, KRAKEN_FUTURES_BASE_URL_PATH
from rotkehlchen.db.constants import KRAKEN_ACCOUNT_TYPE_KEY
from rotkehlchen.db.history_events import DBHistoryEvents
from rotkehlchen.db.settings import CachedSettings
from rotkehlchen.errors.asset import UnknownAsset
from rotkehlchen.errors.misc import RemoteError
from rotkehlchen.errors.serialization import DeserializationError
from rotkehlchen.exchanges.data_structures import MarginPosition
from rotkehlchen.exchanges.exchange import (
    ExchangeInterface,
    ExchangeQueryBalances,
    ExchangeWithExtras,
)
from rotkehlchen.exchanges.kraken import Kraken
from rotkehlchen.exchanges.utils import SignatureGeneratorMixin
from rotkehlchen.history.events.structures.asset_movement import (
    AssetMovement,
    create_asset_movement_with_fee,
)
from rotkehlchen.history.events.structures.base import (
    HistoryBaseEntry,
    HistoryEvent,
    HistoryEventSubType,
    HistoryEventType,
)
from rotkehlchen.history.events.structures.swap import SwapEvent, create_swap_events
from rotkehlchen.history.events.utils import create_group_identifier_from_unique_id
from rotkehlchen.inquirer import Inquirer
from rotkehlchen.logging import RotkehlchenLogsAdapter
from rotkehlchen.serialization.deserialize import deserialize_fval
from rotkehlchen.types import (
    ApiKey,
    ApiSecret,
    AssetAmount,
    ExchangeAuthCredentials,
    Location,
    Timestamp,
    TimestampMS,
)
from rotkehlchen.utils.misc import pairwise, ts_ms_to_sec, ts_now
from rotkehlchen.utils.mixins.cacheable import cache_response_timewise
from rotkehlchen.utils.mixins.enums import SerializableEnumNameMixin
from rotkehlchen.utils.mixins.lockable import protect_with_lock
from rotkehlchen.utils.serialization import jsonloads_dict

if TYPE_CHECKING:
    from rotkehlchen.assets.asset import AssetWithOracles
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


class KrakenFutures(Kraken):
    def __init__(
            self,
            name: str,
            api_key: ApiKey,
            secret: ApiSecret,
            database: 'DBHandler',
            msg_aggregator: 'MessagesAggregator',
    ):
        super().__init__(
            name=name,
            api_key=api_key,
            secret=secret,
            location=Location.KRAKEN_FUTURES,
            database=database,
            msg_aggregator=msg_aggregator,
        )
        # Kraken provides base64-encoded secrets, decode it for use with mixin methods
        self.secret = ApiSecret(base64.b64decode(self.secret))
        self.session.headers.update({'API-Key': self.api_key})
        self.call_counter = 0
        self.last_query_ts = 0
        self.history_events_db = DBHistoryEvents(self.db)
