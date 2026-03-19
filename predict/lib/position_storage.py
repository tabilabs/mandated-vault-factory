from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any


_storage_lock = Lock()


@dataclass
class LocalPosition:
    position_id: str
    market_id: str
    question: str
    outcome_name: str
    token_id: str
    side: str
    strategy: str
    entry_time: str
    entry_price: float
    quantity: str
    notional_usdt: float
    order_hash: str
    order_status: str
    fill_amount: str | None
    fee_rate_bps: int
    source: str = "tracked"
    notes: str | None = None
    status: str = "OPEN"

    def to_dict(self) -> dict[str, Any]:
        return {
            "position_id": self.position_id,
            "market_id": self.market_id,
            "question": self.question,
            "outcome_name": self.outcome_name,
            "token_id": self.token_id,
            "side": self.side,
            "strategy": self.strategy,
            "entry_time": self.entry_time,
            "entry_price": self.entry_price,
            "quantity": self.quantity,
            "notional_usdt": self.notional_usdt,
            "order_hash": self.order_hash,
            "order_status": self.order_status,
            "fill_amount": self.fill_amount,
            "fee_rate_bps": self.fee_rate_bps,
            "source": self.source,
            "notes": self.notes,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "LocalPosition":
        normalized = {
            "position_id": payload.get("position_id", payload.get("positionId", "")),
            "market_id": payload.get("market_id", payload.get("marketId", "")),
            "question": payload.get("question", payload.get("market_question", "")),
            "outcome_name": payload.get(
                "outcome_name", payload.get("outcome", "UNKNOWN")
            ),
            "token_id": payload.get("token_id", payload.get("tokenId", "")),
            "side": payload.get("side", "BUY"),
            "strategy": payload.get("strategy", "MARKET"),
            "entry_time": payload.get("entry_time", payload.get("created_at", "")),
            "entry_price": payload.get("entry_price", 0.0),
            "quantity": payload.get("quantity", payload.get("size_wei", "0")),
            "notional_usdt": payload.get("notional_usdt", 0.0),
            "order_hash": payload.get("order_hash", ""),
            "order_status": payload.get("order_status", payload.get("status", "OPEN")),
            "fill_amount": payload.get("fill_amount"),
            "fee_rate_bps": payload.get("fee_rate_bps", 0),
            "source": payload.get("source", "tracked"),
            "notes": payload.get("notes"),
            "status": payload.get("status", "OPEN"),
        }
        return cls(**normalized)


class PositionStorage:
    def __init__(self, storage_dir: Path) -> None:
        self.storage_dir = storage_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.storage_dir / "positions.json"

    def list_positions(self) -> list[LocalPosition]:
        return [LocalPosition.from_dict(item) for item in self._read_payload()]

    def get_position(self, position_id: str) -> LocalPosition | None:
        for position in self.list_positions():
            if position.position_id == position_id:
                return position
        return None

    def upsert(self, position: LocalPosition) -> None:
        with _storage_lock:
            positions = self.list_positions()
            replaced = False
            for index, existing in enumerate(positions):
                if existing.position_id == position.position_id:
                    positions[index] = position
                    replaced = True
                    break
            if not replaced:
                positions.append(position)
            self._write_payload([item.to_dict() for item in positions])

    def seed(self, positions: list[LocalPosition]) -> None:
        with _storage_lock:
            self._write_payload([item.to_dict() for item in positions])

    def _read_payload(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            payload = json.loads(self.path.read_text())
        except json.JSONDecodeError:
            return []
        if not isinstance(payload, list):
            return []
        return [item for item in payload if isinstance(item, dict)]

    def _write_payload(self, payload: list[dict[str, Any]]) -> None:
        temp_path = self.path.with_suffix(".tmp")
        temp_path.write_text(json.dumps(payload, indent=2))
        temp_path.replace(self.path)
