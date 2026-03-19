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

from eth_account import Account
from eth_account.messages import encode_typed_data

from lib.config import ConfigError, PredictConfig
from lib.mandated_mcp_bridge import MandatedVaultMcpBridge

ARTIFACT_PATH = (
    SKILL_DIR
    / "artifacts"
    / "reports"
    / "autonomous-preflight"
    / "single-key-permissions.json"
)
ADDRESS_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")
HEX32_RE = re.compile(r"^0x[a-fA-F0-9]{64}$")
UINT_RE = re.compile(r"^[0-9]+$")
DEFAULT_ALLOWED_ADAPTERS_ROOT = "0x" + "11" * 32
DEFAULT_CREATED_AT = "2026-03-10T00:00:00Z"
DEFAULT_UPDATED_AT = "2026-03-10T00:05:00Z"


def _value(source: Mapping[str, str], name: str) -> str | None:
    raw = source.get(name)
    if raw is None:
        return None
    value = raw.strip()
    return value or None


def _append_unique(reasons: list[str], reason: str) -> None:
    if reason not in reasons:
        reasons.append(reason)


def _derive_address(private_key: str | None, *, label: str, reasons: list[str]) -> str | None:
    if private_key is None:
        _append_unique(reasons, f"missing {label}")
        return None
    try:
        return Account.from_key(private_key).address
    except Exception as error:
        _append_unique(reasons, f"invalid {label}: {error}")
        return None


def _uint_string(
    source: Mapping[str, str],
    name: str,
    *,
    default: str,
    reasons: list[str],
) -> str:
    value = _value(source, name) or default
    if not UINT_RE.fullmatch(value):
        _append_unique(reasons, f"{name} must be an unsigned integer string")
        return default
    return value


def _adapter_proofs(
    source: Mapping[str, str],
    *,
    allowed_adapters_root: str,
    reasons: list[str],
) -> list[list[str]]:
    raw = _value(source, "PREDICT_SINGLE_KEY_POC_ADAPTER_PROOFS_JSON")
    if raw is None:
        return [[allowed_adapters_root]]
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        _append_unique(reasons, f"invalid PREDICT_SINGLE_KEY_POC_ADAPTER_PROOFS_JSON: {error.msg}")
        return [[allowed_adapters_root]]
    if not isinstance(payload, list):
        _append_unique(reasons, "PREDICT_SINGLE_KEY_POC_ADAPTER_PROOFS_JSON must be a list")
        return [[allowed_adapters_root]]
    normalized: list[list[str]] = []
    for group in payload:
        if not isinstance(group, list):
            _append_unique(
                reasons,
                "PREDICT_SINGLE_KEY_POC_ADAPTER_PROOFS_JSON entries must be lists",
            )
            return [[allowed_adapters_root]]
        normalized_group: list[str] = []
        for proof in group:
            if not isinstance(proof, str) or not HEX32_RE.fullmatch(proof):
                _append_unique(reasons, "adapter proofs must be 32-byte hex strings")
                return [[allowed_adapters_root]]
            normalized_group.append(proof)
        normalized.append(normalized_group)
    return normalized


async def _run_bridge_checks(
    *,
    config: PredictConfig,
    source: Mapping[str, str],
    vault_address: str,
    token_address: str,
    authority_address: str,
    configured_executor_address: str,
    evidence: dict[str, Any],
    reasons: list[str],
) -> None:
    allowed_adapters_root = (
        _value(source, "PREDICT_SINGLE_KEY_POC_ALLOWED_ADAPTERS_ROOT")
        or DEFAULT_ALLOWED_ADAPTERS_ROOT
    )
    if not HEX32_RE.fullmatch(allowed_adapters_root):
        _append_unique(
            reasons,
            "PREDICT_SINGLE_KEY_POC_ALLOWED_ADAPTERS_ROOT must be a 32-byte hex string",
        )
        allowed_adapters_root = DEFAULT_ALLOWED_ADAPTERS_ROOT
    payload_binding = _value(source, "PREDICT_SINGLE_KEY_POC_PAYLOAD_BINDING") or "actionsDigest"
    if payload_binding not in {"actionsDigest", "none"}:
        _append_unique(
            reasons,
            "PREDICT_SINGLE_KEY_POC_PAYLOAD_BINDING must be actionsDigest or none",
        )
        payload_binding = "actionsDigest"
    amount_raw = _uint_string(source, "PREDICT_SINGLE_KEY_POC_AMOUNT_RAW", default="1", reasons=reasons)
    nonce = _uint_string(source, "PREDICT_SINGLE_KEY_POC_NONCE", default="1", reasons=reasons)
    deadline = _uint_string(
        source,
        "PREDICT_SINGLE_KEY_POC_DEADLINE",
        default="9999999999",
        reasons=reasons,
    )
    max_drawdown_bps = _uint_string(
        source,
        "PREDICT_SINGLE_KEY_POC_MAX_DRAWDOWN_BPS",
        default="100",
        reasons=reasons,
    )
    max_cumulative_drawdown_bps = _uint_string(
        source,
        "PREDICT_SINGLE_KEY_POC_MAX_CUMULATIVE_DRAWDOWN_BPS",
        default="200",
        reasons=reasons,
    )
    extensions = _value(source, "PREDICT_SINGLE_KEY_POC_EXTENSIONS") or "0x"
    recipient = _value(source, "PREDICT_SINGLE_KEY_POC_RECIPIENT") or authority_address
    if not ADDRESS_RE.fullmatch(recipient):
        _append_unique(reasons, f"invalid recipient: {recipient}")
    adapter_proofs = _adapter_proofs(
        source,
        allowed_adapters_root=allowed_adapters_root,
        reasons=reasons,
    )

    policy_id = f"single-key-poc:{authority_address.lower()}"
    chain_value = str(config.mandated_chain_id or int(config.chain_id))
    bridge = MandatedVaultMcpBridge(config)
    await bridge.connect()
    evidence["availableTools"] = sorted(bridge.available_tools)
    evidence["mcpRuntimeReady"] = bridge.runtime_ready
    try:
        health = await bridge.health_check(vault_address)
        evidence["healthCheckAuthority"] = health.mandateAuthority
        evidence["authorityEpoch"] = health.authorityEpoch
        evidence["vaultHealthAuthorityMatchesAuthorityKey"] = (
            health.mandateAuthority.lower() == authority_address.lower()
        )
        if not evidence["vaultHealthAuthorityMatchesAuthorityKey"]:
            _append_unique(reasons, "vault mandateAuthority does not match authority key")

        account_context_result = await bridge.create_agent_account_context(
            agent_id="single-key-permissions-poc",
            vault=vault_address,
            authority=authority_address,
            executor=configured_executor_address,
            asset_registry_ref=f"poc/{token_address.lower()}",
            funding_policy_ref=policy_id,
            defaults={
                "allowedAdaptersRoot": allowed_adapters_root,
                "maxDrawdownBps": max_drawdown_bps,
                "maxCumulativeDrawdownBps": max_cumulative_drawdown_bps,
                "payloadBinding": payload_binding,
                "extensions": extensions,
            },
            created_at=DEFAULT_CREATED_AT,
            updated_at=DEFAULT_UPDATED_AT,
        )
        funding_policy_result = await bridge.create_agent_funding_policy(
            policy_id=policy_id,
            allowed_token_addresses=[token_address],
            allowed_recipients=[recipient],
            max_amount_per_tx=amount_raw,
            max_amount_per_window=amount_raw,
            window_seconds=3600,
            expires_at="2099-01-01T00:00:00Z",
            repeatable=True,
            created_at=DEFAULT_CREATED_AT,
            updated_at=DEFAULT_UPDATED_AT,
        )

        account_context = account_context_result.accountContext
        funding_policy = funding_policy_result.fundingPolicy
        evidence["accountContextExecutor"] = account_context.executor
        evidence["accountContextExecutorMatchesAuthorityKey"] = (
            account_context.executor.lower() == authority_address.lower()
        )
        evidence["accountContextExecutorMatchesConfiguredExecutor"] = (
            account_context.executor.lower() == configured_executor_address.lower()
        )
        if not evidence["accountContextExecutorMatchesAuthorityKey"]:
            _append_unique(reasons, "account context executor does not match authority key")

        plan = await bridge.build_vault_asset_transfer_plan_from_context(
            account_context=account_context.model_dump(by_alias=True),
            funding_policy=funding_policy.model_dump(by_alias=True),
            token_address=token_address,
            to=recipient,
            amount_raw=amount_raw,
            nonce=nonce,
            deadline=deadline,
            authority_epoch=health.authorityEpoch,
            allowed_adapters_root=allowed_adapters_root,
            max_drawdown_bps=max_drawdown_bps,
            max_cumulative_drawdown_bps=max_cumulative_drawdown_bps,
            payload_binding=payload_binding,
            extensions=extensions,
        )
        evidence["signRequestPresent"] = True
        evidence["mandateExecutor"] = plan.signRequest.mandate.executor
        evidence["mandateExecutorMatchesAuthorityKey"] = (
            plan.signRequest.mandate.executor.lower() == authority_address.lower()
        )
        if not evidence["mandateExecutorMatchesAuthorityKey"]:
            _append_unique(reasons, "signRequest mandate.executor does not match authority key")

        signed = Account.from_key(config.mandated_authority_private_key_value).sign_typed_data(
            full_message=plan.signRequest.typedData
        )
        recovered = Account.recover_message(
            encode_typed_data(full_message=plan.signRequest.typedData),
            signature=signed.signature,
        )
        signature_hex = "0x" + signed.signature.hex()
        evidence["typedDataSigned"] = True
        evidence["recoveredSignerAddress"] = recovered
        evidence["recoveredSignerMatchesAuthorityKey"] = (
            recovered.lower() == authority_address.lower()
        )
        if not evidence["recoveredSignerMatchesAuthorityKey"]:
            _append_unique(reasons, "typed-data signature does not recover the authority key")

        simulated = await bridge.simulate_vault_asset_transfer_from_context(
            account_context=account_context.model_dump(by_alias=True),
            funding_policy=funding_policy.model_dump(by_alias=True),
            from_address=configured_executor_address,
            token_address=token_address,
            to=recipient,
            amount_raw=amount_raw,
            nonce=nonce,
            deadline=deadline,
            authority_epoch=health.authorityEpoch,
            signature=signature_hex,
            adapter_proofs=adapter_proofs,
            allowed_adapters_root=allowed_adapters_root,
            max_drawdown_bps=max_drawdown_bps,
            max_cumulative_drawdown_bps=max_cumulative_drawdown_bps,
            payload_binding=payload_binding,
            extensions=extensions,
        )
        evidence["simulateOk"] = simulated.simulate.ok
        if not simulated.simulate.ok:
            _append_unique(reasons, "simulate execute path did not report ok=true")

        prepared = await bridge.prepare_vault_asset_transfer_from_context(
            account_context=account_context.model_dump(by_alias=True),
            funding_policy=funding_policy.model_dump(by_alias=True),
            from_address=configured_executor_address,
            token_address=token_address,
            to=recipient,
            amount_raw=amount_raw,
            nonce=nonce,
            deadline=deadline,
            authority_epoch=health.authorityEpoch,
            signature=signature_hex,
            adapter_proofs=adapter_proofs,
            allowed_adapters_root=allowed_adapters_root,
            max_drawdown_bps=max_drawdown_bps,
            max_cumulative_drawdown_bps=max_cumulative_drawdown_bps,
            payload_binding=payload_binding,
            extensions=extensions,
        )
        evidence["preparedTxExists"] = True
        evidence["preparedTxFrom"] = prepared.txRequest.from_address
        evidence["preparedTxTo"] = prepared.txRequest.to
        evidence["preparedTxFromMatchesAuthorityKey"] = (
            prepared.txRequest.from_address.lower() == authority_address.lower()
        )
        evidence["preparedTxFromMatchesConfiguredExecutor"] = (
            prepared.txRequest.from_address.lower() == configured_executor_address.lower()
        )
        evidence["preparedTxTargetsVault"] = (
            prepared.txRequest.to.lower() == vault_address.lower()
        )
        if not evidence["preparedTxFromMatchesAuthorityKey"]:
            _append_unique(reasons, "prepared txRequest.from does not match authority key")
        if not evidence["preparedTxTargetsVault"]:
            _append_unique(reasons, "prepared txRequest.to does not match vaultAddress")

        evidence["chainId"] = chain_value
    finally:
        await bridge.close()


def _base_evidence(executor_key_source: str | None) -> dict[str, Any]:
    return {
        "configuredExecutorKeySource": executor_key_source,
        "configuredSingleKey": False,
        "availableTools": [],
        "mcpRuntimeReady": False,
        "healthCheckAuthority": None,
        "vaultHealthAuthorityMatchesAuthorityKey": False,
        "authorityEpoch": None,
        "accountContextExecutor": None,
        "accountContextExecutorMatchesAuthorityKey": False,
        "accountContextExecutorMatchesConfiguredExecutor": False,
        "signRequestPresent": False,
        "mandateExecutor": None,
        "mandateExecutorMatchesAuthorityKey": False,
        "typedDataSigned": False,
        "recoveredSignerAddress": None,
        "recoveredSignerMatchesAuthorityKey": False,
        "simulateOk": False,
        "preparedTxExists": False,
        "preparedTxFrom": None,
        "preparedTxTo": None,
        "preparedTxFromMatchesAuthorityKey": False,
        "preparedTxFromMatchesConfiguredExecutor": False,
        "preparedTxTargetsVault": False,
        "sameKeySatisfiesAuthorityAndExecutor": False,
        "gaps": [],
    }


def run_single_key_permission_poc(env: Mapping[str, str] | None = None) -> dict[str, Any]:
    source = env or os.environ
    reasons: list[str] = []
    wallet_mode = _value(source, "PREDICT_WALLET_MODE")
    vault_address = _value(source, "ERC_MANDATED_VAULT_ADDRESS")
    token_address = _value(source, "PREDICT_SINGLE_KEY_POC_TOKEN_ADDRESS") or _value(
        source, "ERC_MANDATED_VAULT_ASSET_ADDRESS"
    )
    chain = _value(source, "ERC_MANDATED_CHAIN_ID") or _value(source, "PREDICT_ENV")
    authority_private_key = _value(source, "ERC_MANDATED_AUTHORITY_PRIVATE_KEY")
    explicit_executor_key = _value(source, "ERC_MANDATED_EXECUTOR_PRIVATE_KEY")
    executor_key_source = (
        "explicit"
        if explicit_executor_key is not None
        else "authority-fallback"
        if authority_private_key is not None
        else None
    )
    evidence = _base_evidence(executor_key_source)

    if wallet_mode != "mandated-vault":
        _append_unique(reasons, "PREDICT_WALLET_MODE must be mandated-vault for the single-key permission PoC")
    if chain is None:
        _append_unique(reasons, "missing chain")
    if vault_address is None:
        _append_unique(reasons, "missing vaultAddress")
    if token_address is None:
        _append_unique(reasons, "missing tokenAddress")
    for label, value in {
        "vaultAddress": vault_address,
        "tokenAddress": token_address,
    }.items():
        if value is not None and not ADDRESS_RE.fullmatch(value):
            _append_unique(reasons, f"invalid {label}: {value}")

    authority_address = _derive_address(
        authority_private_key,
        label="ERC_MANDATED_AUTHORITY_PRIVATE_KEY",
        reasons=reasons,
    )
    configured_executor_address = _derive_address(
        explicit_executor_key or authority_private_key,
        label="ERC_MANDATED_EXECUTOR_PRIVATE_KEY",
        reasons=reasons,
    )

    configured_single_key = bool(
        authority_address
        and configured_executor_address
        and authority_address.lower() == configured_executor_address.lower()
    )
    evidence["configuredSingleKey"] = configured_single_key
    if authority_address and configured_executor_address and not configured_single_key:
        _append_unique(reasons, "configured executor key does not match authority key")

    config: PredictConfig | None = None
    config_source = dict(source)
    if vault_address is not None:
        for env_name in (
            "ERC_MANDATED_FACTORY_ADDRESS",
            "ERC_MANDATED_VAULT_ASSET_ADDRESS",
            "ERC_MANDATED_VAULT_NAME",
            "ERC_MANDATED_VAULT_SYMBOL",
            "ERC_MANDATED_VAULT_AUTHORITY",
            "ERC_MANDATED_VAULT_SALT",
        ):
            config_source.pop(env_name, None)
    try:
        config = PredictConfig.from_env(config_source)
        if chain is None:
            chain = str(config.mandated_chain_id or int(config.chain_id))
    except ConfigError as error:
        _append_unique(reasons, str(error))

    if (
        config is not None
        and vault_address is not None
        and token_address is not None
        and authority_address is not None
        and configured_executor_address is not None
        and not reasons
    ):
        try:
            asyncio.run(
                _run_bridge_checks(
                    config=config,
                    source=source,
                    vault_address=vault_address,
                    token_address=token_address,
                    authority_address=authority_address,
                    configured_executor_address=configured_executor_address,
                    evidence=evidence,
                    reasons=reasons,
                )
            )
        except Exception as error:
            _append_unique(reasons, f"single-key permission MCP validation failed: {error}")

    evidence["gaps"] = list(reasons)
    evidence["sameKeySatisfiesAuthorityAndExecutor"] = bool(
        configured_single_key
        and evidence["vaultHealthAuthorityMatchesAuthorityKey"]
        and evidence["accountContextExecutorMatchesAuthorityKey"]
        and evidence["mandateExecutorMatchesAuthorityKey"]
        and evidence["typedDataSigned"]
        and evidence["recoveredSignerMatchesAuthorityKey"]
        and evidence["simulateOk"]
        and evidence["preparedTxExists"]
        and evidence["preparedTxFromMatchesAuthorityKey"]
        and evidence["preparedTxTargetsVault"]
        and not reasons
    )

    artifact = {
        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "verdict": "PASS" if evidence["sameKeySatisfiesAuthorityAndExecutor"] else "NO-GO",
        "chain": chain,
        "vaultAddress": vault_address,
        "tokenAddress": token_address,
        "authorityAddress": authority_address,
        "executorAddress": configured_executor_address,
        "singleKeyAddress": authority_address if configured_single_key else None,
        "singleKeyPermissionEvidence": evidence,
        "reasons": reasons,
    }
    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT_PATH.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    return artifact


def main() -> int:
    try:
        artifact = run_single_key_permission_poc()
    except Exception as error:  # pragma: no cover - hard fail-safe path
        artifact = {
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "verdict": "NO-GO",
            "chain": None,
            "vaultAddress": None,
            "tokenAddress": None,
            "authorityAddress": None,
            "executorAddress": None,
            "singleKeyAddress": None,
            "singleKeyPermissionEvidence": {
                **_base_evidence(None),
                "gaps": [f"unexpected-error: {error}"],
            },
            "reasons": [f"unexpected-error: {error}"],
        }
        ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
        ARTIFACT_PATH.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    return 0 if artifact["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())