from __future__ import annotations

from lib.models import OrderBookRecord
from lib.orderbook import orderbook_record_to_sdk_book


def test_orderbook_record_to_sdk_book_preserves_levels() -> None:
    record = OrderBookRecord(
        marketId="123",
        updateTimestampMs=42,
        asks=[[0.62, 100.0]],
        bids=[[0.58, 80.0]],
    )

    book = orderbook_record_to_sdk_book(record)

    assert book.market_id == 123
    assert book.update_timestamp_ms == 42
    assert book.asks == [(0.62, 100.0)]
    assert book.bids == [(0.58, 80.0)]
