from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

PREDICT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = PREDICT_ROOT / "scripts" / "poc_predict_account_crediting.py"
ARTIFACT_PATH = (
    PREDICT_ROOT
    / "artifacts"
    / "reports"
    / "autonomous-preflight"
    / "crediting-poc.json"
)
PREDICT_ACCOUNT_ADDRESS = "0x1234567890123456789012345678901234567890"
VAULT_ADDRESS = "0x2222222222222222222222222222222222222222"
TOKEN_ADDRESS = "0x4444444444444444444444444444444444444444"


def _run_poc(*, env: dict[str, str]) -> tuple[subprocess.CompletedProcess[str], dict[str, object]]:
    ARTIFACT_PATH.unlink(missing_ok=True)
    command_env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("PREDICT_") and not key.startswith("ERC_MANDATED_")
    }
    command_env.update(env)
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH)],
        cwd=PREDICT_ROOT,
        capture_output=True,
        text=True,
        env=command_env,
        check=False,
    )
    return result, json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))


def test_crediting_poc_missing_env_writes_no_go_artifact(tmp_path: Path) -> None:
    result, artifact = _run_poc(env={"PREDICT_STORAGE_DIR": str(tmp_path)})

    assert result.returncode == 1
    assert artifact["verdict"] == "NO-GO"
    assert artifact["txCorrelatedCreditEvidence"]["exists"] is False
    assert "missing predictAccountAddress" in artifact["reasons"]
    assert ARTIFACT_PATH.exists()


def test_crediting_poc_passes_with_explicit_tx_correlated_evidence(tmp_path: Path) -> None:
    evidence = {
        "fundingTxHash": "0x" + "ab" * 32,
        "recipient": PREDICT_ACCOUNT_ADDRESS,
        "tokenAddress": TOKEN_ADDRESS,
        "txStatus": "success",
        "creditReady": True,
        "creditSignalSource": "predict-wallet-status",
        "creditSignalReferencesTx": True,
        "observedBalanceBeforeRaw": "2000",
        "observedBalanceAfterRaw": "3500",
        "txMinedAt": "2026-03-10T00:00:00Z",
        "creditObservedAt": "2026-03-10T00:00:45Z",
    }
    result, artifact = _run_poc(
        env={
            "PREDICT_STORAGE_DIR": str(tmp_path),
            "PREDICT_ENV": "testnet",
            "PREDICT_WALLET_MODE": "predict-account",
            "PREDICT_ACCOUNT_ADDRESS": PREDICT_ACCOUNT_ADDRESS,
            "ERC_MANDATED_VAULT_ADDRESS": VAULT_ADDRESS,
            "ERC_MANDATED_VAULT_ASSET_ADDRESS": TOKEN_ADDRESS,
            "PREDICT_CREDITING_POC_EXPECTED_AMOUNT_RAW": "1000",
            "PREDICT_CREDITING_POC_EVIDENCE_JSON": json.dumps(evidence),
        }
    )

    assert result.returncode == 0
    assert artifact["verdict"] == "PASS"
    assert artifact["chain"] == "testnet"
    assert artifact["vaultAddress"] == VAULT_ADDRESS
    assert artifact["tokenAddress"] == TOKEN_ADDRESS
    evidence_payload = artifact["txCorrelatedCreditEvidence"]
    assert evidence_payload["strongEnoughForAutonomousContinuation"] is True
    assert evidence_payload["fundingTxHash"] == evidence["fundingTxHash"]
    assert artifact["reasons"] == []


def test_crediting_poc_rejects_unattributed_balance_increase(tmp_path: Path) -> None:
    evidence = {
        "fundingTxHash": "0x" + "cd" * 32,
        "recipient": PREDICT_ACCOUNT_ADDRESS,
        "tokenAddress": TOKEN_ADDRESS,
        "txStatus": "success",
        "creditReady": True,
        "creditSignalSource": "predict-wallet-status",
        "creditSignalReferencesTx": False,
        "observedBalanceBeforeRaw": "2000",
        "observedBalanceAfterRaw": "3500",
        "txMinedAt": "2026-03-10T00:00:00Z",
        "creditObservedAt": "2026-03-10T00:00:30Z",
    }
    result, artifact = _run_poc(
        env={
            "PREDICT_STORAGE_DIR": str(tmp_path),
            "PREDICT_ENV": "testnet",
            "PREDICT_WALLET_MODE": "predict-account",
            "PREDICT_ACCOUNT_ADDRESS": PREDICT_ACCOUNT_ADDRESS,
            "ERC_MANDATED_VAULT_ADDRESS": VAULT_ADDRESS,
            "ERC_MANDATED_VAULT_ASSET_ADDRESS": TOKEN_ADDRESS,
            "PREDICT_CREDITING_POC_EXPECTED_AMOUNT_RAW": "1000",
            "PREDICT_CREDITING_POC_EVIDENCE_JSON": json.dumps(evidence),
        }
    )

    assert result.returncode == 1
    assert artifact["verdict"] == "NO-GO"
    assert artifact["txCorrelatedCreditEvidence"]["strongEnoughForAutonomousContinuation"] is False
    assert "credit signal does not reference the funding transaction" in artifact["reasons"]