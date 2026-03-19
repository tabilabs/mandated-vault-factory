#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SKILL_DIR = Path(__file__).resolve().parent.parent
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

from lib.config import ConfigError, PredictConfig
from lib.mandated_mcp_bridge import MandatedVaultMcpBridge
from lib.wallet_manager import build_vault_to_predict_account_orchestration

ARTIFACT_PATH = (
    SKILL_DIR / "artifacts" / "reports" / "autonomous-preflight" / "follow-up-autonomy.json"
)
ADDRESS_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")
TX_HASH_RE = re.compile(r"^0x[a-fA-F0-9]{64}$")


def _value(source: Mapping[str, str], name: str) -> str | None:
    raw = source.get(name)
    if raw is None:
        return None
    value = raw.strip()
    return value or None


def _append_unique(reasons: list[str], reason: str) -> None:
    if reason not in reasons:
        reasons.append(reason)


def _parse_int(raw: str | None, *, field: str, reasons: list[str]) -> int | None:
    if raw is None:
        return None
    try:
        return int(raw, 10)
    except ValueError:
        _append_unique(reasons, f"invalid integer for {field}: {raw}")
        return None


def _parse_evidence(source: Mapping[str, str], reasons: list[str]) -> dict[str, Any] | None:
    inline = _value(source, "PREDICT_FOLLOW_UP_POC_EVIDENCE_JSON")
    file_path = _value(source, "PREDICT_FOLLOW_UP_POC_EVIDENCE_FILE")
    if inline and file_path:
        _append_unique(
            reasons,
            "set only one of PREDICT_FOLLOW_UP_POC_EVIDENCE_JSON or PREDICT_FOLLOW_UP_POC_EVIDENCE_FILE",
        )
        return None
    raw = inline
    if file_path:
        try:
            raw = Path(file_path).read_text(encoding="utf-8")
        except OSError as error:
            _append_unique(reasons, f"unable to read follow-up evidence file: {error}")
            return None
    if raw is None:
        _append_unique(reasons, "missing follow-up autonomy evidence input")
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        _append_unique(reasons, f"invalid follow-up autonomy evidence JSON: {error.msg}")
        return None
    if not isinstance(payload, dict):
        _append_unique(reasons, "follow-up autonomy evidence JSON must be an object")
        return None
    return payload


def _load_config(source: Mapping[str, str], reasons: list[str]) -> PredictConfig | None:
    sanitized = dict(source)
    explicit_vault = _value(source, "ERC_MANDATED_VAULT_ADDRESS")
    token_address = _value(source, "ERC_MANDATED_VAULT_ASSET_ADDRESS")
    authority_address = _value(source, "ERC_MANDATED_VAULT_AUTHORITY")
    if explicit_vault is not None:
        for name in (
            "ERC_MANDATED_FACTORY_ADDRESS",
            "ERC_MANDATED_VAULT_ASSET_ADDRESS",
            "ERC_MANDATED_VAULT_NAME",
            "ERC_MANDATED_VAULT_SYMBOL",
            "ERC_MANDATED_VAULT_AUTHORITY",
            "ERC_MANDATED_VAULT_SALT",
        ):
            sanitized.pop(name, None)
    try:
        config = PredictConfig.from_env(sanitized)
    except ConfigError as error:
        _append_unique(reasons, str(error))
        return None
    if explicit_vault is not None:
        config = config.model_copy(
            update={
                "mandated_vault_asset_address": token_address,
                "mandated_vault_authority": authority_address,
            }
        )
    return config


async def _collect_orchestration(
    *,
    config: PredictConfig,
    predict_account_address: str,
    trade_signer_address: str,
    current_balance_raw: int,
    reasons: list[str],
) -> dict[str, Any]:
    bridge = MandatedVaultMcpBridge(config)
    evidence: dict[str, Any] = {
        "availableTools": [],
        "mcpRuntimeReady": False,
        "followUpResultToolAvailable": False,
        "sessionStatus": None,
        "currentStep": None,
        "followUpStepStatus": None,
        "nextStepKind": None,
        "followUpActionKind": None,
        "followUpActionTarget": None,
        "followUpActionDeferred": None,
        "followUpActionReason": None,
        "followUpPlanKind": None,
        "followUpPlanTarget": None,
        "followUpExecutionMode": None,
        "followUpPlanDeferred": None,
        "followUpPlanReason": None,
        "followUpPlanUsesExpectedToken": False,
        "tradeSignerAddress": trade_signer_address,
    }
    try:
        await bridge.connect()
        evidence["availableTools"] = sorted(bridge.available_tools)
        evidence["mcpRuntimeReady"] = bridge.runtime_ready
        evidence["followUpResultToolAvailable"] = (
            "agent_follow_up_action_result_create" in bridge.available_tools
        )
        orchestration = await build_vault_to_predict_account_orchestration(
            config,
            bridge,
            predict_account_address=predict_account_address,
            trade_signer_address=trade_signer_address,
            current_usdt_balance_wei=current_balance_raw,
        )
        plan = orchestration.funding_plan
        session = orchestration.funding_session
        next_step = orchestration.funding_next_step
        action = plan.get("followUpAction", {}) if isinstance(plan, dict) else {}
        follow_up_plan = plan.get("followUpActionPlan", {}) if isinstance(plan, dict) else {}
        task = next_step.get("task", {}) if isinstance(next_step, dict) else {}
        follow_up_step = session.get("followUpStep", {}) if isinstance(session, dict) else {}
        payload = action.get("payload", {}) if isinstance(action, dict) else {}
        plan_payload = (
            follow_up_plan.get("payload", {}) if isinstance(follow_up_plan, dict) else {}
        )
        asset_requirement = (
            follow_up_plan.get("assetRequirement", {})
            if isinstance(follow_up_plan, dict)
            else {}
        )
        evidence.update(
            {
                "sessionStatus": session.get("status") if isinstance(session, dict) else None,
                "currentStep": session.get("currentStep") if isinstance(session, dict) else None,
                "followUpStepStatus": (
                    follow_up_step.get("status") if isinstance(follow_up_step, dict) else None
                ),
                "nextStepKind": task.get("kind") if isinstance(task, dict) else None,
                "followUpActionKind": action.get("kind") if isinstance(action, dict) else None,
                "followUpActionTarget": action.get("target") if isinstance(action, dict) else None,
                "followUpActionDeferred": (
                    isinstance(payload, dict) and payload.get("status") == "deferred"
                ),
                "followUpActionReason": (
                    payload.get("reason") if isinstance(payload, dict) else None
                ),
                "followUpPlanKind": (
                    follow_up_plan.get("kind") if isinstance(follow_up_plan, dict) else None
                ),
                "followUpPlanTarget": (
                    follow_up_plan.get("target") if isinstance(follow_up_plan, dict) else None
                ),
                "followUpExecutionMode": (
                    follow_up_plan.get("executionMode")
                    if isinstance(follow_up_plan, dict)
                    else None
                ),
                "followUpPlanDeferred": (
                    isinstance(plan_payload, dict) and plan_payload.get("status") == "deferred"
                ),
                "followUpPlanReason": (
                    plan_payload.get("reason") if isinstance(plan_payload, dict) else None
                ),
                "followUpPlanUsesExpectedToken": (
                    isinstance(asset_requirement, dict)
                    and str(asset_requirement.get("tokenAddress") or "").lower()
                    == str(config.mandated_vault_asset_address or "").lower()
                )
                or (
                    isinstance(plan_payload, dict)
                    and str(plan_payload.get("collateralTokenAddress") or "").lower()
                    == str(config.mandated_vault_asset_address or "").lower()
                ),
            }
        )
    except Exception as error:
        _append_unique(reasons, f"unable to build overlay orchestration: {error}")
    finally:
        try:
            await bridge.close()
        except Exception:
            pass
    return evidence


def _credit_signal(
    evidence: dict[str, Any] | None,
    *,
    predict_account_address: str | None,
    token_address: str | None,
    reasons: list[str],
) -> tuple[dict[str, Any], bool]:
    raw = evidence.get("creditReadinessSignal") if isinstance(evidence, dict) else None
    gaps: list[str] = []
    payload = {
        "exists": isinstance(raw, dict),
        "source": None,
        "fundingTxHash": None,
        "ready": False,
        "referencesFundingTx": False,
        "recipient": None,
        "recipientMatchesPredictAccount": False,
        "tokenAddress": None,
        "tokenMatchesExpected": False,
        "gaps": gaps,
    }
    if not isinstance(raw, dict):
        _append_unique(gaps, "missing creditReadinessSignal")
    else:
        payload["source"] = str(raw.get("source") or "") or None
        payload["fundingTxHash"] = str(raw.get("fundingTxHash") or "") or None
        payload["ready"] = bool(raw.get("ready"))
        payload["referencesFundingTx"] = bool(raw.get("referencesFundingTx"))
        payload["recipient"] = str(raw.get("recipient") or "") or None
        payload["tokenAddress"] = str(raw.get("tokenAddress") or "") or None
        payload["recipientMatchesPredictAccount"] = (
            payload["recipient"] is not None
            and predict_account_address is not None
            and str(payload["recipient"]).lower() == predict_account_address.lower()
        )
        payload["tokenMatchesExpected"] = (
            payload["tokenAddress"] is not None
            and token_address is not None
            and str(payload["tokenAddress"]).lower() == token_address.lower()
        )
        if payload["source"] is None:
            _append_unique(gaps, "credit readiness signal is missing source")
        if payload["fundingTxHash"] is None or not TX_HASH_RE.fullmatch(
            str(payload["fundingTxHash"])
        ):
            _append_unique(gaps, "credit readiness signal is missing a valid fundingTxHash")
        if not payload["ready"]:
            _append_unique(gaps, "credit readiness signal did not report ready=true")
        if not payload["referencesFundingTx"]:
            _append_unique(
                gaps,
                "credit readiness signal does not reference the funding transaction",
            )
        if not payload["recipientMatchesPredictAccount"]:
            _append_unique(
                gaps,
                "credit readiness signal recipient does not match predictAccountAddress",
            )
        if not payload["tokenMatchesExpected"]:
            _append_unique(
                gaps,
                "credit readiness signal token does not match tokenAddress",
            )
    for gap in gaps:
        _append_unique(reasons, gap)
    return payload, not gaps


def _auth_signal(
    evidence: dict[str, Any] | None,
    *,
    config: PredictConfig | None,
    predict_account_address: str | None,
    reasons: list[str],
) -> tuple[dict[str, Any], bool]:
    raw = evidence.get("authOwnershipSignal") if isinstance(evidence, dict) else None
    gaps: list[str] = []
    configured_signer = config.auth_signer_address if config is not None else None
    config_noninteractive = bool(
        config is not None
        and config.wallet_mode.value == "predict-account"
        and config.predict_account_address
        and config.privy_private_key_value
    )
    payload = {
        "exists": isinstance(raw, dict),
        "source": None,
        "ownerAddress": None,
        "authSignerAddress": None,
        "ownerMatchesPredictAccount": False,
        "signerMatchesPredictAccount": False,
        "refreshCanBePerformedNonInteractively": False,
        "refreshRequiresInteraction": False,
        "configBasedAuthSignerAddress": configured_signer,
        "configBasedAuthSignerMatchesPredictAccount": (
            configured_signer is not None
            and predict_account_address is not None
            and configured_signer.lower() == predict_account_address.lower()
        ),
        "configBasedNonInteractiveAuthConfigured": config_noninteractive,
        "gaps": gaps,
    }
    if not payload["configBasedNonInteractiveAuthConfigured"]:
        _append_unique(
            gaps,
            "local predict-account credentials are not configured for non-interactive auth refresh",
        )
    if not payload["configBasedAuthSignerMatchesPredictAccount"]:
        _append_unique(
            gaps,
            "configured auth signer does not match predictAccountAddress",
        )
    if not isinstance(raw, dict):
        _append_unique(gaps, "missing authOwnershipSignal")
    else:
        payload["source"] = str(raw.get("source") or "") or None
        payload["ownerAddress"] = str(raw.get("ownerAddress") or "") or None
        payload["authSignerAddress"] = str(raw.get("authSignerAddress") or "") or None
        payload["refreshCanBePerformedNonInteractively"] = bool(
            raw.get("refreshCanBePerformedNonInteractively")
        )
        payload["refreshRequiresInteraction"] = bool(
            raw.get("refreshRequiresInteraction")
        )
        payload["ownerMatchesPredictAccount"] = (
            payload["ownerAddress"] is not None
            and predict_account_address is not None
            and str(payload["ownerAddress"]).lower() == predict_account_address.lower()
        )
        payload["signerMatchesPredictAccount"] = (
            payload["authSignerAddress"] is not None
            and predict_account_address is not None
            and str(payload["authSignerAddress"]).lower() == predict_account_address.lower()
        )
        if payload["source"] is None:
            _append_unique(gaps, "auth ownership signal is missing source")
        if not payload["ownerMatchesPredictAccount"]:
            _append_unique(
                gaps,
                "auth ownership signal ownerAddress does not match predictAccountAddress",
            )
        if not payload["signerMatchesPredictAccount"]:
            _append_unique(
                gaps,
                "auth ownership signal authSignerAddress does not match predictAccountAddress",
            )
        if not payload["refreshCanBePerformedNonInteractively"]:
            _append_unique(
                gaps,
                "auth ownership signal did not prove non-interactive refresh capability",
            )
        if payload["refreshRequiresInteraction"]:
            _append_unique(
                gaps,
                "auth ownership signal says refresh requires interaction",
            )
    for gap in gaps:
        _append_unique(reasons, gap)
    return payload, not gaps


def run_follow_up_autonomy_poc(env: Mapping[str, str] | None = None) -> dict[str, Any]:
    source = env or os.environ
    reasons: list[str] = []
    wallet_mode = _value(source, "PREDICT_WALLET_MODE")
    chain = _value(source, "ERC_MANDATED_CHAIN_ID") or _value(source, "PREDICT_ENV")
    vault_address = _value(source, "ERC_MANDATED_VAULT_ADDRESS")
    token_address = _value(source, "ERC_MANDATED_VAULT_ASSET_ADDRESS")
    predict_account_address = _value(source, "PREDICT_ACCOUNT_ADDRESS")
    trade_signer_address = (
        _value(source, "PREDICT_FOLLOW_UP_POC_TRADE_SIGNER_ADDRESS")
        or predict_account_address
    )
    current_balance_raw = _parse_int(
        _value(source, "PREDICT_FOLLOW_UP_POC_CURRENT_BALANCE_RAW") or "0",
        field="PREDICT_FOLLOW_UP_POC_CURRENT_BALANCE_RAW",
        reasons=reasons,
    )

    if wallet_mode != "predict-account":
        _append_unique(
            reasons,
            "PREDICT_WALLET_MODE must be predict-account for the follow-up autonomy PoC",
        )
    for label, value in {
        "chain": chain,
        "vaultAddress": vault_address,
        "tokenAddress": token_address,
        "predictAccountAddress": predict_account_address,
        "tradeSignerAddress": trade_signer_address,
    }.items():
        if value is None:
            _append_unique(reasons, f"missing {label}")
    for label, value in {
        "vaultAddress": vault_address,
        "tokenAddress": token_address,
        "predictAccountAddress": predict_account_address,
        "tradeSignerAddress": trade_signer_address,
    }.items():
        if value is not None and not ADDRESS_RE.fullmatch(value):
            _append_unique(reasons, f"invalid {label}: {value}")

    config = _load_config(source, reasons)
    raw_evidence = _parse_evidence(source, reasons)
    orchestration = {
        "availableTools": [],
        "mcpRuntimeReady": False,
        "followUpResultToolAvailable": False,
        "sessionStatus": None,
        "currentStep": None,
        "followUpStepStatus": None,
        "nextStepKind": None,
        "followUpActionKind": None,
        "followUpActionTarget": None,
        "followUpActionDeferred": None,
        "followUpActionReason": None,
        "followUpPlanKind": None,
        "followUpPlanTarget": None,
        "followUpExecutionMode": None,
        "followUpPlanDeferred": None,
        "followUpPlanReason": None,
        "followUpPlanUsesExpectedToken": False,
        "tradeSignerAddress": trade_signer_address,
    }
    if (
        config is not None
        and predict_account_address is not None
        and trade_signer_address is not None
        and current_balance_raw is not None
        and not [
            reason
            for reason in reasons
            if reason.startswith("missing ") or reason.startswith("invalid ")
        ]
    ):
        orchestration = asyncio.run(
            _collect_orchestration(
                config=config,
                predict_account_address=predict_account_address,
                trade_signer_address=trade_signer_address,
                current_balance_raw=current_balance_raw,
                reasons=reasons,
            )
        )

    follow_up_gaps: list[str] = []
    if not orchestration["mcpRuntimeReady"]:
        _append_unique(follow_up_gaps, "MCP runtime is not ready for overlay follow-up checks")
    if not orchestration["followUpResultToolAvailable"]:
        _append_unique(
            follow_up_gaps,
            "MCP runtime does not expose agent_follow_up_action_result_create",
        )
    if orchestration["followUpPlanKind"] != "predict.createOrder":
        _append_unique(
            follow_up_gaps,
            "follow-up action plan kind must be predict.createOrder",
        )
    if orchestration["followUpExecutionMode"] != "offchain-api":
        _append_unique(
            follow_up_gaps,
            "follow-up action plan executionMode must be offchain-api",
        )
    if orchestration["followUpActionDeferred"]:
        _append_unique(follow_up_gaps, "follow-up action remains deferred")
    if orchestration["followUpPlanDeferred"]:
        _append_unique(follow_up_gaps, "follow-up action plan remains deferred")
    if not orchestration["followUpPlanUsesExpectedToken"]:
        _append_unique(
            follow_up_gaps,
            "follow-up action plan does not bind the expected tokenAddress",
        )
    if orchestration["sessionStatus"] not in {"pendingFollowUp", "succeeded"}:
        _append_unique(
            follow_up_gaps,
            "session did not expose a post-funding follow-up continuation state",
        )
    if orchestration["nextStepKind"] not in {
        "submitFollowUp",
        "pollFollowUpResult",
        "completed",
    }:
        _append_unique(
            follow_up_gaps,
            "next step did not expose submitFollowUp/pollFollowUpResult/completed",
        )
    for gap in follow_up_gaps:
        _append_unique(reasons, gap)

    credit_signal, credit_ok = _credit_signal(
        raw_evidence,
        predict_account_address=predict_account_address,
        token_address=token_address,
        reasons=reasons,
    )
    auth_signal, auth_ok = _auth_signal(
        raw_evidence,
        config=config,
        predict_account_address=predict_account_address,
        reasons=reasons,
    )
    strong_enough = not reasons and not follow_up_gaps and credit_ok and auth_ok
    artifact = {
        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "verdict": "PASS" if strong_enough else "NO-GO",
        "chain": chain,
        "vaultAddress": vault_address,
        "tokenAddress": token_address,
        "predictAccountAddress": predict_account_address,
        "followUpAutonomyEvidence": {
            **orchestration,
            "predictSideCreditReadinessSignal": credit_signal,
            "authOwnershipSignal": auth_signal,
            "strongEnoughForAutonomousContinuation": strong_enough,
            "gaps": reasons,
        },
        "reasons": reasons,
    }
    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT_PATH.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    return artifact


def main() -> int:
    try:
        artifact = run_follow_up_autonomy_poc()
    except Exception as error:  # pragma: no cover - hard fail-safe path
        artifact = {
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "verdict": "NO-GO",
            "chain": None,
            "vaultAddress": None,
            "tokenAddress": None,
            "predictAccountAddress": None,
            "followUpAutonomyEvidence": {
                "availableTools": [],
                "mcpRuntimeReady": False,
                "followUpResultToolAvailable": False,
                "sessionStatus": None,
                "currentStep": None,
                "followUpStepStatus": None,
                "nextStepKind": None,
                "followUpActionKind": None,
                "followUpActionTarget": None,
                "followUpActionDeferred": None,
                "followUpActionReason": None,
                "followUpPlanKind": None,
                "followUpPlanTarget": None,
                "followUpExecutionMode": None,
                "followUpPlanDeferred": None,
                "followUpPlanReason": None,
                "followUpPlanUsesExpectedToken": False,
                "tradeSignerAddress": None,
                "predictSideCreditReadinessSignal": {
                    "exists": False,
                    "source": None,
                    "fundingTxHash": None,
                    "ready": False,
                    "referencesFundingTx": False,
                    "recipient": None,
                    "recipientMatchesPredictAccount": False,
                    "tokenAddress": None,
                    "tokenMatchesExpected": False,
                    "gaps": [f"unexpected-error: {error}"],
                },
                "authOwnershipSignal": {
                    "exists": False,
                    "source": None,
                    "ownerAddress": None,
                    "authSignerAddress": None,
                    "ownerMatchesPredictAccount": False,
                    "signerMatchesPredictAccount": False,
                    "refreshCanBePerformedNonInteractively": False,
                    "refreshRequiresInteraction": False,
                    "configBasedAuthSignerAddress": None,
                    "configBasedAuthSignerMatchesPredictAccount": False,
                    "configBasedNonInteractiveAuthConfigured": False,
                    "gaps": [f"unexpected-error: {error}"],
                },
                "strongEnoughForAutonomousContinuation": False,
                "gaps": [f"unexpected-error: {error}"],
            },
            "reasons": [f"unexpected-error: {error}"],
        }
        ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
        ARTIFACT_PATH.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    return 0 if artifact["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())