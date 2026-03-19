from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from .api import PredictApiClient
from .auth import PredictAuthenticator
from .config import ConfigError, PredictConfig, RuntimeEnv
from .fixture_api import FixturePredictApiClient
from .models import PositionRecord
from .pnl import compute_pnl
from .position_storage import LocalPosition, PositionStorage


@dataclass
class PositionView:
    position_id: str
    market_id: str
    question: str
    outcome: str
    source: str
    status: str
    quantity_wei: str
    remote_quantity_wei: str | None
    current_mark_price: float
    entry_price: float | None
    notional_usdt: float | None
    unrealized_pnl_usdt: float | None
    unrealized_pnl_pct: float | None
    order_hash: str | None = None
    fee_rate_bps: int | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "positionId": self.position_id,
            "marketId": self.market_id,
            "question": self.question,
            "outcome": self.outcome,
            "source": self.source,
            "status": self.status,
            "quantityWei": self.quantity_wei,
            "remoteQuantityWei": self.remote_quantity_wei,
            "currentMarkPrice": self.current_mark_price,
            "entryPrice": self.entry_price,
            "notionalUsdt": self.notional_usdt,
            "unrealizedPnlUsdt": self.unrealized_pnl_usdt,
            "unrealizedPnlPct": self.unrealized_pnl_pct,
            "orderHash": self.order_hash,
            "feeRateBps": self.fee_rate_bps,
        }


class PositionsService:
    def __init__(self, config: PredictConfig) -> None:
        self._config = config
        self._storage = PositionStorage(config.storage_dir)

    def sync_fixture_positions(self) -> None:
        if self._config.env != RuntimeEnv.TEST_FIXTURE:
            return
        if self._storage.list_positions():
            return
        now = datetime.now(timezone.utc).isoformat()
        self._storage.seed(
            [
                LocalPosition(
                    position_id="pos-123-yes",
                    market_id="123",
                    question="Will the 2028 U.S. election winner be the Democratic nominee?",
                    outcome_name="YES",
                    token_id="1001",
                    side="BUY",
                    strategy="MARKET",
                    entry_time=now,
                    entry_price=0.60,
                    quantity="25000000000000000000",
                    notional_usdt=25.0,
                    order_hash="0xfixture-order-123",
                    order_status="FILLED",
                    fill_amount="25000000000000000000",
                    fee_rate_bps=100,
                    source="tracked",
                    status="OPEN",
                )
            ]
        )

    async def list_positions(self, *, include_all: bool = False) -> list[PositionView]:
        merged = await self._merge_positions()
        if include_all:
            return merged
        return [
            item
            for item in merged
            if item.source != "external" and item.status.upper() == "OPEN"
        ]

    async def get_position(self, position_id: str) -> PositionView:
        for position in await self._merge_positions(include_external=True):
            if position.position_id == position_id:
                return position
        raise ConfigError(f"Unknown position id: {position_id}")

    async def _merge_positions(
        self, include_external: bool = True
    ) -> list[PositionView]:
        local_positions = self._storage.list_positions()
        remote_positions = await self._fetch_remote_positions()
        remote_by_token = {
            item.tokenId: item for item in remote_positions if item.tokenId
        }
        views: list[PositionView] = []

        for local in local_positions:
            remote = remote_by_token.get(local.token_id)
            mark = await self._current_mark_price(local.market_id, local.outcome_name)
            merged_quantity = (
                str(remote.quantity)
                if remote and remote.quantity is not None
                else local.quantity
            )
            pnl = compute_pnl(
                quantity_wei=merged_quantity,
                entry_price=local.entry_price,
                current_mark_price=mark,
                notional_usdt=local.notional_usdt,
            )
            views.append(
                PositionView(
                    position_id=local.position_id,
                    market_id=local.market_id,
                    question=local.question,
                    outcome=local.outcome_name,
                    source=local.source,
                    status=(
                        remote.status if remote and remote.status else local.status
                    ).upper(),
                    quantity_wei=local.quantity,
                    remote_quantity_wei=merged_quantity
                    if remote and remote.quantity is not None
                    else None,
                    current_mark_price=mark,
                    entry_price=local.entry_price,
                    notional_usdt=local.notional_usdt,
                    unrealized_pnl_usdt=float(pnl.unrealized_pnl_usdt),
                    unrealized_pnl_pct=float(pnl.unrealized_pnl_pct),
                    order_hash=local.order_hash,
                    fee_rate_bps=local.fee_rate_bps,
                )
            )

        if include_external:
            tracked_tokens = {local.token_id for local in local_positions}
            for remote in remote_positions:
                if remote.tokenId in tracked_tokens:
                    continue
                question = await self._market_question(str(remote.marketId or ""))
                outcome = remote.outcomeName or "UNKNOWN"
                mark = await self._current_mark_price(
                    str(remote.marketId or ""), outcome
                )
                views.append(
                    PositionView(
                        position_id=remote.positionId
                        or f"external-{remote.marketId}-{remote.tokenId}",
                        market_id=str(remote.marketId or ""),
                        question=question,
                        outcome=outcome,
                        source="external",
                        status=(remote.status or "OPEN").upper(),
                        quantity_wei=str(remote.quantity or "0"),
                        remote_quantity_wei=str(remote.quantity or "0"),
                        current_mark_price=mark,
                        entry_price=None,
                        notional_usdt=None,
                        unrealized_pnl_usdt=None,
                        unrealized_pnl_pct=None,
                    )
                )

        return views

    async def _fetch_remote_positions(self) -> list[PositionRecord]:
        if self._config.env == RuntimeEnv.TEST_FIXTURE:
            client = FixturePredictApiClient()
            return await client.get_positions()
        if self._config.auth_signer_address is None:
            return []
        client = PredictApiClient(self._config)
        try:
            authenticator = PredictAuthenticator(self._config, client)
            client._jwt_provider = authenticator.get_jwt
            return await client.get_positions()
        finally:
            await client.close()

    async def _current_mark_price(self, market_id: str, outcome: str) -> float:
        detail = await self._get_market_detail(market_id)
        return detail["yes"] if outcome.upper() == "YES" else detail["no"]

    async def _market_question(self, market_id: str) -> str:
        detail = await self._get_market_detail(market_id)
        return detail["question"]

    async def _get_market_detail(self, market_id: str) -> dict[str, Any]:
        if self._config.env == RuntimeEnv.TEST_FIXTURE:
            client = FixturePredictApiClient()
            market = await client.get_market(market_id)
            orderbook = await client.get_orderbook(market_id)
            asks = orderbook.asks or []
            bids = orderbook.bids or []
            yes = round(
                ((asks[0][0] if asks else 0.5) + (bids[0][0] if bids else 0.5)) / 2,
                market.decimalPrecision or 2,
            )
            return {
                "question": market.question or market.title or "",
                "yes": yes,
                "no": round(1 - yes, market.decimalPrecision or 2),
            }
        client = PredictApiClient(self._config)
        try:
            market = await client.get_market(market_id)
            orderbook = await client.get_orderbook(market_id)
        finally:
            await client.close()
        asks = orderbook.asks or []
        bids = orderbook.bids or []
        yes = round(
            ((asks[0][0] if asks else 0.5) + (bids[0][0] if bids else 0.5)) / 2,
            market.decimalPrecision or 2,
        )
        return {
            "question": market.question or market.title or "",
            "yes": yes,
            "no": round(1 - yes, market.decimalPrecision or 2),
        }


def format_positions_table(positions: list[PositionView]) -> str:
    if not positions:
        return "No positions found."
    rows = [
        f"{'ID':<14} {'Market':<42} {'Side':<4} {'Mark':>6} {'PnL':>9} {'Source':<8}"
    ]
    for position in positions:
        label = (
            position.question
            if len(position.question) <= 42
            else position.question[:39] + "..."
        )
        pnl = (
            "-"
            if position.unrealized_pnl_usdt is None
            else f"{position.unrealized_pnl_usdt:+.2f}"
        )
        rows.append(
            f"{position.position_id:<14} {label:<42} {position.outcome:<4} {position.current_mark_price:>6.2f} {pnl:>9} {position.source:<8}"
        )
    return "\n".join(rows)
