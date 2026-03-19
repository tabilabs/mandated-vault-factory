#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

SKILL_DIR = Path(__file__).resolve().parent.parent
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

import lib

from lib.config import ConfigError, PredictConfig
from lib.wallet_manager import WalletManager

FundingService = getattr(lib, "FundingService")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="predictclaw wallet",
        description="Inspect predict.fun wallet readiness, funding addresses, approvals, and withdrawals.",
    )
    subparsers = parser.add_subparsers(dest="command")

    status = subparsers.add_parser(
        "status",
        help="Show wallet mode, deposit address, balances, and approval readiness.",
    )
    status.add_argument("--json", action="store_true")
    status.set_defaults(handler=_handle_status)

    approve = subparsers.add_parser(
        "approve",
        help="Set regular and yield-bearing approvals for predict.fun trading.",
    )
    approve.add_argument("--json", action="store_true")
    approve.set_defaults(handler=_handle_approve)

    deposit = subparsers.add_parser(
        "deposit",
        help="Show the active funding address, account mode, chain, and accepted assets.",
        description=(
            "Display the wallet funding address for the current mode. EOA mode deposits to the signer "
            "address directly. Predict Account mode deposits to the Predict Account funding address. "
            "BNB is required for gas and USDT is the supported trading asset."
        ),
    )
    deposit.add_argument("--json", action="store_true")
    deposit.set_defaults(handler=_handle_deposit)

    withdraw = subparsers.add_parser(
        "withdraw",
        help="Withdraw USDT or BNB to an external address.",
        description=(
            "Withdraw predict.fun assets to an external destination. USDT uses token transfer semantics and "
            "BNB uses native value transfer semantics. Commands validate destination format, positive amount, "
            "sufficient balance, and gas headroom before submission."
        ),
    )
    withdraw_subparsers = withdraw.add_subparsers(dest="asset")

    for asset in ("usdt", "bnb"):
        asset_parser = withdraw_subparsers.add_parser(
            asset,
            help=f"Withdraw {asset.upper()} to an external address.",
        )
        asset_parser.add_argument("amount")
        asset_parser.add_argument("to")
        asset_parser.add_argument("--json", action="store_true")
        asset_parser.add_argument("--all", action="store_true")
        asset_parser.set_defaults(handler=_handle_withdraw)

    return parser


def _load_manager() -> WalletManager:
    return WalletManager(PredictConfig.from_env())


def _load_funding_service() -> Any:
    return FundingService(PredictConfig.from_env())


def _handle_status(args: argparse.Namespace) -> int:
    try:
        status = _load_manager().get_status()
    except ConfigError as error:
        print(str(error))
        return 1

    if args.json:
        print(json.dumps(status.to_dict(), indent=2))
        return 0

    print(f"Mode: {status.mode}")
    print(f"Chain: {status.chain}")
    print(f"Signer Address: {status.signer_address}")
    print(f"Funding Address: {status.funding_address}")
    print(f"BNB Balance (wei): {status.bnb_balance_wei}")
    print(f"USDT Balance (wei): {status.usdt_balance_wei}")
    print(f"Auth Ready: {'yes' if status.auth_ready else 'no'}")
    print(
        f"Standard Approvals Ready: {'yes' if status.approvals.standard_ready else 'no'}"
    )
    print(
        f"Yield-bearing Approvals Ready: {'yes' if status.approvals.yield_ready else 'no'}"
    )
    return 0


def _handle_approve(args: argparse.Namespace) -> int:
    try:
        result = _load_manager().approve()
    except ConfigError as error:
        print(str(error))
        return 1

    payload = result.to_dict()
    if args.json:
        print(json.dumps(payload, indent=2, default=str))
        return 0

    standard = payload["standard"]
    yield_bearing = payload["yieldBearing"]
    print(f"Standard approvals: {standard}")
    print(f"Yield-bearing approvals: {yield_bearing}")
    return 0


def _handle_deposit(args: argparse.Namespace) -> int:
    try:
        details = _load_funding_service().get_deposit_details()
    except ConfigError as error:
        print(str(error))
        return 1

    payload = details.to_dict()
    if args.json:
        print(json.dumps(payload, indent=2))
        return 0

    accepted_assets = ", ".join(details.accepted_assets)
    print(f"Mode: {payload['mode']}")
    print(f"Funding Address: {payload['fundingAddress']}")
    print(f"Signer Address: {payload['signerAddress']}")
    print(f"Chain: {payload['chain']}")
    print(f"Accepted Assets: {accepted_assets}")
    print(f"BNB Balance (wei): {payload['bnbBalanceWei']}")
    print(f"USDT Balance (wei): {payload['usdtBalanceWei']}")
    return 0


def _handle_withdraw(args: argparse.Namespace) -> int:
    try:
        result = _load_funding_service().withdraw(
            args.asset,
            args.amount,
            args.to,
            withdraw_all=args.all,
        )
    except ConfigError as error:
        print(str(error))
        return 1

    payload = result.to_dict()
    if args.json:
        print(json.dumps(payload, indent=2, default=str))
        return 0

    print(f"Asset: {payload['asset']}")
    print(f"Amount (wei): {payload['amountWei']}")
    print(f"Destination: {payload['destination']}")
    print(f"Result: {payload['result']}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return 0
    return handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
