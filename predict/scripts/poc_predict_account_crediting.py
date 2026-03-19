#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import sys
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SKILL_DIR = Path(__file__).resolve().parent.parent
ARTIFACT_PATH = (
    SKILL_DIR / "artifacts" / "reports" / "autonomous-preflight" / "crediting-poc.json"
)
ADDRESS_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")
TX_HASH_RE = re.compile(r"^0x[a-fA-F0-9]{64}$")


def _value(source: Mapping[str, str], name: str) -> str | None:
    raw = source.get(name)
    if raw is None:
        return None
    value = raw.strip()
    return value or None


def _parse_json(source: Mapping[str, str], reasons: list[str]) -> dict[str, Any] | None:
    inline = _value(source, "PREDICT_CREDITING_POC_EVIDENCE_JSON")
    file_path = _value(source, "PREDICT_CREDITING_POC_EVIDENCE_FILE")
    if inline and file_path:
        reasons.append(
            "set only one of PREDICT_CREDITING_POC_EVIDENCE_JSON or PREDICT_CREDITING_POC_EVIDENCE_FILE"
        )
        return None
    raw = inline
    if file_path:
        try:
            raw = Path(file_path).read_text(encoding="utf-8")
        except OSError as error:
            reasons.append(f"unable to read evidence file: {error}")
            return None
    if raw is None:
        reasons.append("missing tx-correlated credit evidence input")
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        reasons.append(f"invalid credit evidence JSON: {error.msg}")
        return None
    if not isinstance(payload, dict):
        reasons.append("credit evidence JSON must be an object")
        return None
    return payload


def _parse_int(raw: Any, field: str, reasons: list[str]) -> int | None:
    if raw in (None, ""):
        reasons.append(f"missing {field}")
        return None
    try:
        return int(str(raw), 10)
    except ValueError:
        reasons.append(f"invalid integer for {field}: {raw}")
        return None


def _parse_ts(raw: Any, field: str, reasons: list[str]) -> datetime | None:
    if raw in (None, ""):
        reasons.append(f"missing {field}")
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        reasons.append(f"invalid timestamp for {field}: {raw}")
        return None


def run_crediting_poc(env: Mapping[str, str] | None = None) -> dict[str, Any]:
    source = env or os.environ
    reasons: list[str] = []
    wallet_mode = _value(source, "PREDICT_WALLET_MODE")
    chain = (
        _value(source, "PREDICT_CREDITING_POC_CHAIN")
        or _value(source, "ERC_MANDATED_CHAIN_ID")
        or _value(source, "PREDICT_ENV")
    )
    vault_address = _value(source, "ERC_MANDATED_VAULT_ADDRESS")
    token_address = _value(source, "PREDICT_CREDITING_POC_TOKEN_ADDRESS") or _value(
        source, "ERC_MANDATED_VAULT_ASSET_ADDRESS"
    )
    predict_account_address = _value(source, "PREDICT_ACCOUNT_ADDRESS")

    if wallet_mode != "predict-account":
        reasons.append("PREDICT_WALLET_MODE must be predict-account for the crediting PoC")
    for label, value in {
        "chain": chain,
        "vaultAddress": vault_address,
        "tokenAddress": token_address,
        "predictAccountAddress": predict_account_address,
    }.items():
        if value is None:
            reasons.append(f"missing {label}")
    for label, value in {
        "vaultAddress": vault_address,
        "tokenAddress": token_address,
        "predictAccountAddress": predict_account_address,
    }.items():
        if value is not None and not ADDRESS_RE.fullmatch(value):
            reasons.append(f"invalid {label}: {value}")

    evidence = _parse_json(source, reasons)
    evidence_reasons: list[str] = []
    tx_hash = recipient = observed_token = credit_signal_source = None
    tx_status = None
    credit_ready = credit_refs_tx = False
    observed_delta = observed_latency_seconds = None
    recipient_match = token_match = amount_match = within_window = False
    max_latency_seconds = _parse_int(
        _value(source, "PREDICT_CREDITING_POC_MAX_CREDIT_LATENCY_SECONDS") or "180",
        "PREDICT_CREDITING_POC_MAX_CREDIT_LATENCY_SECONDS",
        reasons,
    )
    expected_amount = _parse_int(
        _value(source, "PREDICT_CREDITING_POC_EXPECTED_AMOUNT_RAW"),
        "PREDICT_CREDITING_POC_EXPECTED_AMOUNT_RAW",
        reasons,
    )

    if evidence is not None:
        tx_hash = str(evidence.get("fundingTxHash") or "") or None
        recipient = str(evidence.get("recipient") or "") or None
        observed_token = str(evidence.get("tokenAddress") or "") or None
        tx_status = str(evidence.get("txStatus") or "") or None
        credit_signal_source = str(evidence.get("creditSignalSource") or "") or None
        credit_ready = bool(evidence.get("creditReady"))
        credit_refs_tx = bool(evidence.get("creditSignalReferencesTx"))
        before_balance = _parse_int(
            evidence.get("observedBalanceBeforeRaw"),
            "observedBalanceBeforeRaw",
            evidence_reasons,
        )
        after_balance = _parse_int(
            evidence.get("observedBalanceAfterRaw"),
            "observedBalanceAfterRaw",
            evidence_reasons,
        )
        tx_mined_at = _parse_ts(evidence.get("txMinedAt"), "txMinedAt", evidence_reasons)
        credit_observed_at = _parse_ts(
            evidence.get("creditObservedAt"), "creditObservedAt", evidence_reasons
        )
        if tx_hash is None or not TX_HASH_RE.fullmatch(tx_hash):
            evidence_reasons.append("missing or invalid fundingTxHash")
        if tx_status != "success":
            evidence_reasons.append("funding transaction did not report txStatus=success")
        if not credit_ready:
            evidence_reasons.append("creditReady must be true")
        if not credit_refs_tx:
            evidence_reasons.append(
                "credit signal does not reference the funding transaction"
            )
        recipient_match = (
            recipient is not None
            and predict_account_address is not None
            and recipient.lower() == predict_account_address.lower()
        )
        token_match = (
            observed_token is not None
            and token_address is not None
            and observed_token.lower() == token_address.lower()
        )
        if not recipient_match:
            evidence_reasons.append("recipient does not match predictAccountAddress")
        if not token_match:
            evidence_reasons.append("tokenAddress does not match configured tokenAddress")
        if before_balance is not None and after_balance is not None:
            observed_delta = after_balance - before_balance
        if observed_delta is None or observed_delta <= 0:
            evidence_reasons.append("observed credited balance delta must be positive")
        amount_match = expected_amount is not None and observed_delta is not None and observed_delta >= expected_amount
        if not amount_match:
            evidence_reasons.append("observed credited delta is smaller than expected")
        if (
            tx_mined_at is not None
            and credit_observed_at is not None
            and max_latency_seconds is not None
        ):
            observed_latency_seconds = int(
                (credit_observed_at - tx_mined_at).total_seconds()
            )
            within_window = 0 <= observed_latency_seconds <= max_latency_seconds
        if not within_window:
            evidence_reasons.append(
                "credit was not observed within the configured latency window"
            )

    reasons.extend(evidence_reasons)
    strong_enough = bool(evidence is not None) and not evidence_reasons and not [
        reason
        for reason in reasons
        if reason not in evidence_reasons
    ]
    artifact = {
        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "verdict": "PASS" if strong_enough else "NO-GO",
        "chain": chain,
        "vaultAddress": vault_address,
        "tokenAddress": token_address,
        "predictAccountAddress": predict_account_address,
        "txCorrelatedCreditEvidence": {
            "exists": evidence is not None,
            "strongEnoughForAutonomousContinuation": strong_enough,
            "fundingTxHash": tx_hash,
            "creditSignalSource": credit_signal_source,
            "creditReady": credit_ready,
            "creditSignalReferencesTx": credit_refs_tx,
            "recipientMatchesPredictAccount": recipient_match,
            "tokenMatchesExpected": token_match,
            "expectedAmountRaw": str(expected_amount) if expected_amount is not None else None,
            "observedAmountDeltaRaw": str(observed_delta) if observed_delta is not None else None,
            "observedLatencySeconds": observed_latency_seconds,
            "withinLatencyWindow": within_window,
            "txStatus": tx_status,
            "gaps": evidence_reasons,
        },
        "reasons": reasons,
    }
    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT_PATH.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    return artifact


def main() -> int:
    try:
        artifact = run_crediting_poc()
    except Exception as error:  # pragma: no cover - hard fail-safe path
        artifact = {
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "verdict": "NO-GO",
            "chain": None,
            "vaultAddress": None,
            "tokenAddress": None,
            "predictAccountAddress": None,
            "txCorrelatedCreditEvidence": {
                "exists": False,
                "strongEnoughForAutonomousContinuation": False,
                "fundingTxHash": None,
                "creditSignalSource": None,
                "creditReady": False,
                "creditSignalReferencesTx": False,
                "recipientMatchesPredictAccount": False,
                "tokenMatchesExpected": False,
                "expectedAmountRaw": None,
                "observedAmountDeltaRaw": None,
                "observedLatencySeconds": None,
                "withinLatencyWindow": False,
                "txStatus": None,
                "gaps": [f"unexpected-error: {error}"],
            },
            "reasons": [f"unexpected-error: {error}"],
        }
        ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
        ARTIFACT_PATH.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(artifact, indent=2))
    return 0 if artifact["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())