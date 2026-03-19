from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

PREDICT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = PREDICT_ROOT / "scripts" / "poc_predict_follow_up_autonomy.py"
ARTIFACT_PATH = (
    PREDICT_ROOT
    / "artifacts"
    / "reports"
    / "autonomous-preflight"
    / "follow-up-autonomy.json"
)
PREDICT_ACCOUNT_ADDRESS = "0x1234567890123456789012345678901234567890"
VAULT_ADDRESS = "0x2222222222222222222222222222222222222222"
TOKEN_ADDRESS = "0x4444444444444444444444444444444444444444"
AUTHORITY_ADDRESS = "0x5555555555555555555555555555555555555555"
TRADE_SIGNER_ADDRESS = "0x7777777777777777777777777777777777777777"
HEX64_A = "0x" + "aa" * 32
PREDICTED_VAULT = "0x6666666666666666666666666666666666666666"


def _plan(*, autonomous: bool) -> dict[str, object]:
    if autonomous:
        follow_up_action = {
            "kind": "predict.createOrder",
            "target": "order/market-1",
            "payload": {
                "marketId": "market-1",
                "collateralTokenAddress": TOKEN_ADDRESS,
                "collateralAmountRaw": "800",
                "orderSide": "buy",
                "outcomeId": "yes",
                "clientOrderId": "client-1",
            },
        }
        follow_up_plan = {
            "kind": "predict.createOrder",
            "target": "order/market-1",
            "executionMode": "offchain-api",
            "summary": "Place Predict order",
            "assetRequirement": {"tokenAddress": TOKEN_ADDRESS, "amountRaw": "800"},
            "payload": {
                "marketId": "market-1",
                "collateralTokenAddress": TOKEN_ADDRESS,
                "collateralAmountRaw": "800",
                "orderSide": "buy",
                "outcomeId": "yes",
                "clientOrderId": "client-1",
            },
        }
    else:
        follow_up_action = {
            "kind": "predict-order-submission",
            "target": "predict-api",
            "payload": {
                "status": "deferred",
                "reason": "buy-orchestration-not-enabled-in-this-task",
            },
        }
        follow_up_plan = {
            "kind": "predict-order-submission",
            "target": "predict-api",
            "executionMode": "custom",
            "summary": "Submit Predict order after funding is ready",
            "payload": {
                "status": "deferred",
                "reason": "buy-orchestration-not-enabled-in-this-task",
            },
        }
    return {
        "accountContext": {
            "agentId": f"predict-account:{PREDICT_ACCOUNT_ADDRESS.lower()}",
            "chainId": 97,
            "vault": VAULT_ADDRESS,
            "authority": AUTHORITY_ADDRESS,
            "executor": TRADE_SIGNER_ADDRESS,
            "fundingPolicyRef": f"vault-to-predict-account:{PREDICT_ACCOUNT_ADDRESS.lower()}",
            "defaults": {"payloadBinding": "actionsDigest", "extensions": "0x"},
            "createdAt": "2026-03-10T00:00:00Z",
            "updatedAt": "2026-03-10T00:00:00Z",
        },
        "fundingPolicy": {
            "policyId": f"vault-to-predict-account:{PREDICT_ACCOUNT_ADDRESS.lower()}",
            "allowedTokenAddresses": [TOKEN_ADDRESS],
            "allowedRecipients": [PREDICT_ACCOUNT_ADDRESS],
            "repeatable": True,
            "createdAt": "2026-03-10T00:00:00Z",
            "updatedAt": "2026-03-10T00:00:00Z",
        },
        "fundingTarget": {
            "label": "predict-account-usdt",
            "recipient": PREDICT_ACCOUNT_ADDRESS,
            "tokenAddress": TOKEN_ADDRESS,
            "requiredAmountRaw": "3000000000000000000",
            "currentBalanceRaw": "2000000000000000000",
            "balanceSnapshot": {
                "snapshotAt": "2026-03-10T00:00:00Z",
                "maxStalenessSeconds": 120,
                "source": "predict-wallet-status",
            },
            "fundingShortfallRaw": "1000000000000000000",
        },
        "evaluatedAt": "2026-03-10T00:00:00Z",
        "fundingRequired": True,
        "fundingPlan": None,
        "followUpAction": follow_up_action,
        "followUpActionPlan": follow_up_plan,
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


def _session(
    plan: dict[str, object],
    *,
    status: str,
    current_step: str,
    funding_step_status: str,
    follow_up_step_status: str,
) -> dict[str, object]:
    return {
        "sessionId": "session-follow-up-autonomy",
        "status": status,
        "currentStep": current_step,
        "createdAt": "2026-03-10T00:00:00Z",
        "updatedAt": "2026-03-10T00:01:00Z",
        "fundAndActionPlan": plan,
        "fundingStep": {
            "required": True,
            "status": funding_step_status,
            "summary": "Funding step",
            "updatedAt": "2026-03-10T00:01:00Z",
        },
        "followUpStep": {
            "status": follow_up_step_status,
            "summary": "Follow-up step",
            "updatedAt": "2026-03-10T00:01:00Z",
        },
    }


def _next_step(session: dict[str, object], *, task_kind: str) -> dict[str, object]:
    return {
        "session": session,
        "task": {
            "kind": task_kind,
            "summary": "Next overlay action",
        },
    }


def _tool_results(
    *,
    plan: dict[str, object],
    session: dict[str, object],
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
                    "authorityEpoch": "7",
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
        "agent_fund_and_action_session_next_step": {
            "structuredContent": {"result": next_step}
        },
        "agent_fund_and_action_session_apply_event": {
            "structuredContent": {"result": {"session": session}}
        },
        "agent_follow_up_action_result_create": {
            "structuredContent": {
                "result": {
                    "followUpActionResult": {
                        "kind": plan["followUpActionPlan"]["kind"],
                        "target": plan["followUpActionPlan"]["target"],
                        "executionMode": plan["followUpActionPlan"].get(
                            "executionMode", "custom"
                        ),
                        "status": "pending",
                        "summary": "Follow-up pending",
                        "updatedAt": "2026-03-10T00:01:00Z",
                        "attempt": 1,
                        "plan": plan["followUpActionPlan"],
                    }
                }
            }
        },
    }


def _write_fake_mcp_server(
    tmp_path: Path,
    *,
    plan: dict[str, object],
    session: dict[str, object],
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
                    "agent_fund_and_action_session_next_step",
                    "agent_fund_and_action_session_apply_event",
                    "agent_follow_up_action_result_create",
                ],
                "tool_results": _tool_results(
                    plan=plan, session=session, next_step=next_step
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
        if line in {b"\\r\\n", b"\\n"}:
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


fixture = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
tools = fixture['tools']
tool_results = fixture['tool_results']

while True:
    request = read_message()
    if request is None:
        break

    method = request.get('method')
    request_id = request.get('id')

    if method == 'initialize':
        write_message({'jsonrpc': '2.0', 'id': request_id, 'result': {'protocolVersion': '2024-11-05', 'serverInfo': {'name': 'fake-mcp', 'version': '0.1.0'}, 'capabilities': {'tools': {'listChanged': False}}}})
    elif method == 'notifications/initialized':
        continue
    elif method == 'tools/list':
        write_message({'jsonrpc': '2.0', 'id': request_id, 'result': {'tools': [{'name': name, 'description': name, 'inputSchema': {'type': 'object'}, 'outputSchema': {'type': 'object'}} for name in tools]}})
    elif method == 'tools/call':
        name = request['params']['name']
        tool_result = tool_results[name]
        write_message({'jsonrpc': '2.0', 'id': request_id, 'result': {'content': [{'type': 'text', 'text': 'ok'}], 'isError': tool_result.get('isError', False), 'structuredContent': tool_result['structuredContent']}})
    else:
        write_message({'jsonrpc': '2.0', 'id': request_id, 'error': {'code': -32601, 'message': f'Unknown method: {method}'}})
""".strip()
        + "\n",
        encoding="utf-8",
    )
    return f"{sys.executable} {server_path} {fixture_path}"


def _evidence(*, interactive_refresh: bool = False) -> str:
    return json.dumps(
        {
            "creditReadinessSignal": {
                "source": "predict-wallet-status",
                "fundingTxHash": HEX64_A,
                "ready": True,
                "referencesFundingTx": True,
                "recipient": PREDICT_ACCOUNT_ADDRESS,
                "tokenAddress": TOKEN_ADDRESS,
            },
            "authOwnershipSignal": {
                "source": "predict-auth-session",
                "ownerAddress": PREDICT_ACCOUNT_ADDRESS,
                "authSignerAddress": PREDICT_ACCOUNT_ADDRESS,
                "refreshCanBePerformedNonInteractively": not interactive_refresh,
                "refreshRequiresInteraction": interactive_refresh,
            },
        }
    )


def _run_poc(
    *, env: dict[str, str]
) -> tuple[subprocess.CompletedProcess[str], dict[str, object]]:
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


def test_follow_up_autonomy_poc_missing_env_writes_no_go_artifact(
    tmp_path: Path,
) -> None:
    result, artifact = _run_poc(env={"PREDICT_STORAGE_DIR": str(tmp_path)})

    assert result.returncode == 1
    assert artifact["verdict"] == "NO-GO"
    assert "missing predictAccountAddress" in artifact["reasons"]
    assert ARTIFACT_PATH.exists()


def test_follow_up_autonomy_poc_passes_with_non_interactive_follow_up_path(
    tmp_path: Path,
) -> None:
    plan = _plan(autonomous=True)
    session = _session(
        plan,
        status="pendingFollowUp",
        current_step="followUpAction",
        funding_step_status="succeeded",
        follow_up_step_status="pending",
    )
    next_step = _next_step(session, task_kind="submitFollowUp")
    result, artifact = _run_poc(
        env={
            "PREDICT_STORAGE_DIR": str(tmp_path),
            "PREDICT_ENV": "testnet",
            "PREDICT_WALLET_MODE": "predict-account",
            "PREDICT_ACCOUNT_ADDRESS": PREDICT_ACCOUNT_ADDRESS,
            "PREDICT_PRIVY_PRIVATE_KEY": "0x8b3a350cf5c34c9194ca0f4e664f9f47d8f8be06d87564ce4b64f59b8d66c1f0",
            "ERC_MANDATED_VAULT_ADDRESS": VAULT_ADDRESS,
            "ERC_MANDATED_VAULT_ASSET_ADDRESS": TOKEN_ADDRESS,
            "ERC_MANDATED_VAULT_AUTHORITY": AUTHORITY_ADDRESS,
            "PREDICT_FOLLOW_UP_POC_TRADE_SIGNER_ADDRESS": TRADE_SIGNER_ADDRESS,
            "ERC_MANDATED_MCP_COMMAND": _write_fake_mcp_server(
                tmp_path,
                plan=plan,
                session=session,
                next_step=next_step,
            ),
            "PREDICT_FOLLOW_UP_POC_EVIDENCE_JSON": _evidence(),
        }
    )

    assert result.returncode == 0
    assert artifact["verdict"] == "PASS"
    evidence = artifact["followUpAutonomyEvidence"]
    assert evidence["strongEnoughForAutonomousContinuation"] is True
    assert evidence["followUpExecutionMode"] == "offchain-api"
    assert evidence["nextStepKind"] == "submitFollowUp"
    assert artifact["reasons"] == []


def test_follow_up_autonomy_poc_rejects_deferred_follow_up_plan(tmp_path: Path) -> None:
    plan = _plan(autonomous=False)
    session = _session(
        plan,
        status="pendingFunding",
        current_step="fundTargetAccount",
        funding_step_status="pending",
        follow_up_step_status="pending",
    )
    next_step = _next_step(session, task_kind="submitFunding")
    result, artifact = _run_poc(
        env={
            "PREDICT_STORAGE_DIR": str(tmp_path),
            "PREDICT_ENV": "testnet",
            "PREDICT_WALLET_MODE": "predict-account",
            "PREDICT_ACCOUNT_ADDRESS": PREDICT_ACCOUNT_ADDRESS,
            "PREDICT_PRIVY_PRIVATE_KEY": "0x8b3a350cf5c34c9194ca0f4e664f9f47d8f8be06d87564ce4b64f59b8d66c1f0",
            "ERC_MANDATED_VAULT_ADDRESS": VAULT_ADDRESS,
            "ERC_MANDATED_VAULT_ASSET_ADDRESS": TOKEN_ADDRESS,
            "ERC_MANDATED_VAULT_AUTHORITY": AUTHORITY_ADDRESS,
            "PREDICT_FOLLOW_UP_POC_TRADE_SIGNER_ADDRESS": TRADE_SIGNER_ADDRESS,
            "ERC_MANDATED_MCP_COMMAND": _write_fake_mcp_server(
                tmp_path,
                plan=plan,
                session=session,
                next_step=next_step,
            ),
            "PREDICT_FOLLOW_UP_POC_EVIDENCE_JSON": _evidence(),
        }
    )

    assert result.returncode == 1
    assert artifact["verdict"] == "NO-GO"
    assert (
        "follow-up action plan kind must be predict.createOrder" in artifact["reasons"]
    )
    assert "follow-up action plan remains deferred" in artifact["reasons"]


def test_follow_up_autonomy_poc_rejects_interactive_auth_refresh(
    tmp_path: Path,
) -> None:
    plan = _plan(autonomous=True)
    session = _session(
        plan,
        status="pendingFollowUp",
        current_step="followUpAction",
        funding_step_status="succeeded",
        follow_up_step_status="pending",
    )
    next_step = _next_step(session, task_kind="submitFollowUp")
    result, artifact = _run_poc(
        env={
            "PREDICT_STORAGE_DIR": str(tmp_path),
            "PREDICT_ENV": "testnet",
            "PREDICT_WALLET_MODE": "predict-account",
            "PREDICT_ACCOUNT_ADDRESS": PREDICT_ACCOUNT_ADDRESS,
            "PREDICT_PRIVY_PRIVATE_KEY": "0x8b3a350cf5c34c9194ca0f4e664f9f47d8f8be06d87564ce4b64f59b8d66c1f0",
            "ERC_MANDATED_VAULT_ADDRESS": VAULT_ADDRESS,
            "ERC_MANDATED_VAULT_ASSET_ADDRESS": TOKEN_ADDRESS,
            "ERC_MANDATED_VAULT_AUTHORITY": AUTHORITY_ADDRESS,
            "PREDICT_FOLLOW_UP_POC_TRADE_SIGNER_ADDRESS": TRADE_SIGNER_ADDRESS,
            "ERC_MANDATED_MCP_COMMAND": _write_fake_mcp_server(
                tmp_path,
                plan=plan,
                session=session,
                next_step=next_step,
            ),
            "PREDICT_FOLLOW_UP_POC_EVIDENCE_JSON": _evidence(interactive_refresh=True),
        }
    )

    assert result.returncode == 1
    assert artifact["verdict"] == "NO-GO"
    assert (
        "auth ownership signal says refresh requires interaction" in artifact["reasons"]
    )
    evidence = artifact["followUpAutonomyEvidence"]["authOwnershipSignal"]
    assert evidence["refreshRequiresInteraction"] is True
