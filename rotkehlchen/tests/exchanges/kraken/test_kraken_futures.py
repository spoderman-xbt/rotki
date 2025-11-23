import os
import warnings as test_warnings
from unittest import mock

import pytest
import requests

from rotkehlchen.accounting.structures.balance import Balance
from rotkehlchen.assets.asset import Asset
from rotkehlchen.assets.converters import asset_from_kraken
from rotkehlchen.constants.assets import A_USDC, A_USDT
from rotkehlchen.errors.asset import UnknownAsset
from rotkehlchen.errors.serialization import DeserializationError
from rotkehlchen.exchanges.krakenfutures import Krakenfutures
from rotkehlchen.fval import FVal
from rotkehlchen.tests.utils.exchanges import get_exchange_asset_symbols
from rotkehlchen.tests.utils.kraken import KRAKEN_DELISTED
from rotkehlchen.types import Location


@pytest.mark.skipif('CI' in os.environ, reason='temporarily skip kraken in CI')
def test_kraken_validate_key(demo_kraken_futures):
    """Test that validate api key works for a correct api key

    Uses the kraken demo
    """
    result, msg = demo_kraken_futures.validate_api_key()
    assert result is True
    assert msg == ''


def test_querying_balances(demo_kraken_futures):
    # Below mock is used to fix AttributeError: type object 'Inquirer' has no attribute '_cached_current_price'
    find_usd_price_mock = mock.patch(
        'rotkehlchen.inquirer.Inquirer.find_usd_price',
        return_value=1,
    )

    with find_usd_price_mock:
        result, error_or_empty = demo_kraken_futures.query_balances()
    assert error_or_empty == ''
    assert isinstance(result, dict)
    for asset, entry in result.items():
        assert isinstance(asset, Asset)
        assert isinstance(entry, Balance)

    assert result['USD'] == Balance(FVal(5000), usd_value=FVal(5000))
    assert result['EUR'] == Balance(FVal(5000), usd_value=FVal(5000))
    assert result['GBP'] == Balance(FVal(3791.9006), usd_value=FVal(3791.9006))
    assert result['BTC'].amount > 0
    assert result['ETH'].amount > 0
    assert result['LTC'].amount > 0
    assert result['BCH'].amount > 0
    assert result['XRP'].amount > 0
    assert result[A_USDC.identifier].amount > 0
    assert result[A_USDT.identifier].amount > 0



@pytest.mark.skipif('CI' in os.environ, reason='temporarily skip kraken in CI')
@pytest.mark.parametrize('kraken_demo_api_secret', [b'16NFMLWrVWf1TrHQtVExRFmBovnq'])
def test_kraken_wrong_secret(demo_kraken_futures):
    """Test that giving wrong api secret is detected

    Uses the kraken demo
    """
    result, _ = demo_kraken_futures.validate_api_key()
    assert not result
    balances, msg = demo_kraken_futures.query_balances()
    assert balances is None
    assert 'authenticationError' in msg


@pytest.mark.skipif('CI' in os.environ, reason='temporarily skip kraken in CI')
@pytest.mark.parametrize('kraken_demo_api_key', ['fddad'])
def test_kraken_wrong_key(demo_kraken_futures):
    """Test that giving wrong api key is detected

    Uses the kraken demo
    """
    result, _ = demo_kraken_futures.validate_api_key()
    assert not result
    balances, msg = demo_kraken_futures.query_balances()
    assert balances is None
    assert 'authenticationError' in msg


### Below tests are taken from test_kraken

def test_name():
    exchange = Krakenfutures('kraken1', 'a', b'YQ==', object(), object())  # b'YQ==' is base64 for 'a'
    assert exchange.location == Location.KRAKENFUTURES
    assert exchange.name == 'krakenfutures1'
