import os
from unittest import mock

import pytest

from rotkehlchen.accounting.structures.balance import Balance
from rotkehlchen.assets.asset import Asset
from rotkehlchen.constants import ZERO
from rotkehlchen.constants.assets import A_BCH, A_BTC, A_ETH, A_USD, A_USDC, A_USDT, A_EUR
from rotkehlchen.exchanges.krakenfutures import Krakenfutures
from rotkehlchen.fval import FVal
from rotkehlchen.tests.utils.constants import A_LTC, A_GBP, A_XRP
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
        balances, error_or_empty = demo_kraken_futures.query_balances()
    assert error_or_empty == ''
    assert isinstance(balances, dict)
    for asset, entry in balances.items():
        assert isinstance(asset, Asset)
        assert isinstance(entry, Balance)

    assert balances[A_USD].amount == FVal('5000')
    assert balances[A_USD].usd_value == balances[A_USD].amount
    assert balances[A_EUR].amount == FVal('5000')
    assert balances[A_EUR].usd_value == balances[A_EUR].amount
    assert balances[A_GBP].amount == FVal('3791.9006')
    assert balances[A_GBP].usd_value == balances[A_GBP].amount
    assert balances[A_ETH].amount == FVal('1.5717981686')
    assert balances[A_ETH].usd_value > ZERO
    assert balances[A_LTC].amount == FVal('52.1910861801')
    assert balances[A_LTC].usd_value > ZERO
    assert balances[A_BTC].amount == FVal('0.0524990493')
    assert balances[A_BTC].usd_value > ZERO
    assert balances[A_BCH].amount == FVal('10.0184941402')
    assert balances[A_BCH].usd_value > ZERO
    assert balances[A_XRP].amount == FVal('2213.8685582')
    assert balances[A_XRP].usd_value > ZERO
    assert balances[A_USDC.identifier].amount == FVal('5000.65008452')
    assert balances[A_USDC.identifier].usd_value > ZERO
    assert balances[A_USDT.identifier].amount == FVal('5003.96313881')
    assert balances[A_USDT.identifier].usd_value > ZERO


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


# Below tests are taken from test_kraken

def test_name():
    exchange = Krakenfutures('kraken1', 'a', b'YQ==', object(), object())  # b'YQ==' is base64 for 'a'
    assert exchange.location == Location.KRAKENFUTURES
    assert exchange.name == 'krakenfutures1'
