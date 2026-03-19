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

    for raw_line in env_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


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
    print("  PREDICT_PRIVATE_KEY         EOA trading credential")
    print("  PREDICT_ACCOUNT_ADDRESS     Predict Account smart-wallet address")
    print(
        "  PREDICT_PRIVY_PRIVATE_KEY   Privy-exported signer for Predict Account mode"
    )
    print("  PREDICT_API_KEY             mainnet-only authenticated REST access")
    print("  OPENROUTER_API_KEY          hedge analysis model access")
    print()
    print("Notes:")
    print("  - Default local posture is testnet or fixture mode.")
    print("  - Mainnet requires PREDICT_API_KEY for authenticated predict.fun flows.")
    print(
        "  - Predict Account mode is supported through wallet subcommands and signed flows."
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
