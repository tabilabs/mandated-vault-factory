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
from lib.mandated_mcp_bridge import MandatedVaultMcpError
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
    except (ConfigError, MandatedVaultMcpError) as error:
        print(str(error))
        return 1

    if args.json:
        print(json.dumps(status.to_dict(), indent=2))
        return 0

    payload = status.to_dict()
    if payload.get("mode") == "mandated-vault":
        selected_chain = payload.get("selectedChain")
        if not isinstance(selected_chain, dict):
            selected_chain = {}
        mcp = payload.get("mcp")
        if not isinstance(mcp, dict):
            mcp = {}
        print(f"Mode: {payload.get('mode')}")
        print(
            f"Selected Chain: {selected_chain.get('name')} ({selected_chain.get('chainId')})"
        )
        print(f"MCP Command: {mcp.get('command')}")
        print(f"MCP Runtime Ready: {'yes' if mcp.get('runtimeReady') else 'no'}")
        print(
            "State-changing Flows Enabled: "
            f"{'yes' if payload.get('stateChangingFlowsEnabled') else 'no'}"
        )
        print(
            f"Vault Address: {payload.get('vaultAddress')} ({payload.get('vaultAddressSource')})"
        )
        print(f"Vault Deployed: {'yes' if payload.get('vaultDeployed') else 'no'}")
        missing = mcp.get("missingRequiredTools", [])
        print(
            f"Missing Required MCP Tools: {', '.join(missing) if missing else 'none'}"
        )
        health = payload.get("vaultHealth")
        if isinstance(health, dict):
            print(f"Mandate Authority: {health.get('mandateAuthority')}")
            print(f"Authority Epoch: {health.get('authorityEpoch')}")
            print(f"Nonce Threshold: {health.get('nonceThreshold')}")
            print(f"Total Assets: {health.get('totalAssets')}")
        return 0

    approvals = payload.get("approvals")
    if not isinstance(approvals, dict):
        approvals = {}
    standard = approvals.get("standard")
    if not isinstance(standard, dict):
        standard = {}
    yield_bearing = approvals.get("yieldBearing")
    if not isinstance(yield_bearing, dict):
        yield_bearing = {}

    print(f"Mode: {payload.get('mode')}")
    print(f"Chain: {payload.get('chain')}")
    print(f"Signer Address: {payload.get('signerAddress')}")
    print(f"Funding Address: {payload.get('fundingAddress')}")
    print(f"BNB Balance (wei): {payload.get('bnbBalanceWei')}")
    print(f"USDT Balance (wei): {payload.get('usdtBalanceWei')}")
    print(f"Auth Ready: {'yes' if payload.get('authReady') else 'no'}")
    print(f"Standard Approvals Ready: {'yes' if standard.get('ready') else 'no'}")
    print(
        f"Yield-bearing Approvals Ready: {'yes' if yield_bearing.get('ready') else 'no'}"
    )
    if payload.get("fundingRoute") == "vault-to-predict-account":
        print(f"Funding Route: {payload.get('fundingRoute')}")
        print(f"Predict Account Address: {payload.get('predictAccountAddress')}")
        print(f"Trade Signer Address: {payload.get('tradeSignerAddress')}")
        print(
            f"Funding Vault Address: {payload.get('vaultAddress')} ({payload.get('vaultAddressSource', 'unknown')})"
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
    except (ConfigError, MandatedVaultMcpError) as error:
        print(str(error))
        return 1

    payload = details.to_dict()
    if args.json:
        print(json.dumps(payload, indent=2))
        return 0

    if payload.get("mode") == "mandated-vault":
        print(f"Mode: {payload['mode']}")
        print(
            f"Funding Vault Address: {payload['fundingAddress']} ({payload.get('vaultAddressSource', 'unknown')})"
        )
        print(f"Vault Exists: {'yes' if payload.get('vaultExists') else 'no'}")
        print("Accepted Assets: BNB, USDT")
        preparation = payload.get("createVaultPreparation")
        if isinstance(preparation, dict):
            tx_summary = preparation.get("txSummary", {})
            print("Create Vault Transaction: prepared only (not broadcast)")
            print(f"  from: {tx_summary.get('from')}")
            print(f"  to: {tx_summary.get('to')}")
            print(f"  value: {tx_summary.get('value')}")
            print(f"  gas: {tx_summary.get('gas')}")
            print(f"  data: {tx_summary.get('data')}")
        return 0

    if payload.get("fundingRoute") == "vault-to-predict-account":
        print(f"Mode: {payload['mode']}")
        print(f"Funding Route: {payload['fundingRoute']}")
        print(f"Predict Account Address: {payload['predictAccountAddress']}")
        print(f"Trade Signer Address: {payload['tradeSignerAddress']}")
        print(
            f"Funding Vault Address: {payload['vaultAddress']} ({payload.get('vaultAddressSource', 'unknown')})"
        )
        print(f"Vault Exists: {'yes' if payload.get('vaultExists') else 'no'}")
        print("Accepted Assets: BNB, USDT")
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
