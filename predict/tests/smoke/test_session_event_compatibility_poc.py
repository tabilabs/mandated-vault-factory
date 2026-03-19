from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from eth_account import Account

PREDICT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = PREDICT_ROOT / "scripts" / "poc_session_event_compatibility.py"
ARTIFACT_PATH = (
    PREDICT_ROOT
    / "artifacts"
    / "reports"
    / "autonomous-preflight"
    / "session-event-compatibility.json"
)
PREDICT_ACCOUNT_ADDRESS = "0x1234567890123456789012345678901234567890"
VAULT_ADDRESS = "0x2222222222222222222222222222222222222222"
TOKEN_ADDRESS = "0x4444444444444444444444444444444444444444"
AUTHORITY_PRIVATE_KEY = (
    "0x59c6995e998f97a5a0044976f4d060f5d89c8b8c7f11b9aa0dbf3f0f7c7c1e01"
)
EXECUTOR_PRIVATE_KEY = (
    "0x8b3a350cf5c34c9194ca3a545d6f7d8b2e77f4d6d2c3b4a59687766554433221"
)
AUTHORITY_ADDRESS = Account.from_key(AUTHORITY_PRIVATE_KEY).address
EXECUTOR_ADDRESS = Account.from_key(EXECUTOR_PRIVATE_KEY).address
CHAIN_ID = 8453
HEX64_A = "0x" + "aa" * 32
HEX64_B = "0x" + "bb" * 32
HEX64_C = "0x" + "cc" * 32
HEX64_D = "0x" + "dd" * 32
HEX64_E = "0x" + "ee" * 32
HEX64_F = "0x" + "ff" * 32
BLOCK_HASH = "0x" + "12" * 32
PREDICTED_VAULT = "0x6666666666666666666666666666666666666666"


def _build_account_context() -> dict[str, object]:
    return {
        "agentId": f"predict-account:{PREDICT_ACCOUNT_ADDRESS.lower()}",
        "chainId": CHAIN_ID,
        "vault": VAULT_ADDRESS,
        "authority": AUTHORITY_ADDRESS,
        "executor": EXECUTOR_ADDRESS,
        "assetRegistryRef": f"predict/{TOKEN_ADDRESS.lower()}",
        "fundingPolicyRef": f"session-event-compatibility:{PREDICT_ACCOUNT_ADDRESS.lower()}",
        "defaults": {
            "allowedAdaptersRoot": HEX64_A,
            "maxDrawdownBps": "100",
            "maxCumulativeDrawdownBps": "200",
            "payloadBinding": "actionsDigest",
            "extensions": "0x",
        },
        "createdAt": "2026-03-10T00:00:00Z",
        "updatedAt": "2026-03-10T00:05:00Z",
    }


def _build_funding_policy() -> dict[str, object]:
    return {
        "policyId": f"session-event-compatibility:{PREDICT_ACCOUNT_ADDRESS.lower()}",
        "allowedTokenAddresses": [TOKEN_ADDRESS],
        "allowedRecipients": [PREDICT_ACCOUNT_ADDRESS],
        "maxAmountPerTx": "800",
        "maxAmountPerWindow": "800",
        "windowSeconds": 3600,
        "expiresAt": "2099-01-01T00:00:00Z",
        "repeatable": True,
        "createdAt": "2026-03-10T00:00:00Z",
        "updatedAt": "2026-03-10T00:05:00Z",
    }


def _build_sign_request() -> dict[str, object]:
    return {
        "typedData": {"domain": {"name": "Mandated", "chainId": CHAIN_ID}},
        "mandate": {
            "vault": VAULT_ADDRESS,
            "executor": EXECUTOR_ADDRESS,
            "nonce": "7",
            "deadline": "9999999999",
            "authorityEpoch": "2",
            "allowedAdaptersRoot": HEX64_A,
            "maxDrawdownBps": "100",
            "maxCumulativeDrawdownBps": "200",
            "payloadDigest": HEX64_B,
            "extensionsHash": HEX64_C,
        },
        "mandateHash": HEX64_D,
        "actionsDigest": HEX64_E,
        "extensionsHash": HEX64_C,
    }


def _build_funding_plan() -> dict[str, object]:
    return {
        "accountContext": _build_account_context(),
        "action": {"type": "erc20Transfer", "to": PREDICT_ACCOUNT_ADDRESS},
        "erc20Call": {
            "tokenAddress": TOKEN_ADDRESS,
            "to": PREDICT_ACCOUNT_ADDRESS,
            "amountRaw": "800",
        },
        "humanReadableSummary": {
            "kind": "erc20Transfer",
            "tokenAddress": TOKEN_ADDRESS,
            "to": PREDICT_ACCOUNT_ADDRESS,
            "amountRaw": "800",
            "symbol": "USDC",
            "decimals": 6,
        },
        "signRequest": _build_sign_request(),
        "policyCheck": {
            "allowed": True,
            "fundingPolicy": _build_funding_policy(),
            "violations": [],
        },
        "simulateExecuteInput": {
            "chainId": CHAIN_ID,
            "vault": VAULT_ADDRESS,
            "from": EXECUTOR_ADDRESS,
            "mandate": _build_sign_request()["mandate"],
            "signature": "0x1234",
            "actions": [{"type": "erc20Transfer"}],
            "adapterProofs": [[HEX64_A]],
            "extensions": "0x",
        },
        "prepareExecuteInput": {
            "chainId": CHAIN_ID,
            "vault": VAULT_ADDRESS,
            "from": EXECUTOR_ADDRESS,
            "mandate": _build_sign_request()["mandate"],
            "signature": "0x1234",
            "actions": [{"type": "erc20Transfer"}],
            "adapterProofs": [[HEX64_A]],
            "extensions": "0x",
        },
    }


def _build_plan(*, funding_plan: dict[str, object] | None = None) -> dict[str, object]:
    return {
        "accountContext": _build_account_context(),
        "fundingPolicy": _build_funding_policy(),
        "fundingTarget": {
            "label": "predict-account-funding",
            "recipient": PREDICT_ACCOUNT_ADDRESS,
            "tokenAddress": TOKEN_ADDRESS,
            "requiredAmountRaw": "800",
            "currentBalanceRaw": "0",
            "balanceSnapshot": {
                "snapshotAt": "2026-03-10T00:00:00Z",
                "maxStalenessSeconds": 60,
                "source": "session-event-compatibility-poc",
            },
            "fundingShortfallRaw": "800",
        },
        "evaluatedAt": "2026-03-10T00:00:00Z",
        "fundingRequired": True,
        "fundingPlan": funding_plan or _build_funding_plan(),
        "followUpAction": {
            "kind": "predict.createOrder",
            "target": "order/session-event-compatibility",
            "payload": {
                "marketId": "session-event-compatibility",
                "collateralTokenAddress": TOKEN_ADDRESS,
                "collateralAmountRaw": "800",
                "orderSide": "buy",
                "outcomeId": "yes",
                "clientOrderId": "session-event-compatibility",
            },
        },
        "followUpActionPlan": {
            "kind": "predict.createOrder",
            "target": "order/session-event-compatibility",
            "executionMode": "offchain-api",
            "summary": "Place Predict order",
            "assetRequirement": {"tokenAddress": TOKEN_ADDRESS, "amountRaw": "800"},
            "payload": {
                "marketId": "session-event-compatibility",
                "collateralTokenAddress": TOKEN_ADDRESS,
                "collateralAmountRaw": "800",
                "orderSide": "buy",
                "outcomeId": "yes",
                "clientOrderId": "session-event-compatibility",
            },
        },
        "steps": [
            {
                "kind": "fundTargetAccount",
                "status": "required",
                "summary": "Fund target account",
            },
            {
                "kind": "followUpAction",
                "status": "pending",
                "summary": "Submit follow-up action",
            },
        ],
    }


def _build_session(plan: dict[str, object]) -> dict[str, object]:
    return {
        "sessionId": "session-event-compatibility-poc",
        "status": "pendingFunding",
        "currentStep": "fundTargetAccount",
        "createdAt": "2026-03-10T00:00:00Z",
        "updatedAt": "2026-03-10T00:00:00Z",
        "fundAndActionPlan": plan,
        "fundingStep": {
            "required": True,
            "status": "pending",
            "summary": "Await funding submission",
            "updatedAt": "2026-03-10T00:00:00Z",
        },
        "followUpStep": {
            "status": "pending",
            "summary": "Await follow-up execution",
            "updatedAt": "2026-03-10T00:00:00Z",
        },
    }


def _build_asset_transfer_result(plan: dict[str, object]) -> dict[str, object]:
    return {
        "status": "confirmed",
        "summary": "Funding confirmed",
        "updatedAt": "2026-03-10T00:05:00Z",
        "submittedAt": "2026-03-10T00:04:00Z",
        "completedAt": "2026-03-10T00:05:00Z",
        "attempt": 1,
        "chainId": CHAIN_ID,
        "txHash": HEX64_F,
        "receipt": {
            "blockNumber": "123",
            "blockHash": BLOCK_HASH,
            "confirmations": 2,
        },
        "output": {"status": "ok"},
        "plan": plan["fundingPlan"],
    }


def _build_applied_session(
    plan: dict[str, object],
    asset_transfer_result: dict[str, object],
    *,
    compatible: bool = True,
) -> dict[str, object]:
    return {
        "sessionId": "session-event-compatibility-poc",
        "status": "pendingFollowUp" if compatible else "pendingFunding",
        "currentStep": "followUpAction" if compatible else "fundTargetAccount",
        "createdAt": "2026-03-10T00:00:00Z",
        "updatedAt": "2026-03-10T00:05:00Z",
        "fundAndActionPlan": plan,
        "fundingStep": {
            "required": True,
            "status": "succeeded" if compatible else "pending",
            "summary": "Funding confirmed",
            "updatedAt": "2026-03-10T00:05:00Z",
            "result": asset_transfer_result if compatible else None,
        },
        "followUpStep": {
            "status": "pending",
            "summary": "Await follow-up execution",
            "updatedAt": "2026-03-10T00:05:00Z",
        },
    }


def _build_next_step(
    session: dict[str, object], *, kind: str = "submitFollowUp"
) -> dict[str, object]:
    return {
        "session": session,
        "task": {
            "kind": kind,
            "summary": "Next overlay action",
        },
    }


def _delete_path(payload: dict[str, object], path: str) -> None:
    current: object = payload
    parts = path.split(".")
    for part in parts[:-1]:
        assert isinstance(current, dict)
        current = current[part]
    assert isinstance(current, dict)
    current.pop(parts[-1], None)


def _tool_results(
    *,
    plan: dict[str, object],
    session: dict[str, object],
    asset_transfer_result: dict[str, object],
    applied_session: dict[str, object],
    next_step: dict[str, object],
) -> dict[str, dict[str, object]]:
    return {
        "factory_predict_vault_address": {
            "structuredContent": {"result": {"predictedVault": PREDICTED_VAULT}}
        },
        "factory_create_vault_prepare": {
            "structuredContent": {
                "result": {
                    "predictedVault": PREDICTED_VAULT,
                    "txRequest": {
                        "from": AUTHORITY_ADDRESS,
                        "to": VAULT_ADDRESS,
                        "data": "0xfeedbeef",
                        "value": "0x0",
                        "gas": "210000",
                    },
                }
            }
        },
        "vault_health_check": {
            "structuredContent": {
                "result": {
                    "blockNumber": 101,
                    "vault": VAULT_ADDRESS,
                    "mandateAuthority": AUTHORITY_ADDRESS,
                    "authorityEpoch": "2",
                    "pendingAuthority": AUTHORITY_ADDRESS,
                    "nonceThreshold": "1",
                    "totalAssets": "123000000000000000000",
                }
            }
        },
        "agent_account_context_create": {
            "structuredContent": {"result": {"accountContext": plan["accountContext"]}}
        },
        "agent_funding_policy_create": {
            "structuredContent": {"result": {"fundingPolicy": plan["fundingPolicy"]}}
        },
        "agent_build_fund_and_action_plan": {"structuredContent": {"result": plan}},
        "agent_fund_and_action_session_create": {
            "structuredContent": {"result": {"session": session}}
        },
        "vault_asset_transfer_result_create": {
            "structuredContent": {
                "result": {"assetTransferResult": asset_transfer_result}
            }
        },
        "agent_fund_and_action_session_apply_event": {
            "structuredContent": {"result": {"session": applied_session}}
        },
        "agent_fund_and_action_session_next_step": {
            "structuredContent": {"result": next_step}
        },
    }


def _write_fake_mcp_server(
    tmp_path: Path,
    *,
    plan: dict[str, object],
    session: dict[str, object],
    asset_transfer_result: dict[str, object],
    applied_session: dict[str, object],
    next_step: dict[str, object],
) -> str:
    fixture_path = tmp_path / "fake-mcp-fixture.json"
    server_path = tmp_path / "fake_mcp_server.py"
    fixture_path.write_text(
        json.dumps(
            {
                "tools": [
                    "factory_predict_vault_address",
                    "factory_create_vault_prepare",
                    "vault_health_check",
                    "agent_account_context_create",
                    "agent_funding_policy_create",
                    "agent_build_fund_and_action_plan",
                    "agent_fund_and_action_session_create",
                    "vault_asset_transfer_result_create",
                    "agent_fund_and_action_session_apply_event",
                    "agent_fund_and_action_session_next_step",
                ],
                "tool_results": _tool_results(
                    plan=plan,
                    session=session,
                    asset_transfer_result=asset_transfer_result,
                    applied_session=applied_session,
                    next_step=next_step,
                ),
            }
        ),
        encoding="utf-8",
    )
    server_path.write_text(
        """
from __future__ import annotations

import json
import sys
from pathlib import Path


def read_message() -> dict[str, object] | None:
    first_line = sys.stdin.buffer.readline()
    if not first_line:
        return None
    if not first_line.lower().startswith(b"content-length:"):
        return json.loads(first_line.decode("utf-8"))

    headers: dict[str, str] = {}
    line = first_line
    while True:
        if line in {b"\\r\\n", b"\\n", b""}:
            break
        key, value = line.decode("utf-8").split(":", 1)
        headers[key.lower()] = value.strip()
        line = sys.stdin.buffer.readline()
        if not line:
            return None
    length = int(headers["content-length"])
    body = sys.stdin.buffer.read(length)
    return json.loads(body.decode("utf-8"))


def write_message(message: dict[str, object]) -> None:
    payload = json.dumps(message).encode("utf-8")
    sys.stdout.buffer.write(f"Content-Length: {len(payload)}\\r\\n\\r\\n".encode("utf-8"))
    sys.stdout.buffer.write(payload)
    sys.stdout.buffer.flush()


fixture = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))

while True:
    request = read_message()
    if request is None:
        break

    method = request.get("method")
    request_id = request.get("id")

    if method == "notifications/initialized":
        continue
    if method == "initialize":
        write_message(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": {"name": "fake-mcp", "version": "0.1.0"},
                    "capabilities": {"tools": {"listChanged": False}},
                },
            }
        )
        continue
    if method == "tools/list":
        write_message(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "tools": [
                        {
                            "name": name,
                            "description": name,
                            "inputSchema": {"type": "object"},
                            "outputSchema": {"type": "object"},
                        }
                        for name in fixture["tools"]
                    ]
                },
            }
        )
        continue
    if method == "tools/call":
        tool_result = fixture["tool_results"][request["params"]["name"]]
        write_message(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [{"type": "text", "text": "ok"}],
                    "isError": tool_result.get("isError", False),
                    "structuredContent": tool_result["structuredContent"],
                },
            }
        )
        continue
    write_message(
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32601, "message": f"Unknown method: {method}"},
        }
    )
""".strip()
        + "\n",
        encoding="utf-8",
    )
    return f"{sys.executable} {server_path} {fixture_path}"


def _run_poc(
    *, env: dict[str, str]
) -> tuple[subprocess.CompletedProcess[str], dict[str, object]]:
    ARTIFACT_PATH.unlink(missing_ok=True)
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH)],
        cwd=PREDICT_ROOT,
        env={**os.environ, **env},
        capture_output=True,
        text=True,
        check=False,
    )
    return result, json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))


def _base_env(tmp_path: Path, *, mcp_command: str) -> dict[str, str]:
    return {
        "PREDICT_STORAGE_DIR": str(tmp_path),
        "PREDICT_ENV": "testnet",
        "PREDICT_WALLET_MODE": "mandated-vault",
        "PREDICT_SESSION_EVENT_POC_RECIPIENT_ADDRESS": PREDICT_ACCOUNT_ADDRESS,
        "ERC_MANDATED_CHAIN_ID": str(CHAIN_ID),
        "ERC_MANDATED_VAULT_ADDRESS": VAULT_ADDRESS,
        "ERC_MANDATED_VAULT_ASSET_ADDRESS": TOKEN_ADDRESS,
        "ERC_MANDATED_VAULT_AUTHORITY": AUTHORITY_ADDRESS,
        "ERC_MANDATED_AUTHORITY_PRIVATE_KEY": AUTHORITY_PRIVATE_KEY,
        "ERC_MANDATED_EXECUTOR_PRIVATE_KEY": EXECUTOR_PRIVATE_KEY,
        "ERC_MANDATED_MCP_COMMAND": mcp_command,
    }


def test_session_event_compatibility_poc_missing_env_writes_no_go_artifact(
    tmp_path: Path,
) -> None:
    result, artifact = _run_poc(env={"PREDICT_STORAGE_DIR": str(tmp_path)})

    assert result.returncode == 1
    assert artifact["verdict"] == "NO-GO"
    assert "missing predictAccountAddress" in artifact["reasons"]
    assert ARTIFACT_PATH.exists()


def test_session_event_compatibility_poc_passes_on_canonical_session_apply_event(
    tmp_path: Path,
) -> None:
    plan = _build_plan()
    session = _build_session(plan)
    asset_transfer_result = _build_asset_transfer_result(plan)
    applied_session = _build_applied_session(plan, asset_transfer_result)
    next_step = _build_next_step(applied_session)
    result, artifact = _run_poc(
        env=_base_env(
            tmp_path,
            mcp_command=_write_fake_mcp_server(
                tmp_path,
                plan=plan,
                session=session,
                asset_transfer_result=asset_transfer_result,
                applied_session=applied_session,
                next_step=next_step,
            ),
        )
    )

    assert result.returncode == 0
    assert artifact["verdict"] == "PASS"
    evidence = artifact["sessionEventCompatibilityEvidence"]
    assert evidence["sessionTransitionCompatible"] is True
    assert evidence["bindingFieldSetSufficientForTask9"] is True
    assert evidence["strongEnoughForTask9"] is True
    assert evidence["nextTaskKind"] == "submitFollowUp"
    assert artifact["reasons"] == []


def test_session_event_compatibility_poc_rejects_missing_binding_field(
    tmp_path: Path,
) -> None:
    funding_plan = _build_funding_plan()
    _delete_path(funding_plan, "prepareExecuteInput.adapterProofs")
    plan = _build_plan(funding_plan=funding_plan)
    session = _build_session(plan)
    asset_transfer_result = _build_asset_transfer_result(plan)
    applied_session = _build_applied_session(plan, asset_transfer_result)
    next_step = _build_next_step(applied_session)
    result, artifact = _run_poc(
        env=_base_env(
            tmp_path,
            mcp_command=_write_fake_mcp_server(
                tmp_path,
                plan=plan,
                session=session,
                asset_transfer_result=asset_transfer_result,
                applied_session=applied_session,
                next_step=next_step,
            ),
        )
    )

    assert result.returncode == 1
    assert artifact["verdict"] == "NO-GO"
    assert (
        "runtime binding field adapterProofs is missing or inconsistent"
        in artifact["reasons"]
    )
    assert (
        artifact["sessionEventCompatibilityEvidence"][
            "bindingFieldSetSufficientForTask9"
        ]
        is False
    )


def test_session_event_compatibility_poc_rejects_bad_session_transition(
    tmp_path: Path,
) -> None:
    plan = _build_plan()
    session = _build_session(plan)
    asset_transfer_result = _build_asset_transfer_result(plan)
    applied_session = _build_applied_session(
        plan, asset_transfer_result, compatible=False
    )
    next_step = _build_next_step(applied_session, kind="submitFunding")
    result, artifact = _run_poc(
        env=_base_env(
            tmp_path,
            mcp_command=_write_fake_mcp_server(
                tmp_path,
                plan=plan,
                session=session,
                asset_transfer_result=asset_transfer_result,
                applied_session=applied_session,
                next_step=next_step,
            ),
        )
    )

    assert result.returncode == 1
    assert artifact["verdict"] == "NO-GO"
    assert (
        "fundingConfirmed event did not transition session to pendingFollowUp"
        in artifact["reasons"]
    )
    assert (
        artifact["sessionEventCompatibilityEvidence"]["sessionTransitionCompatible"]
        is False
    )
