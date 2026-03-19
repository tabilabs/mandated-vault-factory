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

from lib.config import ConfigError, PredictConfig
from lib.trade_service import TradeService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="predictclaw trade",
        description="Trade predict.fun markets with native order flow.",
    )
    subparsers = parser.add_subparsers(dest="command")

    buy = subparsers.add_parser(
        "buy",
        help="Buy YES or NO exposure on a predict.fun market.",
    )
    buy.add_argument("market_id")
    buy.add_argument("outcome", choices=["YES", "NO"])
    buy.add_argument("amount")
    buy.add_argument("--limit-price", type=float)
    buy.add_argument("--slippage-bps", type=int)
    buy.add_argument("--expiration-minutes", type=int)
    buy.add_argument("--json", action="store_true")
    buy.set_defaults(handler=_handle_buy)
    return parser


async def _handle_buy(args: argparse.Namespace) -> int:
    try:
        result = await TradeService(PredictConfig.from_env()).buy(
            args.market_id,
            args.outcome,
            args.amount,
            limit_price=args.limit_price,
            slippage_bps=args.slippage_bps,
            expiration_minutes=args.expiration_minutes,
        )
    except ConfigError as error:
        print(str(error))
        return 1

    payload = result.to_dict()
    if args.json:
        print(json.dumps(payload, indent=2))
        return 0

    print(f"Order Hash: {payload['order_hash']}")
    print(f"Status: {payload['status']}")
    print(f"Outcome: {payload['outcome']}")
    print(f"Token ID: {payload['token_id']}")
    print(f"Maker Amount: {payload['maker_amount']}")
    print(f"Taker Amount: {payload['taker_amount']}")
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
