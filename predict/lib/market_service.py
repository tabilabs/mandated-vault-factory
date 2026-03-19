from __future__ import annotations

from dataclasses import dataclass

from .api import PredictApiClient
from .config import PredictConfig, RuntimeEnv
from .fixture_api import FixturePredictApiClient
from .models import LastSaleRecord, MarketRecord, MarketStatsRecord, OrderBookRecord


@dataclass
class MarketSummary:
    id: str
    title: str
    question: str
    category_slug: str
    fee_rate_bps: int | None
    yes_mark_price: float
    no_mark_price: float
    volume_24h_usd: float
    decimal_precision: int


@dataclass
class MarketDetail:
    market: MarketRecord
    stats: MarketStatsRecord
    last_sale: LastSaleRecord
    orderbook: OrderBookRecord
    yes_mark_price: float
    no_mark_price: float


class MarketService:
    def __init__(self, config: PredictConfig) -> None:
        self._config = config

    async def get_trending(self, limit: int = 10) -> list[MarketSummary]:
        client = self._make_client()
        try:
            markets = await client.get_markets(
                status="OPEN", sort="VOLUME_24H_DESC", first=limit
            )
            return await self._enrich_markets(client, markets[:limit])
        finally:
            await client.close()

    async def search(self, query: str, limit: int = 10) -> list[MarketSummary]:
        client = self._make_client()
        try:
            matches: list[MarketRecord] = []
            normalized = query.lower().strip()
            for page in range(5):
                page_markets = await client.get_markets(
                    status="OPEN",
                    sort="VOLUME_24H_DESC",
                    first=100,
                    skip=page * 100,
                )
                if not page_markets:
                    break
                matches.extend(
                    market
                    for market in page_markets
                    if normalized in (market.title or "").lower()
                    or normalized in (market.question or "").lower()
                    or normalized in (market.categorySlug or "").lower()
                )
            enriched = await self._enrich_markets(client, matches)
            return sorted(enriched, key=lambda item: item.volume_24h_usd, reverse=True)[
                :limit
            ]
        finally:
            await client.close()

    async def get_detail(self, market_id: str | int) -> MarketDetail:
        client = self._make_client()
        try:
            market = await client.get_market(market_id)
            stats = await client.get_market_stats(market_id)
            last_sale = await client.get_market_last_sale(market_id)
            orderbook = await client.get_orderbook(market_id)
            yes_mark, no_mark = derive_mark_prices(
                orderbook=orderbook,
                last_sale=last_sale,
                decimal_precision=market.decimalPrecision or 2,
            )
            return MarketDetail(
                market=market,
                stats=stats,
                last_sale=last_sale,
                orderbook=orderbook,
                yes_mark_price=yes_mark,
                no_mark_price=no_mark,
            )
        finally:
            await client.close()

    def _make_client(self) -> FixturePredictApiClient | PredictApiClient:
        if self._config.env == RuntimeEnv.TEST_FIXTURE:
            return FixturePredictApiClient()
        return PredictApiClient(self._config)

    async def _enrich_markets(
        self,
        client: FixturePredictApiClient | PredictApiClient,
        markets: list[MarketRecord],
    ) -> list[MarketSummary]:
        summaries: list[MarketSummary] = []
        for market in markets:
            stats = await client.get_market_stats(market.id)
            last_sale = await client.get_market_last_sale(market.id)
            orderbook = await client.get_orderbook(market.id)
            yes_mark, no_mark = derive_mark_prices(
                orderbook=orderbook,
                last_sale=last_sale,
                decimal_precision=market.decimalPrecision or 2,
            )
            summaries.append(
                MarketSummary(
                    id=str(market.id),
                    title=market.title or "",
                    question=market.question or market.title or "",
                    category_slug=market.categorySlug or "",
                    fee_rate_bps=market.feeRateBps,
                    yes_mark_price=yes_mark,
                    no_mark_price=no_mark,
                    volume_24h_usd=stats.volume24hUsd or market.volume24hUsd or 0.0,
                    decimal_precision=market.decimalPrecision or 2,
                )
            )
        return summaries


def derive_mark_prices(
    *,
    orderbook: OrderBookRecord,
    last_sale: LastSaleRecord,
    decimal_precision: int,
) -> tuple[float, float]:
    best_ask = orderbook.asks[0][0] if orderbook.asks else None
    best_bid = orderbook.bids[0][0] if orderbook.bids else None

    if best_ask is not None and best_bid is not None:
        yes_mark = round((best_ask + best_bid) / 2, decimal_precision)
    elif last_sale.price is not None:
        yes_mark = round(last_sale.price, decimal_precision)
    elif best_ask is not None:
        yes_mark = round(best_ask, decimal_precision)
    elif best_bid is not None:
        yes_mark = round(best_bid, decimal_precision)
    else:
        yes_mark = round(0.5, decimal_precision)

    no_mark = round(1 - yes_mark, decimal_precision)
    return yes_mark, no_mark


def summary_to_dict(summary: MarketSummary) -> dict[str, object]:
    return {
        "id": summary.id,
        "title": summary.title,
        "question": summary.question,
        "categorySlug": summary.category_slug,
        "feeRateBps": summary.fee_rate_bps,
        "yesMarkPrice": summary.yes_mark_price,
        "noMarkPrice": summary.no_mark_price,
        "volume24hUsd": summary.volume_24h_usd,
        "decimalPrecision": summary.decimal_precision,
    }


def detail_to_dict(detail: MarketDetail) -> dict[str, object]:
    payload = detail.market.model_dump(mode="json")
    payload.update(
        {
            "yesMarkPrice": detail.yes_mark_price,
            "noMarkPrice": detail.no_mark_price,
            "stats": detail.stats.model_dump(mode="json"),
            "lastSale": detail.last_sale.model_dump(mode="json"),
            "orderbook": detail.orderbook.model_dump(mode="json"),
        }
    )
    return payload


def format_market_table(summaries: list[MarketSummary], *, full: bool = False) -> str:
    if not summaries:
        return "No markets found."

    rows = [f"{'ID':<6} {'Market':<42} {'YES':>6} {'NO':>6} {'Vol24h':>12}"]
    for summary in summaries:
        label = summary.question if full else _truncate(summary.question, 42)
        rows.append(
            f"{summary.id:<6} {label:<42} {summary.yes_mark_price:>6.{summary.decimal_precision}f} {summary.no_mark_price:>6.{summary.decimal_precision}f} {summary.volume_24h_usd:>12.0f}"
        )
    return "\n".join(rows)


def format_market_detail(detail: MarketDetail) -> str:
    market = detail.market
    return "\n".join(
        [
            f"ID: {market.id}",
            f"Title: {market.title}",
            f"Question: {market.question}",
            f"Category: {market.categorySlug}",
            f"Fee Bps: {market.feeRateBps}",
            f"YES Mark: {detail.yes_mark_price}",
            f"NO Mark: {detail.no_mark_price}",
            f"24h Volume: {detail.stats.volume24hUsd}",
            f"Liquidity: {detail.stats.liquidityUsd}",
            f"Last Sale: {detail.last_sale.price}",
        ]
    )


def _truncate(value: str, width: int) -> str:
    if len(value) <= width:
        return value
    return value[: width - 3] + "..."
