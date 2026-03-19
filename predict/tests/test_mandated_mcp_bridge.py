from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

from lib.config import PredictConfig
from lib.mandated_mcp_bridge import (
    MANDATED_BOOTSTRAP_REQUIRED_TOOLS,
    MANDATED_V1_REQUIRED_TOOLS,
    MandatedVaultMcpBridge,
    MandatedVaultMcpMissingToolsError,
    MandatedVaultMcpUnavailableError,
    _drop_none_values,
)


VAULT_ADDRESS = "0xabcdefabcdefabcdefabcdefabcdefabcdefabcd"
FACTORY_ADDRESS = "0x1111111111111111111111111111111111111111"
ASSET_ADDRESS = "0x2222222222222222222222222222222222222222"
AUTHORITY_ADDRESS = "0x3333333333333333333333333333333333333333"
FROM_ADDRESS = "0x4444444444444444444444444444444444444444"
PREDICTED_VAULT = "0x5555555555555555555555555555555555555555"
TX_TARGET = "0x6666666666666666666666666666666666666666"
SALT = "0x" + "12" * 32
HEX64_A = "0x" + "aa" * 32
HEX64_B = "0x" + "bb" * 32
HEX64_C = "0x" + "cc" * 32
HEX64_D = "0x" + "dd" * 32
HEX64_E = "0x" + "ee" * 32
HEX64_F = "0x" + "ff" * 32
BLOCK_HASH = "0x" + "11" * 32

AGENT_SESSION_TOOLS = [
    "agent_account_context_create",
    "agent_funding_policy_create",
    "agent_build_fund_and_action_plan",
    "agent_fund_and_action_session_create",
    "agent_fund_and_action_session_next_step",
    "agent_fund_and_action_session_apply_event",
    "agent_follow_up_action_result_create",
]

ASSET_TRANSFER_TOOLS = [
    "vault_asset_transfer_result_create",
    "vault_check_asset_transfer_policy",
    "vault_build_asset_transfer_plan_from_context",
    "vault_simulate_asset_transfer_from_context",
    "vault_prepare_asset_transfer_from_context",
]


def test_drop_none_values_recursively_removes_nested_nulls() -> None:
    assert _drop_none_values(
        {
            "accountContext": {
                "assetRegistryRef": None,
                "defaults": {
                    "allowedAdaptersRoot": None,
                    "maxDrawdownBps": None,
                    "payloadBinding": "actionsDigest",
                    "extensions": "0x",
                },
            },
            "fundingPolicy": {"expiresAt": None, "repeatable": True},
            "fundingContext": {
                "allowedAdaptersRoot": "0x" + "00" * 32,
                "maxDrawdownBps": "0",
                "maxCumulativeDrawdownBps": "0",
            },
            "optional": None,
        }
    ) == {
        "accountContext": {
            "defaults": {
                "payloadBinding": "actionsDigest",
                "extensions": "0x",
            }
        },
        "fundingPolicy": {"repeatable": True},
        "fundingContext": {
            "allowedAdaptersRoot": "0x" + "00" * 32,
            "maxDrawdownBps": "0",
            "maxCumulativeDrawdownBps": "0",
        },
    }


def mandated_env(command: str, **extra_env: str) -> dict[str, str]:
    return {
        "PREDICT_ENV": "testnet",
        "PREDICT_STORAGE_DIR": "/tmp/predict",
        "PREDICT_WALLET_MODE": "mandated-vault",
        "ERC_MANDATED_VAULT_ADDRESS": VAULT_ADDRESS,
        "ERC_MANDATED_MCP_COMMAND": command,
        **extra_env,
    }


def build_account_context() -> dict[str, Any]:
    return {
        "agentId": "agent-1",
        "chainId": 8453,
        "vault": VAULT_ADDRESS,
        "authority": AUTHORITY_ADDRESS,
        "executor": FROM_ADDRESS,
        "assetRegistryRef": "registry/usdc",
        "fundingPolicyRef": "policy-1",
        "defaults": {
            "allowedAdaptersRoot": HEX64_A,
            "maxDrawdownBps": "100",
            "maxCumulativeDrawdownBps": "200",
            "payloadBinding": "actionsDigest",
            "extensions": "0x",
        },
        "createdAt": "2026-03-09T00:00:00Z",
        "updatedAt": "2026-03-09T00:05:00Z",
    }


def build_funding_policy() -> dict[str, Any]:
    return {
        "policyId": "policy-1",
        "allowedTokenAddresses": [ASSET_ADDRESS],
        "allowedRecipients": [FROM_ADDRESS],
        "maxAmountPerTx": "1000",
        "maxAmountPerWindow": "5000",
        "windowSeconds": 3600,
        "expiresAt": "2026-03-10T00:00:00Z",
        "repeatable": True,
        "createdAt": "2026-03-09T00:00:00Z",
        "updatedAt": "2026-03-09T00:05:00Z",
    }


def build_follow_up_action_plan() -> dict[str, Any]:
    return {
        "kind": "predict.createOrder",
        "target": "order/market-1",
        "executionMode": "offchain-api",
        "summary": "Place Predict order",
        "assetRequirement": {
            "tokenAddress": ASSET_ADDRESS,
            "amountRaw": "800",
        },
        "payload": {
            "marketId": "market-1",
            "collateralTokenAddress": ASSET_ADDRESS,
            "collateralAmountRaw": "800",
            "orderSide": "buy",
            "outcomeId": "yes",
            "clientOrderId": "client-1",
        },
    }


def build_follow_up_action_intent() -> dict[str, Any]:
    return {
        "kind": "predict.createOrder",
        "target": "order/market-1",
        "payload": {
            "marketId": "market-1",
            "collateralTokenAddress": ASSET_ADDRESS,
            "collateralAmountRaw": "800",
            "orderSide": "buy",
            "outcomeId": "yes",
            "clientOrderId": "client-1",
        },
    }


def build_mandate() -> dict[str, Any]:
    return {
        "vault": VAULT_ADDRESS,
        "executor": FROM_ADDRESS,
        "nonce": "7",
        "deadline": "9999999999",
        "authorityEpoch": "2",
        "allowedAdaptersRoot": HEX64_A,
        "maxDrawdownBps": "100",
        "maxCumulativeDrawdownBps": "200",
        "payloadDigest": HEX64_B,
        "extensionsHash": HEX64_C,
    }


def build_sign_request() -> dict[str, Any]:
    return {
        "typedData": {"domain": {"name": "Mandated"}},
        "mandate": build_mandate(),
        "mandateHash": HEX64_D,
        "actionsDigest": HEX64_E,
        "extensionsHash": HEX64_C,
    }


def build_policy_check_result() -> dict[str, Any]:
    return {
        "allowed": True,
        "fundingPolicy": build_funding_policy(),
        "violations": [],
    }


def build_funding_plan() -> dict[str, Any]:
    return {
        "accountContext": build_account_context(),
        "action": {"type": "erc20Transfer", "to": FROM_ADDRESS},
        "erc20Call": {
            "tokenAddress": ASSET_ADDRESS,
            "to": FROM_ADDRESS,
            "amountRaw": "800",
        },
        "humanReadableSummary": {
            "kind": "erc20Transfer",
            "tokenAddress": ASSET_ADDRESS,
            "to": FROM_ADDRESS,
            "amountRaw": "800",
            "symbol": "USDC",
            "decimals": 6,
        },
        "signRequest": build_sign_request(),
        "policyCheck": build_policy_check_result(),
        "simulateExecuteInput": {
            "chainId": 8453,
            "vault": VAULT_ADDRESS,
            "from": FROM_ADDRESS,
            "mandate": build_mandate(),
            "signature": "0x1234",
            "actions": [{"type": "erc20Transfer"}],
            "adapterProofs": [[HEX64_A]],
            "extensions": "0x",
        },
        "prepareExecuteInput": {
            "chainId": 8453,
            "vault": VAULT_ADDRESS,
            "from": FROM_ADDRESS,
            "mandate": build_mandate(),
            "signature": "0x1234",
            "actions": [{"type": "erc20Transfer"}],
            "adapterProofs": [[HEX64_A]],
            "extensions": "0x",
        },
    }


def build_fund_and_action_plan() -> dict[str, Any]:
    return {
        "accountContext": build_account_context(),
        "fundingPolicy": build_funding_policy(),
        "fundingTarget": {
            "label": "predict-account-usdc",
            "recipient": FROM_ADDRESS,
            "tokenAddress": ASSET_ADDRESS,
            "requiredAmountRaw": "1000",
            "currentBalanceRaw": "200",
            "balanceSnapshot": {
                "snapshotAt": "2026-03-09T00:00:00Z",
                "maxStalenessSeconds": 60,
                "observedAtBlock": "123",
                "source": "predict-api",
            },
            "fundingShortfallRaw": "800",
            "symbol": "USDC",
            "decimals": 6,
        },
        "evaluatedAt": "2026-03-09T00:01:00Z",
        "fundingRequired": True,
        "fundingPlan": build_funding_plan(),
        "followUpAction": build_follow_up_action_intent(),
        "followUpActionPlan": build_follow_up_action_plan(),
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


def build_session() -> dict[str, Any]:
    return {
        "sessionId": "session-1",
        "status": "pendingFunding",
        "currentStep": "fundTargetAccount",
        "createdAt": "2026-03-09T00:02:00Z",
        "updatedAt": "2026-03-09T00:02:00Z",
        "fundAndActionPlan": build_fund_and_action_plan(),
        "fundingStep": {
            "required": True,
            "status": "pending",
            "summary": "Await funding submission",
            "updatedAt": "2026-03-09T00:02:00Z",
        },
        "followUpStep": {
            "status": "pending",
            "summary": "Await follow-up execution",
            "updatedAt": "2026-03-09T00:02:00Z",
        },
    }


def build_asset_transfer_result() -> dict[str, Any]:
    return {
        "status": "confirmed",
        "summary": "Funding confirmed",
        "updatedAt": "2026-03-09T00:03:00Z",
        "submittedAt": "2026-03-09T00:02:30Z",
        "completedAt": "2026-03-09T00:03:00Z",
        "attempt": 1,
        "chainId": 8453,
        "txHash": HEX64_F,
        "receipt": {
            "blockNumber": "123",
            "blockHash": BLOCK_HASH,
            "confirmations": 2,
        },
        "output": {"status": "ok"},
        "plan": build_funding_plan(),
    }


def build_follow_up_action_result() -> dict[str, Any]:
    return {
        "kind": "predict.createOrder",
        "target": "order/market-1",
        "executionMode": "offchain-api",
        "status": "succeeded",
        "summary": "Order created",
        "updatedAt": "2026-03-09T00:04:00Z",
        "startedAt": "2026-03-09T00:03:10Z",
        "completedAt": "2026-03-09T00:04:00Z",
        "attempt": 1,
        "reference": {"type": "orderId", "value": "order-1"},
        "output": {"orderId": "order-1"},
        "plan": build_follow_up_action_plan(),
    }


def build_prepared_asset_transfer_result() -> dict[str, Any]:
    return {
        "accountContext": build_account_context(),
        "action": {"type": "erc20Transfer", "to": FROM_ADDRESS},
        "erc20Call": {
            "tokenAddress": ASSET_ADDRESS,
            "to": FROM_ADDRESS,
            "amountRaw": "800",
        },
        "humanReadableSummary": {
            "kind": "erc20Transfer",
            "tokenAddress": ASSET_ADDRESS,
            "to": FROM_ADDRESS,
            "amountRaw": "800",
            "symbol": "USDC",
            "decimals": 6,
        },
        "signRequest": build_sign_request(),
        "policyCheck": build_policy_check_result(),
        "txRequest": {
            "from": FROM_ADDRESS,
            "to": VAULT_ADDRESS,
            "data": "0xdeadbeef",
            "value": "0",
            "gas": "210000",
        },
    }


def build_simulated_asset_transfer_result() -> dict[str, Any]:
    prepared = build_prepared_asset_transfer_result()
    del prepared["txRequest"]
    return {
        **prepared,
        "simulate": {
            "ok": True,
            "blockNumber": 123,
            "preAssets": "2000",
            "postAssets": "1200",
        },
    }


def write_fake_mcp_server(
    tmp_path: Path,
    *,
    tools: list[str] | str,
    tool_results: dict[str, dict[str, object]],
    request_framing: str = "auto",
    framing: str = "content-length",
) -> str:
    fixture_path = tmp_path / "fake-mcp-fixture.json"
    env_path = tmp_path / "observed-contract-version.txt"
    observed_env_path = tmp_path / "observed-env.json"
    server_path = tmp_path / "fake_mcp_server.py"

    fixture_path.write_text(
        json.dumps({"tools": tools, "tool_results": tool_results}),
        encoding="utf-8",
    )
    server_path.write_text(
        """
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def read_message() -> dict[str, object] | None:
    if request_framing == "newline":
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        return json.loads(line.decode("utf-8"))

    first_line = sys.stdin.buffer.readline()
    if not first_line:
        return None
    if request_framing == "auto":
        if first_line.lower().startswith(b"content-length:"):
            pass
        else:
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
Path(sys.argv[2]).write_text(
    os.getenv("ERC_MANDATED_CONTRACT_VERSION", ""),
    encoding="utf-8",
)
Path(sys.argv[3]).write_text(
    json.dumps(
        {
            "contractVersion": os.getenv("ERC_MANDATED_CONTRACT_VERSION", ""),
            "bscMainnetRpcUrl": os.getenv("BSC_MAINNET_RPC_URL"),
            "bscTestnetRpcUrl": os.getenv("BSC_TESTNET_RPC_URL"),
            "bscRpcUrl": os.getenv("BSC_RPC_URL"),
            "ercMandatedRpcUrl": os.getenv("ERC_MANDATED_RPC_URL"),
        }
    ),
    encoding="utf-8",
)
request_framing = sys.argv[4]
framing = sys.argv[5]

while True:
    request = read_message()
    if request is None:
        break

    method = request.get("method")
    request_id = request.get("id")

    if method == "notifications/initialized":
        continue

    if method == "initialize":
        response = {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "fake-mcp", "version": "0.0.0"},
            },
        }
        if framing == "newline":
            sys.stdout.write(json.dumps(response) + "\\n")
            sys.stdout.flush()
        else:
            write_message(response)
        continue

    if method == "tools/list":
        if fixture["tools"] == "__malformed__":
            response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "tools": {"unexpected": True}
                },
            }
            if framing == "newline":
                sys.stdout.write(json.dumps(response) + "\\n")
                sys.stdout.flush()
            else:
                write_message(response)
            continue

        response = {
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
        if framing == "newline":
            sys.stdout.write(json.dumps(response) + "\\n")
            sys.stdout.flush()
        else:
            write_message(response)
        continue

    if method == "tools/call":
        params = request.get("params", {})
        name = params["name"]
        tool_result = fixture["tool_results"][name]
        response = {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "content": [{"type": "text", "text": "ok"}],
                "isError": tool_result.get("isError", False),
                "structuredContent": tool_result["structuredContent"],
            },
        }
        if framing == "newline":
            sys.stdout.write(json.dumps(response) + "\\n")
            sys.stdout.flush()
        else:
            write_message(response)
        continue

    response = {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": -32601, "message": f"Unknown method: {method}"},
    }
    if framing == "newline":
        sys.stdout.write(json.dumps(response) + "\\n")
        sys.stdout.flush()
    else:
        write_message(response)
""".strip(),
        encoding="utf-8",
    )
    return (
        f"{sys.executable} {server_path} {fixture_path} {env_path} {observed_env_path} "
        f"{request_framing} {framing}"
    )


@pytest.mark.asyncio
async def test_bridge_starts_lists_tools_and_normalizes_tool_payloads(
    tmp_path: Path,
) -> None:
    command = write_fake_mcp_server(
        tmp_path,
        tools=sorted(MANDATED_V1_REQUIRED_TOOLS),
        tool_results={
            "factory_predict_vault_address": {
                "structuredContent": {"result": {"predictedVault": PREDICTED_VAULT}}
            },
            "factory_create_vault_prepare": {
                "structuredContent": {
                    "result": {
                        "predictedVault": PREDICTED_VAULT,
                        "txRequest": {
                            "from": FROM_ADDRESS,
                            "to": TX_TARGET,
                            "data": "0xdeadbeef",
                            "value": "0",
                            "gas": "210000",
                        },
                    }
                }
            },
            "vault_health_check": {
                "structuredContent": {
                    "result": {
                        "blockNumber": 123,
                        "vault": VAULT_ADDRESS,
                        "mandateAuthority": AUTHORITY_ADDRESS,
                        "authorityEpoch": "7",
                        "pendingAuthority": AUTHORITY_ADDRESS,
                        "nonceThreshold": "2",
                        "totalAssets": "9000",
                    }
                }
            },
        },
    )
    config = PredictConfig.from_env(mandated_env(command))
    bridge = MandatedVaultMcpBridge(config)

    try:
        await bridge.connect()

        assert bridge.runtime_ready is True
        assert set(bridge.available_tools) == MANDATED_V1_REQUIRED_TOOLS
        assert (tmp_path / "observed-contract-version.txt").read_text(
            encoding="utf-8"
        ) == "v0.3.0-agent-contract"

        predicted = await bridge.predict_vault_address(
            factory=FACTORY_ADDRESS,
            asset=ASSET_ADDRESS,
            name="Mandated Vault",
            symbol="MVLT",
            authority=AUTHORITY_ADDRESS,
            salt=SALT,
        )
        prepared = await bridge.prepare_create_vault(
            from_address=FROM_ADDRESS,
            factory=FACTORY_ADDRESS,
            asset=ASSET_ADDRESS,
            name="Mandated Vault",
            symbol="MVLT",
            authority=AUTHORITY_ADDRESS,
            salt=SALT,
        )
        health = await bridge.health_check(VAULT_ADDRESS)

        assert predicted.predictedVault == PREDICTED_VAULT
        assert prepared.predictedVault == PREDICTED_VAULT
        assert prepared.txRequest.to == TX_TARGET
        assert prepared.txRequest.gas == "210000"
        assert health.vault == VAULT_ADDRESS
        assert health.totalAssets == "9000"
    finally:
        await bridge.close()


@pytest.mark.asyncio
async def test_bridge_supports_newline_delimited_stdio_servers(
    tmp_path: Path,
) -> None:
    command = write_fake_mcp_server(
        tmp_path,
        tools=sorted(MANDATED_V1_REQUIRED_TOOLS),
        tool_results={
            "factory_predict_vault_address": {
                "structuredContent": {"result": {"predictedVault": PREDICTED_VAULT}}
            },
            "factory_create_vault_prepare": {
                "structuredContent": {
                    "result": {
                        "predictedVault": PREDICTED_VAULT,
                        "txRequest": {
                            "from": FROM_ADDRESS,
                            "to": TX_TARGET,
                            "data": "0xdeadbeef",
                            "value": "0",
                            "gas": "210000",
                        },
                    }
                }
            },
            "vault_health_check": {
                "structuredContent": {
                    "result": {
                        "blockNumber": 123,
                        "vault": VAULT_ADDRESS,
                        "mandateAuthority": AUTHORITY_ADDRESS,
                        "authorityEpoch": "7",
                        "pendingAuthority": AUTHORITY_ADDRESS,
                        "nonceThreshold": "2",
                        "totalAssets": "9000",
                    }
                }
            },
        },
        framing="newline",
    )
    config = PredictConfig.from_env(mandated_env(command))
    bridge = MandatedVaultMcpBridge(config)

    try:
        await bridge.connect()

        assert bridge.runtime_ready is True
        assert set(bridge.available_tools) == MANDATED_V1_REQUIRED_TOOLS
        health = await bridge.health_check(VAULT_ADDRESS)
        assert health.totalAssets == "9000"
    finally:
        await bridge.close()


@pytest.mark.asyncio
async def test_bridge_writes_newline_delimited_stdio_requests(
    tmp_path: Path,
) -> None:
    command = write_fake_mcp_server(
        tmp_path,
        tools=sorted(MANDATED_V1_REQUIRED_TOOLS),
        tool_results={
            "factory_predict_vault_address": {
                "structuredContent": {"result": {"predictedVault": PREDICTED_VAULT}}
            },
            "factory_create_vault_prepare": {
                "structuredContent": {
                    "result": {
                        "predictedVault": PREDICTED_VAULT,
                        "txRequest": {
                            "from": FROM_ADDRESS,
                            "to": TX_TARGET,
                            "data": "0xdeadbeef",
                            "value": "0",
                            "gas": "210000",
                        },
                    }
                }
            },
            "vault_health_check": {
                "structuredContent": {
                    "result": {
                        "blockNumber": 123,
                        "vault": VAULT_ADDRESS,
                        "mandateAuthority": AUTHORITY_ADDRESS,
                        "authorityEpoch": "7",
                        "pendingAuthority": AUTHORITY_ADDRESS,
                        "nonceThreshold": "2",
                        "totalAssets": "9000",
                    }
                }
            },
        },
        request_framing="newline",
        framing="newline",
    )
    config = PredictConfig.from_env(mandated_env(command))
    bridge = MandatedVaultMcpBridge(config)

    try:
        await bridge.connect()

        assert bridge.runtime_ready is True
        assert set(bridge.available_tools) == MANDATED_V1_REQUIRED_TOOLS
        health = await bridge.health_check(VAULT_ADDRESS)
        assert health.totalAssets == "9000"
    finally:
        await bridge.close()


@pytest.mark.asyncio
async def test_bridge_sets_default_rpc_url_for_bnb_mainnet_when_missing(
    tmp_path: Path,
) -> None:
    command = write_fake_mcp_server(
        tmp_path,
        tools=sorted(MANDATED_V1_REQUIRED_TOOLS),
        tool_results={
            "factory_predict_vault_address": {
                "structuredContent": {"result": {"predictedVault": PREDICTED_VAULT}}
            },
            "factory_create_vault_prepare": {
                "structuredContent": {
                    "result": {
                        "predictedVault": PREDICTED_VAULT,
                        "txRequest": {
                            "from": FROM_ADDRESS,
                            "to": TX_TARGET,
                            "data": "0xdeadbeef",
                            "value": "0",
                            "gas": "210000",
                        },
                    }
                }
            },
            "vault_health_check": {
                "structuredContent": {
                    "result": {
                        "blockNumber": 123,
                        "vault": VAULT_ADDRESS,
                        "mandateAuthority": AUTHORITY_ADDRESS,
                        "authorityEpoch": "7",
                        "pendingAuthority": AUTHORITY_ADDRESS,
                        "nonceThreshold": "2",
                        "totalAssets": "9000",
                    }
                }
            },
        },
    )
    config = PredictConfig.from_env(
        mandated_env(
            command,
            PREDICT_ENV="mainnet",
            PREDICT_API_KEY="test-mainnet-api-key",
            ERC_MANDATED_CHAIN_ID="56",
        )
    )
    bridge = MandatedVaultMcpBridge(config)

    try:
        await bridge.connect()

        observed = json.loads(
            (tmp_path / "observed-env.json").read_text(encoding="utf-8")
        )
        assert observed["ercMandatedRpcUrl"] == "https://bsc-dataseed.bnbchain.org/"
        assert observed["contractVersion"] == "v0.3.0-agent-contract"
    finally:
        await bridge.close()


@pytest.mark.asyncio
async def test_bridge_supports_vault_bootstrap_runtime_and_parses_plan_result(
    tmp_path: Path,
) -> None:
    command = write_fake_mcp_server(
        tmp_path,
        tools=sorted(MANDATED_BOOTSTRAP_REQUIRED_TOOLS),
        tool_results={
            "vault_bootstrap": {
                "structuredContent": {
                    "result": {
                        "chainId": 56,
                        "mode": "plan",
                        "factory": FACTORY_ADDRESS,
                        "asset": ASSET_ADDRESS,
                        "signerAddress": AUTHORITY_ADDRESS,
                        "predictedVault": PREDICTED_VAULT,
                        "deployedVault": PREDICTED_VAULT,
                        "alreadyDeployed": False,
                        "deploymentStatus": "planned",
                        "authorityConfig": {
                            "mode": "single_key",
                            "authority": AUTHORITY_ADDRESS,
                            "executor": AUTHORITY_ADDRESS,
                        },
                        "createTx": {
                            "mode": "plan",
                            "txRequest": {
                                "from": AUTHORITY_ADDRESS,
                                "to": TX_TARGET,
                                "data": "0xdeadbeef",
                                "value": "0",
                            },
                        },
                        "accountContext": build_account_context(),
                        "fundingPolicy": build_funding_policy(),
                        "envBlock": "ERC_MANDATED_VAULT_ADDRESS=0x...",
                        "configBlock": "{\"vault\":\"0x...\"}",
                    }
                }
            }
        },
    )
    config = PredictConfig.from_env(mandated_env(command))
    bridge = MandatedVaultMcpBridge(config)

    try:
        await bridge.connect()

        assert bridge.runtime_ready is True
        assert bridge.missing_required_tools == frozenset()

        bootstrap = await bridge.vault_bootstrap(
            factory=FACTORY_ADDRESS,
            asset=ASSET_ADDRESS,
            name="Mandated Vault",
            symbol="MVLT",
            salt=SALT,
            signer_address=AUTHORITY_ADDRESS,
            mode="plan",
            authority_mode="single_key",
            authority=AUTHORITY_ADDRESS,
            create_account_context=True,
            create_funding_policy=True,
        )

        assert bootstrap.predictedVault == PREDICTED_VAULT
        assert bootstrap.alreadyDeployed is False
        assert bootstrap.createTx is not None
        assert bootstrap.createTx.txRequest is not None
        assert bootstrap.createTx.txRequest.to == TX_TARGET
        assert bootstrap.accountContext is not None
        assert bootstrap.accountContext.executor == FROM_ADDRESS
        assert bootstrap.fundingPolicy is not None
        assert bootstrap.fundingPolicy.policyId == "policy-1"
    finally:
        await bridge.close()


@pytest.mark.asyncio
async def test_bridge_redacts_missing_binary_errors(tmp_path: Path) -> None:
    secret = "sk-super-secret"
    config = PredictConfig.from_env(
        mandated_env(f"missing-{secret}-binary", OPENROUTER_API_KEY=secret)
    )
    bridge = MandatedVaultMcpBridge(config)

    with pytest.raises(MandatedVaultMcpUnavailableError) as error:
        await bridge.connect()

    assert secret not in str(error.value)
    assert "<redacted>" in str(error.value)
    await bridge.close()


@pytest.mark.asyncio
async def test_bridge_allows_read_only_calls_but_fails_closed_for_tx_prepare_when_required_tools_missing(
    tmp_path: Path,
) -> None:
    command = write_fake_mcp_server(
        tmp_path,
        tools=["vault_health_check"],
        tool_results={
            "vault_health_check": {
                "structuredContent": {
                    "result": {
                        "blockNumber": 1,
                        "vault": VAULT_ADDRESS,
                        "mandateAuthority": AUTHORITY_ADDRESS,
                        "authorityEpoch": "1",
                        "pendingAuthority": AUTHORITY_ADDRESS,
                        "nonceThreshold": "1",
                        "totalAssets": "11",
                    }
                }
            }
        },
    )
    config = PredictConfig.from_env(mandated_env(command))
    bridge = MandatedVaultMcpBridge(config)

    try:
        await bridge.connect()

        assert bridge.runtime_ready is False
        assert bridge.missing_required_tools == frozenset(
            {"factory_predict_vault_address", "factory_create_vault_prepare"}
        )

        health = await bridge.health_check(VAULT_ADDRESS)
        assert health.totalAssets == "11"

        with pytest.raises(MandatedVaultMcpMissingToolsError) as error:
            await bridge.prepare_create_vault(
                from_address=FROM_ADDRESS,
                factory=FACTORY_ADDRESS,
                asset=ASSET_ADDRESS,
                name="Mandated Vault",
                symbol="MVLT",
                authority=AUTHORITY_ADDRESS,
                salt=SALT,
            )

        assert "factory_create_vault_prepare" in str(error.value)
    finally:
        await bridge.close()


@pytest.mark.asyncio
async def test_bridge_rejects_malformed_tool_payloads(tmp_path: Path) -> None:
    command = write_fake_mcp_server(
        tmp_path,
        tools=["vault_health_check"],
        tool_results={
            "vault_health_check": {
                "structuredContent": {
                    "result": {
                        "vault": 123,
                        "totalAssets": "oops",
                    }
                }
            }
        },
    )
    config = PredictConfig.from_env(mandated_env(command))
    bridge = MandatedVaultMcpBridge(config)

    try:
        await bridge.connect()

        with pytest.raises(ValueError, match="vault_health_check"):
            await bridge.health_check(VAULT_ADDRESS)
    finally:
        await bridge.close()


@pytest.mark.asyncio
async def test_bridge_supports_published_agent_session_and_asset_transfer_tools(
    tmp_path: Path,
) -> None:
    command = write_fake_mcp_server(
        tmp_path,
        tools=sorted(
            MANDATED_V1_REQUIRED_TOOLS.union(AGENT_SESSION_TOOLS, ASSET_TRANSFER_TOOLS)
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
                            "from": FROM_ADDRESS,
                            "to": TX_TARGET,
                            "data": "0xdeadbeef",
                            "value": "0",
                        },
                    }
                }
            },
            "vault_health_check": {
                "structuredContent": {
                    "result": {
                        "blockNumber": 123,
                        "vault": VAULT_ADDRESS,
                        "mandateAuthority": AUTHORITY_ADDRESS,
                        "authorityEpoch": "7",
                        "pendingAuthority": AUTHORITY_ADDRESS,
                        "nonceThreshold": "2",
                        "totalAssets": "9000",
                    }
                }
            },
            "agent_account_context_create": {
                "structuredContent": {
                    "result": {"accountContext": build_account_context()}
                }
            },
            "agent_funding_policy_create": {
                "structuredContent": {
                    "result": {"fundingPolicy": build_funding_policy()}
                }
            },
            "agent_build_fund_and_action_plan": {
                "structuredContent": {"result": build_fund_and_action_plan()}
            },
            "agent_fund_and_action_session_create": {
                "structuredContent": {"result": {"session": build_session()}}
            },
            "agent_fund_and_action_session_next_step": {
                "structuredContent": {
                    "result": {
                        "session": build_session(),
                        "task": {
                            "kind": "submitFunding",
                            "summary": "Submit vault funding transaction",
                            "fundingPlan": build_funding_plan(),
                        },
                    }
                }
            },
            "agent_fund_and_action_session_apply_event": {
                "structuredContent": {
                    "result": {
                        "session": {
                            **build_session(),
                            "status": "pendingFollowUp",
                            "currentStep": "followUpAction",
                            "updatedAt": "2026-03-09T00:03:00Z",
                            "fundingStep": {
                                "required": True,
                                "status": "succeeded",
                                "summary": "Funding confirmed",
                                "updatedAt": "2026-03-09T00:03:00Z",
                                "result": build_asset_transfer_result(),
                            },
                        }
                    }
                }
            },
            "agent_follow_up_action_result_create": {
                "structuredContent": {
                    "result": {"followUpActionResult": build_follow_up_action_result()}
                }
            },
            "vault_asset_transfer_result_create": {
                "structuredContent": {
                    "result": {"assetTransferResult": build_asset_transfer_result()}
                }
            },
            "vault_check_asset_transfer_policy": {
                "structuredContent": {"result": build_policy_check_result()}
            },
            "vault_build_asset_transfer_plan_from_context": {
                "structuredContent": {"result": build_funding_plan()}
            },
            "vault_simulate_asset_transfer_from_context": {
                "structuredContent": {"result": build_simulated_asset_transfer_result()}
            },
            "vault_prepare_asset_transfer_from_context": {
                "structuredContent": {"result": build_prepared_asset_transfer_result()}
            },
        },
    )
    config = PredictConfig.from_env(mandated_env(command))
    bridge = MandatedVaultMcpBridge(config)

    try:
        await bridge.connect()

        account_context = await bridge.create_agent_account_context(
            agent_id="agent-1",
            vault=VAULT_ADDRESS,
            authority=AUTHORITY_ADDRESS,
            executor=FROM_ADDRESS,
            asset_registry_ref="registry/usdc",
            funding_policy_ref="policy-1",
            defaults=build_account_context()["defaults"],
            created_at="2026-03-09T00:00:00Z",
            updated_at="2026-03-09T00:05:00Z",
        )
        funding_policy = await bridge.create_agent_funding_policy(
            policy_id="policy-1",
            allowed_token_addresses=[ASSET_ADDRESS],
            allowed_recipients=[FROM_ADDRESS],
            max_amount_per_tx="1000",
            max_amount_per_window="5000",
            window_seconds=3600,
            expires_at="2026-03-10T00:00:00Z",
            repeatable=True,
            created_at="2026-03-09T00:00:00Z",
            updated_at="2026-03-09T00:05:00Z",
        )
        plan = await bridge.build_agent_fund_and_action_plan(
            account_context=build_account_context(),
            funding_policy=build_funding_policy(),
            funding_target={
                "label": "predict-account-usdc",
                "recipient": FROM_ADDRESS,
                "tokenAddress": ASSET_ADDRESS,
                "requiredAmountRaw": "1000",
                "currentBalanceRaw": "200",
                "balanceSnapshot": {
                    "snapshotAt": "2026-03-09T00:00:00Z",
                    "maxStalenessSeconds": 60,
                },
            },
            funding_context={
                "nonce": "7",
                "deadline": "9999999999",
                "authorityEpoch": "2",
                "allowedAdaptersRoot": HEX64_A,
                "maxDrawdownBps": "100",
                "maxCumulativeDrawdownBps": "200",
                "payloadBinding": "actionsDigest",
                "extensions": "0x",
                "executeContext": {
                    "from": FROM_ADDRESS,
                    "signature": "0x1234",
                    "adapterProofs": [[HEX64_A]],
                },
            },
            follow_up_action=build_follow_up_action_intent(),
        )
        session = await bridge.create_agent_fund_and_action_session(
            fund_and_action_plan=build_fund_and_action_plan(),
            session_id="session-1",
            created_at="2026-03-09T00:02:00Z",
        )
        next_step = await bridge.next_agent_fund_and_action_session_step(
            session=build_session()
        )
        applied = await bridge.apply_agent_fund_and_action_session_event(
            session=build_session(),
            event={
                "type": "fundingConfirmed",
                "updatedAt": "2026-03-09T00:03:00Z",
                "assetTransferResult": build_asset_transfer_result(),
            },
        )
        follow_up_result = await bridge.create_agent_follow_up_action_result(
            follow_up_action_plan=build_follow_up_action_plan(),
            status="succeeded",
            updated_at="2026-03-09T00:04:00Z",
            started_at="2026-03-09T00:03:10Z",
            completed_at="2026-03-09T00:04:00Z",
            attempt=1,
            reference={"type": "orderId", "value": "order-1"},
            output={"orderId": "order-1"},
        )
        asset_transfer_result = await bridge.create_vault_asset_transfer_result(
            asset_transfer_plan=build_funding_plan(),
            status="confirmed",
            updated_at="2026-03-09T00:03:00Z",
            submitted_at="2026-03-09T00:02:30Z",
            completed_at="2026-03-09T00:03:00Z",
            attempt=1,
            chain_id=8453,
            tx_hash=HEX64_F,
            receipt={
                "blockNumber": "123",
                "blockHash": BLOCK_HASH,
                "confirmations": 2,
            },
            output={"status": "ok"},
        )
        policy_check = await bridge.check_vault_asset_transfer_policy(
            funding_policy=build_funding_policy(),
            token_address=ASSET_ADDRESS,
            to=FROM_ADDRESS,
            amount_raw="800",
            now="2026-03-09T00:01:00Z",
            current_spent_in_window="100",
        )
        asset_plan = await bridge.build_vault_asset_transfer_plan_from_context(
            account_context=build_account_context(),
            funding_policy=build_funding_policy(),
            token_address=ASSET_ADDRESS,
            to=FROM_ADDRESS,
            amount_raw="800",
            nonce="7",
            deadline="9999999999",
            authority_epoch="2",
            allowed_adapters_root=HEX64_A,
            max_drawdown_bps="100",
            max_cumulative_drawdown_bps="200",
            payload_binding="actionsDigest",
            extensions="0x",
            symbol="USDC",
            decimals=6,
            policy_evaluation={
                "now": "2026-03-09T00:01:00Z",
                "currentSpentInWindow": "100",
            },
        )
        simulated = await bridge.simulate_vault_asset_transfer_from_context(
            account_context=build_account_context(),
            funding_policy=build_funding_policy(),
            from_address=FROM_ADDRESS,
            token_address=ASSET_ADDRESS,
            to=FROM_ADDRESS,
            amount_raw="800",
            nonce="7",
            deadline="9999999999",
            authority_epoch="2",
            allowed_adapters_root=HEX64_A,
            max_drawdown_bps="100",
            max_cumulative_drawdown_bps="200",
            payload_binding="actionsDigest",
            extensions="0x",
            symbol="USDC",
            decimals=6,
            policy_evaluation={
                "now": "2026-03-09T00:01:00Z",
                "currentSpentInWindow": "100",
            },
            signature="0x1234",
            adapter_proofs=[[HEX64_A]],
        )
        prepared = await bridge.prepare_vault_asset_transfer_from_context(
            account_context=build_account_context(),
            funding_policy=build_funding_policy(),
            from_address=FROM_ADDRESS,
            token_address=ASSET_ADDRESS,
            to=FROM_ADDRESS,
            amount_raw="800",
            nonce="7",
            deadline="9999999999",
            authority_epoch="2",
            allowed_adapters_root=HEX64_A,
            max_drawdown_bps="100",
            max_cumulative_drawdown_bps="200",
            payload_binding="actionsDigest",
            extensions="0x",
            symbol="USDC",
            decimals=6,
            policy_evaluation={
                "now": "2026-03-09T00:01:00Z",
                "currentSpentInWindow": "100",
            },
            signature="0x1234",
            adapter_proofs=[[HEX64_A]],
        )

        assert account_context.accountContext.agentId == "agent-1"
        assert funding_policy.fundingPolicy.policyId == "policy-1"
        assert plan.fundingPlan is not None
        assert plan.fundingPlan.humanReadableSummary.amountRaw == "800"
        assert session.session.sessionId == "session-1"
        assert next_step.task.kind == "submitFunding"
        assert applied.session.status == "pendingFollowUp"
        assert follow_up_result.followUpActionResult.reference is not None
        assert follow_up_result.followUpActionResult.reference.value == "order-1"
        assert asset_transfer_result.assetTransferResult.txHash == HEX64_F
        assert policy_check.allowed is True
        assert asset_plan.accountContext.vault == VAULT_ADDRESS
        assert simulated.simulate.ok is True
        assert prepared.txRequest.to == VAULT_ADDRESS
    finally:
        await bridge.close()


@pytest.mark.asyncio
async def test_bridge_scopes_missing_tool_fail_closed_to_requested_new_operation(
    tmp_path: Path,
) -> None:
    command = write_fake_mcp_server(
        tmp_path,
        tools=sorted(
            MANDATED_V1_REQUIRED_TOOLS.union({"agent_account_context_create"})
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
                            "from": FROM_ADDRESS,
                            "to": TX_TARGET,
                            "data": "0xdeadbeef",
                            "value": "0",
                        },
                    }
                }
            },
            "vault_health_check": {
                "structuredContent": {
                    "result": {
                        "blockNumber": 123,
                        "vault": VAULT_ADDRESS,
                        "mandateAuthority": AUTHORITY_ADDRESS,
                        "authorityEpoch": "7",
                        "pendingAuthority": AUTHORITY_ADDRESS,
                        "nonceThreshold": "2",
                        "totalAssets": "9000",
                    }
                }
            },
            "agent_account_context_create": {
                "structuredContent": {
                    "result": {"accountContext": build_account_context()}
                }
            },
        },
    )
    config = PredictConfig.from_env(mandated_env(command))
    bridge = MandatedVaultMcpBridge(config)

    try:
        await bridge.connect()

        health = await bridge.health_check(VAULT_ADDRESS)
        context_result = await bridge.create_agent_account_context(
            agent_id="agent-1",
            vault=VAULT_ADDRESS,
            authority=AUTHORITY_ADDRESS,
            executor=FROM_ADDRESS,
        )

        assert health.totalAssets == "9000"
        assert context_result.accountContext.executor == FROM_ADDRESS

        with pytest.raises(MandatedVaultMcpMissingToolsError) as plan_error:
            await bridge.build_agent_fund_and_action_plan(
                account_context=build_account_context(),
                funding_target={
                    "label": "predict-account-usdc",
                    "recipient": FROM_ADDRESS,
                    "tokenAddress": ASSET_ADDRESS,
                    "requiredAmountRaw": "1000",
                    "currentBalanceRaw": "200",
                    "balanceSnapshot": {
                        "snapshotAt": "2026-03-09T00:00:00Z",
                        "maxStalenessSeconds": 60,
                    },
                },
                funding_context={
                    "nonce": "7",
                    "deadline": "9999999999",
                    "authorityEpoch": "2",
                },
                follow_up_action=build_follow_up_action_intent(),
            )

        assert plan_error.value.missing_tools == frozenset(
            {"agent_build_fund_and_action_plan"}
        )

        with pytest.raises(MandatedVaultMcpMissingToolsError) as transfer_error:
            await bridge.build_vault_asset_transfer_plan_from_context(
                account_context=build_account_context(),
                token_address=ASSET_ADDRESS,
                to=FROM_ADDRESS,
                amount_raw="800",
                nonce="7",
                deadline="9999999999",
                authority_epoch="2",
            )

        assert transfer_error.value.missing_tools == frozenset(
            {"vault_build_asset_transfer_plan_from_context"}
        )
    finally:
        await bridge.close()


@pytest.mark.asyncio
async def test_bridge_cleans_up_when_tool_listing_is_malformed(tmp_path: Path) -> None:
    command = write_fake_mcp_server(
        tmp_path,
        tools="__malformed__",
        tool_results={},
    )

    config = PredictConfig.from_env(mandated_env(command))
    bridge = MandatedVaultMcpBridge(config)

    with pytest.raises(MandatedVaultMcpUnavailableError, match="tools/list"):
        await bridge.connect()

    assert bridge.available_tools == frozenset()
    await bridge.close()
