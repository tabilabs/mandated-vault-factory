from __future__ import annotations

from dataclasses import dataclass
from typing import cast

MIN_COVERAGE = 0.85
NECESSARY_PROBABILITY = 0.98
TIER_THRESHOLDS: list[tuple[float, int, str, str]] = [
    (0.95, 1, "HIGH", "near-arbitrage"),
    (0.90, 2, "GOOD", "strong hedge"),
    (0.85, 3, "MODERATE", "decent hedge"),
    (0.00, 4, "LOW", "speculative"),
]


@dataclass
class HedgePortfolio:
    target_market_id: str
    target_question: str
    target_side: str
    target_price: float
    cover_market_id: str
    cover_question: str
    cover_side: str
    cover_price: float
    coverage: float
    loss_probability: float
    expected_profit: float
    total_cost: float
    tier: int
    tier_label: str
    relationship: str

    def to_dict(self) -> dict[str, object]:
        return {
            "targetMarketId": self.target_market_id,
            "targetQuestion": self.target_question,
            "targetSide": self.target_side,
            "targetPrice": self.target_price,
            "coverMarketId": self.cover_market_id,
            "coverQuestion": self.cover_question,
            "coverSide": self.cover_side,
            "coverPrice": self.cover_price,
            "coverage": self.coverage,
            "lossProbability": self.loss_probability,
            "expectedProfit": self.expected_profit,
            "totalCost": self.total_cost,
            "tier": self.tier,
            "tierLabel": self.tier_label,
            "relationship": self.relationship,
        }


def calculate_coverage_metrics(
    target_price: float, cover_probability: float, total_cost: float
) -> dict[str, float]:
    p_target = target_price
    p_not_target = 1 - target_price
    coverage = p_target + p_not_target * cover_probability
    loss_probability = p_not_target * (1 - cover_probability)
    expected_profit = coverage - total_cost
    return {
        "coverage": round(coverage, 4),
        "loss_probability": round(loss_probability, 4),
        "expected_profit": round(expected_profit, 4),
    }


def classify_tier(coverage: float) -> tuple[int, str]:
    for threshold, tier, label, _desc in TIER_THRESHOLDS:
        if coverage >= threshold:
            return tier, label
    return 4, "LOW"


def build_portfolio(
    *,
    target_market: dict[str, object],
    cover_market: dict[str, object],
    target_position: str,
    cover_position: str,
    cover_probability: float,
    relationship: str,
) -> HedgePortfolio | None:
    target_price = float(
        cast(
            float | int | str,
            target_market["yes_price"]
            if target_position == "YES"
            else target_market["no_price"],
        )
    )
    cover_price = float(
        cast(
            float | int | str,
            cover_market["yes_price"]
            if cover_position == "YES"
            else cover_market["no_price"],
        )
    )
    total_cost = round(target_price + cover_price, 4)
    if total_cost <= 0 or total_cost > 2.0:
        return None

    metrics = calculate_coverage_metrics(target_price, cover_probability, total_cost)
    if metrics["coverage"] < MIN_COVERAGE:
        return None
    tier, tier_label = classify_tier(metrics["coverage"])
    return HedgePortfolio(
        target_market_id=str(target_market["id"]),
        target_question=str(target_market["question"]),
        target_side=target_position,
        target_price=round(target_price, 4),
        cover_market_id=str(cover_market["id"]),
        cover_question=str(cover_market["question"]),
        cover_side=cover_position,
        cover_price=round(cover_price, 4),
        total_cost=total_cost,
        tier=tier,
        tier_label=tier_label,
        relationship=relationship,
        **metrics,
    )


def filter_portfolios_by_tier(
    portfolios: list[HedgePortfolio], max_tier: int = 2
) -> list[HedgePortfolio]:
    return [portfolio for portfolio in portfolios if portfolio.tier <= max_tier]


def filter_portfolios_by_coverage(
    portfolios: list[HedgePortfolio], min_coverage: float = MIN_COVERAGE
) -> list[HedgePortfolio]:
    return [portfolio for portfolio in portfolios if portfolio.coverage >= min_coverage]


def sort_portfolios(portfolios: list[HedgePortfolio]) -> list[HedgePortfolio]:
    return sorted(
        portfolios,
        key=lambda portfolio: (
            portfolio.tier,
            -portfolio.coverage,
            portfolio.total_cost,
        ),
    )
