from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from lib.api import PredictApiError
from lib.config import PredictConfig
from lib.market_service import MarketService
from lib.models import LastSaleRecord, MarketRecord, MarketStatsRecord, OrderBookRecord


def run_predictclaw(
    *args: str, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    predict_root = Path(__file__).resolve().parents[1]
    command_env = os.environ.copy()
    if env:
        command_env.update(env)
    return subprocess.run(
        [sys.executable, str(predict_root / "scripts" / "predictclaw.py"), *args],
        cwd=predict_root,
        env=command_env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_trending_markets_cli_outputs_sorted_rows() -> None:
    result = run_predictclaw(
        "markets",
        "trending",
        "--json",
        env={"PREDICT_ENV": "test-fixture"},
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload[0]["id"] == "123"
    assert payload[0]["yesMarkPrice"] == 0.6
    assert payload[0]["noMarkPrice"] == 0.4
    assert payload[0]["volume24hUsd"] >= payload[1]["volume24hUsd"]


def test_market_detail_json_returns_enriched_payload() -> None:
    result = run_predictclaw(
        "market",
        "123",
        "--json",
        env={"PREDICT_ENV": "test-fixture"},
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["id"] == "123"
    assert payload["stats"]["liquidityUsd"] == 500000.0
    assert payload["orderbook"]["marketId"] == "123"
    assert payload["yesMarkPrice"] == 0.6
    assert payload["noMarkPrice"] == 0.4


def test_search_no_matches_returns_user_safe_message() -> None:
    result = run_predictclaw(
        "markets",
        "search",
        "nonesuch-query",
        env={"PREDICT_ENV": "test-fixture"},
    )

    assert result.returncode == 0
    assert "No markets found" in result.stdout
    assert "Traceback" not in result.stdout + result.stderr


class _MissingOrderbookClient:
    async def get_markets(self, **_kwargs):
        return [
            MarketRecord(
                id="1501",
                title="Live-ish market",
                question="Will fallback pricing still work?",
                status="OPEN",
                decimalPrecision=2,
                volume24hUsd=123.0,
            )
        ]

    async def get_market(self, market_id):
        return MarketRecord(
            id=str(market_id),
            title="Live-ish market",
            question="Will fallback pricing still work?",
            status="OPEN",
            decimalPrecision=2,
            volume24hUsd=123.0,
        )

    async def get_market_stats(self, market_id):
        return MarketStatsRecord(marketId=str(market_id), volume24hUsd=123.0)

    async def get_market_last_sale(self, market_id):
        return LastSaleRecord(marketId=str(market_id), price=0.73)

    async def get_orderbook(self, market_id):
        raise PredictApiError(
            f"missing orderbook for {market_id}",
            status_code=404,
            method="GET",
            path=f"/v1/orderbook/{market_id}",
        )

    async def close(self):
        return None


@pytest.mark.asyncio
async def test_market_service_trending_tolerates_missing_orderbook() -> None:
    service = MarketService(PredictConfig.from_env({"PREDICT_ENV": "testnet"}))
    service._make_client = lambda: _MissingOrderbookClient()  # type: ignore[method-assign]

    summaries = await service.get_trending(limit=1)

    assert len(summaries) == 1
    assert summaries[0].id == "1501"
    assert summaries[0].yes_mark_price == 0.73
    assert summaries[0].no_mark_price == 0.27


@pytest.mark.asyncio
async def test_market_service_detail_tolerates_missing_orderbook() -> None:
    service = MarketService(PredictConfig.from_env({"PREDICT_ENV": "testnet"}))
    service._make_client = lambda: _MissingOrderbookClient()  # type: ignore[method-assign]

    detail = await service.get_detail("1501")

    assert str(detail.market.id) == "1501"
    assert detail.last_sale.price == 0.73
    assert detail.orderbook.asks == []
    assert detail.orderbook.bids == []
    assert detail.yes_mark_price == 0.73
    assert detail.no_mark_price == 0.27
