from __future__ import annotations

import asyncio
import json
from typing import Any, Callable

from .config import PredictConfig, RuntimeEnv
from .coverage import (
    NECESSARY_PROBABILITY,
    HedgePortfolio,
    build_portfolio,
    filter_portfolios_by_coverage,
    filter_portfolios_by_tier,
    sort_portfolios,
)
from .hedge_prompt import IMPLICATION_SYSTEM_PROMPT, build_implication_prompt
from .llm_client import OpenRouterLLMClient
from .market_service import MarketService, MarketSummary, summary_to_dict


class HedgeService:
    def __init__(
        self,
        config: PredictConfig,
        *,
        market_service_factory: Callable[
            [PredictConfig], MarketService
        ] = MarketService,
        llm_client_factory: Callable[
            [PredictConfig], OpenRouterLLMClient
        ] = OpenRouterLLMClient,
    ) -> None:
        self._config = config
        self._market_service_factory = market_service_factory
        self._llm_client_factory = llm_client_factory

    async def scan(
        self,
        *,
        query: str | None = None,
        limit: int = 20,
        min_coverage: float = 0.85,
        tier: int = 2,
        model: str | None = None,
    ) -> list[HedgePortfolio]:
        market_service = self._market_service_factory(self._config)
        summaries = await (
            market_service.search(query, limit=limit)
            if query
            else market_service.get_trending(limit=limit)
        )
        portfolios = await self._scan_portfolios(summaries, model=model)
        return sort_portfolios(
            filter_portfolios_by_tier(
                filter_portfolios_by_coverage(portfolios, min_coverage), tier
            )
        )

    async def analyze(
        self, left_market_id: str, right_market_id: str, *, model: str | None = None
    ) -> list[HedgePortfolio]:
        market_service = self._market_service_factory(self._config)
        left = await market_service.get_trending(limit=50)
        pair = {summary.id: summary for summary in left}
        if left_market_id not in pair or right_market_id not in pair:
            left_detail = await market_service.get_detail(left_market_id)
            right_detail = await market_service.get_detail(right_market_id)
            left_summary = MarketSummary(
                id=str(left_detail.market.id),
                title=left_detail.market.title or "",
                question=left_detail.market.question or left_detail.market.title or "",
                category_slug=left_detail.market.categorySlug or "",
                fee_rate_bps=left_detail.market.feeRateBps,
                yes_mark_price=left_detail.yes_mark_price,
                no_mark_price=left_detail.no_mark_price,
                volume_24h_usd=left_detail.stats.volume24hUsd or 0.0,
                decimal_precision=left_detail.market.decimalPrecision or 2,
            )
            right_summary = MarketSummary(
                id=str(right_detail.market.id),
                title=right_detail.market.title or "",
                question=right_detail.market.question
                or right_detail.market.title
                or "",
                category_slug=right_detail.market.categorySlug or "",
                fee_rate_bps=right_detail.market.feeRateBps,
                yes_mark_price=right_detail.yes_mark_price,
                no_mark_price=right_detail.no_mark_price,
                volume_24h_usd=right_detail.stats.volume24hUsd or 0.0,
                decimal_precision=right_detail.market.decimalPrecision or 2,
            )
        else:
            left_summary = pair[left_market_id]
            right_summary = pair[right_market_id]
        portfolios = await self._pair_portfolios(
            left_summary, right_summary, model=model
        )
        return sort_portfolios(portfolios)

    async def _scan_portfolios(
        self, summaries: list[MarketSummary], *, model: str | None
    ) -> list[HedgePortfolio]:
        if len(summaries) < 2:
            return []
        semaphore = asyncio.Semaphore(3)
        anchor = summaries[0]

        async def analyze_candidate(summary: MarketSummary) -> list[HedgePortfolio]:
            async with semaphore:
                return await self._pair_portfolios(anchor, summary, model=model)

        results = await asyncio.gather(
            *(analyze_candidate(summary) for summary in summaries[1:]),
            return_exceptions=False,
        )
        portfolios: list[HedgePortfolio] = []
        for result in results:
            portfolios.extend(result)
        return portfolios

    async def _pair_portfolios(
        self, left: MarketSummary, right: MarketSummary, *, model: str | None
    ) -> list[HedgePortfolio]:
        if self._config.env == RuntimeEnv.TEST_FIXTURE:
            return _fixture_pair_portfolios(left, right)

        client = self._llm_client_factory(self._config)
        try:
            payload = await client.complete_json(
                build_implication_prompt(left.question, [summary_to_dict(right)]),
                system_prompt=IMPLICATION_SYSTEM_PROMPT,
                model=model,
            )
        finally:
            await client.close()

        if not payload:
            return []
        relationship = _relationship_from_payload(payload)
        if relationship is None:
            return []
        portfolio = build_portfolio(
            target_market=_summary_to_market_dict(left),
            cover_market=_summary_to_market_dict(right),
            target_position=relationship["target_position"],
            cover_position=relationship["cover_position"],
            cover_probability=NECESSARY_PROBABILITY,
            relationship=relationship["relationship"],
        )
        return [portfolio] if portfolio else []


def _summary_to_market_dict(summary: MarketSummary) -> dict[str, object]:
    return {
        "id": summary.id,
        "question": summary.question,
        "yes_price": summary.yes_mark_price,
        "no_price": summary.no_mark_price,
    }


def _fixture_pair_portfolios(
    left: MarketSummary, right: MarketSummary
) -> list[HedgePortfolio]:
    relationship = (
        f"necessary (fixture): {left.question} YES implies {right.question} YES"
    )
    portfolio = build_portfolio(
        target_market=_summary_to_market_dict(left),
        cover_market=_summary_to_market_dict(right),
        target_position="NO",
        cover_position="YES",
        cover_probability=NECESSARY_PROBABILITY,
        relationship=relationship,
    )
    return [portfolio] if portfolio else []


def _relationship_from_payload(payload: dict[str, Any]) -> dict[str, str] | None:
    implied_by = payload.get("implied_by") or []
    implies = payload.get("implies") or []
    if implied_by:
        explanation = implied_by[0].get("explanation", "necessary implication")
        return {
            "target_position": "YES",
            "cover_position": "NO",
            "relationship": f"necessary (contrapositive): {explanation}",
        }
    if implies:
        explanation = implies[0].get("explanation", "necessary implication")
        return {
            "target_position": "NO",
            "cover_position": "YES",
            "relationship": f"necessary (direct): {explanation}",
        }
    return None
