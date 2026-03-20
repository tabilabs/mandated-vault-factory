from __future__ import annotations

import subprocess
import sys
import os
from pathlib import Path

from conftest import get_predict_root


def run_predictclaw(*args: str) -> subprocess.CompletedProcess[str]:
    predict_root = get_predict_root()
    command_env = os.environ.copy()
    command_env["PREDICTCLAW_DISABLE_LOCAL_ENV"] = "1"
    return subprocess.run(
        [sys.executable, str(predict_root / "scripts" / "predictclaw.py"), *args],
        cwd=predict_root,
        env=command_env,
        capture_output=True,
        text=True,
        check=False,
    )


def run_wallet(*args: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    predict_root = get_predict_root()
    command_env = os.environ.copy()
    command_env.update(env)
    return subprocess.run(
        [sys.executable, str(predict_root / "scripts" / "wallet.py"), *args],
        cwd=predict_root,
        env=command_env,
        capture_output=True,
        text=True,
        check=False,
    )


def run_predictclaw_with_env(
    *args: str, env: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    predict_root = get_predict_root()
    command_env = os.environ.copy()
    command_env["PREDICTCLAW_DISABLE_LOCAL_ENV"] = "1"
    command_env.update(env)
    return subprocess.run(
        [sys.executable, str(predict_root / "scripts" / "predictclaw.py"), *args],
        cwd=predict_root,
        env=command_env,
        capture_output=True,
        text=True,
        check=False,
    )


def write_trade_api_error_sitecustomize(tmp_path: Path) -> Path:
    patch_root = tmp_path / "trade-api-error-patch"
    patch_root.mkdir(parents=True, exist_ok=True)
    (patch_root / "sitecustomize.py").write_text(
        """
from __future__ import annotations

from lib.api import PredictApiError
import lib.trade_service as trade_service


async def _fail_buy(self, *args, **kwargs):
    raise PredictApiError(
        'predict.fun API request failed for POST /v1/orders with status 403: {"success":false,"code":403,"error":"forbidden","message":"This operation is not available in your jurisdiction"}',
        status_code=403,
        method='POST',
        path='/v1/orders',
    )


trade_service.TradeService.buy = _fail_buy
""".strip(),
        encoding="utf-8",
    )
    return patch_root


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
    assert "PREDICT_WALLET_MODE" in combined
    assert "Predict Account" in combined
    assert "testnet" in combined.lower()
    assert "mainnet" in combined.lower()
    for mode in ["read-only", "eoa", "predict-account", "mandated-vault"]:
        assert mode in combined
    for env_name in [
        "ERC_MANDATED_VAULT_ADDRESS",
        "ERC_MANDATED_FACTORY_ADDRESS",
        "ERC_MANDATED_VAULT_ASSET_ADDRESS",
        "ERC_MANDATED_VAULT_NAME",
        "ERC_MANDATED_VAULT_SYMBOL",
        "ERC_MANDATED_VAULT_AUTHORITY",
        "ERC_MANDATED_VAULT_SALT",
        "ERC_MANDATED_MCP_COMMAND",
        "ERC_MANDATED_CONTRACT_VERSION",
        "ERC_MANDATED_CHAIN_ID",
        "ERC_MANDATED_FUNDING_MAX_AMOUNT_PER_TX",
        "ERC_MANDATED_FUNDING_MAX_AMOUNT_PER_WINDOW",
        "ERC_MANDATED_FUNDING_WINDOW_SECONDS",
    ]:
        assert env_name in combined
    assert "manual-only" in combined
    assert "vault contract policy authorizes" in combined.lower()
    assert "unsupported-in-mandated-vault-v1" in combined
    assert "vault-to-predict-account" in combined
    assert "funding-required" in combined
    assert "api-testnet.predict.fun" in combined
    assert "wallet status requires signer configuration" in combined


def test_unknown_command_fails_cleanly() -> None:
    result = run_predictclaw("nonsense")

    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "Unknown command" in combined
    assert "Traceback" not in combined


def test_local_env_loader_supports_quoted_values(tmp_path: Path) -> None:
    predict_root = get_predict_root()
    env_path = tmp_path / ".env"
    env_path.write_text(
        'PREDICT_PRIVATE_KEY="0xquoted-private-key"\n'
        "OPENROUTER_API_KEY='sk-or-v1-quoted'\n",
        encoding="utf-8",
    )
    command_env = os.environ.copy()
    command_env["PREDICTCLAW_DISABLE_LOCAL_ENV"] = "1"
    command_env["TEST_ENV_PATH"] = str(env_path)
    command_env.pop("PREDICT_PRIVATE_KEY", None)
    command_env.pop("OPENROUTER_API_KEY", None)

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import os\n"
                "from pathlib import Path\n"
                "from scripts.predictclaw import load_local_env\n"
                'load_local_env(Path(os.environ["TEST_ENV_PATH"]))\n'
                'print(os.environ["PREDICT_PRIVATE_KEY"])\n'
                'print(os.environ["OPENROUTER_API_KEY"])\n'
            ),
        ],
        cwd=predict_root,
        env=command_env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert result.stdout.splitlines() == ["0xquoted-private-key", "sk-or-v1-quoted"]


def test_wallet_deposit_help_documents_funding_semantics() -> None:
    result = run_predictclaw("wallet", "deposit", "--help")

    assert result.returncode == 0
    combined = result.stdout + result.stderr
    assert "funding address" in combined.lower()
    assert "predict account" in combined.lower()
    assert "bnb" in combined.lower()
    assert "usdt" in combined.lower()


def test_wallet_status_and_deposit_fail_cleanly_when_mcp_is_unavailable() -> None:
    env = {
        "PREDICT_ENV": "testnet",
        "PREDICT_STORAGE_DIR": "/tmp/predict",
        "PREDICT_WALLET_MODE": "mandated-vault",
        "ERC_MANDATED_VAULT_ADDRESS": "0x2222222222222222222222222222222222222222",
        "ERC_MANDATED_MCP_COMMAND": "missing-mcp-binary-for-test",
    }

    status = run_wallet("status", "--json", env=env)
    deposit = run_wallet("deposit", "--json", env=env)

    assert status.returncode == 1
    assert deposit.returncode == 1
    status_combined = status.stdout + status.stderr
    deposit_combined = deposit.stdout + deposit.stderr
    assert "Traceback" not in status_combined
    assert "Traceback" not in deposit_combined
    assert "mandated-vault mcp" in status_combined.lower()
    assert "mandated-vault mcp" in deposit_combined.lower()


def test_mandated_vault_unsupported_flows_fail_closed_without_traceback() -> None:
    env = {
        "PREDICT_ENV": "testnet",
        "PREDICT_STORAGE_DIR": "/tmp/predict",
        "PREDICT_WALLET_MODE": "mandated-vault",
        "ERC_MANDATED_VAULT_ADDRESS": "0x2222222222222222222222222222222222222222",
    }

    wallet_approve = run_wallet("approve", "--json", env=env)
    wallet_withdraw = run_wallet(
        "withdraw",
        "usdt",
        "1",
        "0xb30741673D351135Cf96564dfD15f8e135f9C310",
        "--json",
        env=env,
    )
    buy = run_predictclaw_with_env("buy", "123", "YES", "25", env=env)
    positions = run_predictclaw_with_env("positions", "--json", env=env)
    position = run_predictclaw_with_env("position", "pos-123-yes", "--json", env=env)
    hedge_scan = run_predictclaw_with_env("hedge", "scan", "--json", env=env)

    for result in [
        wallet_approve,
        wallet_withdraw,
        buy,
        positions,
        position,
        hedge_scan,
    ]:
        assert result.returncode == 1
        combined = result.stdout + result.stderr
        assert "unsupported-in-mandated-vault-v1" in combined
        assert "Traceback" not in combined


def test_buy_api_error_fails_closed_without_traceback_in_json_mode(
    tmp_path: Path,
) -> None:
    patch_root = write_trade_api_error_sitecustomize(tmp_path)
    env = {
        "PREDICT_ENV": "testnet",
        "PREDICT_STORAGE_DIR": str(tmp_path),
        "PYTHONPATH": str(patch_root),
    }

    result = run_predictclaw_with_env("buy", "123", "YES", "25", "--json", env=env)

    assert result.returncode == 1
    assert result.stderr == ""
    assert "Traceback" not in result.stdout
    payload = result.stdout.strip()
    assert '"success": false' in payload
    assert '"error": "PredictApiError"' in payload
    assert '"statusCode": 403' in payload
    assert '"path": "/v1/orders"' in payload
    assert "jurisdiction" in payload.lower()
