#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

from lib.config import PredictConfig
from lib.market_service import (
    MarketService,
    detail_to_dict,
    format_market_detail,
    format_market_table,
    summary_to_dict,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="predictclaw markets",
        description="Browse predict.fun markets with PolyClaw-style commands.",
    )
    subparsers = parser.add_subparsers(dest="command")

    trending = subparsers.add_parser(
        "trending",
        help="Show trending open markets by 24h volume.",
    )
    trending.add_argument("--limit", type=int, default=10)
    trending.add_argument("--json", action="store_true")
    trending.add_argument("--full", action="store_true")
    trending.set_defaults(handler=_handle_trending)

    search = subparsers.add_parser(
        "search",
        help="Search predict.fun markets by keyword.",
    )
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=10)
    search.add_argument("--json", action="store_true")
    search.add_argument("--full", action="store_true")
    search.set_defaults(handler=_handle_search)

    details = subparsers.add_parser(
        "details",
        help="Show market detail, stats, and orderbook metadata.",
    )
    details.add_argument("market_id")
    details.add_argument("--json", action="store_true")
    details.set_defaults(handler=_handle_details)
    return parser


def _load_config() -> PredictConfig:
    return PredictConfig.from_env()


async def _handle_trending(args: argparse.Namespace) -> int:
    service = MarketService(_load_config())
    summaries = await service.get_trending(limit=args.limit)
    if args.json:
        print(json.dumps([summary_to_dict(item) for item in summaries], indent=2))
        return 0
    print(format_market_table(summaries, full=args.full))
    return 0


async def _handle_search(args: argparse.Namespace) -> int:
    service = MarketService(_load_config())
    summaries = await service.search(args.query, limit=args.limit)
    if args.json:
        print(json.dumps([summary_to_dict(item) for item in summaries], indent=2))
        return 0
    if not summaries:
        print(f"No markets found for query: {args.query}")
        return 0
    print(format_market_table(summaries, full=args.full))
    return 0


async def _handle_details(args: argparse.Namespace) -> int:
    service = MarketService(_load_config())
    detail = await service.get_detail(args.market_id)
    if args.json:
        print(json.dumps(detail_to_dict(detail), indent=2))
        return 0
    print(format_market_detail(detail))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return 0
    return asyncio.run(handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
