from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import cast

from lib.mandated_mcp_bridge import MANDATED_V1_REQUIRED_TOOLS


PREDICT_ACCOUNT_ADDRESS = "0x1234567890123456789012345678901234567890"
VAULT_ADDRESS = "0x2222222222222222222222222222222222222222"
AUTHORITY_ADDRESS = "0x5555555555555555555555555555555555555555"
ASSET_ADDRESS = "0x4444444444444444444444444444444444444444"
PREDICTED_VAULT = "0x1234567890123456789012345678901234567890"


def run_predictclaw(
    *args: str, env: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    predict_root = Path(__file__).resolve().parents[2]
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


def fixture_env(tmp_path: Path) -> dict[str, str]:
    return {
        "PREDICT_ENV": "test-fixture",
        "PREDICT_STORAGE_DIR": str(tmp_path),
        "PREDICT_PRIVATE_KEY": "0x59c6995e998f97a5a0044976f4d060f5d89c8b8c7f11b9aa0dbf3f0f7c7c1e01",
    }


def write_fake_mcp_server(
    tmp_path: Path,
    *,
    tools: list[str],
    tool_results: dict[str, dict[str, object]],
) -> str:
    fixture_path = tmp_path / "fake-mcp-fixture.json"
    server_path = tmp_path / "fake_mcp_server.py"

    fixture_path.write_text(
        json.dumps({"tools": tools, "tool_results": tool_results}),
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
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "fake-mcp", "version": "0.0.0"},
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
        params = request.get("params", {})
        name = params["name"]
        tool_result = fixture["tool_results"][name]
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
""".strip(),
        encoding="utf-8",
    )
    return f"{sys.executable} {server_path} {fixture_path}"


def overlay_fund_and_action_plan(
    *,
    evaluated_at: str = "2026-03-09T00:00:00Z",
    snapshot_at: str = "2026-03-09T00:00:00Z",
    max_staleness_seconds: int = 120,
) -> dict[str, object]:
    return {
        "accountContext": {
            "agentId": "predict-account-agent",
            "chainId": 97,
            "vault": VAULT_ADDRESS,
            "authority": AUTHORITY_ADDRESS,
            "executor": "0x7E5F4552091A69125d5DfCb7b8C2659029395Bdf",
            "assetRegistryRef": "predict/usdt",
            "fundingPolicyRef": f"vault-to-predict-account:{PREDICT_ACCOUNT_ADDRESS.lower()}",
            "defaults": {
                "payloadBinding": "actionsDigest",
                "extensions": "0x",
            },
            "createdAt": "2026-03-09T00:00:00Z",
            "updatedAt": "2026-03-09T00:00:00Z",
        },
        "fundingPolicy": {
            "policyId": f"vault-to-predict-account:{PREDICT_ACCOUNT_ADDRESS.lower()}",
            "allowedTokenAddresses": [ASSET_ADDRESS],
            "allowedRecipients": [PREDICT_ACCOUNT_ADDRESS],
            "repeatable": True,
            "createdAt": "2026-03-09T00:00:00Z",
            "updatedAt": "2026-03-09T00:00:00Z",
        },
        "fundingTarget": {
            "label": "predict-account-usdt",
            "recipient": PREDICT_ACCOUNT_ADDRESS,
            "tokenAddress": ASSET_ADDRESS,
            "requiredAmountRaw": "3000000000000000000",
            "currentBalanceRaw": "2000000000000000000",
            "balanceSnapshot": {
                "snapshotAt": snapshot_at,
                "maxStalenessSeconds": max_staleness_seconds,
                "source": "predict-wallet-status",
            },
            "fundingShortfallRaw": "1000000000000000000",
        },
        "evaluatedAt": evaluated_at,
        "fundingRequired": True,
        "followUpAction": {
            "kind": "predict-order-submission",
            "target": "predict-api",
            "payload": {
                "status": "deferred",
                "reason": "buy-orchestration-not-enabled-in-this-task",
            },
        },
        "followUpActionPlan": {
            "kind": "predict-order-submission",
            "target": "predict-api",
            "executionMode": "custom",
            "summary": "Submit Predict order after funding is ready",
            "payload": {
                "status": "deferred",
                "reason": "buy-orchestration-not-enabled-in-this-task",
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
                "summary": "Submit follow-up action when requested",
            },
        ],
    }


def overlay_fund_and_action_session(
    plan: dict[str, object],
    *,
    status: str = "pendingFunding",
    current_step: str = "fundTargetAccount",
    funding_step_status: str = "pending",
    funding_step_summary: str = "Await funding submission",
    follow_up_step_status: str = "pending",
    follow_up_step_summary: str = "Await follow-up execution",
) -> dict[str, object]:
    return {
        "session": {
            "sessionId": "session-integration-overlay",
            "status": status,
            "currentStep": current_step,
            "createdAt": "2026-03-09T00:00:00Z",
            "updatedAt": "2026-03-09T00:00:00Z",
            "fundAndActionPlan": plan,
            "fundingStep": {
                "required": True,
                "status": funding_step_status,
                "summary": funding_step_summary,
                "updatedAt": "2026-03-09T00:00:00Z",
            },
            "followUpStep": {
                "status": follow_up_step_status,
                "summary": follow_up_step_summary,
                "updatedAt": "2026-03-09T00:00:00Z",
            },
        }
    }


def overlay_fund_and_action_session_payload(
    plan: dict[str, object],
    *,
    status: str = "pendingFunding",
    current_step: str = "fundTargetAccount",
    funding_step_status: str = "pending",
    funding_step_summary: str = "Await funding submission",
    follow_up_step_status: str = "pending",
    follow_up_step_summary: str = "Await follow-up execution",
) -> dict[str, object]:
    return cast(
        dict[str, object],
        overlay_fund_and_action_session(
            plan,
            status=status,
            current_step=current_step,
            funding_step_status=funding_step_status,
            funding_step_summary=funding_step_summary,
            follow_up_step_status=follow_up_step_status,
            follow_up_step_summary=follow_up_step_summary,
        )["session"],
    )


def overlay_fund_and_action_next_step(
    plan: dict[str, object],
    *,
    session: dict[str, object] | None = None,
    task_kind: str = "submitFunding",
    task_summary: str = "Submit vault funding transaction",
) -> dict[str, object]:
    return {
        "session": session or overlay_fund_and_action_session_payload(plan),
        "task": {
            "kind": task_kind,
            "summary": task_summary,
        },
    }


def overlay_mcp_command(
    tmp_path: Path,
    *,
    plan: dict[str, object] | None = None,
    session: dict[str, object] | None = None,
    next_step: dict[str, object] | None = None,
) -> str:
    plan = plan or overlay_fund_and_action_plan()
    session = session or overlay_fund_and_action_session_payload(plan)
    next_step = next_step or overlay_fund_and_action_next_step(plan, session=session)
    return write_fake_mcp_server(
        tmp_path,
        tools=sorted(
            MANDATED_V1_REQUIRED_TOOLS.union(
                {
                    "agent_account_context_create",
                    "agent_funding_policy_create",
                    "agent_build_fund_and_action_plan",
                    "agent_fund_and_action_session_create",
                    "agent_fund_and_action_session_next_step",
                }
            )
        ),
        tool_results={
            "factory_predict_vault_address": {
                "structuredContent": {"result": {"predictedVault": PREDICTED_VAULT}}
            },
            "factory_create_vault_prepare": {
                "structuredContent": {
                    "result": {
                        "predictedVault": PREDICTED_VAULT,
                        "txRequest": {
                            "from": AUTHORITY_ADDRESS,
                            "to": "0x1111111111111111111111111111111111111111",
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
                        "pendingAuthority": "0x0000000000000000000000000000000000000000",
                        "nonceThreshold": "2",
                        "totalAssets": "123000000000000000000",
                    }
                }
            },
            "agent_account_context_create": {
                "structuredContent": {
                    "result": {
                        "accountContext": {
                            "agentId": "predict-account-agent",
                            "chainId": 97,
                            "vault": VAULT_ADDRESS,
                            "authority": AUTHORITY_ADDRESS,
                            "executor": "0x7E5F4552091A69125d5DfCb7b8C2659029395Bdf",
                            "assetRegistryRef": "predict/usdt",
                            "fundingPolicyRef": "vault-to-predict-account:0x1234567890123456789012345678901234567890",
                            "defaults": {
                                "payloadBinding": "actionsDigest",
                                "extensions": "0x",
                            },
                            "createdAt": "2026-03-09T00:00:00Z",
                            "updatedAt": "2026-03-09T00:00:00Z",
                        }
                    }
                }
            },
            "agent_funding_policy_create": {
                "structuredContent": {
                    "result": {
                        "fundingPolicy": {
                            "policyId": "vault-to-predict-account:0x1234567890123456789012345678901234567890",
                            "allowedTokenAddresses": [ASSET_ADDRESS],
                            "allowedRecipients": [PREDICT_ACCOUNT_ADDRESS],
                            "repeatable": True,
                            "createdAt": "2026-03-09T00:00:00Z",
                            "updatedAt": "2026-03-09T00:00:00Z",
                        }
                    }
                }
            },
            "agent_build_fund_and_action_plan": {"structuredContent": {"result": plan}},
            "agent_fund_and_action_session_create": {
                "structuredContent": {"result": {"session": session}}
            },
            "agent_fund_and_action_session_next_step": {
                "structuredContent": {"result": next_step}
            },
        },
    )


def predict_account_overlay_error_env(
    tmp_path: Path,
    *,
    plan: dict[str, object] | None = None,
    session: dict[str, object] | None = None,
    next_step: dict[str, object] | None = None,
) -> dict[str, str]:
    return {
        **predict_account_overlay_env(tmp_path),
        "ERC_MANDATED_MCP_COMMAND": overlay_mcp_command(
            tmp_path,
            plan=plan,
            session=session,
            next_step=next_step,
        ),
    }


def write_overlay_sitecustomize(tmp_path: Path) -> Path:
    patch_root = tmp_path / "overlay-patches"
    patch_root.mkdir(parents=True, exist_ok=True)
    (patch_root / "sitecustomize.py").write_text(
        """
from __future__ import annotations

from lib.config import ConfigError
from lib.position_storage import PositionStorage
import lib.trade_service as trade_service


_original_buy_fixture = trade_service.TradeService._buy_fixture


async def _overlay_aware_buy_fixture(
    self,
    market_id: str,
    outcome_label: str,
    amount_usdt: str,
    *,
    limit_price: float | None,
):
    notes = None
    if trade_service._has_predict_account_overlay(self._config):
        sdk = self._wallet_sdk_factory(self._config)
        amount_wei = trade_service._parse_amount_to_wei(amount_usdt)
        current_usdt_balance_wei = await trade_service._sdk_usdt_balance_wei(sdk)
        if current_usdt_balance_wei < amount_wei:
            orchestration = await self._build_overlay_orchestration(
                predict_account_address=sdk.funding_address,
                trade_signer_address=sdk.signer_address,
                current_usdt_balance_wei=current_usdt_balance_wei,
            )
            raise ConfigError(
                trade_service._format_overlay_funding_required_error(
                    orchestration,
                    attempted_buy_amount_raw=amount_wei,
                    current_balance_raw=current_usdt_balance_wei,
                )
            )
        notes = trade_service._overlay_position_notes(
            predict_account_address=sdk.funding_address,
            trade_signer_address=sdk.signer_address,
        )

    result = await _original_buy_fixture(
        self,
        market_id,
        outcome_label,
        amount_usdt,
        limit_price=limit_price,
    )
    if notes is not None:
        storage = PositionStorage(self._config.storage_dir)
        position = storage.get_position(f"pos-{market_id}-{result.outcome.lower()}")
        if position is not None:
            position.notes = notes
            storage.upsert(position)
    return result


trade_service.TradeService._buy_fixture = _overlay_aware_buy_fixture
""".strip(),
        encoding="utf-8",
    )
    return patch_root


def predict_account_overlay_env(tmp_path: Path) -> dict[str, str]:
    patch_root = write_overlay_sitecustomize(tmp_path)
    return {
        "PREDICT_ENV": "test-fixture",
        "PREDICT_STORAGE_DIR": str(tmp_path),
        "PREDICT_WALLET_MODE": "predict-account",
        "PREDICT_ACCOUNT_ADDRESS": PREDICT_ACCOUNT_ADDRESS,
        "PREDICT_PRIVY_PRIVATE_KEY": "0x59c6995e998f97a5a0044976f4d060f5d89c8b8c7f11b9aa0dbf3f0f7c7c1e01",
        "ERC_MANDATED_VAULT_ADDRESS": VAULT_ADDRESS,
        "ERC_MANDATED_FACTORY_ADDRESS": "0x1111111111111111111111111111111111111111",
        "ERC_MANDATED_VAULT_ASSET_ADDRESS": "0x4444444444444444444444444444444444444444",
        "ERC_MANDATED_VAULT_NAME": "Mandated Vault",
        "ERC_MANDATED_VAULT_SYMBOL": "MVLT",
        "ERC_MANDATED_VAULT_AUTHORITY": AUTHORITY_ADDRESS,
        "ERC_MANDATED_VAULT_SALT": "0x" + "aa" * 32,
        "ERC_MANDATED_CHAIN_ID": "97",
        "ERC_MANDATED_MCP_COMMAND": overlay_mcp_command(tmp_path),
        "PYTHONPATH": str(patch_root),
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


def test_wallet_status_predict_account_overlay_runs_end_to_end(tmp_path) -> None:
    status = run_predictclaw(
        "wallet",
        "status",
        "--json",
        env=predict_account_overlay_env(tmp_path),
    )

    assert status.returncode == 0
    payload = json.loads(status.stdout)
    funding_target = payload["fundingOrchestration"]["fundingTarget"]

    assert payload["mode"] == "predict-account"
    assert payload["fundingRoute"] == "vault-to-predict-account"
    assert payload["predictAccountAddress"] == PREDICT_ACCOUNT_ADDRESS
    assert payload["predictAccountAddress"] != payload["vaultAddress"]
    assert payload["tradeSignerAddress"] != payload["vaultAddress"]
    assert funding_target["recipient"] == PREDICT_ACCOUNT_ADDRESS


def test_wallet_deposit_predict_account_overlay_runs_end_to_end(tmp_path) -> None:
    deposit = run_predictclaw(
        "wallet",
        "deposit",
        "--json",
        env=predict_account_overlay_env(tmp_path),
    )

    assert deposit.returncode == 0
    payload = json.loads(deposit.stdout)
    funding_target = payload["fundingOrchestration"]["fundingTarget"]

    assert payload["mode"] == "predict-account"
    assert payload["fundingRoute"] == "vault-to-predict-account"
    assert payload["predictAccountAddress"] == PREDICT_ACCOUNT_ADDRESS
    assert payload["predictAccountAddress"] != payload["vaultAddress"]
    assert payload["tradeSignerAddress"] != payload["vaultAddress"]
    assert funding_target["recipient"] == PREDICT_ACCOUNT_ADDRESS


def test_buy_predict_account_overlay_runs_end_to_end_when_balance_sufficient(
    tmp_path,
) -> None:
    buy = run_predictclaw(
        "buy",
        "123",
        "YES",
        "25",
        "--json",
        env=predict_account_overlay_env(tmp_path),
    )

    assert buy.returncode == 0
    assert json.loads(buy.stdout)["status"] == "FILLED"

    positions_path = tmp_path / "positions.json"
    stored = json.loads(positions_path.read_text())
    notes = json.loads(stored[0]["notes"])

    assert notes["fundingRoute"] == "vault-to-predict-account"
    assert notes["predictAccountAddress"] == PREDICT_ACCOUNT_ADDRESS
    assert notes["predictAccountAddress"] != VAULT_ADDRESS
    assert notes["tradeSignerAddress"] != VAULT_ADDRESS


def test_buy_predict_account_overlay_returns_deterministic_funding_guidance_when_balance_insufficient(
    tmp_path,
) -> None:
    buy = run_predictclaw(
        "buy",
        "123",
        "YES",
        "30",
        "--json",
        env=predict_account_overlay_env(tmp_path),
    )

    assert buy.returncode == 1
    combined = buy.stdout + buy.stderr

    assert "funding-required" in combined
    assert "vault-to-predict-account" in combined
    assert "requiredAmountRaw=5000000000000000000" in combined
    assert "currentBalanceRaw=25000000000000000000" in combined
    assert PREDICT_ACCOUNT_ADDRESS in combined
    assert "wallet deposit --json" in combined
    assert "Traceback" not in combined
    assert not (tmp_path / "positions.json").exists()


def test_buy_predict_account_overlay_surfaces_stale_balance_without_traceback(
    tmp_path,
) -> None:
    plan = overlay_fund_and_action_plan(
        evaluated_at="2026-03-09T00:10:00Z",
        snapshot_at="2026-03-09T00:00:00Z",
        max_staleness_seconds=60,
    )
    buy = run_predictclaw(
        "buy",
        "123",
        "YES",
        "30",
        "--json",
        env=predict_account_overlay_error_env(tmp_path, plan=plan),
    )

    assert buy.returncode == 1
    combined = buy.stdout + buy.stderr
    assert "sessionOutcome=stale-balance" in combined
    assert "Traceback" not in combined


def test_buy_predict_account_overlay_surfaces_funding_failed_without_traceback(
    tmp_path,
) -> None:
    plan = overlay_fund_and_action_plan()
    session = overlay_fund_and_action_session_payload(
        plan,
        status="failed",
        current_step="none",
        funding_step_status="failed",
        funding_step_summary="Funding failed",
    )
    next_step = overlay_fund_and_action_next_step(
        plan,
        session=session,
        task_kind="completed",
        task_summary="Funding failed",
    )
    buy = run_predictclaw(
        "buy",
        "123",
        "YES",
        "30",
        "--json",
        env=predict_account_overlay_error_env(
            tmp_path,
            plan=plan,
            session=session,
            next_step=next_step,
        ),
    )

    assert buy.returncode == 1
    combined = buy.stdout + buy.stderr
    assert "sessionOutcome=funding-failed" in combined
    assert "Traceback" not in combined


def test_buy_predict_account_overlay_reports_stale_balance_snapshot_outcome(
    tmp_path,
) -> None:
    plan = overlay_fund_and_action_plan(
        evaluated_at="2026-03-09T00:03:01Z",
        snapshot_at="2026-03-09T00:00:00Z",
        max_staleness_seconds=120,
    )
    session = overlay_fund_and_action_session_payload(plan)
    buy = run_predictclaw(
        "buy",
        "123",
        "YES",
        "30",
        "--json",
        env=predict_account_overlay_error_env(tmp_path, plan=plan, session=session),
    )

    assert buy.returncode == 1
    combined = buy.stdout + buy.stderr

    assert "sessionOutcome=stale-balance" in combined
    assert "sessionStatus=pendingFunding" in combined
    assert "Traceback" not in combined
    assert not (tmp_path / "positions.json").exists()


def test_buy_predict_account_overlay_reports_funding_failed_session_outcome(
    tmp_path,
) -> None:
    plan = overlay_fund_and_action_plan()
    session = overlay_fund_and_action_session_payload(
        plan,
        status="failed",
        current_step="fundTargetAccount",
        funding_step_status="failed",
        funding_step_summary="Funding transaction failed",
    )
    next_step = overlay_fund_and_action_next_step(
        plan,
        session=session,
        task_kind="pollFundingResult",
        task_summary="Poll failed vault funding transaction",
    )
    buy = run_predictclaw(
        "buy",
        "123",
        "YES",
        "30",
        "--json",
        env=predict_account_overlay_error_env(
            tmp_path,
            plan=plan,
            session=session,
            next_step=next_step,
        ),
    )

    assert buy.returncode == 1
    combined = buy.stdout + buy.stderr

    assert "sessionOutcome=funding-failed" in combined
    assert "sessionStatus=failed" in combined
    assert "nextStepKind=pollFundingResult" in combined
    assert "Traceback" not in combined
    assert not (tmp_path / "positions.json").exists()


def test_buy_predict_account_overlay_reports_follow_up_failed_session_outcome(
    tmp_path,
) -> None:
    plan = overlay_fund_and_action_plan()
    session = overlay_fund_and_action_session_payload(
        plan,
        status="failed",
        current_step="followUpAction",
        funding_step_status="succeeded",
        funding_step_summary="Funding transaction confirmed",
        follow_up_step_status="failed",
        follow_up_step_summary="Predict order submission failed",
    )
    next_step = overlay_fund_and_action_next_step(
        plan,
        session=session,
        task_kind="pollFollowUpResult",
        task_summary="Poll failed Predict order submission",
    )
    buy = run_predictclaw(
        "buy",
        "123",
        "YES",
        "30",
        "--json",
        env=predict_account_overlay_error_env(
            tmp_path,
            plan=plan,
            session=session,
            next_step=next_step,
        ),
    )

    assert buy.returncode == 1
    combined = buy.stdout + buy.stderr

    assert "sessionOutcome=follow-up-failed" in combined
    assert "sessionStatus=failed" in combined
    assert "nextStepKind=pollFollowUpResult" in combined
    assert "Traceback" not in combined
    assert not (tmp_path / "positions.json").exists()
