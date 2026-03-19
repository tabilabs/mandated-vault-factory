from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timezone

from lib.config import PredictConfig
from lib.position_storage import LocalPosition, PositionStorage

positions_service_module = importlib.import_module("lib.positions_service")
PositionsService = getattr(positions_service_module, "PositionsService")


def run_positions(
    *args: str, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    predict_root = Path(__file__).resolve().parents[1]
    command_env = os.environ.copy()
    if env:
        command_env.update(env)
    return subprocess.run(
        [sys.executable, str(predict_root / "scripts" / "positions.py"), *args],
        cwd=predict_root,
        env=command_env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_positions_merge_local_and_remote_records(tmp_path) -> None:
    config = PredictConfig.from_env(
        {
            "PREDICT_ENV": "test-fixture",
            "PREDICT_STORAGE_DIR": str(tmp_path),
        }
    )
    service = PositionsService(config)
    service.sync_fixture_positions()

    merged = __import__("asyncio").run(service.list_positions(include_all=True))
    tracked = next(item for item in merged if item.position_id == "pos-123-yes")
    external = next(item for item in merged if item.source == "external")

    assert tracked.market_id == "123"
    assert tracked.source == "tracked"
    assert tracked.remote_quantity_wei == "25000000000000000000"
    assert tracked.unrealized_pnl_usdt is not None
    assert external.market_id == "456"
    assert external.source == "external"


def test_positions_cli_lists_and_shows_fixture_positions(tmp_path) -> None:
    env = {
        "PREDICT_ENV": "test-fixture",
        "PREDICT_STORAGE_DIR": str(tmp_path),
    }

    list_result = run_positions("list", "--json", env=env)
    show_result = run_positions("show", "pos-123-yes", "--json", env=env)
    all_result = run_positions("list", "--all", "--json", env=env)

    assert list_result.returncode == 0
    assert show_result.returncode == 0
    assert all_result.returncode == 0

    listed = json.loads(list_result.stdout)
    shown = json.loads(show_result.stdout)
    all_payload = json.loads(all_result.stdout)

    assert listed[0]["positionId"] == "pos-123-yes"
    assert all(item["source"] != "external" for item in listed)
    assert any(item["source"] == "external" for item in all_payload)
    assert shown["positionId"] == "pos-123-yes"
    assert shown["marketId"] == "123"


def test_positions_cli_mandated_vault_blocks_list_and_show_without_traceback() -> None:
    env = {
        "PREDICT_ENV": "testnet",
        "PREDICT_STORAGE_DIR": "/tmp/predict",
        "PREDICT_WALLET_MODE": "mandated-vault",
        "ERC_MANDATED_VAULT_ADDRESS": "0x2222222222222222222222222222222222222222",
    }

    list_result = run_positions("list", "--json", env=env)
    show_result = run_positions("show", "pos-123-yes", "--json", env=env)

    assert list_result.returncode == 1
    assert show_result.returncode == 1

    list_combined = list_result.stdout + list_result.stderr
    show_combined = show_result.stdout + show_result.stderr
    assert "unsupported-in-mandated-vault-v1" in list_combined
    assert "unsupported-in-mandated-vault-v1" in show_combined
    assert "Traceback" not in list_combined
    assert "Traceback" not in show_combined


def test_positions_list_tolerates_overlay_funding_metadata_notes(tmp_path) -> None:
    config = PredictConfig.from_env(
        {
            "PREDICT_ENV": "test-fixture",
            "PREDICT_STORAGE_DIR": str(tmp_path),
        }
    )
    now = datetime.now(timezone.utc).isoformat()
    storage = PositionStorage(config.storage_dir)
    storage.seed(
        [
            LocalPosition(
                position_id="pos-overlay-123-yes",
                market_id="123",
                question="Fixture question",
                outcome_name="YES",
                token_id="1001",
                side="BUY",
                strategy="MARKET",
                entry_time=now,
                entry_price=0.6,
                quantity="25000000000000000000",
                notional_usdt=25.0,
                order_hash="0xoverlay",
                order_status="OPEN",
                fill_amount="25000000000000000000",
                fee_rate_bps=100,
                source="tracked",
                notes='{"fundingRoute":"vault-to-predict-account"}',
                status="OPEN",
            )
        ]
    )
    service = PositionsService(config)

    merged = __import__("asyncio").run(service.list_positions(include_all=True))

    tracked = next(item for item in merged if item.position_id == "pos-overlay-123-yes")
    assert tracked.source == "tracked"
    assert tracked.market_id == "123"
