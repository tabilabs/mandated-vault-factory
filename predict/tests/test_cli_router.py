from __future__ import annotations

import subprocess
import sys

from conftest import get_predict_root


def run_predictclaw(*args: str) -> subprocess.CompletedProcess[str]:
    predict_root = get_predict_root()
    return subprocess.run(
        [sys.executable, str(predict_root / "scripts" / "predictclaw.py"), *args],
        cwd=predict_root,
        capture_output=True,
        text=True,
        check=False,
    )


def test_top_level_help_exposes_planned_command_surface() -> None:
    result = run_predictclaw("--help")

    assert result.returncode == 0
    combined = result.stdout + result.stderr
    for command in [
        "markets",
        "market",
        "wallet",
        "buy",
        "positions",
        "position",
        "hedge",
    ]:
        assert command in combined
    assert "PREDICT_PRIVATE_KEY" in combined
    assert "Predict Account" in combined
    assert "testnet" in combined.lower()
    assert "mainnet" in combined.lower()


def test_unknown_command_fails_cleanly() -> None:
    result = run_predictclaw("nonsense")

    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "Unknown command" in combined
    assert "Traceback" not in combined


def test_wallet_deposit_help_documents_funding_semantics() -> None:
    result = run_predictclaw("wallet", "deposit", "--help")

    assert result.returncode == 0
    combined = result.stdout + result.stderr
    assert "funding address" in combined.lower()
    assert "predict account" in combined.lower()
    assert "bnb" in combined.lower()
    assert "usdt" in combined.lower()
