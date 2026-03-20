#!/usr/bin/env python3
"""PredictClaw CLI - predict.fun skill for OpenClaw.

Usage:
    predictclaw markets trending
    predictclaw markets search "election"
    predictclaw market <id>
    predictclaw wallet status
    predictclaw wallet approve
    predictclaw wallet deposit
    predictclaw wallet withdraw usdt <amount> <to>
    predictclaw wallet withdraw bnb <amount> <to>
    predictclaw buy <market_id> YES 25
    predictclaw positions
    predictclaw position <id>
    predictclaw hedge scan
    predictclaw hedge analyze <id1> <id2>
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from dotenv import dotenv_values

SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPT_DIR = Path(__file__).resolve().parent

HELP_TEXT = """PredictClaw CLI - predict.fun skill for OpenClaw.

Usage:
    predictclaw markets trending
    predictclaw markets search \"election\"
    predictclaw market <id>
    predictclaw wallet status
    predictclaw wallet approve
    predictclaw wallet deposit
    predictclaw wallet withdraw usdt <amount> <to>
    predictclaw wallet withdraw bnb <amount> <to>
    predictclaw buy <market_id> YES 25
    predictclaw positions
    predictclaw position <id>
    predictclaw hedge scan
    predictclaw hedge analyze <id1> <id2>
"""


def load_local_env(env_path: Path) -> None:
    if not env_path.exists():
        return

    for key, value in dotenv_values(env_path).items():
        if value is None:
            continue
        os.environ.setdefault(key, value)


if os.getenv("PREDICTCLAW_DISABLE_LOCAL_ENV") != "1":
    load_local_env(SKILL_DIR / ".env")


def run_script(script_name: str, args: list[str]) -> int:
    script_path = SCRIPT_DIR / f"{script_name}.py"
    if not script_path.exists():
        print(f"Error: Script not found: {script_path}")
        return 1

    result = subprocess.run(
        [sys.executable, str(script_path), *args],
        check=False,
        cwd=SKILL_DIR,
    )
    return result.returncode


def print_help() -> None:
    print(HELP_TEXT.strip())
    print()
    print("Commands:")
    print("  markets trending            Show trending predict.fun markets")
    print("  markets search <query>      Search predict.fun markets")
    print("  market <id>                 Show a single market detail view")
    print("  wallet status               Show wallet mode, balances, and readiness")
    print("  wallet approve              Set predict.fun approvals")
    print("  wallet deposit              Show funding address and asset guidance")
    print("  wallet withdraw ...         Withdraw USDT or BNB to an external address")
    print("  buy <market_id> YES|NO <amount>")
    print(
        "                              Buy a YES/NO position with predict.fun order flow"
    )
    print("  positions                   Show tracked and remote positions")
    print("  position <id>               Show a single position")
    print("  hedge scan                  Scan candidate markets for hedges")
    print("  hedge analyze <id1> <id2>   Analyze a pair for hedge coverage")
    print()
    print("Environment:")
    print("  PREDICT_ENV                 testnet, mainnet, or fixture-safe local mode")
    print(
        "  PREDICT_WALLET_MODE         explicit mode override: read-only, eoa, predict-account, or mandated-vault"
    )
    print("  PREDICT_PRIVATE_KEY         EOA trading credential")
    print("  PREDICT_ACCOUNT_ADDRESS     Predict Account smart-wallet address")
    print(
        "  PREDICT_PRIVY_PRIVATE_KEY   Privy-exported signer for Predict Account mode"
    )
    print("  PREDICT_API_KEY             mainnet-only authenticated REST access")
    print("  ERC_MANDATED_VAULT_ADDRESS  Explicit deployed mandated vault address")
    print(
        "  ERC_MANDATED_FACTORY_ADDRESS Full derivation input for predicted vault lookup"
    )
    print(
        "  ERC_MANDATED_VAULT_ASSET_ADDRESS ERC-4626 asset for predicted vault lookup"
    )
    print("  ERC_MANDATED_VAULT_NAME     Vault name for predicted vault lookup")
    print("  ERC_MANDATED_VAULT_SYMBOL   Vault symbol for predicted vault lookup")
    print("  ERC_MANDATED_VAULT_AUTHORITY Authority / create-vault preparer address")
    print("  ERC_MANDATED_VAULT_SALT     Deterministic salt for predicted vault lookup")
    print(
        "  ERC_MANDATED_MCP_COMMAND    MCP launcher for vault overlay / mandated-vault mode"
    )
    print("  ERC_MANDATED_CONTRACT_VERSION Contract version passed to the MCP")
    print("  ERC_MANDATED_CHAIN_ID       Optional explicit chain selection for the MCP")
    print(
        "  ERC_MANDATED_FUNDING_MAX_AMOUNT_PER_TX Optional Vault->Predict per-tx cap in raw token units"
    )
    print(
        "  ERC_MANDATED_FUNDING_MAX_AMOUNT_PER_WINDOW Optional Vault->Predict window cap in raw token units"
    )
    print(
        "  ERC_MANDATED_FUNDING_WINDOW_SECONDS Optional Vault->Predict funding window duration"
    )
    print("  OPENROUTER_API_KEY          hedge analysis model access")
    print()
    print("Notes:")
    print("  - Default local posture is testnet or fixture mode.")
    print(
        "  - Mainnet market reads and trading require PREDICT_API_KEY for authenticated predict.fun flows."
    )
    print(
        "  - Testnet market reads use https://api-testnet.predict.fun and do not require PREDICT_API_KEY."
    )
    print(
        "  - Predict Account mode is supported through wallet subcommands and signed flows."
    )
    print(
        "  - read-only blocks signer-backed wallet/trading flows; eoa and predict-account preserve the existing live signer paths."
    )
    print(
        "  - wallet status requires signer configuration; start read-only verification with markets trending instead."
    )
    print(
        "  - Pure mandated-vault remains advanced explicit opt-in, but `predict-account + ERC_MANDATED_*` is the preferred advanced funding route."
    )
    print(
        "  - ERC_MANDATED_VAULT_ADDRESS selects an explicit deployed vault; otherwise the full derivation tuple lets the MCP predict the vault address."
    )
    print(
        "  - Overlay wallet status/deposit expose `vault-to-predict-account` routing: Predict Account stays the trading identity while Vault funds it, and undeployed vault setup remains manual-only."
    )
    print(
        "  - Trust boundary: the MCP orchestrates transport/preparation; the vault contract policy authorizes what execution is allowed."
    )
    print(
        "  - Pure mandated-vault v1 does not provide predict.fun trading parity; unsupported-in-mandated-vault-v1 still applies to pure mandated-vault buy/positions/hedge flows."
    )
    print(
        "  - Overlay buy can proceed when funded, and otherwise returns deterministic funding-required guidance that points to wallet deposit --json."
    )


def main() -> int:
    if len(sys.argv) < 2:
        print_help()
        return 0

    command = sys.argv[1]
    args = sys.argv[2:]

    if command in {"--help", "-h", "help"}:
        print_help()
        return 0

    if command == "markets":
        if args[:1] == ["details"]:
            print("Use 'predictclaw market <market_id>' for market details")
            return 1
        return run_script("markets", args)

    if command == "market":
        if not args:
            print("Usage: predictclaw market <market_id>")
            return 1
        return run_script("markets", ["details", *args])

    if command == "wallet":
        return run_script("wallet", args)

    if command == "buy":
        return run_script("trade", ["buy", *args])

    if command == "positions":
        if args[:1] in (["list"], ["show"]):
            print("Use 'predictclaw positions' or 'predictclaw position <position_id>'")
            return 1
        return run_script("positions", args)

    if command == "position":
        if not args:
            print("Usage: predictclaw position <position_id>")
            return 1
        return run_script("positions", ["show", *args])

    if command == "hedge":
        return run_script("hedge", args)

    print(f"Unknown command: {command}")
    print("Run 'predictclaw --help' for usage")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
