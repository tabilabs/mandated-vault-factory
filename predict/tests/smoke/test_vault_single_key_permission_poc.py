from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from eth_account import Account

PREDICT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = PREDICT_ROOT / "scripts" / "poc_vault_single_key_permissions.py"
ARTIFACT_PATH = (
    PREDICT_ROOT
    / "artifacts"
    / "reports"
    / "autonomous-preflight"
    / "single-key-permissions.json"
)
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
PREDICTED_VAULT = "0x5555555555555555555555555555555555555555"


def _typed_data(*, executor_address: str) -> dict[str, object]:
    return {
        "types": {
            "EIP712Domain": [
                {"name": "name", "type": "string"},
                {"name": "chainId", "type": "uint256"},
                {"name": "verifyingContract", "type": "address"},
            ],
            "Mandate": [
                {"name": "vault", "type": "address"},
                {"name": "executor", "type": "address"},
                {"name": "nonce", "type": "uint256"},
                {"name": "authorityEpoch", "type": "uint256"},
            ],
        },
        "primaryType": "Mandate",
        "domain": {
            "name": "Mandated",
            "chainId": CHAIN_ID,
            "verifyingContract": VAULT_ADDRESS,
        },
        "message": {
            "vault": VAULT_ADDRESS,
            "executor": executor_address,
            "nonce": 1,
            "authorityEpoch": 7,
        },
    }


def _tool_results(
    *, authority_address: str, executor_address: str
) -> dict[str, dict[str, object]]:
    sign_request = {
        "typedData": _typed_data(executor_address=executor_address),
        "mandate": {
            "vault": VAULT_ADDRESS,
            "executor": executor_address,
            "nonce": "1",
            "deadline": "9999999999",
            "authorityEpoch": "7",
            "allowedAdaptersRoot": HEX64_A,
            "maxDrawdownBps": "100",
            "maxCumulativeDrawdownBps": "200",
            "payloadDigest": HEX64_B,
            "extensionsHash": HEX64_C,
        },
        "mandateHash": HEX64_D,
        "actionsDigest": HEX64_B,
        "extensionsHash": HEX64_C,
    }
    return {
        "factory_predict_vault_address": {
            "structuredContent": {"result": {"predictedVault": PREDICTED_VAULT}}
        },
        "factory_create_vault_prepare": {
            "structuredContent": {
                "result": {
                    "predictedVault": PREDICTED_VAULT,
                    "txRequest": {
                        "from": authority_address,
                        "to": VAULT_ADDRESS,
                        "data": "0xfeedbeef",
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
                    "mandateAuthority": authority_address,
                    "authorityEpoch": "7",
                    "pendingAuthority": authority_address,
                    "nonceThreshold": "1",
                    "totalAssets": "100",
                }
            }
        },
        "agent_account_context_create": {
            "structuredContent": {
                "result": {
                    "accountContext": {
                        "agentId": "single-key-permissions-poc",
                        "chainId": CHAIN_ID,
                        "vault": VAULT_ADDRESS,
                        "authority": authority_address,
                        "executor": executor_address,
                        "assetRegistryRef": f"poc/{TOKEN_ADDRESS.lower()}",
                        "fundingPolicyRef": f"single-key-poc:{authority_address.lower()}",
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
                }
            }
        },
        "agent_funding_policy_create": {
            "structuredContent": {
                "result": {
                    "fundingPolicy": {
                        "policyId": f"single-key-poc:{authority_address.lower()}",
                        "allowedTokenAddresses": [TOKEN_ADDRESS],
                        "allowedRecipients": [authority_address],
                        "maxAmountPerTx": "1",
                        "maxAmountPerWindow": "1",
                        "windowSeconds": 3600,
                        "expiresAt": "2099-01-01T00:00:00Z",
                        "repeatable": True,
                        "createdAt": "2026-03-10T00:00:00Z",
                        "updatedAt": "2026-03-10T00:05:00Z",
                    }
                }
            }
        },
        "vault_build_asset_transfer_plan_from_context": {
            "structuredContent": {
                "result": {
                    "accountContext": {
                        "agentId": "single-key-permissions-poc",
                        "chainId": CHAIN_ID,
                        "vault": VAULT_ADDRESS,
                        "authority": authority_address,
                        "executor": executor_address,
                        "assetRegistryRef": f"poc/{TOKEN_ADDRESS.lower()}",
                        "fundingPolicyRef": f"single-key-poc:{authority_address.lower()}",
                        "defaults": {
                            "allowedAdaptersRoot": HEX64_A,
                            "maxDrawdownBps": "100",
                            "maxCumulativeDrawdownBps": "200",
                            "payloadBinding": "actionsDigest",
                            "extensions": "0x",
                        },
                        "createdAt": "2026-03-10T00:00:00Z",
                        "updatedAt": "2026-03-10T00:05:00Z",
                    },
                    "action": {"type": "erc20Transfer", "to": authority_address},
                    "erc20Call": {
                        "tokenAddress": TOKEN_ADDRESS,
                        "to": authority_address,
                        "amountRaw": "1",
                    },
                    "humanReadableSummary": {
                        "kind": "erc20Transfer",
                        "tokenAddress": TOKEN_ADDRESS,
                        "to": authority_address,
                        "amountRaw": "1",
                    },
                    "signRequest": sign_request,
                    "policyCheck": {
                        "allowed": True,
                        "fundingPolicy": {
                            "policyId": f"single-key-poc:{authority_address.lower()}",
                            "allowedTokenAddresses": [TOKEN_ADDRESS],
                            "allowedRecipients": [authority_address],
                            "maxAmountPerTx": "1",
                            "maxAmountPerWindow": "1",
                            "windowSeconds": 3600,
                            "expiresAt": "2099-01-01T00:00:00Z",
                            "repeatable": True,
                            "createdAt": "2026-03-10T00:00:00Z",
                            "updatedAt": "2026-03-10T00:05:00Z",
                        },
                        "violations": [],
                    },
                }
            }
        },
        "vault_simulate_asset_transfer_from_context": {
            "structuredContent": {
                "result": {
                    "accountContext": {
                        "agentId": "single-key-permissions-poc",
                        "chainId": CHAIN_ID,
                        "vault": VAULT_ADDRESS,
                        "authority": authority_address,
                        "executor": executor_address,
                        "assetRegistryRef": f"poc/{TOKEN_ADDRESS.lower()}",
                        "fundingPolicyRef": f"single-key-poc:{authority_address.lower()}",
                        "defaults": {
                            "allowedAdaptersRoot": HEX64_A,
                            "maxDrawdownBps": "100",
                            "maxCumulativeDrawdownBps": "200",
                            "payloadBinding": "actionsDigest",
                            "extensions": "0x",
                        },
                        "createdAt": "2026-03-10T00:00:00Z",
                        "updatedAt": "2026-03-10T00:05:00Z",
                    },
                    "action": {"type": "erc20Transfer", "to": authority_address},
                    "erc20Call": {
                        "tokenAddress": TOKEN_ADDRESS,
                        "to": authority_address,
                        "amountRaw": "1",
                    },
                    "humanReadableSummary": {
                        "kind": "erc20Transfer",
                        "tokenAddress": TOKEN_ADDRESS,
                        "to": authority_address,
                        "amountRaw": "1",
                    },
                    "signRequest": sign_request,
                    "policyCheck": {
                        "allowed": True,
                        "fundingPolicy": {
                            "policyId": f"single-key-poc:{authority_address.lower()}",
                            "allowedTokenAddresses": [TOKEN_ADDRESS],
                            "allowedRecipients": [authority_address],
                            "maxAmountPerTx": "1",
                            "maxAmountPerWindow": "1",
                            "windowSeconds": 3600,
                            "expiresAt": "2099-01-01T00:00:00Z",
                            "repeatable": True,
                            "createdAt": "2026-03-10T00:00:00Z",
                            "updatedAt": "2026-03-10T00:05:00Z",
                        },
                        "violations": [],
                    },
                    "simulate": {
                        "ok": True,
                        "blockNumber": 123,
                        "preAssets": "10",
                        "postAssets": "9",
                    },
                }
            }
        },
        "vault_prepare_asset_transfer_from_context": {
            "structuredContent": {
                "result": {
                    "accountContext": {
                        "agentId": "single-key-permissions-poc",
                        "chainId": CHAIN_ID,
                        "vault": VAULT_ADDRESS,
                        "authority": authority_address,
                        "executor": executor_address,
                        "assetRegistryRef": f"poc/{TOKEN_ADDRESS.lower()}",
                        "fundingPolicyRef": f"single-key-poc:{authority_address.lower()}",
                        "defaults": {
                            "allowedAdaptersRoot": HEX64_A,
                            "maxDrawdownBps": "100",
                            "maxCumulativeDrawdownBps": "200",
                            "payloadBinding": "actionsDigest",
                            "extensions": "0x",
                        },
                        "createdAt": "2026-03-10T00:00:00Z",
                        "updatedAt": "2026-03-10T00:05:00Z",
                    },
                    "action": {"type": "erc20Transfer", "to": authority_address},
                    "erc20Call": {
                        "tokenAddress": TOKEN_ADDRESS,
                        "to": authority_address,
                        "amountRaw": "1",
                    },
                    "humanReadableSummary": {
                        "kind": "erc20Transfer",
                        "tokenAddress": TOKEN_ADDRESS,
                        "to": authority_address,
                        "amountRaw": "1",
                    },
                    "signRequest": sign_request,
                    "policyCheck": {
                        "allowed": True,
                        "fundingPolicy": {
                            "policyId": f"single-key-poc:{authority_address.lower()}",
                            "allowedTokenAddresses": [TOKEN_ADDRESS],
                            "allowedRecipients": [authority_address],
                            "maxAmountPerTx": "1",
                            "maxAmountPerWindow": "1",
                            "windowSeconds": 3600,
                            "expiresAt": "2099-01-01T00:00:00Z",
                            "repeatable": True,
                            "createdAt": "2026-03-10T00:00:00Z",
                            "updatedAt": "2026-03-10T00:05:00Z",
                        },
                        "violations": [],
                    },
                    "txRequest": {
                        "from": executor_address,
                        "to": VAULT_ADDRESS,
                        "data": "0xdeadbeef",
                        "value": "0",
                        "gas": "210000",
                    },
                }
            }
        },
    }


def _write_fake_mcp_server(
    tmp_path: Path,
    *,
    authority_address: str,
    executor_address: str,
) -> str:
    fixture_path = tmp_path / "fake-mcp-fixture.json"
    server_path = tmp_path / "fake_mcp_server.py"
    tools = [
        "factory_predict_vault_address",
        "factory_create_vault_prepare",
        "vault_health_check",
        "agent_account_context_create",
        "agent_funding_policy_create",
        "vault_build_asset_transfer_plan_from_context",
        "vault_simulate_asset_transfer_from_context",
        "vault_prepare_asset_transfer_from_context",
    ]
    fixture_path.write_text(
        json.dumps(
            {
                "tools": tools,
                "tool_results": _tool_results(
                    authority_address=authority_address,
                    executor_address=executor_address,
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
    return json.loads(sys.stdin.buffer.read(length).decode("utf-8"))


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
                    "serverInfo": {"name": "fake-mcp", "version": "0.0.0"},
                    "capabilities": {"tools": {}},
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
                        {"name": tool_name, "description": tool_name}
                        for tool_name in fixture["tools"]
                    ]
                },
            }
        )
        continue
    if method == "tools/call":
        params = request.get("params", {})
        tool_name = params.get("name")
        tool_result = fixture["tool_results"][tool_name]
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


def test_single_key_permission_poc_missing_env_writes_no_go_artifact(
    tmp_path: Path,
) -> None:
    result, artifact = _run_poc(env={"PREDICT_STORAGE_DIR": str(tmp_path)})

    assert result.returncode == 1
    assert artifact["verdict"] == "NO-GO"
    assert (
        artifact["singleKeyPermissionEvidence"]["sameKeySatisfiesAuthorityAndExecutor"]
        is False
    )
    assert "missing vaultAddress" in artifact["reasons"]
    assert ARTIFACT_PATH.exists()


def test_single_key_permission_poc_passes_with_authority_fallback_executor(
    tmp_path: Path,
) -> None:
    fake_command = _write_fake_mcp_server(
        tmp_path,
        authority_address=AUTHORITY_ADDRESS,
        executor_address=AUTHORITY_ADDRESS,
    )
    result, artifact = _run_poc(
        env={
            "PREDICT_ENV": "testnet",
            "PREDICT_STORAGE_DIR": str(tmp_path),
            "PREDICT_WALLET_MODE": "mandated-vault",
            "ERC_MANDATED_VAULT_ADDRESS": VAULT_ADDRESS,
            "ERC_MANDATED_VAULT_ASSET_ADDRESS": TOKEN_ADDRESS,
            "ERC_MANDATED_AUTHORITY_PRIVATE_KEY": AUTHORITY_PRIVATE_KEY,
            "ERC_MANDATED_CHAIN_ID": str(CHAIN_ID),
            "ERC_MANDATED_MCP_COMMAND": fake_command,
            "PREDICT_SINGLE_KEY_POC_ALLOWED_ADAPTERS_ROOT": HEX64_A,
        }
    )

    assert result.returncode == 0, result.stderr
    assert artifact["verdict"] == "PASS"
    assert artifact["authorityAddress"] == AUTHORITY_ADDRESS
    assert artifact["executorAddress"] == AUTHORITY_ADDRESS
    evidence = artifact["singleKeyPermissionEvidence"]
    assert evidence["configuredExecutorKeySource"] == "authority-fallback"
    assert evidence["configuredSingleKey"] is True
    assert evidence["recoveredSignerMatchesAuthorityKey"] is True
    assert evidence["preparedTxFrom"] == AUTHORITY_ADDRESS
    assert evidence["sameKeySatisfiesAuthorityAndExecutor"] is True
    assert artifact["reasons"] == []


def test_single_key_permission_poc_rejects_executor_key_mismatch(
    tmp_path: Path,
) -> None:
    fake_command = _write_fake_mcp_server(
        tmp_path,
        authority_address=AUTHORITY_ADDRESS,
        executor_address=EXECUTOR_ADDRESS,
    )
    result, artifact = _run_poc(
        env={
            "PREDICT_ENV": "testnet",
            "PREDICT_STORAGE_DIR": str(tmp_path),
            "PREDICT_WALLET_MODE": "mandated-vault",
            "ERC_MANDATED_VAULT_ADDRESS": VAULT_ADDRESS,
            "ERC_MANDATED_VAULT_ASSET_ADDRESS": TOKEN_ADDRESS,
            "ERC_MANDATED_AUTHORITY_PRIVATE_KEY": AUTHORITY_PRIVATE_KEY,
            "ERC_MANDATED_EXECUTOR_PRIVATE_KEY": EXECUTOR_PRIVATE_KEY,
            "ERC_MANDATED_CHAIN_ID": str(CHAIN_ID),
            "ERC_MANDATED_MCP_COMMAND": fake_command,
            "PREDICT_SINGLE_KEY_POC_ALLOWED_ADAPTERS_ROOT": HEX64_A,
        }
    )

    assert result.returncode == 1
    assert artifact["verdict"] == "NO-GO"
    assert artifact["executorAddress"] == EXECUTOR_ADDRESS
    evidence = artifact["singleKeyPermissionEvidence"]
    assert evidence["configuredSingleKey"] is False
    assert evidence["sameKeySatisfiesAuthorityAndExecutor"] is False
    assert "configured executor key does not match authority key" in artifact["reasons"]
