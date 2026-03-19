from __future__ import annotations

from dataclasses import dataclass

from predict_sdk.types import Book

from .config import ConfigError
from .models import MarketRecord, OrderBookRecord, OutcomeRecord


@dataclass
class ResolvedOutcome:
    label: str
    token_id: str


def orderbook_record_to_sdk_book(orderbook: OrderBookRecord) -> Book:
    market_id = int(orderbook.marketId) if orderbook.marketId is not None else 0
    asks = [(float(level[0]), float(level[1])) for level in (orderbook.asks or [])]
    bids = [(float(level[0]), float(level[1])) for level in (orderbook.bids or [])]
    return Book(
        market_id=market_id,
        update_timestamp_ms=orderbook.updateTimestampMs or 0,
        asks=asks,
        bids=bids,
    )


def resolve_outcome(market: MarketRecord, label: str) -> ResolvedOutcome:
    normalized = label.upper()
    for outcome in market.outcomes or []:
        if _matches_outcome(outcome, normalized):
            token_id = outcome.tokenId or outcome.onChainId
            if not token_id:
                raise ConfigError(
                    f"Outcome {label} is missing a token id in market {market.id}."
                )
            return ResolvedOutcome(label=normalized, token_id=token_id)
    raise ConfigError(f"Outcome {label} is not available for market {market.id}.")


def _matches_outcome(outcome: OutcomeRecord, normalized_label: str) -> bool:
    return (outcome.name or "").upper() == normalized_label
