from __future__ import annotations

from collections.abc import Sequence
from typing import Any


def normalize_question(value: str) -> str:
    return " ".join(value.lower().strip().split())


def match_market_reference(
    *, market_id: str, market_question: str, markets: Sequence[dict[str, Any]]
) -> dict[str, Any] | None:
    if market_id:
        for market in markets:
            if str(market.get("id")) == str(market_id):
                return market

    normalized_question = normalize_question(market_question)
    for market in markets:
        if normalize_question(str(market.get("question", ""))) == normalized_question:
            return market

    for market in markets:
        candidate = normalize_question(str(market.get("question", "")))
        if normalized_question and (
            normalized_question in candidate or candidate in normalized_question
        ):
            return market
    return None
