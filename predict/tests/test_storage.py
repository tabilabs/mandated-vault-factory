from __future__ import annotations

import json

from lib.position_storage import LocalPosition, PositionStorage


def test_corrupted_positions_file_returns_safe_empty_state(tmp_path) -> None:
    storage = PositionStorage(tmp_path)
    storage.path.write_text("{not-json")

    positions = storage.list_positions()

    assert positions == []


def test_storage_writes_atomically_and_round_trips_records(tmp_path) -> None:
    storage = PositionStorage(tmp_path)
    storage.upsert(
        LocalPosition(
            position_id="pos-1",
            market_id="123",
            question="Example market",
            outcome_name="YES",
            token_id="1001",
            side="BUY",
            strategy="MARKET",
            entry_time="2026-03-06T00:00:00+00:00",
            entry_price=0.5,
            quantity="1000000000000000000",
            notional_usdt=1.0,
            order_hash="0xhash",
            order_status="FILLED",
            fill_amount="1000000000000000000",
            fee_rate_bps=100,
        )
    )

    payload = json.loads(storage.path.read_text())
    temp_path = storage.path.with_suffix(".tmp")

    assert temp_path.exists() is False
    assert payload[0]["position_id"] == "pos-1"
    assert storage.get_position("pos-1") is not None
