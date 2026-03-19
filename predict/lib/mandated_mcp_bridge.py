from __future__ import annotations

import asyncio
import json
import os
import shlex
from collections.abc import Mapping, Sequence
from typing import Any, Literal, Self, TypeVar

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from predict_sdk.constants import RPC_URLS_BY_CHAIN_ID

from .config import PredictConfig, redact_text


MANDATED_V1_REQUIRED_TOOLS = frozenset(
    {
        "factory_predict_vault_address",
        "factory_create_vault_prepare",
        "vault_health_check",
    }
)
MANDATED_BOOTSTRAP_REQUIRED_TOOLS = frozenset({"vault_bootstrap"})

MANDATED_AGENT_SESSION_TOOLS = frozenset(
    {
        "agent_account_context_create",
        "agent_funding_policy_create",
        "agent_build_fund_and_action_plan",
        "agent_fund_and_action_session_create",
        "agent_fund_and_action_session_next_step",
        "agent_fund_and_action_session_apply_event",
        "agent_follow_up_action_result_create",
    }
)

MANDATED_ASSET_TRANSFER_TOOLS = frozenset(
    {
        "vault_asset_transfer_result_create",
        "vault_check_asset_transfer_policy",
        "vault_build_asset_transfer_plan_from_context",
        "vault_simulate_asset_transfer_from_context",
        "vault_prepare_asset_transfer_from_context",
    }
)

_CLIENT_PROTOCOL_VERSION = "2024-11-05"
_CLIENT_NAME = "predictclaw"
_CLIENT_VERSION = "0.1.0"
_DEFAULT_RPC_URL_BY_CHAIN_ID = {
    int(chain_id): rpc_url for chain_id, rpc_url in RPC_URLS_BY_CHAIN_ID.items()
}
_RPC_ENV_KEYS_BY_CHAIN_ID = {
    56: ("BSC_MAINNET_RPC_URL", "BSC_RPC_URL", "ERC_MANDATED_RPC_URL"),
    97: ("BSC_TESTNET_RPC_URL", "BSC_RPC_URL", "ERC_MANDATED_RPC_URL"),
}


class MandatedVaultMcpError(RuntimeError):
    pass


class MandatedVaultMcpUnavailableError(MandatedVaultMcpError):
    pass


class MandatedVaultMcpMissingToolsError(MandatedVaultMcpError):
    def __init__(
        self,
        missing_tools: Sequence[str],
        *,
        operation: str | None = None,
    ) -> None:
        unique_tools = tuple(sorted(set(missing_tools)))
        self.missing_tools = frozenset(unique_tools)
        missing = ", ".join(unique_tools)
        if operation:
            message = f"Mandated-vault MCP cannot perform {operation}; missing required tools: {missing}."
        else:
            message = f"Mandated-vault MCP is missing required tools: {missing}."
        super().__init__(message)


class _BridgeModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class McpToolDescriptor(_BridgeModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    name: str
    description: str | None = None


class McpToolError(_BridgeModel):
    code: str
    message: str
    details: dict[str, Any] | None = None
    suggestion: str | None = None


class McpTxRequest(_BridgeModel):
    from_address: str = Field(alias="from")
    to: str
    data: str
    value: str
    gas: str | None = None


class FactoryPredictVaultAddressResult(_BridgeModel):
    predictedVault: str


class FactoryCreateVaultPrepareResult(_BridgeModel):
    predictedVault: str
    txRequest: McpTxRequest


class VaultHealthCheckResult(_BridgeModel):
    blockNumber: int
    vault: str
    mandateAuthority: str
    authorityEpoch: str
    pendingAuthority: str
    nonceThreshold: str
    totalAssets: str


VaultBootstrapMode = Literal["plan", "execute"]
VaultBootstrapAuthorityMode = Literal["single_key", "dual_key"]
VaultBootstrapDeploymentStatus = Literal[
    "planned", "submitted", "confirmed", "reverted", "receipt_unknown"
]
VaultBootstrapReceiptStatus = Literal["success", "reverted", "timeout"]


class VaultBootstrapAuthorityConfig(_BridgeModel):
    mode: VaultBootstrapAuthorityMode
    authority: str
    executor: str


class VaultBootstrapCreateTx(_BridgeModel):
    mode: VaultBootstrapMode
    txRequest: McpTxRequest | None = None
    txHash: str | None = None
    receiptStatus: VaultBootstrapReceiptStatus | None = None
    blockNumber: int | None = None
    confirmations: int | None = None
    receipt: dict[str, Any] | None = None


class VaultBootstrapResult(_BridgeModel):
    chainId: int
    mode: VaultBootstrapMode
    factory: str
    asset: str
    signerAddress: str
    predictedVault: str
    deployedVault: str
    alreadyDeployed: bool
    deploymentStatus: VaultBootstrapDeploymentStatus
    authorityConfig: VaultBootstrapAuthorityConfig
    createTx: VaultBootstrapCreateTx | None = None
    vaultHealth: VaultHealthCheckResult | None = None
    accountContext: AgentAccountContext | None = None
    fundingPolicy: AgentFundingPolicy | None = None
    envBlock: str
    configBlock: str


PayloadBinding = Literal["actionsDigest", "none"]
FollowUpActionExecutionMode = Literal["offchain-api", "custom"]
FollowUpActionExecutionStatus = Literal[
    "pending", "submitted", "succeeded", "failed", "skipped"
]
FundAndActionExecutionSessionStatus = Literal[
    "pendingFunding", "pendingFollowUp", "succeeded", "failed", "skipped"
]
FundAndActionExecutionCurrentStep = Literal[
    "fundTargetAccount", "followUpAction", "none"
]
FundAndActionFundingStepStatus = Literal[
    "pending", "submitted", "succeeded", "failed", "skipped"
]
FundAndActionFollowUpStepStatus = Literal[
    "pending", "submitted", "succeeded", "failed", "skipped"
]
FundAndActionExecutionTaskKind = Literal[
    "submitFunding",
    "pollFundingResult",
    "submitFollowUp",
    "pollFollowUpResult",
    "completed",
]
AssetTransferExecutionStatus = Literal[
    "pending", "submitted", "confirmed", "failed", "skipped"
]


class AccountContextDefaults(_BridgeModel):
    allowedAdaptersRoot: str | None = None
    maxDrawdownBps: str | None = None
    maxCumulativeDrawdownBps: str | None = None
    payloadBinding: PayloadBinding | None = None
    extensions: str | None = None


class AgentAccountContext(_BridgeModel):
    agentId: str
    chainId: int
    vault: str
    authority: str
    executor: str
    assetRegistryRef: str | None = None
    fundingPolicyRef: str | None = None
    defaults: AccountContextDefaults | None = None
    createdAt: str
    updatedAt: str


class AgentAccountContextCreateResult(_BridgeModel):
    accountContext: AgentAccountContext


class AgentFundingPolicy(_BridgeModel):
    policyId: str
    allowedTokenAddresses: list[str] | None = None
    allowedRecipients: list[str] | None = None
    maxAmountPerTx: str | None = None
    maxAmountPerWindow: str | None = None
    windowSeconds: int | None = None
    expiresAt: str | None = None
    repeatable: bool | None = None
    createdAt: str
    updatedAt: str


class AgentFundingPolicyCreateResult(_BridgeModel):
    fundingPolicy: AgentFundingPolicy


class PolicyViolation(_BridgeModel):
    code: str
    field: str
    message: str


class PolicyEvaluationContext(_BridgeModel):
    now: str | None = None
    currentSpentInWindow: str | None = None


class PolicyCheckResult(_BridgeModel):
    allowed: bool
    fundingPolicy: AgentFundingPolicy
    violations: list[PolicyViolation]


class FundAndActionBalanceSnapshot(_BridgeModel):
    snapshotAt: str
    maxStalenessSeconds: int
    observedAtBlock: str | None = None
    source: str | None = None


class FollowUpActionIntent(_BridgeModel):
    kind: str
    target: str | None = None
    payload: dict[str, Any] | None = None


class AssetRequirement(_BridgeModel):
    tokenAddress: str
    amountRaw: str


class FollowUpActionPlan(_BridgeModel):
    kind: str
    target: str | None = None
    executionMode: FollowUpActionExecutionMode
    summary: str
    assetRequirement: AssetRequirement | None = None
    payload: dict[str, Any] | None = None


class FollowUpActionExecutionReference(_BridgeModel):
    type: Literal["requestId", "orderId", "txHash", "custom"]
    value: str


class FollowUpActionExecutionError(_BridgeModel):
    code: str
    message: str
    retriable: bool | None = None
    details: dict[str, Any] | None = None


class FollowUpActionResult(_BridgeModel):
    kind: str
    target: str | None = None
    executionMode: FollowUpActionExecutionMode
    status: FollowUpActionExecutionStatus
    summary: str
    updatedAt: str
    startedAt: str | None = None
    completedAt: str | None = None
    attempt: int
    reference: FollowUpActionExecutionReference | None = None
    output: dict[str, Any] | None = None
    error: FollowUpActionExecutionError | None = None
    plan: FollowUpActionPlan


class FollowUpActionResultCreateResult(_BridgeModel):
    followUpActionResult: FollowUpActionResult


class Mandate(_BridgeModel):
    vault: str
    executor: str
    nonce: str
    deadline: str
    authorityEpoch: str
    allowedAdaptersRoot: str
    maxDrawdownBps: str
    maxCumulativeDrawdownBps: str
    payloadDigest: str
    extensionsHash: str


class ExecuteBaseInput(_BridgeModel):
    chainId: int | None = None
    vault: str
    from_address: str = Field(alias="from")
    mandate: Mandate
    signature: str
    actions: list[dict[str, Any]]
    adapterProofs: list[list[str]]
    extensions: str


class AssetTransferSummary(_BridgeModel):
    kind: Literal["erc20Transfer"]
    tokenAddress: str
    to: str
    amountRaw: str
    symbol: str | None = None
    decimals: int | None = None


class SignRequestResult(_BridgeModel):
    typedData: dict[str, Any]
    mandate: Mandate
    mandateHash: str
    actionsDigest: str
    extensionsHash: str


class SimulateResult(_BridgeModel):
    ok: bool
    blockNumber: int
    preAssets: str | None = None
    postAssets: str | None = None
    revertDecoded: dict[str, Any] | None = None


class AssetTransferPlanResult(_BridgeModel):
    action: dict[str, Any]
    erc20Call: dict[str, Any]
    humanReadableSummary: AssetTransferSummary
    signRequest: SignRequestResult


class AssetTransferPlanWithContextResult(_BridgeModel):
    accountContext: AgentAccountContext
    action: dict[str, Any]
    erc20Call: dict[str, Any]
    humanReadableSummary: AssetTransferSummary
    signRequest: SignRequestResult
    policyCheck: PolicyCheckResult | None = None
    simulateExecuteInput: ExecuteBaseInput | None = None
    prepareExecuteInput: ExecuteBaseInput | None = None


class AssetTransferSimulateWithContextResult(_BridgeModel):
    accountContext: AgentAccountContext
    action: dict[str, Any]
    erc20Call: dict[str, Any]
    humanReadableSummary: AssetTransferSummary
    signRequest: SignRequestResult
    policyCheck: PolicyCheckResult | None = None
    simulate: SimulateResult


class AssetTransferPrepareWithContextResult(_BridgeModel):
    accountContext: AgentAccountContext
    action: dict[str, Any]
    erc20Call: dict[str, Any]
    humanReadableSummary: AssetTransferSummary
    signRequest: SignRequestResult
    policyCheck: PolicyCheckResult | None = None
    txRequest: McpTxRequest


class AssetTransferReceipt(_BridgeModel):
    blockNumber: str
    blockHash: str | None = None
    confirmations: int | None = None


class AssetTransferExecutionError(_BridgeModel):
    code: str
    message: str
    retriable: bool | None = None
    details: dict[str, Any] | None = None


class AssetTransferResult(_BridgeModel):
    status: AssetTransferExecutionStatus
    summary: str
    updatedAt: str
    submittedAt: str | None = None
    completedAt: str | None = None
    attempt: int
    chainId: int | None = None
    txHash: str | None = None
    receipt: AssetTransferReceipt | None = None
    output: dict[str, Any] | None = None
    error: AssetTransferExecutionError | None = None
    plan: AssetTransferPlanResult | AssetTransferPlanWithContextResult


class AssetTransferResultCreateResult(_BridgeModel):
    assetTransferResult: AssetTransferResult


class FundAndActionTargetResult(_BridgeModel):
    label: str
    recipient: str
    tokenAddress: str
    requiredAmountRaw: str
    currentBalanceRaw: str
    balanceSnapshot: FundAndActionBalanceSnapshot
    fundingShortfallRaw: str
    symbol: str | None = None
    decimals: int | None = None


class FundAndActionStep(_BridgeModel):
    kind: Literal["fundTargetAccount", "followUpAction"]
    status: Literal["required", "skipped", "pending"]
    summary: str


class FundAndActionPlanResult(_BridgeModel):
    accountContext: AgentAccountContext
    fundingPolicy: AgentFundingPolicy | None = None
    fundingTarget: FundAndActionTargetResult
    evaluatedAt: str
    fundingRequired: bool
    fundingPlan: AssetTransferPlanWithContextResult | None = None
    followUpAction: FollowUpActionIntent
    followUpActionPlan: FollowUpActionPlan
    steps: list[FundAndActionStep]


class FundAndActionFundingStepExecution(_BridgeModel):
    required: bool
    status: FundAndActionFundingStepStatus
    summary: str
    updatedAt: str
    result: AssetTransferResult | None = None


class FundAndActionFollowUpStepExecution(_BridgeModel):
    status: FundAndActionFollowUpStepStatus
    summary: str
    updatedAt: str
    reference: FollowUpActionExecutionReference | None = None
    result: FollowUpActionResult | None = None


class FundAndActionExecutionSession(_BridgeModel):
    sessionId: str
    status: FundAndActionExecutionSessionStatus
    currentStep: FundAndActionExecutionCurrentStep
    createdAt: str
    updatedAt: str
    fundAndActionPlan: FundAndActionPlanResult
    fundingStep: FundAndActionFundingStepExecution
    followUpStep: FundAndActionFollowUpStepExecution


class FundAndActionSessionCreateResult(_BridgeModel):
    session: FundAndActionExecutionSession


class FundAndActionExecutionTask(_BridgeModel):
    kind: FundAndActionExecutionTaskKind
    summary: str
    fundingPlan: AssetTransferPlanWithContextResult | None = None
    assetTransferResult: AssetTransferResult | None = None
    followUpActionPlan: FollowUpActionPlan | None = None
    reference: FollowUpActionExecutionReference | None = None
    status: FundAndActionExecutionSessionStatus | None = None
    result: FollowUpActionResult | None = None


class FundAndActionSessionNextStepResult(_BridgeModel):
    session: FundAndActionExecutionSession
    task: FundAndActionExecutionTask


T_Result = TypeVar("T_Result", bound=BaseModel)


def _drop_none_values(value: Any) -> Any:
    if isinstance(value, Mapping):
        cleaned: dict[str, Any] = {}
        for key, nested_value in value.items():
            normalized = _drop_none_values(nested_value)
            if normalized is not None:
                cleaned[str(key)] = normalized
        return cleaned

    if isinstance(value, (list, tuple)):
        cleaned_items: list[Any] = []
        for nested_value in value:
            normalized = _drop_none_values(nested_value)
            if normalized is not None:
                cleaned_items.append(normalized)
        return cleaned_items

    return value


class _SubprocessMcpClient:
    def __init__(self, config: PredictConfig) -> None:
        self._config = config
        self._process: asyncio.subprocess.Process | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._stderr_chunks: list[str] = []
        self._stdout_buffer = bytearray()
        self._request_id = 0

    async def start(self) -> None:
        argv = shlex.split(self._config.mandated_mcp_command)
        if not argv:
            raise MandatedVaultMcpUnavailableError(
                "Mandated-vault MCP command is empty."
            )

        env = os.environ.copy()
        env["ERC_MANDATED_CONTRACT_VERSION"] = self._config.mandated_contract_version
        if self._config.mandated_chain_id is not None:
            env["ERC_MANDATED_CHAIN_ID"] = str(self._config.mandated_chain_id)
        _apply_default_rpc_env(env, self._config)

        try:
            self._process = await asyncio.create_subprocess_exec(
                *argv,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                limit=1024 * 1024,
                env=env,
            )
        except OSError as error:
            raise MandatedVaultMcpUnavailableError(
                self._redact(
                    f"Failed to start mandated-vault MCP command {argv[0]!r}: {error}"
                )
            ) from error

        self._stderr_task = asyncio.create_task(self._capture_stderr())

        try:
            await self.request(
                "initialize",
                {
                    "protocolVersion": _CLIENT_PROTOCOL_VERSION,
                    "capabilities": {"tools": {"listChanged": False}},
                    "clientInfo": {
                        "name": _CLIENT_NAME,
                        "version": _CLIENT_VERSION,
                    },
                },
            )
            await self.notify("notifications/initialized", {})
        except Exception:
            await self.close()
            raise

    async def close(self) -> None:
        if self._process is None:
            return

        process = self._process
        self._process = None

        if process.stdin is not None and not process.stdin.is_closing():
            process.stdin.close()

        try:
            await asyncio.wait_for(process.wait(), timeout=1)
        except asyncio.TimeoutError:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=1)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()

        if self._stderr_task is not None:
            self._stderr_task.cancel()
            try:
                await self._stderr_task
            except asyncio.CancelledError:
                pass
            self._stderr_task = None

    async def list_tools(self) -> list[McpToolDescriptor]:
        payload = await self.request("tools/list", {})
        tools = payload.get("tools")
        if not isinstance(tools, list):
            raise MandatedVaultMcpUnavailableError(
                self._redact(
                    "Mandated-vault MCP tools/list response did not include a tools array."
                )
            )
        return [McpToolDescriptor.model_validate(item) for item in tools]

    async def call_tool(
        self, name: str, arguments: Mapping[str, Any] | None = None
    ) -> dict[str, Any]:
        payload = await self.request(
            "tools/call",
            {
                "name": name,
                "arguments": dict(arguments or {}),
            },
        )
        structured = payload.get("structuredContent")
        if not isinstance(structured, dict):
            raise MandatedVaultMcpUnavailableError(
                self._redact(
                    f"Mandated-vault MCP returned malformed structuredContent for {name}."
                )
            )
        return structured

    async def notify(self, method: str, params: Mapping[str, Any]) -> None:
        await self._write_message(
            {
                "jsonrpc": "2.0",
                "method": method,
                "params": dict(params),
            }
        )

    async def request(self, method: str, params: Mapping[str, Any]) -> dict[str, Any]:
        self._require_process()
        self._request_id += 1
        request_id = self._request_id
        await self._write_message(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": dict(params),
            }
        )

        while True:
            message = await self._read_message()
            if message.get("id") != request_id:
                continue

            error = message.get("error")
            if isinstance(error, dict):
                raise MandatedVaultMcpUnavailableError(
                    self._redact(
                        f"Mandated-vault MCP {method} request failed: {error.get('message', error)}"
                    )
                )

            result = message.get("result")
            if not isinstance(result, dict):
                raise MandatedVaultMcpUnavailableError(
                    self._redact(
                        f"Mandated-vault MCP {method} response did not include an object result."
                    )
                )
            return result

    async def _write_message(self, message: Mapping[str, Any]) -> None:
        process = self._require_process()
        if process.stdin is None:
            raise MandatedVaultMcpUnavailableError(
                self._redact("Mandated-vault MCP process did not expose stdin.")
            )

        payload = (json.dumps(message) + "\n").encode("utf-8")
        process.stdin.write(payload)
        await process.stdin.drain()

    async def _read_message(self) -> dict[str, Any]:
        process = self._require_process()
        if process.stdout is None:
            raise MandatedVaultMcpUnavailableError(
                self._redact("Mandated-vault MCP process did not expose stdout.")
            )

        line = await self._read_stdout_line(process)
        if not line:
            raise MandatedVaultMcpUnavailableError(self._build_process_exit_message())

        try:
            stripped = line.decode("utf-8").strip()
        except UnicodeDecodeError as error:
            raise MandatedVaultMcpUnavailableError(
                self._redact(
                    f"Mandated-vault MCP emitted undecodable stdout payload: {error}"
                )
            ) from error

        if stripped.lower().startswith("content-length:"):
            headers: dict[str, str] = {}
            header_line = stripped
            while True:
                if not header_line:
                    break
                try:
                    key, value = header_line.split(":", 1)
                except ValueError as error:
                    raise MandatedVaultMcpUnavailableError(
                        self._redact(
                            f"Mandated-vault MCP emitted malformed response headers: {header_line!r}"
                        )
                    ) from error
                headers[key.lower()] = value.strip()
                next_line = await self._read_stdout_line(process)
                if not next_line:
                    raise MandatedVaultMcpUnavailableError(
                        self._build_process_exit_message()
                    )
                header_line = next_line.decode("utf-8").strip()

            content_length = headers.get("content-length")
            if content_length is None:
                raise MandatedVaultMcpUnavailableError(
                    self._redact(
                        "Mandated-vault MCP response omitted Content-Length header."
                    )
                )

            try:
                body = await self._read_stdout_exactly(process, int(content_length))
                payload = json.loads(body.decode("utf-8"))
            except (ValueError, json.JSONDecodeError, asyncio.IncompleteReadError) as error:
                raise MandatedVaultMcpUnavailableError(
                    self._redact(
                        f"Mandated-vault MCP emitted invalid JSON-RPC payload: {error}"
                    )
                ) from error
        else:
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError as error:
                raise MandatedVaultMcpUnavailableError(
                    self._redact(
                        f"Mandated-vault MCP emitted invalid JSON-RPC payload: {error}"
                    )
                ) from error

        if not isinstance(payload, dict):
            raise MandatedVaultMcpUnavailableError(
                self._redact("Mandated-vault MCP response payload was not an object.")
            )
        return payload

    async def _read_stdout_line(self, process: asyncio.subprocess.Process) -> bytes:
        if process.stdout is None:
            raise MandatedVaultMcpUnavailableError(
                self._redact("Mandated-vault MCP process did not expose stdout.")
            )

        while True:
            newline_index = self._stdout_buffer.find(b"\n")
            if newline_index != -1:
                line = bytes(self._stdout_buffer[: newline_index + 1])
                del self._stdout_buffer[: newline_index + 1]
                return line

            chunk = await process.stdout.read(64 * 1024)
            if not chunk:
                if self._stdout_buffer:
                    line = bytes(self._stdout_buffer)
                    self._stdout_buffer.clear()
                    return line
                return b""
            self._stdout_buffer.extend(chunk)

    async def _read_stdout_exactly(
        self, process: asyncio.subprocess.Process, length: int
    ) -> bytes:
        if process.stdout is None:
            raise MandatedVaultMcpUnavailableError(
                self._redact("Mandated-vault MCP process did not expose stdout.")
            )

        remaining = length
        chunks: list[bytes] = []
        if self._stdout_buffer:
            buffered = bytes(self._stdout_buffer[:remaining])
            if buffered:
                chunks.append(buffered)
                remaining -= len(buffered)
                del self._stdout_buffer[: len(buffered)]

        while remaining > 0:
            chunk = await process.stdout.read(remaining)
            if not chunk:
                raise asyncio.IncompleteReadError(partial=b"".join(chunks), expected=length)
            chunks.append(chunk)
            remaining -= len(chunk)

        return b"".join(chunks)

    async def _capture_stderr(self) -> None:
        process = self._process
        if process is None or process.stderr is None:
            return

        while True:
            line = await process.stderr.readline()
            if not line:
                break
            self._stderr_chunks.append(line.decode("utf-8", errors="replace").rstrip())
            if len(self._stderr_chunks) > 20:
                self._stderr_chunks = self._stderr_chunks[-20:]

    def _build_process_exit_message(self) -> str:
        process = self._require_process()
        suffix = ""
        if self._stderr_chunks:
            suffix = f" stderr={self._redact(' | '.join(self._stderr_chunks)[-400:])}"
        return self._redact(
            f"Mandated-vault MCP process exited before completing the request (returncode={process.returncode}).{suffix}"
        )

    def _redact(self, text: str) -> str:
        return redact_text(text, self._secrets())

    def _secrets(self) -> list[str | None]:
        return [
            self._config.api_key.get_secret_value() if self._config.api_key else None,
            self._config.private_key_value,
            self._config.privy_private_key_value,
            self._config.openrouter_api_key.get_secret_value()
            if self._config.openrouter_api_key
            else None,
        ]

    def _require_process(self) -> asyncio.subprocess.Process:
        if self._process is None:
            raise MandatedVaultMcpUnavailableError(
                "Mandated-vault MCP process has not been started."
            )
        return self._process


def _apply_default_rpc_env(env: dict[str, str], config: PredictConfig) -> None:
    chain_id = config.mandated_chain_id or int(config.chain_id)
    env_keys = _RPC_ENV_KEYS_BY_CHAIN_ID.get(chain_id)
    if env_keys is None:
        return
    if any(env.get(key) for key in env_keys):
        return
    rpc_url = _DEFAULT_RPC_URL_BY_CHAIN_ID.get(chain_id)
    if rpc_url:
        env["ERC_MANDATED_RPC_URL"] = rpc_url


class MandatedVaultMcpBridge:
    def __init__(self, config: PredictConfig) -> None:
        self._config = config
        self._client: _SubprocessMcpClient | None = None
        self._available_tools: dict[str, McpToolDescriptor] = {}

    async def __aenter__(self) -> Self:
        await self.connect()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    @property
    def available_tools(self) -> frozenset[str]:
        return frozenset(self._available_tools)

    @property
    def supports_vault_bootstrap(self) -> bool:
        return MANDATED_BOOTSTRAP_REQUIRED_TOOLS.issubset(self.available_tools)

    @property
    def missing_required_tools(self) -> frozenset[str]:
        if self.runtime_ready:
            return frozenset()
        return MANDATED_V1_REQUIRED_TOOLS.difference(self.available_tools)

    @property
    def runtime_ready(self) -> bool:
        return self.supports_vault_bootstrap or not MANDATED_V1_REQUIRED_TOOLS.difference(
            self.available_tools
        )

    async def connect(self) -> None:
        if self._client is not None:
            return

        client = _SubprocessMcpClient(self._config)
        await client.start()
        self._client = client
        try:
            tools = await client.list_tools()
        except Exception:
            await client.close()
            self._client = None
            self._available_tools = {}
            raise

        self._available_tools = {tool.name: tool for tool in tools}

    async def close(self) -> None:
        client = self._client
        self._client = None
        self._available_tools = {}
        if client is not None:
            await client.close()

    async def health_check(self, vault: str) -> VaultHealthCheckResult:
        structured = await self._call_tool(
            "vault_health_check",
            {"vault": vault, "chainId": self._chain_id_value()},
            tx_preparation=False,
        )
        return self._parse_result(
            "vault_health_check", structured, VaultHealthCheckResult
        )

    async def predict_vault_address(
        self,
        *,
        factory: str | None,
        asset: str,
        name: str,
        symbol: str,
        authority: str,
        salt: str,
    ) -> FactoryPredictVaultAddressResult:
        structured = await self._call_tool(
            "factory_predict_vault_address",
            {
                "chainId": self._chain_id_value(),
                "factory": factory,
                "asset": asset,
                "name": name,
                "symbol": symbol,
                "authority": authority,
                "salt": salt,
            },
            tx_preparation=False,
        )
        return self._parse_result(
            "factory_predict_vault_address",
            structured,
            FactoryPredictVaultAddressResult,
        )

    async def prepare_create_vault(
        self,
        *,
        from_address: str,
        factory: str | None,
        asset: str,
        name: str,
        symbol: str,
        authority: str,
        salt: str,
    ) -> FactoryCreateVaultPrepareResult:
        structured = await self._call_tool(
            "factory_create_vault_prepare",
            {
                "chainId": self._chain_id_value(),
                "factory": factory,
                "from": from_address,
                "asset": asset,
                "name": name,
                "symbol": symbol,
                "authority": authority,
                "salt": salt,
            },
            tx_preparation=True,
        )
        return self._parse_result(
            "factory_create_vault_prepare",
            structured,
            FactoryCreateVaultPrepareResult,
        )

    async def vault_bootstrap(
        self,
        *,
        factory: str | None,
        asset: str,
        name: str,
        symbol: str,
        salt: str,
        signer_address: str | None = None,
        mode: VaultBootstrapMode = "plan",
        authority_mode: VaultBootstrapAuthorityMode | None = None,
        authority: str | None = None,
        executor: str | None = None,
        create_account_context: bool | None = None,
        create_funding_policy: bool | None = None,
        account_context_options: Mapping[str, Any] | None = None,
        funding_policy_options: Mapping[str, Any] | None = None,
    ) -> VaultBootstrapResult:
        structured = await self._call_tool(
            "vault_bootstrap",
            {
                "chainId": self._chain_id_value(),
                "factory": factory,
                "asset": asset,
                "name": name,
                "symbol": symbol,
                "salt": salt,
                "signerAddress": signer_address,
                "mode": mode,
                "authorityMode": authority_mode,
                "authority": authority,
                "executor": executor,
                "createAccountContext": create_account_context,
                "createFundingPolicy": create_funding_policy,
                "accountContextOptions": dict(account_context_options)
                if account_context_options is not None
                else None,
                "fundingPolicyOptions": dict(funding_policy_options)
                if funding_policy_options is not None
                else None,
            },
            tx_preparation=False,
            required_tools=MANDATED_BOOTSTRAP_REQUIRED_TOOLS,
        )
        return self._parse_result("vault_bootstrap", structured, VaultBootstrapResult)

    async def create_agent_account_context(
        self,
        *,
        agent_id: str,
        vault: str,
        authority: str,
        executor: str,
        asset_registry_ref: str | None = None,
        funding_policy_ref: str | None = None,
        defaults: Mapping[str, Any] | None = None,
        created_at: str | None = None,
        updated_at: str | None = None,
    ) -> AgentAccountContextCreateResult:
        structured = await self._call_tool(
            "agent_account_context_create",
            {
                "agentId": agent_id,
                "chainId": self._chain_id_value(),
                "vault": vault,
                "authority": authority,
                "executor": executor,
                "assetRegistryRef": asset_registry_ref,
                "fundingPolicyRef": funding_policy_ref,
                "defaults": defaults,
                "createdAt": created_at,
                "updatedAt": updated_at,
            },
            tx_preparation=False,
        )
        return self._parse_result(
            "agent_account_context_create",
            structured,
            AgentAccountContextCreateResult,
        )

    async def create_agent_funding_policy(
        self,
        *,
        policy_id: str,
        allowed_token_addresses: Sequence[str] | None = None,
        allowed_recipients: Sequence[str] | None = None,
        max_amount_per_tx: str | None = None,
        max_amount_per_window: str | None = None,
        window_seconds: int | None = None,
        expires_at: str | None = None,
        repeatable: bool | None = None,
        created_at: str | None = None,
        updated_at: str | None = None,
    ) -> AgentFundingPolicyCreateResult:
        structured = await self._call_tool(
            "agent_funding_policy_create",
            {
                "policyId": policy_id,
                "allowedTokenAddresses": list(allowed_token_addresses)
                if allowed_token_addresses is not None
                else None,
                "allowedRecipients": list(allowed_recipients)
                if allowed_recipients is not None
                else None,
                "maxAmountPerTx": max_amount_per_tx,
                "maxAmountPerWindow": max_amount_per_window,
                "windowSeconds": window_seconds,
                "expiresAt": expires_at,
                "repeatable": repeatable,
                "createdAt": created_at,
                "updatedAt": updated_at,
            },
            tx_preparation=False,
        )
        return self._parse_result(
            "agent_funding_policy_create",
            structured,
            AgentFundingPolicyCreateResult,
        )

    async def build_agent_fund_and_action_plan(
        self,
        *,
        account_context: Mapping[str, Any],
        funding_target: Mapping[str, Any],
        funding_context: Mapping[str, Any],
        follow_up_action: Mapping[str, Any],
        funding_policy: Mapping[str, Any] | None = None,
    ) -> FundAndActionPlanResult:
        structured = await self._call_tool(
            "agent_build_fund_and_action_plan",
            {
                "accountContext": dict(account_context),
                "fundingPolicy": dict(funding_policy) if funding_policy else None,
                "fundingTarget": dict(funding_target),
                "fundingContext": dict(funding_context),
                "followUpAction": dict(follow_up_action),
            },
            tx_preparation=False,
        )
        return self._parse_result(
            "agent_build_fund_and_action_plan",
            structured,
            FundAndActionPlanResult,
        )

    async def create_agent_fund_and_action_session(
        self,
        *,
        fund_and_action_plan: Mapping[str, Any],
        session_id: str | None = None,
        created_at: str | None = None,
    ) -> FundAndActionSessionCreateResult:
        structured = await self._call_tool(
            "agent_fund_and_action_session_create",
            {
                "fundAndActionPlan": dict(fund_and_action_plan),
                "sessionId": session_id,
                "createdAt": created_at,
            },
            tx_preparation=False,
        )
        return self._parse_result(
            "agent_fund_and_action_session_create",
            structured,
            FundAndActionSessionCreateResult,
        )

    async def next_agent_fund_and_action_session_step(
        self,
        *,
        session: Mapping[str, Any],
    ) -> FundAndActionSessionNextStepResult:
        structured = await self._call_tool(
            "agent_fund_and_action_session_next_step",
            {"session": dict(session)},
            tx_preparation=False,
        )
        return self._parse_result(
            "agent_fund_and_action_session_next_step",
            structured,
            FundAndActionSessionNextStepResult,
        )

    async def apply_agent_fund_and_action_session_event(
        self,
        *,
        session: Mapping[str, Any],
        event: Mapping[str, Any],
    ) -> FundAndActionSessionCreateResult:
        structured = await self._call_tool(
            "agent_fund_and_action_session_apply_event",
            {
                "session": dict(session),
                "event": dict(event),
            },
            tx_preparation=False,
        )
        return self._parse_result(
            "agent_fund_and_action_session_apply_event",
            structured,
            FundAndActionSessionCreateResult,
        )

    async def create_agent_follow_up_action_result(
        self,
        *,
        follow_up_action_plan: Mapping[str, Any],
        status: str,
        updated_at: str,
        started_at: str | None = None,
        completed_at: str | None = None,
        attempt: int | None = None,
        reference: Mapping[str, Any] | None = None,
        output: Mapping[str, Any] | None = None,
        error: Mapping[str, Any] | None = None,
    ) -> FollowUpActionResultCreateResult:
        structured = await self._call_tool(
            "agent_follow_up_action_result_create",
            {
                "followUpActionPlan": dict(follow_up_action_plan),
                "status": status,
                "updatedAt": updated_at,
                "startedAt": started_at,
                "completedAt": completed_at,
                "attempt": attempt,
                "reference": dict(reference) if reference else None,
                "output": dict(output) if output else None,
                "error": dict(error) if error else None,
            },
            tx_preparation=False,
        )
        return self._parse_result(
            "agent_follow_up_action_result_create",
            structured,
            FollowUpActionResultCreateResult,
        )

    async def create_vault_asset_transfer_result(
        self,
        *,
        asset_transfer_plan: Mapping[str, Any],
        status: str,
        updated_at: str,
        submitted_at: str | None = None,
        completed_at: str | None = None,
        attempt: int | None = None,
        chain_id: int | None = None,
        tx_hash: str | None = None,
        receipt: Mapping[str, Any] | None = None,
        output: Mapping[str, Any] | None = None,
        error: Mapping[str, Any] | None = None,
    ) -> AssetTransferResultCreateResult:
        structured = await self._call_tool(
            "vault_asset_transfer_result_create",
            {
                "assetTransferPlan": dict(asset_transfer_plan),
                "status": status,
                "updatedAt": updated_at,
                "submittedAt": submitted_at,
                "completedAt": completed_at,
                "attempt": attempt,
                "chainId": chain_id,
                "txHash": tx_hash,
                "receipt": dict(receipt) if receipt else None,
                "output": dict(output) if output else None,
                "error": dict(error) if error else None,
            },
            tx_preparation=False,
        )
        return self._parse_result(
            "vault_asset_transfer_result_create",
            structured,
            AssetTransferResultCreateResult,
        )

    async def check_vault_asset_transfer_policy(
        self,
        *,
        funding_policy: Mapping[str, Any],
        token_address: str,
        to: str,
        amount_raw: str,
        now: str | None = None,
        current_spent_in_window: str | None = None,
    ) -> PolicyCheckResult:
        structured = await self._call_tool(
            "vault_check_asset_transfer_policy",
            {
                "fundingPolicy": dict(funding_policy),
                "tokenAddress": token_address,
                "to": to,
                "amountRaw": amount_raw,
                "now": now,
                "currentSpentInWindow": current_spent_in_window,
            },
            tx_preparation=False,
        )
        return self._parse_result(
            "vault_check_asset_transfer_policy",
            structured,
            PolicyCheckResult,
        )

    async def build_vault_asset_transfer_plan_from_context(
        self,
        *,
        account_context: Mapping[str, Any],
        token_address: str,
        to: str,
        amount_raw: str,
        nonce: str,
        deadline: str,
        authority_epoch: str,
        funding_policy: Mapping[str, Any] | None = None,
        allowed_adapters_root: str | None = None,
        max_drawdown_bps: str | None = None,
        max_cumulative_drawdown_bps: str | None = None,
        payload_binding: PayloadBinding | None = None,
        extensions: str | None = None,
        symbol: str | None = None,
        decimals: int | None = None,
        policy_evaluation: Mapping[str, Any] | None = None,
    ) -> AssetTransferPlanWithContextResult:
        structured = await self._call_tool(
            "vault_build_asset_transfer_plan_from_context",
            {
                "accountContext": dict(account_context),
                "fundingPolicy": dict(funding_policy) if funding_policy else None,
                "tokenAddress": token_address,
                "to": to,
                "amountRaw": amount_raw,
                "nonce": nonce,
                "deadline": deadline,
                "authorityEpoch": authority_epoch,
                "allowedAdaptersRoot": allowed_adapters_root,
                "maxDrawdownBps": max_drawdown_bps,
                "maxCumulativeDrawdownBps": max_cumulative_drawdown_bps,
                "payloadBinding": payload_binding,
                "extensions": extensions,
                "symbol": symbol,
                "decimals": decimals,
                "policyEvaluation": dict(policy_evaluation)
                if policy_evaluation
                else None,
            },
            tx_preparation=False,
        )
        return self._parse_result(
            "vault_build_asset_transfer_plan_from_context",
            structured,
            AssetTransferPlanWithContextResult,
        )

    async def simulate_vault_asset_transfer_from_context(
        self,
        *,
        account_context: Mapping[str, Any],
        token_address: str,
        to: str,
        amount_raw: str,
        nonce: str,
        deadline: str,
        authority_epoch: str,
        signature: str,
        adapter_proofs: Sequence[Sequence[str]],
        funding_policy: Mapping[str, Any] | None = None,
        from_address: str | None = None,
        allowed_adapters_root: str | None = None,
        max_drawdown_bps: str | None = None,
        max_cumulative_drawdown_bps: str | None = None,
        payload_binding: PayloadBinding | None = None,
        extensions: str | None = None,
        symbol: str | None = None,
        decimals: int | None = None,
        policy_evaluation: Mapping[str, Any] | None = None,
    ) -> AssetTransferSimulateWithContextResult:
        structured = await self._call_tool(
            "vault_simulate_asset_transfer_from_context",
            {
                "accountContext": dict(account_context),
                "fundingPolicy": dict(funding_policy) if funding_policy else None,
                "from": from_address,
                "tokenAddress": token_address,
                "to": to,
                "amountRaw": amount_raw,
                "nonce": nonce,
                "deadline": deadline,
                "authorityEpoch": authority_epoch,
                "allowedAdaptersRoot": allowed_adapters_root,
                "maxDrawdownBps": max_drawdown_bps,
                "maxCumulativeDrawdownBps": max_cumulative_drawdown_bps,
                "payloadBinding": payload_binding,
                "extensions": extensions,
                "symbol": symbol,
                "decimals": decimals,
                "policyEvaluation": dict(policy_evaluation)
                if policy_evaluation
                else None,
                "signature": signature,
                "adapterProofs": [list(group) for group in adapter_proofs],
            },
            tx_preparation=False,
        )
        return self._parse_result(
            "vault_simulate_asset_transfer_from_context",
            structured,
            AssetTransferSimulateWithContextResult,
        )

    async def prepare_vault_asset_transfer_from_context(
        self,
        *,
        account_context: Mapping[str, Any],
        token_address: str,
        to: str,
        amount_raw: str,
        nonce: str,
        deadline: str,
        authority_epoch: str,
        signature: str,
        adapter_proofs: Sequence[Sequence[str]],
        funding_policy: Mapping[str, Any] | None = None,
        from_address: str | None = None,
        allowed_adapters_root: str | None = None,
        max_drawdown_bps: str | None = None,
        max_cumulative_drawdown_bps: str | None = None,
        payload_binding: PayloadBinding | None = None,
        extensions: str | None = None,
        symbol: str | None = None,
        decimals: int | None = None,
        policy_evaluation: Mapping[str, Any] | None = None,
    ) -> AssetTransferPrepareWithContextResult:
        structured = await self._call_tool(
            "vault_prepare_asset_transfer_from_context",
            {
                "accountContext": dict(account_context),
                "fundingPolicy": dict(funding_policy) if funding_policy else None,
                "from": from_address,
                "tokenAddress": token_address,
                "to": to,
                "amountRaw": amount_raw,
                "nonce": nonce,
                "deadline": deadline,
                "authorityEpoch": authority_epoch,
                "allowedAdaptersRoot": allowed_adapters_root,
                "maxDrawdownBps": max_drawdown_bps,
                "maxCumulativeDrawdownBps": max_cumulative_drawdown_bps,
                "payloadBinding": payload_binding,
                "extensions": extensions,
                "symbol": symbol,
                "decimals": decimals,
                "policyEvaluation": dict(policy_evaluation)
                if policy_evaluation
                else None,
                "signature": signature,
                "adapterProofs": [list(group) for group in adapter_proofs],
            },
            tx_preparation=False,
        )
        return self._parse_result(
            "vault_prepare_asset_transfer_from_context",
            structured,
            AssetTransferPrepareWithContextResult,
        )

    async def _call_tool(
        self,
        tool_name: str,
        arguments: Mapping[str, Any],
        *,
        tx_preparation: bool,
        required_tools: Sequence[str] | None = None,
    ) -> dict[str, Any]:
        await self.connect()
        self._assert_tool_available(
            tool_name,
            tx_preparation=tx_preparation,
            required_tools=required_tools,
        )

        client = self._require_client()
        filtered_arguments = _drop_none_values(arguments)
        if not isinstance(filtered_arguments, dict):
            raise MandatedVaultMcpUnavailableError(
                f"Mandated-vault MCP {tool_name} arguments did not normalize to an object."
            )
        return await client.call_tool(tool_name, filtered_arguments)

    def _assert_tool_available(
        self,
        tool_name: str,
        *,
        tx_preparation: bool,
        required_tools: Sequence[str] | None = None,
    ) -> None:
        if tool_name not in self._available_tools:
            raise MandatedVaultMcpMissingToolsError([tool_name], operation=tool_name)

        if required_tools is not None:
            missing = frozenset(required_tools).difference(self.available_tools)
            if missing:
                raise MandatedVaultMcpMissingToolsError(
                    sorted(missing),
                    operation=tool_name,
                )
            return

        if tx_preparation and self.missing_required_tools:
            raise MandatedVaultMcpMissingToolsError(
                sorted(self.missing_required_tools),
                operation=tool_name,
            )

    def _require_client(self) -> _SubprocessMcpClient:
        if self._client is None:
            raise MandatedVaultMcpUnavailableError(
                "Mandated-vault MCP client is not connected."
            )
        return self._client

    def _chain_id_value(self) -> int:
        return self._config.mandated_chain_id or int(self._config.chain_id)

    def _parse_result(
        self,
        tool_name: str,
        structured: Mapping[str, Any],
        model: type[T_Result],
    ) -> T_Result:
        tool_error = structured.get("error")
        if isinstance(tool_error, dict):
            parsed_error = McpToolError.model_validate(tool_error)
            raise MandatedVaultMcpError(
                f"Mandated-vault MCP tool {tool_name} failed: {parsed_error.code} {parsed_error.message}"
            )

        payload = structured.get("result")
        if not isinstance(payload, dict):
            raise ValueError(f"Malformed {tool_name} response: missing result object.")

        try:
            return model.model_validate(payload)
        except ValidationError as error:
            raise ValueError(f"Malformed {tool_name} response: {error}") from error
