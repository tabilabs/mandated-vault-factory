from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


WEI_SCALE = Decimal(10) ** 18


@dataclass
class PnLSnapshot:
    quantity_tokens: Decimal
    current_mark_price: Decimal
    current_value_usdt: Decimal
    notional_usdt: Decimal
    unrealized_pnl_usdt: Decimal
    unrealized_pnl_pct: Decimal

    def to_dict(self) -> dict[str, float]:
        return {
            "quantityTokens": float(self.quantity_tokens),
            "currentMarkPrice": float(self.current_mark_price),
            "currentValueUsdt": float(self.current_value_usdt),
            "notionalUsdt": float(self.notional_usdt),
            "unrealizedPnlUsdt": float(self.unrealized_pnl_usdt),
            "unrealizedPnlPct": float(self.unrealized_pnl_pct),
        }


def compute_pnl(
    *,
    quantity_wei: str,
    entry_price: float,
    current_mark_price: float,
    notional_usdt: float,
) -> PnLSnapshot:
    quantity_tokens = Decimal(quantity_wei) / WEI_SCALE
    mark = Decimal(str(current_mark_price))
    notional = Decimal(str(notional_usdt))
    current_value = quantity_tokens * mark
    pnl = current_value - notional
    pnl_pct = Decimal("0") if notional == 0 else (pnl / notional) * Decimal("100")
    return PnLSnapshot(
        quantity_tokens=quantity_tokens,
        current_mark_price=mark,
        current_value_usdt=current_value,
        notional_usdt=notional,
        unrealized_pnl_usdt=pnl,
        unrealized_pnl_pct=pnl_pct,
    )
