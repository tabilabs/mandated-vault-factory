from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def run_predictclaw(
    *args: str, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    predict_root = Path(__file__).resolve().parents[1]
    command_env = os.environ.copy()
    if env:
        command_env.update(env)
    return subprocess.run(
        [sys.executable, str(predict_root / "scripts" / "predictclaw.py"), *args],
        cwd=predict_root,
        env=command_env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_trending_markets_cli_outputs_sorted_rows() -> None:
    result = run_predictclaw(
        "markets",
        "trending",
        "--json",
        env={"PREDICT_ENV": "test-fixture"},
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload[0]["id"] == "123"
    assert payload[0]["yesMarkPrice"] == 0.6
    assert payload[0]["noMarkPrice"] == 0.4
    assert payload[0]["volume24hUsd"] >= payload[1]["volume24hUsd"]


def test_market_detail_json_returns_enriched_payload() -> None:
    result = run_predictclaw(
        "market",
        "123",
        "--json",
        env={"PREDICT_ENV": "test-fixture"},
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["id"] == "123"
    assert payload["stats"]["liquidityUsd"] == 500000.0
    assert payload["orderbook"]["marketId"] == "123"
    assert payload["yesMarkPrice"] == 0.6
    assert payload["noMarkPrice"] == 0.4


def test_search_no_matches_returns_user_safe_message() -> None:
    result = run_predictclaw(
        "markets",
        "search",
        "nonesuch-query",
        env={"PREDICT_ENV": "test-fixture"},
    )

    assert result.returncode == 0
    assert "No markets found" in result.stdout
    assert "Traceback" not in result.stdout + result.stderr
