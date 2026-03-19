from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def run_hedge(
    *args: str, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    predict_root = Path(__file__).resolve().parents[1]
    command_env = os.environ.copy()
    if env:
        command_env.update(env)
    return subprocess.run(
        [sys.executable, str(predict_root / "scripts" / "hedge.py"), *args],
        cwd=predict_root,
        env=command_env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_hedge_analyze_outputs_ranked_portfolios() -> None:
    env = {"PREDICT_ENV": "test-fixture", "PREDICT_STORAGE_DIR": "/tmp/predict"}
    result = run_hedge("analyze", "101", "202", "--json", env=env)

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload[0]["tier"] <= 2
    assert payload[0]["coverage"] >= 0.85
    assert "totalCost" in payload[0]
    assert "targetSide" in payload[0]
    assert "coverSide" in payload[0]
    assert "relationship" in payload[0]


def test_hedge_scan_handles_no_results_cleanly() -> None:
    env = {"PREDICT_ENV": "test-fixture", "PREDICT_STORAGE_DIR": "/tmp/predict"}
    result = run_hedge("scan", "--query", "nonesuchquery", "--json", env=env)

    assert result.returncode == 0
    assert json.loads(result.stdout) == []


def test_hedge_scan_fixture_limit_json() -> None:
    env = {"PREDICT_ENV": "test-fixture", "PREDICT_STORAGE_DIR": "/tmp/predict"}
    result = run_hedge("scan", "--limit", "5", "--json", env=env)

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert len(payload) >= 1
