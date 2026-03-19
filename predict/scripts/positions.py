#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib
import asyncio
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

SKILL_DIR = Path(__file__).resolve().parent.parent
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

from lib.config import ConfigError, PredictConfig

positions_service_module = importlib.import_module("lib.positions_service")
PositionsService = getattr(positions_service_module, "PositionsService")
format_positions_table = getattr(positions_service_module, "format_positions_table")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="predictclaw positions",
        description="Inspect tracked and remote predict.fun positions.",
    )
    subparsers = parser.add_subparsers(dest="command")

    listing = subparsers.add_parser(
        "list",
        help="List tracked positions with optional remote reconciliation.",
    )
    listing.add_argument("--all", action="store_true")
    listing.add_argument("--json", action="store_true")
    listing.set_defaults(handler=_handle_list)

    show = subparsers.add_parser(
        "show",
        help="Show a single position record by id.",
    )
    show.add_argument("position_id")
    show.add_argument("--json", action="store_true")
    show.set_defaults(handler=_handle_show)

    return parser


def _load_service() -> Any:
    service = PositionsService(PredictConfig.from_env())
    service.sync_fixture_positions()
    return service


async def _handle_list(args: argparse.Namespace) -> int:
    service = _load_service()
    positions = await service.list_positions(include_all=args.all)
    if args.json:
        print(json.dumps([item.to_dict() for item in positions], indent=2))
        return 0
    print(format_positions_table(positions))
    return 0


async def _handle_show(args: argparse.Namespace) -> int:
    service = _load_service()
    try:
        position = await service.get_position(args.position_id)
    except ConfigError as error:
        print(str(error))
        return 1

    if args.json:
        print(json.dumps(position.to_dict(), indent=2))
        return 0

    print(f"Position ID: {position.position_id}")
    print(f"Market ID: {position.market_id}")
    print(f"Question: {position.question}")
    print(f"Outcome: {position.outcome}")
    print(f"Source: {position.source}")
    print(f"Status: {position.status}")
    print(f"Quantity (wei): {position.quantity_wei}")
    print(f"Current Mark: {position.current_mark_price}")
    if position.entry_price is not None:
        print(f"Entry Price: {position.entry_price}")
    if position.unrealized_pnl_usdt is not None:
        print(f"Unrealized PnL: {position.unrealized_pnl_usdt:+.2f}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    if argv is None:
        argv = sys.argv[1:]
    if len(argv) == 0 or argv[0].startswith("-"):
        argv = ["list", *argv]
    if len(argv) == 0:
        argv = ["list"]
    args = parser.parse_args(argv)
    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return 0
    return asyncio.run(handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
