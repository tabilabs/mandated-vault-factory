from __future__ import annotations

from lib.coverage import (
    MIN_COVERAGE,
    NECESSARY_PROBABILITY,
    build_portfolio,
    classify_tier,
    filter_portfolios_by_coverage,
    sort_portfolios,
)


def test_build_portfolio_classifies_tier_correctly() -> None:
    portfolio = build_portfolio(
        target_market={
            "id": "101",
            "question": "Target",
            "yes_price": 0.4,
            "no_price": 0.6,
        },
        cover_market={
            "id": "202",
            "question": "Cover",
            "yes_price": 0.33,
            "no_price": 0.67,
        },
        target_position="NO",
        cover_position="YES",
        cover_probability=NECESSARY_PROBABILITY,
        relationship="necessary (direct)",
    )

    assert portfolio is not None
    assert portfolio.coverage >= 0.95
    assert portfolio.tier == 1
    assert classify_tier(0.92) == (2, "GOOD")
    assert MIN_COVERAGE == 0.85


def test_sort_and_filter_portfolios() -> None:
    high = build_portfolio(
        target_market={"id": "1", "question": "A", "yes_price": 0.4, "no_price": 0.6},
        cover_market={"id": "2", "question": "B", "yes_price": 0.2, "no_price": 0.8},
        target_position="NO",
        cover_position="YES",
        cover_probability=0.98,
        relationship="r1",
    )
    mid = build_portfolio(
        target_market={"id": "3", "question": "C", "yes_price": 0.85, "no_price": 0.15},
        cover_market={"id": "4", "question": "D", "yes_price": 0.1, "no_price": 0.9},
        target_position="YES",
        cover_position="YES",
        cover_probability=0.9,
        relationship="r2",
    )

    portfolios = [portfolio for portfolio in [mid, high] if portfolio is not None]
    assert [
        portfolio.target_market_id for portfolio in sort_portfolios(portfolios)
    ] == ["1", "3"]
    assert len(filter_portfolios_by_coverage(portfolios, 0.9)) == 2
