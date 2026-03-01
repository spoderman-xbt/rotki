import json
import pytest
from rotkehlchen.exchanges.kraken import Kraken
from rotkehlchen.tests.utils.kraken import KRAKEN_FUTURES_ACCOUNT_LOG_RESPONSE
from rotkehlchen.types import ApiKey, ApiSecret, Location
from rotkehlchen.constants.assets import A_ETH, A_USD, A_EUR
from rotkehlchen.history.events.structures.base import (
    HistoryEvent,
    HistoryEventSubType,
    HistoryEventType,
)
from rotkehlchen.history.events.structures.swap import SwapEvent

def test_process_all_raw_logs(database, messages_aggregator):
    import os
    from rotkehlchen.history.events.structures.asset_movement import AssetMovement
    kraken = Kraken(
        name='kraken_test',
        api_key=ApiKey('a'),
        secret=ApiSecret(b'YQ=='),
        database=database,
        msg_aggregator=messages_aggregator
    )
    
    path = os.path.join('rotkehlchen', 'tests', 'utils', 'raw_logs.json')
    with open(path, 'r') as f:
        logs = json.load(f)
    
    events = kraken.process_futures_account_log(logs)
    
    assert len(events) > 0
    print(f"Processed {len(logs)} logs into {len(events)} events")
    
    swap_events = [e for e in events if isinstance(e, SwapEvent)]
    history_events = [e for e in events if isinstance(e, HistoryEvent)]
    asset_movements = [e for e in events if isinstance(e, AssetMovement)]
    
    # 1. pi_ethusd trade
    eth_trade = next((e for e in swap_events if e.asset == A_ETH), None)
    assert eth_trade is not None, "pi_ethusd trade should be processed"
    
    # 2. funding rate change
    funding = next((e for e in history_events if e.group_identifier == "realized_funding_372"), None)
    assert funding is not None
    assert funding.asset == A_ETH
    assert funding.event_type == HistoryEventType.RECEIVE
    
    # 3. futures assignor
    assignor = next((e for e in swap_events if e.notes and "assignor" in e.notes), None)
    assert assignor is not None
    
    # 4. futures liquidation
    liquidation = next((e for e in swap_events if e.notes and "liquidation" in e.notes), None)
    assert liquidation is not None
    
    # 5 & 6. Transfers
    transfer = next((e for e in asset_movements if e.asset.identifier == "EUR"), None)
    assert transfer is not None
    admin_transfer = next((e for e in asset_movements if e.asset.identifier == "USD"), None)
    assert admin_transfer is not None

def test_process_small_sample(database, messages_aggregator):
    kraken = Kraken(
        name='kraken_test',
        api_key=ApiKey('a'),
        secret=ApiSecret(b'YQ=='),
        database=database,
        msg_aggregator=messages_aggregator
    )
    
    logs = json.loads(KRAKEN_FUTURES_ACCOUNT_LOG_RESPONSE)['logs']
    events = kraken.process_futures_account_log(logs)
    
    from rotkehlchen.history.events.structures.asset_movement import AssetMovement
    swap_events = [e for e in events if isinstance(e, SwapEvent)]
    history_events = [e for e in events if isinstance(e, HistoryEvent)]
    asset_movements = [e for e in events if isinstance(e, AssetMovement)]
    
    # Each swap trade produces 3 SwapEvents (spend, receive, fee)
    # eth trade (3) + assignor (3) + liquidation (3) = 9
    assert len(swap_events) == 9
    assert len(history_events) == 1 # funding
    # Each transfer produces 1 AssetMovement (since fee is 0)
    assert len(asset_movements) == 2 # transfer, admin transfer
    
    # 1. pi_ethusd trade
    eth_trade = next((e for e in swap_events if e.asset == A_ETH), None)
    assert eth_trade is not None
    
    # 2. funding
    funding = next((e for e in history_events if e.group_identifier == "realized_funding_372"), None)
    assert funding is not None
    assert funding.asset == A_ETH
    
    # 5. transfer
    transfer = next((e for e in asset_movements if e.asset.identifier == "EUR"), None)
    assert transfer is not None
