from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import (
    LastSaleRecord,
    MarketRecord,
    MarketStatsRecord,
    OrderBookRecord,
    PositionRecord,
)


class FixturePredictApiClient:
    def __init__(self, fixture_path: Path | None = None) -> None:
        root = Path(__file__).resolve().parents[1]
        self._fixture_path = (
            fixture_path or root / "tests" / "fixtures" / "market_api.json"
        )
        self._payload = json.loads(self._fixture_path.read_text())

    async def close(self) -> None:
        return None

    async def get_markets(self, **params: Any) -> list[MarketRecord]:
        status = params.get("status")
        first = int(params.get("first", len(self._payload["markets"])))
        skip = int(params.get("skip", 0))
        markets = self._payload["markets"]

        if status:
            markets = [market for market in markets if market.get("status") == status]

        return [
            MarketRecord.model_validate(item) for item in markets[skip : skip + first]
        ]

    async def get_market(self, market_id: str | int) -> MarketRecord:
        for item in self._payload["markets"]:
            if str(item["id"]) == str(market_id):
                return MarketRecord.model_validate(item)
        raise KeyError(f"Unknown fixture market: {market_id}")

    async def get_market_stats(self, market_id: str | int) -> MarketStatsRecord:
        return MarketStatsRecord.model_validate(self._payload["stats"][str(market_id)])

    async def get_market_last_sale(self, market_id: str | int) -> LastSaleRecord:
        return LastSaleRecord.model_validate(
            self._payload["last_sales"][str(market_id)]
        )

    async def get_orderbook(self, market_id: str | int) -> OrderBookRecord:
        return OrderBookRecord.model_validate(
            self._payload["orderbooks"][str(market_id)]
        )

    async def get_positions(self) -> list[PositionRecord]:
        return [
            PositionRecord.model_validate(item)
            for item in self._payload.get("positions", [])
        ]
