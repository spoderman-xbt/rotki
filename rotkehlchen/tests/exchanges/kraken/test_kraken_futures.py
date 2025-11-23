import os
from unittest import mock

import pytest

from rotkehlchen.accounting.structures.balance import Balance
from rotkehlchen.assets.asset import Asset
from rotkehlchen.exchanges.kraken.krakenfutures import KrakenFutures
from rotkehlchen.fval import FVal
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



# @pytest.mark.skipif('CI' in os.environ, reason='temporarily skip kraken in CI')
# @pytest.mark.parametrize('kraken_demo_api_secret', [b'16NFMLWrVWf1TrHQtVExRFmBovnq'])
# def test_kraken_wrong_secret(demo_kraken_futures):
#     """Test that giving wrong api secret is detected
#
#     Uses the kraken demo
#     """
#     result, _ = demo_kraken_futures.validate_api_key()
#     assert not result
#     balances, msg = demo_kraken_futures.query_balances()
#     assert balances is None
#     assert 'Invalid API Key or API secret' in msg


# @pytest.mark.skipif('CI' in os.environ, reason='temporarily skip kraken in CI')
# @pytest.mark.parametrize('kraken_demo_api_key', ['fddad'])
# def test_kraken_wrong_key(demo_kraken_futures):
#     """Test that giving wrong api key is detected
#
#     Uses the kraken demo
#     """
#     result, _ = demo_kraken_futures.validate_api_key()
#     assert not result
#     balances, msg = demo_kraken_futures.query_balances()
#     assert balances is None
#     assert 'Invalid API Key or API secret' in msg
#

### Below tests are taken from test_kraken

def test_name():
    exchange = KrakenFutures('kraken1', 'a', b'YQ==', object(), object())  # b'YQ==' is base64 for 'a'
    assert exchange.location == Location.KRAKEN
    assert exchange.name == 'kraken1'


@pytest.mark.asset_test
def test_coverage_of_kraken_balances():
    response = requests.get('https://api.kraken.com/0/public/Assets')
    got_assets = set(response.json()['result'].keys())
    expected_assets = get_exchange_asset_symbols(
        exchange=Location.KRAKEN,
        query_suffix=';',  # exclude false-positives of delisted assets
    )

    # Special/staking assets and which assets they should map to
    special_assets = {
        'XTZ.S': Asset('XTZ'),
        'DOT.S': A_DOT,
        'ATOM.S': Asset('ATOM'),
        'EUR.M': A_EUR,
        'USD.M': A_USD,
        'XBT.M': A_BTC,
        'KSM.S': A_KSM,
        'ETH2.S': A_ETH2,
        'KAVA.S': Asset('KAVA'),
        'EUR.HOLD': A_EUR,
        'USD.HOLD': A_USD,
        'FLOW.S': Asset('FLOW'),
        'FLOWH.S': Asset('FLOW'),
        'FLOWH': Asset('FLOW'),
        'ADA.S': A_ADA,
        'SOL.S': Asset('SOL'),
        'KSM.P': A_KSM,  # kusama bonded for parachains
        'ALGO.S': Asset('ALGO'),
        'DOT.P': A_DOT,
        'MINA.S': Asset('MINA'),
        'TRX.S': strethaddress_to_identifier('0x50327c6c5a14DCaDE707ABad2E27eB517df87AB5'),
        'LUNA.S': strethaddress_to_identifier('0xd2877702675e6cEb975b4A1dFf9fb7BAF4C91ea9'),
        'SCRT.S': Asset('SCRT'),
        'MATIC.S': strethaddress_to_identifier('0x7D1AfA7B718fb893dB30A3aBc0Cfc608AaCfeBB0'),
        'GBP.HOLD': Asset('GBP'),
        'CHF.HOLD': Asset('CHF'),
        'CAD.HOLD': Asset('CAD'),
        'AUD.HOLD': Asset('AUD'),
        'AED.HOLD': Asset('AED'),
        'USDC.M': A_USDC,
        'GRT.S': A_GRT,
        'FLR.S': Asset('FLR'),
        'USDT.M': A_USDT,
        'DOT28.S': A_DOT,
        'GRT28.S': A_GRT,
        'SCRT21.S': Asset('SCRT'),
        'KAVA21.S': Asset('KAVA'),
        'ATOM21.S': Asset('ATOM'),
        'SOL03.S': Asset('SOL'),
        'FLOW14.S': Asset('FLOW'),
        'MATIC04.S': strethaddress_to_identifier('0x7D1AfA7B718fb893dB30A3aBc0Cfc608AaCfeBB0'),
        'KSM07.S': A_KSM,
    }
    missing_assets = {
        'ZARS',  # doesn't appear yet in the platform
        'ZMXN',  # not listed yet in the platform
    }

    for kraken_asset in got_assets:
        if kraken_asset in special_assets:
            assert asset_from_kraken(kraken_asset) == special_assets[kraken_asset]
        elif kraken_asset not in KRAKEN_DELISTED:
            try:
                asset_from_kraken(kraken_asset)
            except (DeserializationError, UnknownAsset):
                if kraken_asset not in missing_assets:
                    test_warnings.warn(UserWarning(
                        f'Found unknown primary asset {kraken_asset} in kraken. '
                        f'Support for it has to be added',
                    ))

    delisted = expected_assets - got_assets - set(KRAKEN_DELISTED)
    if delisted:
        test_warnings.warn(UserWarning(
            f'Detected newly delisted assets from Kraken: {delisted}. '
            f'Please update KRAKEN_DELISTED constant.',
        ))

