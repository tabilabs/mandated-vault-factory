from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import pytest
from eth_abi import encode as abi_encode
from web3 import Web3

from lib.config import ConfigError, PredictConfig, WalletMode
from lib.config import MANDATED_ALLOWED_ADAPTERS_ROOT_DEFAULT
from lib.mandated_mcp_bridge import (
    FactoryCreateVaultPrepareResult,
    FactoryPredictVaultAddressResult,
    MandatedVaultMcpError,
    MandatedVaultMcpUnavailableError,
    McpTxRequest,
    VaultBootstrapAuthorityConfig,
    VaultBootstrapCreateTx,
    VaultBootstrapResult,
    VaultHealthCheckResult,
)
from lib.wallet_manager import (
    ApprovalSnapshot,
    MANDATED_FUNDING_TRANSFER_MAX_CUMULATIVE_DRAWDOWN_BPS,
    MANDATED_FUNDING_TRANSFER_MAX_DRAWDOWN_BPS,
    WalletManager,
    WalletSdkProtocol,
)


@dataclass
class FakeWalletSdk(WalletSdkProtocol):
    wallet_mode: WalletMode = WalletMode.EOA
    wallet_signer_address: str = "0x1111111111111111111111111111111111111111"
    wallet_funding_address: str = "0x1111111111111111111111111111111111111111"
    wallet_chain_name: str = "BNB Testnet"
    approve_calls: list[str] | None = None

    @property
    def mode(self) -> WalletMode:
        return self.wallet_mode

    @property
    def signer_address(self) -> str:
        return self.wallet_signer_address

    @property
    def funding_address(self) -> str:
        return self.wallet_funding_address

    @property
    def chain_name(self) -> str:
        return self.wallet_chain_name

    def get_bnb_balance_wei(self) -> int:
        return 2_000_000_000_000_000_000

    def get_usdt_balance_wei(self) -> int:
        return 30_000_000_000_000_000_000

    def get_approval_snapshot(self) -> ApprovalSnapshot:
        return ApprovalSnapshot(
            standard_exchange_approval=True,
            standard_exchange_allowance=True,
            standard_neg_risk_exchange_approval=True,
            standard_neg_risk_exchange_allowance=True,
            standard_neg_risk_adapter_approval=True,
            yield_exchange_approval=True,
            yield_exchange_allowance=True,
            yield_neg_risk_exchange_approval=True,
            yield_neg_risk_exchange_allowance=True,
            yield_neg_risk_adapter_approval=True,
        )

    def set_all_approvals(self) -> dict[str, object]:
        if self.approve_calls is not None:
            self.approve_calls.extend(["standard", "yield"])
        return {
            "standard": {"success": True},
            "yieldBearing": {"success": True},
        }


class AsyncUnsafeWalletSdk(FakeWalletSdk):
    def _assert_outside_event_loop(self) -> None:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return
        raise AssertionError("balance getter called inside running event loop")

    def get_bnb_balance_wei(self) -> int:
        self._assert_outside_event_loop()
        return super().get_bnb_balance_wei()

    def get_usdt_balance_wei(self) -> int:
        self._assert_outside_event_loop()
        return super().get_usdt_balance_wei()


class CodehashWalletSdk(FakeWalletSdk):
    def __init__(self, *, contract_code: bytes, **kwargs: Any) -> None:
        super().__init__(**kwargs)

        class _Eth:
            def __init__(self, code: bytes) -> None:
                self._code = code

            def get_code(self, _address: str) -> bytes:
                return self._code

        class _Web3:
            def __init__(self, code: bytes) -> None:
                self.eth = _Eth(code)

        class _Builder:
            def __init__(self, code: bytes) -> None:
                self._web3 = _Web3(code)

        self._builder = _Builder(contract_code)


class FakeMandatedBridge:
    def __init__(
        self,
        *,
        runtime_ready: bool = True,
        missing_required_tools: frozenset[str] | None = None,
        predicted_vault: str = "0x1234567890123456789012345678901234567890",
        health_result: VaultHealthCheckResult | None = None,
        health_error: Exception | None = None,
        enforce_single_loop_close: bool = False,
    ) -> None:
        self.runtime_ready = runtime_ready
        self.missing_required_tools = missing_required_tools or frozenset()
        self.predicted_vault = predicted_vault
        self.health_result = health_result
        self.health_error = health_error
        self.enforce_single_loop_close = enforce_single_loop_close
        self.bootstrap_calls = 0
        self.predict_calls = 0
        self.health_check_calls = 0
        self.connect_loop_id: int | None = None
        self.close_loop_id: int | None = None
        self.close_called = False
        self.available_tools = frozenset(
            {
                "vault_bootstrap",
                "factory_predict_vault_address",
                "factory_create_vault_prepare",
                "vault_health_check",
            }
        )

    async def connect(self) -> None:
        self.connect_loop_id = id(asyncio.get_running_loop())
        return None

    async def close(self) -> None:
        self.close_called = True
        self.close_loop_id = id(asyncio.get_running_loop())
        if (
            self.enforce_single_loop_close
            and self.connect_loop_id is not None
            and self.connect_loop_id != self.close_loop_id
        ):
            raise RuntimeError("Event loop is closed")
        return None

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
        self.predict_calls += 1
        assert factory is not None
        assert asset.startswith("0x")
        assert name
        assert symbol
        assert authority.startswith("0x")
        assert salt.startswith("0x")
        return FactoryPredictVaultAddressResult(predictedVault=self.predicted_vault)

    async def vault_bootstrap(
        self,
        *,
        factory: str | None,
        asset: str,
        name: str,
        symbol: str,
        salt: str,
        signer_address: str | None = None,
        mode: str = "plan",
        authority_mode: str | None = None,
        authority: str | None = None,
        executor: str | None = None,
        create_account_context: bool | None = None,
        create_funding_policy: bool | None = None,
        account_context_options: dict[str, Any] | None = None,
        funding_policy_options: dict[str, Any] | None = None,
    ) -> VaultBootstrapResult:
        self.bootstrap_calls += 1
        assert factory is not None
        assert asset.startswith("0x")
        assert name
        assert symbol
        assert salt.startswith("0x")
        assert signer_address is not None and signer_address.startswith("0x")
        assert authority is not None and authority.startswith("0x")
        assert executor is None or executor.startswith("0x")
        assert create_account_context is False
        assert create_funding_policy is False
        assert account_context_options is None
        assert funding_policy_options is None
        if self.health_error is not None:
            message = str(self.health_error).upper()
            undeployed_markers = (
                "VAULT_NOT_DEPLOYED",
                "VAULT_UNDEPLOYED",
                "VAULT_NOT_FOUND",
                "NO_CONTRACT_CODE",
                "NOT DEPLOYED",
            )
            if not any(marker in message for marker in undeployed_markers):
                raise self.health_error
        deployed = self.health_result is not None and self.health_error is None
        return VaultBootstrapResult(
            chainId=56,
            mode=mode,
            factory=factory,
            asset=asset,
            signerAddress=signer_address,
            predictedVault=self.predicted_vault,
            deployedVault=self.predicted_vault,
            alreadyDeployed=deployed,
            deploymentStatus="confirmed" if deployed else "planned",
            authorityConfig=VaultBootstrapAuthorityConfig(
                mode=authority_mode or "single_key",
                authority=authority,
                executor=executor or signer_address,
            ),
            createTx=(
                None
                if deployed
                else VaultBootstrapCreateTx(
                    mode="plan",
                    txRequest=McpTxRequest(
                        **{
                            "from": signer_address,
                            "to": factory,
                            "data": "0xfeedbeef",
                            "value": "0x0",
                            "gas": "0x5208",
                        }
                    ),
                )
            ),
            vaultHealth=self.health_result if deployed else None,
            accountContext=None,
            fundingPolicy=None,
            envBlock="ERC_MANDATED_VAULT_ADDRESS=0x...",
            configBlock="{\"vault\":\"0x...\"}",
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
        assert from_address.startswith("0x")
        assert factory is not None
        assert asset.startswith("0x")
        assert name
        assert symbol
        assert authority.startswith("0x")
        assert salt.startswith("0x")
        return FactoryCreateVaultPrepareResult(
            predictedVault=self.predicted_vault,
            txRequest=McpTxRequest(
                **{
                    "from": from_address,
                    "to": factory,
                    "data": "0xfeedbeef",
                    "value": "0x0",
                    "gas": "0x5208",
                }
            ),
        )

    async def health_check(self, vault: str) -> VaultHealthCheckResult:
        self.health_check_calls += 1
        assert vault.startswith("0x")
        if self.health_error is not None:
            raise self.health_error
        assert self.health_result is not None
        return self.health_result

    async def create_agent_account_context(
        self,
        *,
        agent_id: str,
        vault: str,
        authority: str,
        executor: str,
        asset_registry_ref: str | None = None,
        funding_policy_ref: str | None = None,
        defaults: dict[str, Any] | None = None,
        created_at: str | None = None,
        updated_at: str | None = None,
    ) -> Any:
        assert agent_id
        assert vault.startswith("0x")
        assert authority.startswith("0x")
        assert executor.startswith("0x")
        return {
            "accountContext": {
                "agentId": agent_id,
                "chainId": 56,
                "vault": vault,
                "authority": authority,
                "executor": executor,
                "assetRegistryRef": asset_registry_ref,
                "fundingPolicyRef": funding_policy_ref,
                "defaults": defaults,
                "createdAt": created_at or "2026-03-09T00:00:00Z",
                "updatedAt": updated_at or "2026-03-09T00:00:00Z",
            }
        }

    async def create_agent_funding_policy(
        self,
        *,
        policy_id: str,
        allowed_token_addresses: list[str] | None = None,
        allowed_recipients: list[str] | None = None,
        max_amount_per_tx: str | None = None,
        max_amount_per_window: str | None = None,
        window_seconds: int | None = None,
        expires_at: str | None = None,
        repeatable: bool | None = None,
        created_at: str | None = None,
        updated_at: str | None = None,
    ) -> Any:
        assert policy_id
        assert allowed_recipients
        return {
            "fundingPolicy": {
                "policyId": policy_id,
                "allowedTokenAddresses": allowed_token_addresses,
                "allowedRecipients": allowed_recipients,
                "maxAmountPerTx": max_amount_per_tx,
                "maxAmountPerWindow": max_amount_per_window,
                "windowSeconds": window_seconds,
                "expiresAt": expires_at,
                "repeatable": repeatable,
                "createdAt": created_at or "2026-03-09T00:00:00Z",
                "updatedAt": updated_at or "2026-03-09T00:00:00Z",
            }
        }

    async def build_agent_fund_and_action_plan(
        self,
        *,
        account_context: dict[str, Any],
        funding_target: dict[str, Any],
        funding_context: dict[str, Any],
        follow_up_action: dict[str, Any],
        funding_policy: dict[str, Any] | None = None,
    ) -> Any:
        return {
            "accountContext": account_context,
            "fundingPolicy": funding_policy,
            "fundingTarget": {
                **funding_target,
                "fundingShortfallRaw": "1000000000000000000",
            },
            "evaluatedAt": "2026-03-09T00:00:00Z",
            "fundingRequired": True,
            "fundingPlan": {
                "accountContext": account_context,
                "humanReadableSummary": {
                    "kind": "erc20Transfer",
                    "tokenAddress": funding_target["tokenAddress"],
                    "to": funding_target["recipient"],
                    "amountRaw": "1000000000000000000",
                    "symbol": "USDT",
                    "decimals": 18,
                },
            },
            "followUpAction": follow_up_action,
            "followUpActionPlan": {
                "kind": follow_up_action["kind"],
                "executionMode": "custom",
                "summary": "Deferred until buy flow task",
            },
            "steps": [
                {"kind": "fundTargetAccount", "status": "required", "summary": "fund"},
                {"kind": "followUpAction", "status": "pending", "summary": "deferred"},
            ],
            "fundingContext": funding_context,
        }

    async def create_agent_fund_and_action_session(
        self,
        *,
        fund_and_action_plan: dict[str, Any],
        session_id: str | None = None,
        created_at: str | None = None,
    ) -> Any:
        return {
            "session": {
                "sessionId": session_id or "session-wallet-overlay",
                "status": "pendingFunding",
                "currentStep": "fundTargetAccount",
                "createdAt": created_at or "2026-03-09T00:00:00Z",
                "updatedAt": "2026-03-09T00:00:00Z",
                "fundAndActionPlan": fund_and_action_plan,
                "fundingStep": {
                    "required": True,
                    "status": "pending",
                    "summary": "Funding required",
                    "updatedAt": "2026-03-09T00:00:00Z",
                    "result": None,
                },
                "followUpStep": {
                    "status": "pending",
                    "summary": "Follow-up pending",
                    "updatedAt": "2026-03-09T00:00:00Z",
                    "reference": None,
                    "result": None,
                },
            }
        }

    async def next_agent_fund_and_action_session_step(
        self,
        *,
        session: dict[str, Any],
    ) -> Any:
        return {
            "session": session,
            "task": {
                "kind": "submitFunding",
                "summary": "Submit vault funding transaction",
                "fundingPlan": session["fundAndActionPlan"].get("fundingPlan"),
            },
        }


def test_wallet_status_reports_mode_balances_and_approvals() -> None:
    config = PredictConfig.from_env(
        {
            "PREDICT_ENV": "testnet",
            "PREDICT_STORAGE_DIR": "/tmp/predict",
            "PREDICT_PRIVATE_KEY": "0x59c6995e998f97a5a0044976f4d060f5d89c8b8c7f11b9aa0dbf3f0f7c7c1e01",
        }
    )
    manager = WalletManager(config, sdk_factory=lambda _config: FakeWalletSdk())

    status = manager.get_status()
    payload = status.to_dict()
    approvals = cast(dict[str, Any], payload["approvals"])
    standard = cast(dict[str, Any], approvals["standard"])
    yield_bearing = cast(dict[str, Any], approvals["yieldBearing"])

    assert payload["mode"] == "eoa"
    assert payload["chain"] == "BNB Testnet"
    assert payload["bnbBalanceWei"] == 2_000_000_000_000_000_000
    assert payload["usdtBalanceWei"] == 30_000_000_000_000_000_000
    assert payload["authReady"] is True
    assert standard["ready"] is True
    assert yield_bearing["ready"] is True
    assert "59c6995e" not in str(payload)


def test_wallet_status_requires_signer_configuration() -> None:
    config = PredictConfig.from_env(
        {
            "PREDICT_ENV": "testnet",
            "PREDICT_STORAGE_DIR": "/tmp/predict",
        }
    )
    manager = WalletManager(config, sdk_factory=lambda _config: FakeWalletSdk())

    with pytest.raises(
        ConfigError, match="Wallet actions require signer configuration"
    ):
        manager.get_status()


def test_wallet_approve_runs_regular_and_yield_branches() -> None:
    config = PredictConfig.from_env(
        {
            "PREDICT_ENV": "testnet",
            "PREDICT_STORAGE_DIR": "/tmp/predict",
            "PREDICT_PRIVATE_KEY": "0x59c6995e998f97a5a0044976f4d060f5d89c8b8c7f11b9aa0dbf3f0f7c7c1e01",
        }
    )
    calls: list[str] = []
    manager = WalletManager(
        config, sdk_factory=lambda _config: FakeWalletSdk(approve_calls=calls)
    )

    result = manager.approve().to_dict()
    standard_result = cast(dict[str, Any], result["standard"])
    yield_result = cast(dict[str, Any], result["yieldBearing"])

    assert calls == ["standard", "yield"]
    assert standard_result["success"] is True
    assert yield_result["success"] is True


def test_wallet_runtime_has_single_module_surface() -> None:
    predict_root = Path(__file__).resolve().parents[1]

    assert not (predict_root / "lib" / "sdk_wallet.py").exists()
    assert not (predict_root / "lib" / "predict_sdk_wrapper.py").exists()


def test_wallet_status_mandated_vault_reports_explicit_deployed_health() -> None:
    config = PredictConfig.from_env(
        {
            "PREDICT_ENV": "testnet",
            "PREDICT_STORAGE_DIR": "/tmp/predict",
            "PREDICT_WALLET_MODE": "mandated-vault",
            "ERC_MANDATED_VAULT_ADDRESS": "0x2222222222222222222222222222222222222222",
            "ERC_MANDATED_CHAIN_ID": "56",
        }
    )
    bridge = FakeMandatedBridge(
        health_result=VaultHealthCheckResult(
            blockNumber=101,
            vault="0x2222222222222222222222222222222222222222",
            mandateAuthority="0x3333333333333333333333333333333333333333",
            authorityEpoch="7",
            pendingAuthority="0x0000000000000000000000000000000000000000",
            nonceThreshold="2",
            totalAssets="123000000000000000000",
        )
    )
    manager = WalletManager(
        config,
        bridge_factory=lambda _config: bridge,
    )

    payload = manager.get_status().to_dict()
    mcp = cast(dict[str, Any], payload["mcp"])
    health = cast(dict[str, Any], payload["vaultHealth"])
    selected_chain = cast(dict[str, Any], payload["selectedChain"])

    assert payload["mode"] == "mandated-vault"
    assert payload["vaultAddress"] == "0x2222222222222222222222222222222222222222"
    assert payload["vaultAddressSource"] == "explicit"
    assert payload["vaultDeployed"] is True
    assert payload["stateChangingFlowsEnabled"] is True
    assert selected_chain["chainId"] == 56
    assert mcp["runtimeReady"] is True
    assert mcp["missingRequiredTools"] == []
    assert health["mandateAuthority"] == "0x3333333333333333333333333333333333333333"
    assert health["authorityEpoch"] == "7"
    assert health["nonceThreshold"] == "2"
    assert health["totalAssets"] == "123000000000000000000"


def test_wallet_status_mandated_vault_predicts_address_when_not_explicit() -> None:
    config = PredictConfig.from_env(
        {
            "PREDICT_ENV": "testnet",
            "PREDICT_STORAGE_DIR": "/tmp/predict",
            "PREDICT_WALLET_MODE": "mandated-vault",
            "ERC_MANDATED_FACTORY_ADDRESS": "0x1111111111111111111111111111111111111111",
            "ERC_MANDATED_VAULT_ASSET_ADDRESS": "0x4444444444444444444444444444444444444444",
            "ERC_MANDATED_VAULT_NAME": "Mandated Vault",
            "ERC_MANDATED_VAULT_SYMBOL": "MVLT",
            "ERC_MANDATED_VAULT_AUTHORITY": "0x5555555555555555555555555555555555555555",
            "ERC_MANDATED_VAULT_SALT": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        }
    )
    bridge = FakeMandatedBridge(
        health_error=MandatedVaultMcpError(
            "Mandated-vault MCP tool vault_health_check failed: VAULT_NOT_DEPLOYED vault has no code"
        )
    )
    manager = WalletManager(
        config,
        bridge_factory=lambda _config: bridge,
    )

    payload = manager.get_status().to_dict()

    assert payload["mode"] == "mandated-vault"
    assert payload["vaultAddress"] == "0x1234567890123456789012345678901234567890"
    assert payload["vaultAddressSource"] == "predicted"
    assert payload["vaultDeployed"] is False
    assert payload["vaultHealth"] is None
    assert payload["stateChangingFlowsEnabled"] is True
    assert bridge.bootstrap_calls == 1
    assert bridge.predict_calls == 0
    assert bridge.health_check_calls == 0


def test_wallet_status_mandated_vault_fails_closed_on_mcp_outage() -> None:
    config = PredictConfig.from_env(
        {
            "PREDICT_ENV": "testnet",
            "PREDICT_STORAGE_DIR": "/tmp/predict",
            "PREDICT_WALLET_MODE": "mandated-vault",
            "ERC_MANDATED_FACTORY_ADDRESS": "0x1111111111111111111111111111111111111111",
            "ERC_MANDATED_VAULT_ASSET_ADDRESS": "0x4444444444444444444444444444444444444444",
            "ERC_MANDATED_VAULT_NAME": "Mandated Vault",
            "ERC_MANDATED_VAULT_SYMBOL": "MVLT",
            "ERC_MANDATED_VAULT_AUTHORITY": "0x5555555555555555555555555555555555555555",
            "ERC_MANDATED_VAULT_SALT": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        }
    )
    bridge = FakeMandatedBridge(
        health_error=MandatedVaultMcpUnavailableError(
            "Mandated-vault MCP process exited before completing the request"
        )
    )
    manager = WalletManager(
        config,
        bridge_factory=lambda _config: bridge,
    )

    with pytest.raises(MandatedVaultMcpUnavailableError):
        manager.get_status()


def test_wallet_status_mandated_vault_uses_single_loop_bridge_lifecycle() -> None:
    config = PredictConfig.from_env(
        {
            "PREDICT_ENV": "testnet",
            "PREDICT_STORAGE_DIR": "/tmp/predict",
            "PREDICT_WALLET_MODE": "mandated-vault",
            "ERC_MANDATED_VAULT_ADDRESS": "0x2222222222222222222222222222222222222222",
        }
    )
    bridge = FakeMandatedBridge(
        enforce_single_loop_close=True,
        health_result=VaultHealthCheckResult(
            blockNumber=101,
            vault="0x2222222222222222222222222222222222222222",
            mandateAuthority="0x3333333333333333333333333333333333333333",
            authorityEpoch="7",
            pendingAuthority="0x0000000000000000000000000000000000000000",
            nonceThreshold="2",
            totalAssets="123000000000000000000",
        ),
    )
    manager = WalletManager(config, bridge_factory=lambda _config: bridge)

    payload = manager.get_status().to_dict()

    assert payload["vaultDeployed"] is True
    assert bridge.close_called is True
    assert bridge.connect_loop_id is not None
    assert bridge.close_loop_id is not None
    assert bridge.connect_loop_id == bridge.close_loop_id


def test_wallet_approve_mandated_vault_fails_closed_with_v1_guidance() -> None:
    config = PredictConfig.from_env(
        {
            "PREDICT_ENV": "testnet",
            "PREDICT_STORAGE_DIR": "/tmp/predict",
            "PREDICT_WALLET_MODE": "mandated-vault",
            "ERC_MANDATED_VAULT_ADDRESS": "0x2222222222222222222222222222222222222222",
        }
    )
    manager = WalletManager(config)

    with pytest.raises(ConfigError) as error:
        manager.approve()

    message = str(error.value)
    assert "unsupported-in-mandated-vault-v1" in message
    assert "protected funding/control-plane operations" in message
    assert "predict.fun trading parity" in message


def test_wallet_status_predict_account_with_vault_overlay_exposes_route_and_roles() -> (
    None
):
    config = PredictConfig.from_env(
        {
            "PREDICT_ENV": "testnet",
            "PREDICT_STORAGE_DIR": "/tmp/predict",
            "PREDICT_WALLET_MODE": "predict-account",
            "PREDICT_ACCOUNT_ADDRESS": "0x1234567890123456789012345678901234567890",
            "PREDICT_PRIVY_PRIVATE_KEY": "0x59c6995e998f97a5a0044976f4d060f5d89c8b8c7f11b9aa0dbf3f0f7c7c1e01",
            "ERC_MANDATED_VAULT_ADDRESS": "0x2222222222222222222222222222222222222222",
            "ERC_MANDATED_FACTORY_ADDRESS": "0x1111111111111111111111111111111111111111",
            "ERC_MANDATED_VAULT_ASSET_ADDRESS": "0x4444444444444444444444444444444444444444",
            "ERC_MANDATED_VAULT_NAME": "Mandated Vault",
            "ERC_MANDATED_VAULT_SYMBOL": "MVLT",
            "ERC_MANDATED_VAULT_AUTHORITY": "0x5555555555555555555555555555555555555555",
            "ERC_MANDATED_VAULT_SALT": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "ERC_MANDATED_CHAIN_ID": "56",
            "ERC_MANDATED_FUNDING_MAX_AMOUNT_PER_TX": "5000000000000000000",
            "ERC_MANDATED_FUNDING_MAX_AMOUNT_PER_WINDOW": "10000000000000000000",
            "ERC_MANDATED_FUNDING_WINDOW_SECONDS": "3600",
        }
    )
    bridge = FakeMandatedBridge(
        health_result=VaultHealthCheckResult(
            blockNumber=101,
            vault="0x2222222222222222222222222222222222222222",
            mandateAuthority="0x5555555555555555555555555555555555555555",
            authorityEpoch="7",
            pendingAuthority="0x0000000000000000000000000000000000000000",
            nonceThreshold="2",
            totalAssets="123000000000000000000",
        )
    )
    manager = WalletManager(
        config,
        sdk_factory=lambda _config: FakeWalletSdk(
            wallet_mode=WalletMode.PREDICT_ACCOUNT,
            wallet_signer_address="0x7777777777777777777777777777777777777777",
            wallet_funding_address="0x1234567890123456789012345678901234567890",
        ),
        bridge_factory=lambda _config: bridge,
    )

    payload = manager.get_status().to_dict()
    orchestration = cast(dict[str, Any], payload["fundingOrchestration"])
    account_context = cast(dict[str, Any], orchestration["accountContext"])
    funding_policy = cast(dict[str, Any], orchestration["fundingPolicy"])
    funding_target = cast(dict[str, Any], orchestration["fundingTarget"])
    funding_plan = cast(dict[str, Any], orchestration["fundingPlan"])
    funding_session = cast(dict[str, Any], orchestration["fundingSession"])
    funding_next_step = cast(dict[str, Any], orchestration["fundingNextStep"])
    funding_task = cast(dict[str, Any], funding_next_step["task"])

    assert payload["mode"] == "predict-account"
    assert payload["fundingRoute"] == "vault-to-predict-account"
    assert (
        payload["predictAccountAddress"] == "0x1234567890123456789012345678901234567890"
    )
    assert payload["tradeSignerAddress"] == "0x7777777777777777777777777777777777777777"
    assert payload["vaultAddress"] == "0x2222222222222222222222222222222222222222"
    assert payload["vaultAddressSource"] == "explicit"
    assert payload["vaultExists"] is True
    assert account_context["executor"] == "0x5555555555555555555555555555555555555555"
    assert (
        account_context["defaults"]["allowedAdaptersRoot"]
        == MANDATED_ALLOWED_ADAPTERS_ROOT_DEFAULT
    )
    assert (
        account_context["defaults"]["maxDrawdownBps"]
        == MANDATED_FUNDING_TRANSFER_MAX_DRAWDOWN_BPS
    )
    assert (
        account_context["defaults"]["maxCumulativeDrawdownBps"]
        == MANDATED_FUNDING_TRANSFER_MAX_CUMULATIVE_DRAWDOWN_BPS
    )
    assert (
        funding_plan["fundingContext"]["allowedAdaptersRoot"]
        == MANDATED_ALLOWED_ADAPTERS_ROOT_DEFAULT
    )
    assert (
        funding_plan["fundingContext"]["maxDrawdownBps"]
        == MANDATED_FUNDING_TRANSFER_MAX_DRAWDOWN_BPS
    )
    assert (
        funding_plan["fundingContext"]["maxCumulativeDrawdownBps"]
        == MANDATED_FUNDING_TRANSFER_MAX_CUMULATIVE_DRAWDOWN_BPS
    )
    assert funding_policy["maxAmountPerTx"] == "5000000000000000000"
    assert funding_policy["maxAmountPerWindow"] == "10000000000000000000"
    assert funding_policy["windowSeconds"] == 3600
    assert funding_target["recipient"] == "0x1234567890123456789012345678901234567890"
    assert (
        funding_target["tokenAddress"] == "0x4444444444444444444444444444444444444444"
    )
    assert funding_session["sessionId"] == "session-wallet-overlay"
    assert funding_session["currentStep"] == "fundTargetAccount"
    assert funding_task["kind"] == "submitFunding"


def test_wallet_status_predict_account_overlay_reads_balances_outside_event_loop() -> None:
    config = PredictConfig.from_env(
        {
            "PREDICT_ENV": "testnet",
            "PREDICT_STORAGE_DIR": "/tmp/predict",
            "PREDICT_WALLET_MODE": "predict-account",
            "PREDICT_ACCOUNT_ADDRESS": "0x1234567890123456789012345678901234567890",
            "PREDICT_PRIVY_PRIVATE_KEY": "0x59c6995e998f97a5a0044976f4d060f5d89c8b8c7f11b9aa0dbf3f0f7c7c1e01",
            "ERC_MANDATED_VAULT_ADDRESS": "0x2222222222222222222222222222222222222222",
            "ERC_MANDATED_FACTORY_ADDRESS": "0x1111111111111111111111111111111111111111",
            "ERC_MANDATED_VAULT_ASSET_ADDRESS": "0x4444444444444444444444444444444444444444",
            "ERC_MANDATED_VAULT_NAME": "Mandated Vault",
            "ERC_MANDATED_VAULT_SYMBOL": "MVLT",
            "ERC_MANDATED_VAULT_AUTHORITY": "0x5555555555555555555555555555555555555555",
            "ERC_MANDATED_VAULT_SALT": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        }
    )
    bridge = FakeMandatedBridge(
        health_result=VaultHealthCheckResult(
            blockNumber=101,
            vault="0x2222222222222222222222222222222222222222",
            mandateAuthority="0x5555555555555555555555555555555555555555",
            authorityEpoch="7",
            pendingAuthority="0x0000000000000000000000000000000000000000",
            nonceThreshold="2",
            totalAssets="123000000000000000000",
        )
    )
    manager = WalletManager(
        config,
        sdk_factory=lambda _config: AsyncUnsafeWalletSdk(
            wallet_mode=WalletMode.PREDICT_ACCOUNT,
            wallet_signer_address="0x7777777777777777777777777777777777777777",
            wallet_funding_address="0x1234567890123456789012345678901234567890",
        ),
        bridge_factory=lambda _config: bridge,
    )

    payload = manager.get_status().to_dict()

    assert payload["fundingRoute"] == "vault-to-predict-account"
    assert payload["bnbBalanceWei"] == 2_000_000_000_000_000_000
    assert payload["usdtBalanceWei"] == 30_000_000_000_000_000_000


def test_wallet_status_predict_account_overlay_treats_empty_contract_reads_as_undeployed() -> None:
    config = PredictConfig.from_env(
        {
            "PREDICT_ENV": "testnet",
            "PREDICT_STORAGE_DIR": "/tmp/predict",
            "PREDICT_WALLET_MODE": "predict-account",
            "PREDICT_ACCOUNT_ADDRESS": "0x1234567890123456789012345678901234567890",
            "PREDICT_PRIVY_PRIVATE_KEY": "0x59c6995e998f97a5a0044976f4d060f5d89c8b8c7f11b9aa0dbf3f0f7c7c1e01",
            "ERC_MANDATED_VAULT_ADDRESS": "0x2222222222222222222222222222222222222222",
            "ERC_MANDATED_FACTORY_ADDRESS": "0x1111111111111111111111111111111111111111",
            "ERC_MANDATED_VAULT_ASSET_ADDRESS": "0x4444444444444444444444444444444444444444",
            "ERC_MANDATED_VAULT_NAME": "Mandated Vault",
            "ERC_MANDATED_VAULT_SYMBOL": "MVLT",
            "ERC_MANDATED_VAULT_AUTHORITY": "0x5555555555555555555555555555555555555555",
            "ERC_MANDATED_VAULT_SALT": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        }
    )
    bridge = FakeMandatedBridge(
        health_error=MandatedVaultMcpError(
            'Mandated-vault MCP tool vault_health_check failed: SDK_ERROR The contract function "mandateAuthority" returned no data ("0x"). The address is not a contract.'
        )
    )
    manager = WalletManager(
        config,
        sdk_factory=lambda _config: FakeWalletSdk(
            wallet_mode=WalletMode.PREDICT_ACCOUNT,
            wallet_signer_address="0x7777777777777777777777777777777777777777",
            wallet_funding_address="0x1234567890123456789012345678901234567890",
        ),
        bridge_factory=lambda _config: bridge,
    )

    payload = manager.get_status().to_dict()

    assert payload["fundingRoute"] == "vault-to-predict-account"
    assert payload["vaultAddress"] == "0x2222222222222222222222222222222222222222"
    assert payload["vaultExists"] is False


def test_wallet_status_predict_account_overlay_computes_dynamic_adapter_root() -> None:
    config = PredictConfig.from_env(
        {
            "PREDICT_ENV": "testnet",
            "PREDICT_STORAGE_DIR": "/tmp/predict",
            "PREDICT_WALLET_MODE": "predict-account",
            "PREDICT_ACCOUNT_ADDRESS": "0x1234567890123456789012345678901234567890",
            "PREDICT_PRIVY_PRIVATE_KEY": "0x59c6995e998f97a5a0044976f4d060f5d89c8b8c7f11b9aa0dbf3f0f7c7c1e01",
            "ERC_MANDATED_VAULT_ADDRESS": "0x2222222222222222222222222222222222222222",
            "ERC_MANDATED_FACTORY_ADDRESS": "0x1111111111111111111111111111111111111111",
            "ERC_MANDATED_VAULT_ASSET_ADDRESS": "0x4444444444444444444444444444444444444444",
            "ERC_MANDATED_VAULT_NAME": "Mandated Vault",
            "ERC_MANDATED_VAULT_SYMBOL": "MVLT",
            "ERC_MANDATED_VAULT_AUTHORITY": "0x5555555555555555555555555555555555555555",
            "ERC_MANDATED_VAULT_SALT": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "ERC_MANDATED_CHAIN_ID": "56",
        }
    )
    bridge = FakeMandatedBridge(
        health_result=VaultHealthCheckResult(
            blockNumber=101,
            vault="0x2222222222222222222222222222222222222222",
            mandateAuthority="0x5555555555555555555555555555555555555555",
            authorityEpoch="7",
            pendingAuthority="0x0000000000000000000000000000000000000000",
            nonceThreshold="2",
            totalAssets="123000000000000000000",
        )
    )
    manager = WalletManager(
        config,
        sdk_factory=lambda _config: CodehashWalletSdk(
            wallet_mode=WalletMode.PREDICT_ACCOUNT,
            wallet_signer_address="0x7777777777777777777777777777777777777777",
            wallet_funding_address="0x1234567890123456789012345678901234567890",
            contract_code=b"\x60\x60\x60\x40\x52",
        ),
        bridge_factory=lambda _config: bridge,
    )

    payload = manager.get_status().to_dict()
    orchestration = cast(dict[str, Any], payload["fundingOrchestration"])
    account_context = cast(dict[str, Any], orchestration["accountContext"])
    funding_plan = cast(dict[str, Any], orchestration["fundingPlan"])
    codehash = Web3.keccak(b"\x60\x60\x60\x40\x52")
    expected_root = "0x" + Web3.keccak(
        abi_encode(
            ["address", "bytes32"],
            [Web3.to_checksum_address("0x4444444444444444444444444444444444444444"), codehash],
        )
    ).hex()

    assert account_context["defaults"]["allowedAdaptersRoot"] == expected_root
    assert funding_plan["fundingContext"]["allowedAdaptersRoot"] == expected_root
