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

from eth_account import Account

SKILL_DIR = Path(__file__).resolve().parent.parent
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

from lib.config import ConfigError, PredictConfig
from lib.mandated_mcp_bridge import (
    AgentAccountContext,
    AssetTransferPlanWithContextResult,
    AssetTransferResult,
    FundAndActionExecutionSession,
    FundAndActionSessionNextStepResult,
    MandatedVaultMcpBridge,
)

ARTIFACT_PATH = (
    SKILL_DIR
    / "artifacts"
    / "reports"
    / "autonomous-preflight"
    / "session-event-compatibility.json"
)
ADDRESS_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")
HEX32_RE = re.compile(r"^0x[a-fA-F0-9]{64}$")
DEFAULT_ALLOWED_ADAPTERS_ROOT = "0x" + "11" * 32
DEFAULT_CREATED_AT = "2026-03-10T00:00:00Z"
DEFAULT_UPDATED_AT = "2026-03-10T00:05:00Z"
DEFAULT_AMOUNT_RAW = "800"
DEFAULT_NONCE = "7"
DEFAULT_DEADLINE = "9999999999"
DEFAULT_AUTHORITY_EPOCH = "2"
DEFAULT_EXTENSIONS = "0x"

REQUIRED_RUNTIME_FIELD_SET = [
    {
        "name": "payloadBinding",
        "sourcePaths": ["fundingPlan.accountContext.defaults.payloadBinding"],
    },
    {
        "name": "typedData",
        "sourcePaths": ["fundingPlan.signRequest.typedData"],
    },
    {
        "name": "chainId",
        "sourcePaths": [
            "fundingPlan.accountContext.chainId",
            "fundingPlan.simulateExecuteInput.chainId",
            "fundingPlan.prepareExecuteInput.chainId",
        ],
    },
    {
        "name": "vault",
        "sourcePaths": [
            "fundingPlan.accountContext.vault",
            "fundingPlan.signRequest.mandate.vault",
            "fundingPlan.simulateExecuteInput.vault",
            "fundingPlan.prepareExecuteInput.vault",
        ],
    },
    {
        "name": "executor",
        "sourcePaths": [
            "fundingPlan.accountContext.executor",
            "fundingPlan.signRequest.mandate.executor",
            "fundingPlan.simulateExecuteInput.from",
            "fundingPlan.prepareExecuteInput.from",
        ],
    },
    {
        "name": "tokenAddress",
        "sourcePaths": [
            "fundingPlan.humanReadableSummary.tokenAddress",
            "fundingPlan.erc20Call.tokenAddress",
        ],
    },
    {
        "name": "recipient",
        "sourcePaths": [
            "fundingPlan.humanReadableSummary.to",
            "fundingPlan.erc20Call.to",
        ],
    },
    {
        "name": "amountRaw",
        "sourcePaths": [
            "fundingPlan.humanReadableSummary.amountRaw",
            "fundingPlan.erc20Call.amountRaw",
        ],
    },
    {
        "name": "nonce",
        "sourcePaths": [
            "fundingPlan.signRequest.mandate.nonce",
            "fundingPlan.simulateExecuteInput.mandate.nonce",
            "fundingPlan.prepareExecuteInput.mandate.nonce",
        ],
    },
    {
        "name": "deadline",
        "sourcePaths": [
            "fundingPlan.signRequest.mandate.deadline",
            "fundingPlan.simulateExecuteInput.mandate.deadline",
            "fundingPlan.prepareExecuteInput.mandate.deadline",
        ],
    },
    {
        "name": "authorityEpoch",
        "sourcePaths": [
            "fundingPlan.signRequest.mandate.authorityEpoch",
            "fundingPlan.simulateExecuteInput.mandate.authorityEpoch",
            "fundingPlan.prepareExecuteInput.mandate.authorityEpoch",
        ],
    },
    {
        "name": "allowedAdaptersRoot",
        "sourcePaths": [
            "fundingPlan.signRequest.mandate.allowedAdaptersRoot",
            "fundingPlan.simulateExecuteInput.mandate.allowedAdaptersRoot",
            "fundingPlan.prepareExecuteInput.mandate.allowedAdaptersRoot",
        ],
    },
    {
        "name": "payloadDigest",
        "sourcePaths": [
            "fundingPlan.signRequest.mandate.payloadDigest",
            "fundingPlan.simulateExecuteInput.mandate.payloadDigest",
            "fundingPlan.prepareExecuteInput.mandate.payloadDigest",
        ],
    },
    {
        "name": "actionsDigest",
        "sourcePaths": ["fundingPlan.signRequest.actionsDigest"],
    },
    {
        "name": "extensionsHash",
        "sourcePaths": [
            "fundingPlan.signRequest.extensionsHash",
            "fundingPlan.signRequest.mandate.extensionsHash",
            "fundingPlan.simulateExecuteInput.mandate.extensionsHash",
            "fundingPlan.prepareExecuteInput.mandate.extensionsHash",
        ],
    },
    {
        "name": "actions",
        "sourcePaths": [
            "fundingPlan.simulateExecuteInput.actions",
            "fundingPlan.prepareExecuteInput.actions",
        ],
    },
    {
        "name": "adapterProofs",
        "sourcePaths": [
            "fundingPlan.simulateExecuteInput.adapterProofs",
            "fundingPlan.prepareExecuteInput.adapterProofs",
        ],
    },
    {
        "name": "extensions",
        "sourcePaths": [
            "fundingPlan.simulateExecuteInput.extensions",
            "fundingPlan.prepareExecuteInput.extensions",
        ],
    },
]


def _value(source: Mapping[str, str], name: str) -> str | None:
    raw = source.get(name)
    if raw is None:
        return None
    value = raw.strip()
    return value or None


def _append_unique(reasons: list[str], reason: str) -> None:
    if reason not in reasons:
        reasons.append(reason)


def _uint_string(source: Mapping[str, str], name: str, *, default: str) -> str:
    value = _value(source, name) or default
    return value if value.isdigit() else default


def _load_config(source: Mapping[str, str], reasons: list[str]) -> PredictConfig | None:
    sanitized = dict(source)
    if _value(source, "PREDICT_WALLET_MODE") == "mandated-vault":
        sanitized.pop("PREDICT_ACCOUNT_ADDRESS", None)
        sanitized.pop("PREDICT_PRIVY_PRIVATE_KEY", None)
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


def _derive_address(
    private_key: str | None, *, label: str, reasons: list[str]
) -> str | None:
    if private_key is None:
        return None
    try:
        return Account.from_key(private_key).address
    except Exception:
        _append_unique(reasons, f"invalid {label}")
        return None


def _normalize_value(value: Any, *, address: bool = False) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        return stripped.lower() if address else stripped
    if isinstance(value, (list, dict)):
        if not value:
            return None
        return json.dumps(value, sort_keys=True)
    return str(value)


def _field_evidence(
    *,
    name: str,
    values_by_source: Mapping[str, Any],
    address: bool = False,
) -> dict[str, Any]:
    normalized = {
        source: _normalize_value(value, address=address)
        for source, value in values_by_source.items()
    }
    missing_sources = [source for source, value in normalized.items() if value is None]
    present_values = [value for value in normalized.values() if value is not None]
    unique_values = list(dict.fromkeys(present_values))
    consistent = bool(present_values) and len(set(present_values)) == 1
    canonical_value = unique_values[0] if consistent else None
    return {
        "name": name,
        "sourcePaths": list(values_by_source),
        "values": normalized,
        "missingSources": missing_sources,
        "presentInAllSources": not missing_sources,
        "consistent": consistent,
        "canonicalValue": canonical_value,
        "sufficient": not missing_sources and consistent,
    }


def _required_runtime_field_evidence(
    funding_plan: AssetTransferPlanWithContextResult,
) -> tuple[dict[str, Any], list[str]]:
    defaults = funding_plan.accountContext.defaults
    simulate = funding_plan.simulateExecuteInput
    prepare = funding_plan.prepareExecuteInput
    field_evidence = {
        "payloadBinding": _field_evidence(
            name="payloadBinding",
            values_by_source={
                "fundingPlan.accountContext.defaults.payloadBinding": (
                    defaults.payloadBinding if defaults is not None else None
                )
            },
        ),
        "typedData": _field_evidence(
            name="typedData",
            values_by_source={"fundingPlan.signRequest.typedData": funding_plan.signRequest.typedData},
        ),
        "chainId": _field_evidence(
            name="chainId",
            values_by_source={
                "fundingPlan.accountContext.chainId": funding_plan.accountContext.chainId,
                "fundingPlan.simulateExecuteInput.chainId": (
                    simulate.chainId if simulate is not None else None
                ),
                "fundingPlan.prepareExecuteInput.chainId": (
                    prepare.chainId if prepare is not None else None
                ),
            },
        ),
        "vault": _field_evidence(
            name="vault",
            address=True,
            values_by_source={
                "fundingPlan.accountContext.vault": funding_plan.accountContext.vault,
                "fundingPlan.signRequest.mandate.vault": funding_plan.signRequest.mandate.vault,
                "fundingPlan.simulateExecuteInput.vault": (
                    simulate.vault if simulate is not None else None
                ),
                "fundingPlan.prepareExecuteInput.vault": (
                    prepare.vault if prepare is not None else None
                ),
            },
        ),
        "executor": _field_evidence(
            name="executor",
            address=True,
            values_by_source={
                "fundingPlan.accountContext.executor": funding_plan.accountContext.executor,
                "fundingPlan.signRequest.mandate.executor": funding_plan.signRequest.mandate.executor,
                "fundingPlan.simulateExecuteInput.from": (
                    simulate.from_address if simulate is not None else None
                ),
                "fundingPlan.prepareExecuteInput.from": (
                    prepare.from_address if prepare is not None else None
                ),
            },
        ),
        "tokenAddress": _field_evidence(
            name="tokenAddress",
            address=True,
            values_by_source={
                "fundingPlan.humanReadableSummary.tokenAddress": (
                    funding_plan.humanReadableSummary.tokenAddress
                ),
                "fundingPlan.erc20Call.tokenAddress": funding_plan.erc20Call.get("tokenAddress"),
            },
        ),
        "recipient": _field_evidence(
            name="recipient",
            address=True,
            values_by_source={
                "fundingPlan.humanReadableSummary.to": funding_plan.humanReadableSummary.to,
                "fundingPlan.erc20Call.to": funding_plan.erc20Call.get("to"),
            },
        ),
        "amountRaw": _field_evidence(
            name="amountRaw",
            values_by_source={
                "fundingPlan.humanReadableSummary.amountRaw": (
                    funding_plan.humanReadableSummary.amountRaw
                ),
                "fundingPlan.erc20Call.amountRaw": funding_plan.erc20Call.get("amountRaw"),
            },
        ),
        "nonce": _field_evidence(
            name="nonce",
            values_by_source={
                "fundingPlan.signRequest.mandate.nonce": funding_plan.signRequest.mandate.nonce,
                "fundingPlan.simulateExecuteInput.mandate.nonce": (
                    simulate.mandate.nonce if simulate is not None else None
                ),
                "fundingPlan.prepareExecuteInput.mandate.nonce": (
                    prepare.mandate.nonce if prepare is not None else None
                ),
            },
        ),
        "deadline": _field_evidence(
            name="deadline",
            values_by_source={
                "fundingPlan.signRequest.mandate.deadline": funding_plan.signRequest.mandate.deadline,
                "fundingPlan.simulateExecuteInput.mandate.deadline": (
                    simulate.mandate.deadline if simulate is not None else None
                ),
                "fundingPlan.prepareExecuteInput.mandate.deadline": (
                    prepare.mandate.deadline if prepare is not None else None
                ),
            },
        ),
        "authorityEpoch": _field_evidence(
            name="authorityEpoch",
            values_by_source={
                "fundingPlan.signRequest.mandate.authorityEpoch": (
                    funding_plan.signRequest.mandate.authorityEpoch
                ),
                "fundingPlan.simulateExecuteInput.mandate.authorityEpoch": (
                    simulate.mandate.authorityEpoch if simulate is not None else None
                ),
                "fundingPlan.prepareExecuteInput.mandate.authorityEpoch": (
                    prepare.mandate.authorityEpoch if prepare is not None else None
                ),
            },
        ),
        "allowedAdaptersRoot": _field_evidence(
            name="allowedAdaptersRoot",
            values_by_source={
                "fundingPlan.signRequest.mandate.allowedAdaptersRoot": (
                    funding_plan.signRequest.mandate.allowedAdaptersRoot
                ),
                "fundingPlan.simulateExecuteInput.mandate.allowedAdaptersRoot": (
                    simulate.mandate.allowedAdaptersRoot if simulate is not None else None
                ),
                "fundingPlan.prepareExecuteInput.mandate.allowedAdaptersRoot": (
                    prepare.mandate.allowedAdaptersRoot if prepare is not None else None
                ),
            },
        ),
        "payloadDigest": _field_evidence(
            name="payloadDigest",
            values_by_source={
                "fundingPlan.signRequest.mandate.payloadDigest": (
                    funding_plan.signRequest.mandate.payloadDigest
                ),
                "fundingPlan.simulateExecuteInput.mandate.payloadDigest": (
                    simulate.mandate.payloadDigest if simulate is not None else None
                ),
                "fundingPlan.prepareExecuteInput.mandate.payloadDigest": (
                    prepare.mandate.payloadDigest if prepare is not None else None
                ),
            },
        ),
        "actionsDigest": _field_evidence(
            name="actionsDigest",
            values_by_source={"fundingPlan.signRequest.actionsDigest": funding_plan.signRequest.actionsDigest},
        ),
        "extensionsHash": _field_evidence(
            name="extensionsHash",
            values_by_source={
                "fundingPlan.signRequest.extensionsHash": funding_plan.signRequest.extensionsHash,
                "fundingPlan.signRequest.mandate.extensionsHash": (
                    funding_plan.signRequest.mandate.extensionsHash
                ),
                "fundingPlan.simulateExecuteInput.mandate.extensionsHash": (
                    simulate.mandate.extensionsHash if simulate is not None else None
                ),
                "fundingPlan.prepareExecuteInput.mandate.extensionsHash": (
                    prepare.mandate.extensionsHash if prepare is not None else None
                ),
            },
        ),
        "actions": _field_evidence(
            name="actions",
            values_by_source={
                "fundingPlan.simulateExecuteInput.actions": (
                    simulate.actions if simulate is not None else None
                ),
                "fundingPlan.prepareExecuteInput.actions": (
                    prepare.actions if prepare is not None else None
                ),
            },
        ),
        "adapterProofs": _field_evidence(
            name="adapterProofs",
            values_by_source={
                "fundingPlan.simulateExecuteInput.adapterProofs": (
                    simulate.adapterProofs if simulate is not None else None
                ),
                "fundingPlan.prepareExecuteInput.adapterProofs": (
                    prepare.adapterProofs if prepare is not None else None
                ),
            },
        ),
        "extensions": _field_evidence(
            name="extensions",
            values_by_source={
                "fundingPlan.simulateExecuteInput.extensions": (
                    simulate.extensions if simulate is not None else None
                ),
                "fundingPlan.prepareExecuteInput.extensions": (
                    prepare.extensions if prepare is not None else None
                ),
            },
        ),
    }
    gaps: list[str] = []
    if field_evidence["payloadBinding"]["canonicalValue"] != "actionsDigest":
        gaps.append("payloadBinding must be actionsDigest for local replay-safe verification")
    for name, evidence in field_evidence.items():
        if not evidence["sufficient"]:
            gaps.append(f"runtime binding field {name} is missing or inconsistent")
    return field_evidence, gaps


def _runtime_field_evidence_from_plan_error(error_text: str) -> tuple[dict[str, Any], list[str]]:
    if "Field required" not in error_text and "[type=missing" not in error_text:
        return {}, []

    field_evidence: dict[str, Any] = {}
    gaps: list[str] = []
    for field in REQUIRED_RUNTIME_FIELD_SET:
        missing_sources = [
            source_path
            for source_path in field["sourcePaths"]
            if source_path.removeprefix("fundingPlan.") in error_text
        ]
        if not missing_sources:
            continue
        field_evidence[field["name"]] = {
            "name": field["name"],
            "sourcePaths": field["sourcePaths"],
            "values": {},
            "missingSources": missing_sources,
            "presentInAllSources": False,
            "consistent": False,
            "canonicalValue": None,
            "sufficient": False,
        }
        gaps.append(f"runtime binding field {field['name']} is missing or inconsistent")
    return field_evidence, gaps


def _session_transition_evidence(
    *,
    created_result: AssetTransferResult,
    initial_session: FundAndActionExecutionSession,
    applied_session: FundAndActionExecutionSession,
    next_step: FundAndActionSessionNextStepResult | None,
    funding_plan: AssetTransferPlanWithContextResult,
) -> tuple[dict[str, Any], list[str]]:
    funding_result = applied_session.fundingStep.result
    evidence = {
        "initialSessionStatus": initial_session.status,
        "initialCurrentStep": initial_session.currentStep,
        "appliedSessionStatus": applied_session.status,
        "appliedCurrentStep": applied_session.currentStep,
        "appliedFundingStepStatus": applied_session.fundingStep.status,
        "appliedFundingResultStatus": funding_result.status if funding_result is not None else None,
        "appliedFundingTxHash": funding_result.txHash if funding_result is not None else None,
        "appliedFollowUpStepStatus": applied_session.followUpStep.status,
        "nextTaskKind": next_step.task.kind if next_step is not None else None,
        "createdAssetTransferResultStatus": created_result.status,
        "createdAssetTransferResultTxHash": created_result.txHash,
        "createdAssetTransferConfirmations": (
            created_result.receipt.confirmations if created_result.receipt is not None else None
        ),
        "createdAssetTransferPlanTokenMatchesFundingPlan": (
            str(created_result.plan.humanReadableSummary.tokenAddress).lower()
            == str(funding_plan.humanReadableSummary.tokenAddress).lower()
        ),
        "createdAssetTransferPlanRecipientMatchesFundingPlan": (
            str(created_result.plan.humanReadableSummary.to).lower()
            == str(funding_plan.humanReadableSummary.to).lower()
        ),
        "createdAssetTransferPlanAmountMatchesFundingPlan": (
            str(created_result.plan.humanReadableSummary.amountRaw)
            == str(funding_plan.humanReadableSummary.amountRaw)
        ),
    }
    gaps: list[str] = []
    if initial_session.status != "pendingFunding":
        gaps.append("initial session status must be pendingFunding")
    if initial_session.currentStep != "fundTargetAccount":
        gaps.append("initial session currentStep must be fundTargetAccount")
    if created_result.status != "confirmed":
        gaps.append("created assetTransferResult status must be confirmed")
    if evidence["createdAssetTransferConfirmations"] is None:
        gaps.append("created assetTransferResult receipt.confirmations is missing")
    if applied_session.status != "pendingFollowUp":
        gaps.append("fundingConfirmed event did not transition session to pendingFollowUp")
    if applied_session.currentStep != "followUpAction":
        gaps.append("fundingConfirmed event did not transition currentStep to followUpAction")
    if applied_session.fundingStep.status != "succeeded":
        gaps.append("applied session fundingStep.status must be succeeded")
    if funding_result is None or funding_result.status != "confirmed":
        gaps.append("applied session fundingStep.result must be confirmed")
    if funding_result is not None and funding_result.txHash != created_result.txHash:
        gaps.append("applied session fundingStep.result txHash does not match created assetTransferResult")
    if applied_session.followUpStep.status != "pending":
        gaps.append("applied session followUpStep.status must remain pending")
    if next_step is None:
        gaps.append("next-step check after fundingConfirmed is unavailable")
    elif next_step.task.kind != "submitFollowUp":
        gaps.append("next-step after fundingConfirmed must be submitFollowUp")
    if not evidence["createdAssetTransferPlanTokenMatchesFundingPlan"]:
        gaps.append("created assetTransferResult plan tokenAddress does not match funding plan")
    if not evidence["createdAssetTransferPlanRecipientMatchesFundingPlan"]:
        gaps.append("created assetTransferResult plan recipient does not match funding plan")
    if not evidence["createdAssetTransferPlanAmountMatchesFundingPlan"]:
        gaps.append("created assetTransferResult plan amountRaw does not match funding plan")
    return evidence, gaps


def _base_evidence(recipient_address: str | None, executor_address: str | None) -> dict[str, Any]:
    return {
        "availableTools": [],
        "mcpRuntimeReady": False,
        "assetTransferResultCreateAvailable": False,
        "sessionApplyEventAvailable": False,
        "sessionNextStepAvailable": False,
        "recipientAddress": recipient_address,
        "executorAddress": executor_address,
        "fundingPlanPresent": False,
        "requiredRuntimeFieldSet": REQUIRED_RUNTIME_FIELD_SET,
        "requiredRuntimeFieldEvidence": {},
        "initialSessionStatus": None,
        "initialCurrentStep": None,
        "appliedSessionStatus": None,
        "appliedCurrentStep": None,
        "appliedFundingStepStatus": None,
        "appliedFundingResultStatus": None,
        "appliedFundingTxHash": None,
        "appliedFollowUpStepStatus": None,
        "nextTaskKind": None,
        "createdAssetTransferResultStatus": None,
        "createdAssetTransferResultTxHash": None,
        "createdAssetTransferConfirmations": None,
        "createdAssetTransferPlanTokenMatchesFundingPlan": False,
        "createdAssetTransferPlanRecipientMatchesFundingPlan": False,
        "createdAssetTransferPlanAmountMatchesFundingPlan": False,
        "sessionTransitionCompatible": False,
        "bindingFieldSetSufficientForTask9": False,
        "strongEnoughForTask9": False,
        "gaps": [],
    }


async def _collect_compatibility(
    *,
    config: PredictConfig,
    chain: str,
    vault_address: str,
    token_address: str,
    authority_address: str,
    executor_address: str,
    recipient_address: str,
    amount_raw: str,
    reasons: list[str],
) -> dict[str, Any]:
    bridge = MandatedVaultMcpBridge(config)
    evidence = _base_evidence(recipient_address, executor_address)
    try:
        await bridge.connect()
        evidence["availableTools"] = sorted(bridge.available_tools)
        evidence["mcpRuntimeReady"] = bridge.runtime_ready
        evidence["assetTransferResultCreateAvailable"] = (
            "vault_asset_transfer_result_create" in bridge.available_tools
        )
        evidence["sessionApplyEventAvailable"] = (
            "agent_fund_and_action_session_apply_event" in bridge.available_tools
        )
        evidence["sessionNextStepAvailable"] = (
            "agent_fund_and_action_session_next_step" in bridge.available_tools
        )
        for tool_name, reason in {
            "vault_asset_transfer_result_create": "MCP runtime does not expose vault_asset_transfer_result_create",
            "agent_fund_and_action_session_apply_event": (
                "MCP runtime does not expose agent_fund_and_action_session_apply_event"
            ),
            "agent_fund_and_action_session_next_step": (
                "MCP runtime does not expose agent_fund_and_action_session_next_step"
            ),
        }.items():
            if tool_name not in bridge.available_tools:
                _append_unique(reasons, reason)

        account_context = await bridge.create_agent_account_context(
            agent_id=f"predict-account:{recipient_address.lower()}",
            vault=vault_address,
            authority=authority_address,
            executor=executor_address,
            asset_registry_ref=f"predict/{token_address.lower()}",
            funding_policy_ref=f"session-event-compatibility:{recipient_address.lower()}",
            defaults={
                "allowedAdaptersRoot": DEFAULT_ALLOWED_ADAPTERS_ROOT,
                "maxDrawdownBps": "100",
                "maxCumulativeDrawdownBps": "200",
                "payloadBinding": "actionsDigest",
                "extensions": DEFAULT_EXTENSIONS,
            },
            created_at=DEFAULT_CREATED_AT,
            updated_at=DEFAULT_UPDATED_AT,
        )
        funding_policy = await bridge.create_agent_funding_policy(
            policy_id=f"session-event-compatibility:{recipient_address.lower()}",
            allowed_token_addresses=[token_address],
            allowed_recipients=[recipient_address],
            max_amount_per_tx=amount_raw,
            max_amount_per_window=amount_raw,
            window_seconds=3600,
            expires_at="2099-01-01T00:00:00Z",
            repeatable=True,
            created_at=DEFAULT_CREATED_AT,
            updated_at=DEFAULT_UPDATED_AT,
        )
        try:
            plan = await bridge.build_agent_fund_and_action_plan(
                account_context=account_context.accountContext.model_dump(by_alias=True),
                funding_policy=funding_policy.fundingPolicy.model_dump(by_alias=True),
                funding_target={
                    "label": "predict-account-funding",
                    "recipient": recipient_address,
                    "tokenAddress": token_address,
                    "requiredAmountRaw": amount_raw,
                    "currentBalanceRaw": "0",
                    "balanceSnapshot": {
                        "snapshotAt": DEFAULT_CREATED_AT,
                        "maxStalenessSeconds": 60,
                        "source": "session-event-compatibility-poc",
                    },
                    "fundingShortfallRaw": amount_raw,
                },
                funding_context={
                    "reason": "autonomous-preflight-session-event-compatibility",
                    "chain": chain,
                },
                follow_up_action={
                    "kind": "predict.createOrder",
                    "target": "order/session-event-compatibility",
                    "payload": {
                        "marketId": "session-event-compatibility",
                        "collateralTokenAddress": token_address,
                        "collateralAmountRaw": amount_raw,
                        "orderSide": "buy",
                        "outcomeId": "yes",
                        "clientOrderId": "session-event-compatibility",
                    },
                },
            )
        except Exception as error:
            binding_evidence, binding_gaps = _runtime_field_evidence_from_plan_error(str(error))
            if not binding_gaps:
                raise
            evidence["requiredRuntimeFieldEvidence"] = binding_evidence
            evidence["bindingFieldSetSufficientForTask9"] = False
            for gap in binding_gaps:
                _append_unique(reasons, gap)
            return evidence
        funding_plan = plan.fundingPlan
        evidence["fundingPlanPresent"] = funding_plan is not None
        if funding_plan is None:
            _append_unique(reasons, "fund-and-action plan did not include a fundingPlan")
            return evidence

        session_created = await bridge.create_agent_fund_and_action_session(
            fund_and_action_plan=plan.model_dump(by_alias=True),
            session_id="session-event-compatibility-poc",
            created_at=DEFAULT_CREATED_AT,
        )
        created_transfer = await bridge.create_vault_asset_transfer_result(
            asset_transfer_plan=funding_plan.model_dump(by_alias=True),
            status="confirmed",
            updated_at=DEFAULT_UPDATED_AT,
            submitted_at="2026-03-10T00:04:00Z",
            completed_at=DEFAULT_UPDATED_AT,
            attempt=1,
            chain_id=int(chain),
            tx_hash="0x" + "ef" * 32,
            receipt={
                "blockNumber": "123",
                "blockHash": "0x" + "ab" * 32,
                "confirmations": 2,
            },
            output={"status": "ok"},
        )
        applied = await bridge.apply_agent_fund_and_action_session_event(
            session=session_created.session.model_dump(by_alias=True),
            event={
                "type": "fundingConfirmed",
                "updatedAt": DEFAULT_UPDATED_AT,
                "assetTransferResult": created_transfer.assetTransferResult.model_dump(by_alias=True),
            },
        )
        next_step = None
        if evidence["sessionNextStepAvailable"]:
            next_step = await bridge.next_agent_fund_and_action_session_step(
                session=applied.session.model_dump(by_alias=True)
            )

        binding_evidence, binding_gaps = _required_runtime_field_evidence(funding_plan)
        transition_evidence, transition_gaps = _session_transition_evidence(
            created_result=created_transfer.assetTransferResult,
            initial_session=session_created.session,
            applied_session=applied.session,
            next_step=next_step,
            funding_plan=funding_plan,
        )
        evidence["requiredRuntimeFieldEvidence"] = binding_evidence
        evidence.update(transition_evidence)
        evidence["sessionTransitionCompatible"] = not transition_gaps
        evidence["bindingFieldSetSufficientForTask9"] = not binding_gaps
        evidence["strongEnoughForTask9"] = (
            evidence["mcpRuntimeReady"]
            and evidence["sessionTransitionCompatible"]
            and evidence["bindingFieldSetSufficientForTask9"]
            and evidence["assetTransferResultCreateAvailable"]
            and evidence["sessionApplyEventAvailable"]
            and evidence["sessionNextStepAvailable"]
        )
        for gap in [*binding_gaps, *transition_gaps]:
            _append_unique(reasons, gap)
    except Exception as error:
        _append_unique(reasons, f"unable to evaluate session-event compatibility: {error}")
    finally:
        evidence["gaps"] = list(reasons)
        try:
            await bridge.close()
        except Exception:
            pass
    return evidence


def run_session_event_compatibility_poc(env: Mapping[str, str] | None = None) -> dict[str, Any]:
    source = env or os.environ
    reasons: list[str] = []
    wallet_mode = _value(source, "PREDICT_WALLET_MODE")
    chain = _value(source, "ERC_MANDATED_CHAIN_ID") or _value(source, "PREDICT_ENV")
    vault_address = _value(source, "ERC_MANDATED_VAULT_ADDRESS")
    token_address = _value(source, "ERC_MANDATED_VAULT_ASSET_ADDRESS")
    authority_private_key = _value(source, "ERC_MANDATED_AUTHORITY_PRIVATE_KEY")
    explicit_executor_key = _value(source, "ERC_MANDATED_EXECUTOR_PRIVATE_KEY")
    authority_address = _value(source, "ERC_MANDATED_VAULT_AUTHORITY") or _derive_address(
        authority_private_key,
        label="ERC_MANDATED_AUTHORITY_PRIVATE_KEY",
        reasons=reasons,
    )
    executor_address = _derive_address(
        explicit_executor_key or authority_private_key,
        label="ERC_MANDATED_EXECUTOR_PRIVATE_KEY",
        reasons=reasons,
    )
    recipient_address = _value(source, "PREDICT_ACCOUNT_ADDRESS") or _value(
        source, "PREDICT_SESSION_EVENT_POC_RECIPIENT_ADDRESS"
    )
    amount_raw = _uint_string(
        source,
        "PREDICT_SESSION_EVENT_POC_AMOUNT_RAW",
        default=DEFAULT_AMOUNT_RAW,
    )

    if wallet_mode != "mandated-vault":
        _append_unique(
            reasons,
            "PREDICT_WALLET_MODE must be mandated-vault for the session-event compatibility PoC",
        )
    for label, value in {
        "chain": chain,
        "vaultAddress": vault_address,
        "tokenAddress": token_address,
        "authorityAddress": authority_address,
        "executorAddress": executor_address,
        "predictAccountAddress": recipient_address,
    }.items():
        if value is None:
            _append_unique(reasons, f"missing {label}")
    for label, value in {
        "vaultAddress": vault_address,
        "tokenAddress": token_address,
        "authorityAddress": authority_address,
        "executorAddress": executor_address,
        "predictAccountAddress": recipient_address,
    }.items():
        if value is not None and not ADDRESS_RE.fullmatch(value):
            _append_unique(reasons, f"invalid {label}: {value}")

    config = _load_config(source, reasons)
    if config is not None and chain is None:
        chain = str(config.mandated_chain_id or int(config.chain_id))
    if chain is not None and not chain.isdigit():
        _append_unique(reasons, f"invalid chain: {chain}")

    evidence = _base_evidence(recipient_address, executor_address)
    blocking_reasons = [
        reason for reason in reasons if reason.startswith("missing ") or reason.startswith("invalid ")
    ]
    if (
        config is not None
        and chain is not None
        and vault_address is not None
        and token_address is not None
        and authority_address is not None
        and executor_address is not None
        and recipient_address is not None
        and not blocking_reasons
    ):
        evidence = asyncio.run(
            _collect_compatibility(
                config=config,
                chain=chain,
                vault_address=vault_address,
                token_address=token_address,
                authority_address=authority_address,
                executor_address=executor_address,
                recipient_address=recipient_address,
                amount_raw=amount_raw,
                reasons=reasons,
            )
        )
    evidence["gaps"] = list(reasons)
    strong_enough = bool(evidence.get("strongEnoughForTask9")) and not reasons
    artifact = {
        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "verdict": "PASS" if strong_enough else "NO-GO",
        "chain": chain,
        "vaultAddress": vault_address,
        "tokenAddress": token_address,
        "predictAccountAddress": recipient_address,
        "sessionEventCompatibilityEvidence": evidence,
        "reasons": reasons,
    }
    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT_PATH.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    return artifact


def main() -> int:
    try:
        artifact = run_session_event_compatibility_poc()
    except Exception as error:  # pragma: no cover - hard fail-safe path
        artifact = {
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "verdict": "NO-GO",
            "chain": None,
            "vaultAddress": None,
            "tokenAddress": None,
            "predictAccountAddress": None,
            "sessionEventCompatibilityEvidence": {
                **_base_evidence(None, None),
                "gaps": [f"unexpected-error: {error}"],
            },
            "reasons": [f"unexpected-error: {error}"],
        }
        ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
        ARTIFACT_PATH.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    return 0 if artifact["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())