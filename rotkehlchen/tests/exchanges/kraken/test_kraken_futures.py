import os

import pytest

from rotkehlchen.accounting.structures.balance import Balance
from rotkehlchen.assets.asset import Asset


@pytest.mark.skipif('CI' in os.environ, reason='temporarily skip kraken in CI')
def test_kraken_validate_key(demo_kraken_futures):
    """Test that validate api key works for a correct api key

    Uses the kraken demo
    """
    result, msg = demo_kraken_futures.validate_api_key()
    assert result is True
    assert msg == ''


def test_querying_balances(demo_kraken_futures):
    result, error_or_empty = demo_kraken_futures.query_balances()
    assert error_or_empty == ''
    assert isinstance(result, dict)
    for asset, entry in result.items():
        assert isinstance(asset, Asset)
        assert isinstance(entry, Balance)

    assert result['USD'] == 5000



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
