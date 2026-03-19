from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def run_predictclaw(
    *args: str, env: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    predict_root = Path(__file__).resolve().parents[2]
    command_env = os.environ.copy()
    command_env.update(env)
    return subprocess.run(
        [sys.executable, str(predict_root / "scripts" / "predictclaw.py"), *args],
        cwd=predict_root,
        env=command_env,
        capture_output=True,
        text=True,
        check=False,
    )


def fixture_env(tmp_path: Path) -> dict[str, str]:
    return {
        "PREDICT_ENV": "test-fixture",
        "PREDICT_STORAGE_DIR": str(tmp_path),
        "PREDICT_PRIVATE_KEY": "0x59c6995e998f97a5a0044976f4d060f5d89c8b8c7f11b9aa0dbf3f0f7c7c1e01",
    }


def test_markets_family_runs_end_to_end(tmp_path) -> None:
    result = run_predictclaw("markets", "trending", "--json", env=fixture_env(tmp_path))
    payload = json.loads(result.stdout)
    assert result.returncode == 0
    assert payload[0]["id"] == "123"


def test_wallet_status_deposit_withdraw_flow_runs_end_to_end(tmp_path) -> None:
    env = fixture_env(tmp_path)
    checksum = "0xb30741673D351135Cf96564dfD15f8e135f9C310"

    status = run_predictclaw("wallet", "status", "--json", env=env)
    deposit = run_predictclaw("wallet", "deposit", "--json", env=env)
    withdraw = run_predictclaw(
        "wallet", "withdraw", "usdt", "1", checksum, "--json", env=env
    )

    assert status.returncode == 0
    assert deposit.returncode == 0
    assert withdraw.returncode == 0
    assert json.loads(status.stdout)["mode"] == "eoa"
    assert json.loads(deposit.stdout)["acceptedAssets"] == ["BNB", "USDT"]
    assert json.loads(withdraw.stdout)["asset"] == "usdt"


def test_buy_positions_and_hedge_commands_run_end_to_end(tmp_path) -> None:
    env = fixture_env(tmp_path)

    buy = run_predictclaw("buy", "123", "YES", "25", "--json", env=env)
    positions = run_predictclaw("positions", "--json", env=env)
    hedge = run_predictclaw("hedge", "scan", "--limit", "5", "--json", env=env)

    assert buy.returncode == 0
    assert positions.returncode == 0
    assert hedge.returncode == 0
    assert json.loads(buy.stdout)["status"] == "FILLED"
    assert len(json.loads(positions.stdout)) >= 1
    assert len(json.loads(hedge.stdout)) >= 1
