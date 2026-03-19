#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

SKILL_DIR = Path(__file__).resolve().parent.parent
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

from lib.config import ConfigError, PredictConfig

hedge_service_module = importlib.import_module("lib.hedge_service")
HedgeService = getattr(hedge_service_module, "HedgeService")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="predictclaw hedge",
        description="Analyze predict.fun hedge opportunities with bounded model usage.",
    )
    subparsers = parser.add_subparsers(dest="command")

    scan = subparsers.add_parser(
        "scan", help="Scan candidate markets for hedge relationships."
    )
    scan.add_argument("--query")
    scan.add_argument("--limit", type=int, default=20)
    scan.add_argument("--min-coverage", type=float, default=0.85)
    scan.add_argument("--tier", type=int, default=2)
    scan.add_argument("--model")
    scan.add_argument("--json", action="store_true")
    scan.set_defaults(handler=_handle_scan)

    analyze = subparsers.add_parser(
        "analyze", help="Analyze two market ids for hedge compatibility."
    )
    analyze.add_argument("market_id_1")
    analyze.add_argument("market_id_2")
    analyze.add_argument("--min-coverage", type=float, default=0.85)
    analyze.add_argument("--model")
    analyze.add_argument("--json", action="store_true")
    analyze.set_defaults(handler=_handle_analyze)
    return parser


def _load_service() -> Any:
    return HedgeService(PredictConfig.from_env())


async def _handle_scan(args: argparse.Namespace) -> int:
    try:
        portfolios = await _load_service().scan(
            query=args.query,
            limit=args.limit,
            min_coverage=args.min_coverage,
            tier=args.tier,
            model=args.model,
        )
    except ConfigError as error:
        print(str(error))
        return 1
    payload = [portfolio.to_dict() for portfolio in portfolios]
    if args.json:
        print(json.dumps(payload, indent=2))
        return 0
    if not payload:
        print("No hedge portfolios found.")
        return 0
    for item in payload:
        print(
            f"Tier {item['tier']} | coverage {item['coverage']:.4f} | total cost {item['totalCost']:.2f}"
        )
        print(
            f"  target: {item['targetSide']} @ {item['targetPrice']:.2f} | {item['targetQuestion']}"
        )
        print(
            f"  cover:  {item['coverSide']} @ {item['coverPrice']:.2f} | {item['coverQuestion']}"
        )
        print(f"  relationship: {item['relationship']}")
    return 0


async def _handle_analyze(args: argparse.Namespace) -> int:
    try:
        portfolios = await _load_service().analyze(
            args.market_id_1, args.market_id_2, model=args.model
        )
    except ConfigError as error:
        print(str(error))
        return 1
    payload = [
        portfolio.to_dict()
        for portfolio in portfolios
        if portfolio.coverage >= args.min_coverage
    ]
    if args.json:
        print(json.dumps(payload, indent=2))
        return 0
    if not payload:
        print("No hedge portfolios found.")
        return 0
    for item in payload:
        print(
            f"Tier {item['tier']} | coverage {item['coverage']:.4f} | total cost {item['totalCost']:.2f}"
        )
        print(
            f"  target: {item['targetSide']} @ {item['targetPrice']:.2f} | {item['targetQuestion']}"
        )
        print(
            f"  cover:  {item['coverSide']} @ {item['coverPrice']:.2f} | {item['coverQuestion']}"
        )
        print(f"  relationship: {item['relationship']}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    if argv is None:
        argv = sys.argv[1:]
    args = parser.parse_args(argv)
    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return 0
    return asyncio.run(handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
