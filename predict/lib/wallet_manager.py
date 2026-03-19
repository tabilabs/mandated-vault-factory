from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Callable, Protocol

from eth_abi import encode as abi_encode
from eth_account import Account
from predict_sdk import OrderBuilder, OrderBuilderOptions
from predict_sdk._internal.contracts import (
    get_conditional_tokens_contract,
    get_exchange_contract,
    get_neg_risk_adapter_contract,
)
from web3 import Web3

from .config import (
    ConfigError,
    PredictConfig,
    RuntimeEnv,
    WalletMode,
    mandated_vault_v1_unsupported_error,
)
from .mandated_mcp_bridge import (
    FactoryCreateVaultPrepareResult,
    MandatedVaultMcpBridge,
    MandatedVaultMcpError,
    VaultBootstrapResult,
    VaultHealthCheckResult,
)


@dataclass
class ApprovalSnapshot:
    standard_exchange_approval: bool
    standard_exchange_allowance: bool
    standard_neg_risk_exchange_approval: bool
    standard_neg_risk_exchange_allowance: bool
    standard_neg_risk_adapter_approval: bool
    yield_exchange_approval: bool
    yield_exchange_allowance: bool
    yield_neg_risk_exchange_approval: bool
    yield_neg_risk_exchange_allowance: bool
    yield_neg_risk_adapter_approval: bool

    @property
    def standard_ready(self) -> bool:
        return all(
            [
                self.standard_exchange_approval,
                self.standard_exchange_allowance,
                self.standard_neg_risk_exchange_approval,
                self.standard_neg_risk_exchange_allowance,
                self.standard_neg_risk_adapter_approval,
            ]
        )

    @property
    def yield_ready(self) -> bool:
        return all(
            [
                self.yield_exchange_approval,
                self.yield_exchange_allowance,
                self.yield_neg_risk_exchange_approval,
                self.yield_neg_risk_exchange_allowance,
                self.yield_neg_risk_adapter_approval,
            ]
        )

    @property
    def all_ready(self) -> bool:
        return self.standard_ready and self.yield_ready

    def to_dict(self) -> dict[str, object]:
        return {
            "standard": {
                "exchangeApproval": self.standard_exchange_approval,
                "exchangeAllowance": self.standard_exchange_allowance,
                "negRiskExchangeApproval": self.standard_neg_risk_exchange_approval,
                "negRiskExchangeAllowance": self.standard_neg_risk_exchange_allowance,
                "negRiskAdapterApproval": self.standard_neg_risk_adapter_approval,
                "ready": self.standard_ready,
            },
            "yieldBearing": {
                "exchangeApproval": self.yield_exchange_approval,
                "exchangeAllowance": self.yield_exchange_allowance,
                "negRiskExchangeApproval": self.yield_neg_risk_exchange_approval,
                "negRiskExchangeAllowance": self.yield_neg_risk_exchange_allowance,
                "negRiskAdapterApproval": self.yield_neg_risk_adapter_approval,
                "ready": self.yield_ready,
            },
            "allReady": self.all_ready,
        }


class WalletSdkProtocol(Protocol):
    @property
    def mode(self) -> WalletMode: ...

    @property
    def signer_address(self) -> str: ...

    @property
    def funding_address(self) -> str: ...

    @property
    def chain_name(self) -> str: ...

    def get_bnb_balance_wei(self) -> int: ...

    def get_usdt_balance_wei(self) -> int: ...

    def get_approval_snapshot(self) -> ApprovalSnapshot: ...

    def set_all_approvals(self) -> dict[str, Any]: ...


class MandatedVaultBridgeProtocol(Protocol):
    @property
    def available_tools(self) -> frozenset[str]: ...

    @property
    def missing_required_tools(self) -> frozenset[str]: ...

    @property
    def runtime_ready(self) -> bool: ...

    async def connect(self) -> None: ...

    async def close(self) -> None: ...

    async def predict_vault_address(
        self,
        *,
        factory: str | None,
        asset: str,
        name: str,
        symbol: str,
        authority: str,
        salt: str,
    ) -> Any: ...

    async def health_check(self, vault: str) -> VaultHealthCheckResult: ...

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
    ) -> FactoryCreateVaultPrepareResult: ...

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
    ) -> VaultBootstrapResult: ...

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
    ) -> Any: ...

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
    ) -> Any: ...

    async def build_agent_fund_and_action_plan(
        self,
        *,
        account_context: dict[str, Any],
        funding_target: dict[str, Any],
        funding_context: dict[str, Any],
        follow_up_action: dict[str, Any],
        funding_policy: dict[str, Any] | None = None,
    ) -> Any: ...

    async def create_agent_fund_and_action_session(
        self,
        *,
        fund_and_action_plan: dict[str, Any],
        session_id: str | None = None,
        created_at: str | None = None,
    ) -> Any: ...

    async def next_agent_fund_and_action_session_step(
        self,
        *,
        session: dict[str, Any],
    ) -> Any: ...


class PredictSdkWallet:
    def __init__(self, config: PredictConfig) -> None:
        self._config = config
        if config.wallet_mode == WalletMode.READ_ONLY:
            raise ConfigError(
                "Wallet actions require PREDICT_PRIVATE_KEY or Predict Account credentials."
            )

        if config.wallet_mode == WalletMode.PREDICT_ACCOUNT:
            assert config.privy_private_key_value is not None
            assert config.predict_account_address is not None
            self._builder = OrderBuilder.make(
                config.chain_id,
                config.privy_private_key_value,
                OrderBuilderOptions(predict_account=config.predict_account_address),
            )
        else:
            assert config.private_key_value is not None
            self._builder = OrderBuilder.make(config.chain_id, config.private_key_value)

    @property
    def mode(self) -> WalletMode:
        return self._config.wallet_mode

    @property
    def signer_address(self) -> str:
        if self._config.wallet_mode == WalletMode.PREDICT_ACCOUNT:
            assert self._config.privy_private_key_value is not None
            return Account.from_key(self._config.privy_private_key_value).address
        assert self._config.private_key_value is not None
        return Account.from_key(self._config.private_key_value).address

    @property
    def funding_address(self) -> str:
        return self._config.predict_account_address or self.signer_address

    @property
    def chain_name(self) -> str:
        return (
            "BNB Mainnet" if self._config.env == RuntimeEnv.MAINNET else "BNB Testnet"
        )

    def get_bnb_balance_wei(self) -> int:
        web3 = getattr(self._builder, "_web3", None)
        if web3 is None:
            raise ConfigError(
                "BNB balance requires an initialized Web3 signer context."
            )
        return int(web3.eth.get_balance(self.funding_address))

    def get_usdt_balance_wei(self) -> int:
        return int(self._builder.balance_of("USDT", self.funding_address))

    def get_approval_snapshot(self) -> ApprovalSnapshot:
        contracts = self._builder.contracts
        if contracts is None:
            raise ConfigError(
                "Approval checks require initialized predict.fun contracts."
            )

        owner = self.funding_address
        return ApprovalSnapshot(
            standard_exchange_approval=self._erc1155_approval(
                owner, is_neg_risk=False, is_yield_bearing=False
            ),
            standard_exchange_allowance=self._usdt_allowance(
                owner, is_neg_risk=False, is_yield_bearing=False
            ),
            standard_neg_risk_exchange_approval=self._erc1155_approval(
                owner, is_neg_risk=True, is_yield_bearing=False
            ),
            standard_neg_risk_exchange_allowance=self._usdt_allowance(
                owner, is_neg_risk=True, is_yield_bearing=False
            ),
            standard_neg_risk_adapter_approval=self._adapter_approval(
                owner, is_yield_bearing=False
            ),
            yield_exchange_approval=self._erc1155_approval(
                owner, is_neg_risk=False, is_yield_bearing=True
            ),
            yield_exchange_allowance=self._usdt_allowance(
                owner, is_neg_risk=False, is_yield_bearing=True
            ),
            yield_neg_risk_exchange_approval=self._erc1155_approval(
                owner, is_neg_risk=True, is_yield_bearing=True
            ),
            yield_neg_risk_exchange_allowance=self._usdt_allowance(
                owner, is_neg_risk=True, is_yield_bearing=True
            ),
            yield_neg_risk_adapter_approval=self._adapter_approval(
                owner, is_yield_bearing=True
            ),
        )

    def set_all_approvals(self) -> dict[str, Any]:
        return {
            "standard": self._builder.set_approvals(is_yield_bearing=False),
            "yieldBearing": self._builder.set_approvals(is_yield_bearing=True),
        }

    def _erc1155_approval(
        self, owner: str, *, is_neg_risk: bool, is_yield_bearing: bool
    ) -> bool:
        contracts = self._builder.contracts
        assert contracts is not None
        exchange = get_exchange_contract(
            contracts,
            is_neg_risk=is_neg_risk,
            is_yield_bearing=is_yield_bearing,
        )
        conditional_tokens = get_conditional_tokens_contract(
            contracts,
            is_neg_risk=is_neg_risk,
            is_yield_bearing=is_yield_bearing,
        )
        return bool(
            conditional_tokens.functions.isApprovedForAll(
                owner, exchange.address
            ).call()
        )

    def _adapter_approval(self, owner: str, *, is_yield_bearing: bool) -> bool:
        contracts = self._builder.contracts
        assert contracts is not None
        adapter = get_neg_risk_adapter_contract(
            contracts, is_yield_bearing=is_yield_bearing
        )
        conditional_tokens = get_conditional_tokens_contract(
            contracts,
            is_neg_risk=True,
            is_yield_bearing=is_yield_bearing,
        )
        return bool(
            conditional_tokens.functions.isApprovedForAll(owner, adapter.address).call()
        )

    def _usdt_allowance(
        self, owner: str, *, is_neg_risk: bool, is_yield_bearing: bool
    ) -> bool:
        contracts = self._builder.contracts
        assert contracts is not None
        exchange = get_exchange_contract(
            contracts,
            is_neg_risk=is_neg_risk,
            is_yield_bearing=is_yield_bearing,
        )
        allowance = contracts.usdt.functions.allowance(owner, exchange.address).call()
        return int(allowance) > 0


class FixtureWalletSdk:
    def __init__(self, config: PredictConfig) -> None:
        self._config = config
        if config.wallet_mode == WalletMode.READ_ONLY:
            raise ConfigError(
                "Wallet actions require PREDICT_PRIVATE_KEY or Predict Account credentials."
            )

    @property
    def mode(self) -> WalletMode:
        return self._config.wallet_mode

    @property
    def signer_address(self) -> str:
        if self._config.wallet_mode == WalletMode.PREDICT_ACCOUNT:
            assert self._config.privy_private_key_value is not None
            return Account.from_key(self._config.privy_private_key_value).address
        assert self._config.private_key_value is not None
        return Account.from_key(self._config.private_key_value).address

    @property
    def funding_address(self) -> str:
        return self._config.predict_account_address or self.signer_address

    @property
    def chain_name(self) -> str:
        return "BNB Testnet"

    def get_bnb_balance_wei(self) -> int:
        return 1_500_000_000_000_000_000

    def get_usdt_balance_wei(self) -> int:
        return 25_000_000_000_000_000_000

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

    def set_all_approvals(self) -> dict[str, Any]:
        return {
            "standard": {"success": True, "mode": "fixture"},
            "yieldBearing": {"success": True, "mode": "fixture"},
        }


async def load_wallet_bnb_balance_wei(sdk: WalletSdkProtocol) -> int:
    return int(await asyncio.to_thread(sdk.get_bnb_balance_wei))


async def load_wallet_usdt_balance_wei(sdk: WalletSdkProtocol) -> int:
    return int(await asyncio.to_thread(sdk.get_usdt_balance_wei))


def make_wallet_sdk(config: PredictConfig) -> WalletSdkProtocol:
    if config.env == RuntimeEnv.TEST_FIXTURE:
        return FixtureWalletSdk(config)
    return PredictSdkWallet(config)


@dataclass
class WalletStatusSnapshot:
    mode: str
    signer_address: str
    funding_address: str
    chain: str
    bnb_balance_wei: int
    usdt_balance_wei: int
    auth_ready: bool
    approvals: ApprovalSnapshot
    funding_route: str | None = None
    predict_account_address: str | None = None
    trade_signer_address: str | None = None
    vault_address: str | None = None
    vault_address_source: str | None = None
    vault_exists: bool | None = None
    funding_orchestration: dict[str, object] | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "mode": self.mode,
            "signerAddress": self.signer_address,
            "fundingAddress": self.funding_address,
            "chain": self.chain,
            "bnbBalanceWei": self.bnb_balance_wei,
            "usdtBalanceWei": self.usdt_balance_wei,
            "authReady": self.auth_ready,
            "approvals": self.approvals.to_dict(),
        }
        if self.funding_route is not None:
            payload.update(
                {
                    "fundingRoute": self.funding_route,
                    "predictAccountAddress": self.predict_account_address,
                    "tradeSignerAddress": self.trade_signer_address,
                    "vaultAddress": self.vault_address,
                    "vaultAddressSource": self.vault_address_source,
                    "vaultExists": self.vault_exists,
                    "fundingOrchestration": self.funding_orchestration,
                }
            )
        return payload


@dataclass
class VaultToPredictAccountFundingOrchestration:
    funding_route: str
    predict_account_address: str
    trade_signer_address: str
    vault_address: str
    vault_address_source: str
    vault_exists: bool
    account_context: dict[str, Any]
    funding_policy: dict[str, Any]
    funding_target: dict[str, Any]
    funding_plan: dict[str, Any]
    funding_session: dict[str, Any]
    funding_next_step: dict[str, Any]

    def to_dict(self) -> dict[str, object]:
        return {
            "fundingRoute": self.funding_route,
            "predictAccountAddress": self.predict_account_address,
            "tradeSignerAddress": self.trade_signer_address,
            "vaultAddress": self.vault_address,
            "vaultAddressSource": self.vault_address_source,
            "vaultExists": self.vault_exists,
            "accountContext": self.account_context,
            "fundingPolicy": self.funding_policy,
            "fundingTarget": self.funding_target,
            "fundingPlan": self.funding_plan,
            "fundingSession": self.funding_session,
            "fundingNextStep": self.funding_next_step,
        }


@dataclass
class ApprovalRunSummary:
    standard: Any
    yield_bearing: Any

    def to_dict(self) -> dict[str, object]:
        return {
            "standard": self.standard,
            "yieldBearing": self.yield_bearing,
        }


MANDATED_FUNDING_TRANSFER_MAX_DRAWDOWN_BPS = "10000"
MANDATED_FUNDING_TRANSFER_MAX_CUMULATIVE_DRAWDOWN_BPS = "10000"


@dataclass
class MandatedVaultResolution:
    vault_address: str
    vault_address_source: str
    vault_deployed: bool
    vault_health: VaultHealthCheckResult | None
    create_vault_prepare: FactoryCreateVaultPrepareResult | None


@dataclass
class MandatedWalletStatusSnapshot:
    mode: str
    selected_chain_name: str
    selected_chain_id: int
    mcp_command: str
    mcp_available_tools: list[str]
    mcp_missing_required_tools: list[str]
    mcp_runtime_ready: bool
    vault_address: str
    vault_address_source: str
    vault_deployed: bool
    vault_health: VaultHealthCheckResult | None
    state_changing_flows_enabled: bool

    def to_dict(self) -> dict[str, object]:
        health_payload: dict[str, object] | None = None
        if self.vault_health is not None:
            health_payload = {
                "mandateAuthority": self.vault_health.mandateAuthority,
                "authorityEpoch": self.vault_health.authorityEpoch,
                "nonceThreshold": self.vault_health.nonceThreshold,
                "totalAssets": self.vault_health.totalAssets,
            }

        return {
            "mode": self.mode,
            "selectedChain": {
                "name": self.selected_chain_name,
                "chainId": self.selected_chain_id,
            },
            "mcp": {
                "command": self.mcp_command,
                "availableTools": self.mcp_available_tools,
                "missingRequiredTools": self.mcp_missing_required_tools,
                "runtimeReady": self.mcp_runtime_ready,
            },
            "vaultAddress": self.vault_address,
            "vaultAddressSource": self.vault_address_source,
            "vaultDeployed": self.vault_deployed,
            "vaultDeploymentState": "deployed" if self.vault_deployed else "undeployed",
            "vaultHealth": health_payload,
            "stateChangingFlowsEnabled": self.state_changing_flows_enabled,
        }


def has_mandated_vault_derivation(config: PredictConfig) -> bool:
    return all(
        [
            config.mandated_factory_address,
            config.mandated_vault_asset_address,
            config.mandated_vault_name,
            config.mandated_vault_symbol,
            config.mandated_vault_authority,
            config.mandated_vault_salt,
        ]
    )


def _supports_vault_bootstrap(bridge: MandatedVaultBridgeProtocol) -> bool:
    return "vault_bootstrap" in bridge.available_tools


def _bootstrap_create_vault_prepare(
    bootstrap: VaultBootstrapResult,
) -> FactoryCreateVaultPrepareResult | None:
    create_tx = bootstrap.createTx
    if create_tx is None or create_tx.txRequest is None:
        return None
    return FactoryCreateVaultPrepareResult(
        predictedVault=bootstrap.predictedVault,
        txRequest=create_tx.txRequest,
    )


async def resolve_mandated_vault(
    config: PredictConfig,
    bridge: MandatedVaultBridgeProtocol,
    *,
    include_create_prepare: bool,
) -> MandatedVaultResolution:
    if config.mandated_vault_address:
        vault_address = config.mandated_vault_address
        vault_address_source = "explicit"
    else:
        if not has_mandated_vault_derivation(config):
            raise ConfigError(
                "mandated-vault mode requires ERC_MANDATED_VAULT_ADDRESS or full derivation inputs."
            )

        if _supports_vault_bootstrap(bridge):
            assert config.mandated_vault_authority is not None
            bootstrap = await bridge.vault_bootstrap(
                factory=config.mandated_factory_address,
                asset=str(config.mandated_vault_asset_address),
                name=str(config.mandated_vault_name),
                symbol=str(config.mandated_vault_symbol),
                salt=str(config.mandated_vault_salt),
                signer_address=str(config.mandated_vault_authority),
                mode="plan",
                authority_mode="single_key",
                authority=str(config.mandated_vault_authority),
                create_account_context=False,
                create_funding_policy=False,
            )
            vault_address = bootstrap.deployedVault
            vault_address_source = "predicted"
            vault_deployed = bootstrap.alreadyDeployed
            vault_health = bootstrap.vaultHealth
            if vault_deployed and vault_health is None:
                vault_health = await bridge.health_check(vault_address)

            return MandatedVaultResolution(
                vault_address=vault_address,
                vault_address_source=vault_address_source,
                vault_deployed=vault_deployed,
                vault_health=vault_health,
                create_vault_prepare=(
                    _bootstrap_create_vault_prepare(bootstrap)
                    if include_create_prepare and not vault_deployed
                    else None
                ),
            )

        predicted = await bridge.predict_vault_address(
            factory=config.mandated_factory_address,
            asset=str(config.mandated_vault_asset_address),
            name=str(config.mandated_vault_name),
            symbol=str(config.mandated_vault_symbol),
            authority=str(config.mandated_vault_authority),
            salt=str(config.mandated_vault_salt),
        )
        vault_address = str(getattr(predicted, "predictedVault"))
        vault_address_source = "predicted"

    vault_health: VaultHealthCheckResult | None = None
    vault_deployed = False
    try:
        vault_health = await bridge.health_check(vault_address)
        vault_deployed = True
    except MandatedVaultMcpError as error:
        if not _is_expected_undeployed_health_error(error):
            raise
        vault_health = None

    create_vault_prepare: FactoryCreateVaultPrepareResult | None = None
    if (
        include_create_prepare
        and not vault_deployed
        and has_mandated_vault_derivation(config)
    ):
        assert config.mandated_vault_authority is not None
        create_vault_prepare = await bridge.prepare_create_vault(
            from_address=config.mandated_vault_authority,
            factory=config.mandated_factory_address,
            asset=str(config.mandated_vault_asset_address),
            name=str(config.mandated_vault_name),
            symbol=str(config.mandated_vault_symbol),
            authority=str(config.mandated_vault_authority),
            salt=str(config.mandated_vault_salt),
        )

    return MandatedVaultResolution(
        vault_address=vault_address,
        vault_address_source=vault_address_source,
        vault_deployed=vault_deployed,
        vault_health=vault_health,
        create_vault_prepare=create_vault_prepare,
    )


def _is_expected_undeployed_health_error(error: MandatedVaultMcpError) -> bool:
    message = str(error).upper()
    undeployed_markers = (
        "VAULT_NOT_DEPLOYED",
        "VAULT_UNDEPLOYED",
        "VAULT_NOT_FOUND",
        "NO_CONTRACT_CODE",
        "NOT DEPLOYED",
        "RETURNED NO DATA",
        "ADDRESS IS NOT A CONTRACT",
    )
    return any(marker in message for marker in undeployed_markers)


def _has_predict_account_overlay(config: PredictConfig) -> bool:
    return (
        config.wallet_mode == WalletMode.PREDICT_ACCOUNT
        and config.has_mandated_config_input
    )


def _result_dict(result: Any, *, field: str, operation: str) -> dict[str, Any]:
    payload = result.model_dump() if hasattr(result, "model_dump") else result
    if not isinstance(payload, dict):
        raise ConfigError(f"Malformed {operation} response: expected object payload.")
    nested = payload.get(field)
    if not isinstance(nested, dict):
        raise ConfigError(
            f"Malformed {operation} response: expected `{field}` object in payload."
        )
    return nested


async def build_vault_to_predict_account_orchestration(
    config: PredictConfig,
    bridge: MandatedVaultBridgeProtocol,
    *,
    predict_account_address: str,
    trade_signer_address: str,
    current_usdt_balance_wei: int,
    wallet_sdk: Any | None = None,
) -> VaultToPredictAccountFundingOrchestration:
    if not config.mandated_vault_authority:
        raise ConfigError(
            "predict-account + vault overlay requires ERC_MANDATED_VAULT_AUTHORITY for funding orchestration."
        )
    if not config.mandated_vault_asset_address:
        raise ConfigError(
            "predict-account + vault overlay requires ERC_MANDATED_VAULT_ASSET_ADDRESS for funding orchestration."
        )

    resolution = await resolve_mandated_vault(
        config, bridge, include_create_prepare=False
    )
    timestamp = (
        datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    )
    agent_id = f"predict-account:{predict_account_address.lower()}"
    policy_id = f"vault-to-predict-account:{predict_account_address.lower()}"
    funding_executor_address = config.mandated_executor_address
    if not funding_executor_address:
        raise ConfigError(
            "predict-account + vault overlay requires an authorized funding executor address."
        )
    allowed_adapters_root = _resolve_transfer_allowed_adapters_root(
        token_address=str(config.mandated_vault_asset_address),
        wallet_sdk=wallet_sdk,
        fallback_root=config.mandated_allowed_adapters_root,
    )
    mandate_defaults = {
        "allowedAdaptersRoot": allowed_adapters_root,
        "maxDrawdownBps": MANDATED_FUNDING_TRANSFER_MAX_DRAWDOWN_BPS,
        "maxCumulativeDrawdownBps": MANDATED_FUNDING_TRANSFER_MAX_CUMULATIVE_DRAWDOWN_BPS,
        "payloadBinding": "actionsDigest",
        "extensions": "0x",
    }

    context_result = await bridge.create_agent_account_context(
        agent_id=agent_id,
        vault=resolution.vault_address,
        authority=config.mandated_vault_authority,
        executor=funding_executor_address,
        funding_policy_ref=policy_id,
        defaults=dict(mandate_defaults),
        created_at=timestamp,
        updated_at=timestamp,
    )
    account_context = _result_dict(
        context_result,
        field="accountContext",
        operation="agent_account_context_create",
    )

    policy_result = await bridge.create_agent_funding_policy(
        policy_id=policy_id,
        allowed_token_addresses=[config.mandated_vault_asset_address],
        allowed_recipients=[predict_account_address],
        max_amount_per_tx=config.mandated_funding_max_amount_per_tx,
        max_amount_per_window=config.mandated_funding_max_amount_per_window,
        window_seconds=config.mandated_funding_window_seconds,
        repeatable=True,
        created_at=timestamp,
        updated_at=timestamp,
    )
    funding_policy = _result_dict(
        policy_result,
        field="fundingPolicy",
        operation="agent_funding_policy_create",
    )

    minimum_target_balance_wei = 5 * (10**18)
    required_amount_raw = str(
        max(minimum_target_balance_wei - max(current_usdt_balance_wei, 0), 0)
    )
    funding_target = {
        "label": "predict-account-usdt",
        "recipient": predict_account_address,
        "tokenAddress": config.mandated_vault_asset_address,
        "requiredAmountRaw": required_amount_raw,
        "currentBalanceRaw": str(max(current_usdt_balance_wei, 0)),
        "balanceSnapshot": {
            "snapshotAt": timestamp,
            "maxStalenessSeconds": 120,
            "source": "predict-wallet-status",
        },
    }
    funding_context = {
        "nonce": "0",
        "deadline": "0",
        "authorityEpoch": (
            resolution.vault_health.authorityEpoch if resolution.vault_health else "0"
        ),
        **mandate_defaults,
    }
    follow_up_action = {
        "kind": "predict-order-submission",
        "target": "predict-api",
        "payload": {
            "status": "deferred",
            "reason": "buy-orchestration-not-enabled-in-this-task",
        },
    }
    plan_result = await bridge.build_agent_fund_and_action_plan(
        account_context=account_context,
        funding_policy=funding_policy,
        funding_target=funding_target,
        funding_context=funding_context,
        follow_up_action=follow_up_action,
    )
    funding_plan = (
        plan_result.model_dump() if hasattr(plan_result, "model_dump") else plan_result
    )
    if not isinstance(funding_plan, dict):
        raise ConfigError(
            "Malformed agent_build_fund_and_action_plan response: expected object payload."
        )

    session_result = await bridge.create_agent_fund_and_action_session(
        fund_and_action_plan=funding_plan,
        created_at=timestamp,
    )
    funding_session = _result_dict(
        session_result,
        field="session",
        operation="agent_fund_and_action_session_create",
    )

    next_step_result = await bridge.next_agent_fund_and_action_session_step(
        session=funding_session,
    )
    funding_next_step = (
        next_step_result.model_dump()
        if hasattr(next_step_result, "model_dump")
        else next_step_result
    )
    if not isinstance(funding_next_step, dict):
        raise ConfigError(
            "Malformed agent_fund_and_action_session_next_step response: expected object payload."
        )
    task_payload = funding_next_step.get("task")
    if not isinstance(task_payload, dict):
        raise ConfigError(
            "Malformed agent_fund_and_action_session_next_step response: expected `task` object in payload."
        )

    return VaultToPredictAccountFundingOrchestration(
        funding_route="vault-to-predict-account",
        predict_account_address=predict_account_address,
        trade_signer_address=trade_signer_address,
        vault_address=resolution.vault_address,
        vault_address_source=resolution.vault_address_source,
        vault_exists=resolution.vault_deployed,
        account_context=account_context,
        funding_policy=funding_policy,
        funding_target=funding_target,
        funding_plan=funding_plan,
        funding_session=funding_session,
        funding_next_step=funding_next_step,
    )


def _resolve_transfer_allowed_adapters_root(
    *,
    token_address: str,
    wallet_sdk: Any | None,
    fallback_root: str,
) -> str:
    builder = getattr(wallet_sdk, "_builder", None)
    web3 = getattr(builder, "_web3", None)
    if web3 is None:
        return fallback_root

    checksum_token = Web3.to_checksum_address(token_address)
    try:
        token_code = web3.eth.get_code(checksum_token)
    except Exception as error:  # pragma: no cover - defensive live-path guard
        raise ConfigError(
            f"Unable to load token code for mandated funding adapter root: {checksum_token}"
        ) from error
    if len(token_code) == 0:
        raise ConfigError(
            f"Mandated funding token address has no deployed code: {checksum_token}"
        )

    codehash = Web3.keccak(token_code)
    leaf_root = Web3.keccak(
        abi_encode(["address", "bytes32"], [checksum_token, codehash])
    )
    return "0x" + leaf_root.hex()


class WalletManager:
    def __init__(
        self,
        config: PredictConfig,
        *,
        sdk_factory: Callable[[PredictConfig], WalletSdkProtocol] = make_wallet_sdk,
        bridge_factory: Callable[
            [PredictConfig], MandatedVaultBridgeProtocol
        ] = MandatedVaultMcpBridge,
    ) -> None:
        self._config = config
        self._sdk_factory = sdk_factory
        self._bridge_factory = bridge_factory

    def get_status(self) -> WalletStatusSnapshot | MandatedWalletStatusSnapshot:
        if self._config.wallet_mode == WalletMode.MANDATED_VAULT:
            return self._get_mandated_status()

        sdk = self._require_sdk()
        if _has_predict_account_overlay(self._config):
            return self._get_predict_account_overlay_status(sdk)

        return WalletStatusSnapshot(
            mode=sdk.mode.value,
            signer_address=sdk.signer_address,
            funding_address=sdk.funding_address,
            chain=sdk.chain_name,
            bnb_balance_wei=sdk.get_bnb_balance_wei(),
            usdt_balance_wei=sdk.get_usdt_balance_wei(),
            auth_ready=bool(self._config.auth_signer_address),
            approvals=sdk.get_approval_snapshot(),
        )

    def _get_predict_account_overlay_status(
        self, sdk: WalletSdkProtocol
    ) -> WalletStatusSnapshot:
        bridge = self._bridge_factory(self._config)

        async def _load_and_close() -> WalletStatusSnapshot:
            await bridge.connect()
            try:
                bnb_balance = await load_wallet_bnb_balance_wei(sdk)
                usdt_balance = await load_wallet_usdt_balance_wei(sdk)
                orchestration = await build_vault_to_predict_account_orchestration(
                    self._config,
                    bridge,
                    predict_account_address=sdk.funding_address,
                    trade_signer_address=sdk.signer_address,
                    current_usdt_balance_wei=usdt_balance,
                    wallet_sdk=sdk,
                )
                return WalletStatusSnapshot(
                    mode=sdk.mode.value,
                    signer_address=sdk.signer_address,
                    funding_address=sdk.funding_address,
                    chain=sdk.chain_name,
                    bnb_balance_wei=bnb_balance,
                    usdt_balance_wei=usdt_balance,
                    auth_ready=bool(self._config.auth_signer_address),
                    approvals=sdk.get_approval_snapshot(),
                    funding_route=orchestration.funding_route,
                    predict_account_address=orchestration.predict_account_address,
                    trade_signer_address=orchestration.trade_signer_address,
                    vault_address=orchestration.vault_address,
                    vault_address_source=orchestration.vault_address_source,
                    vault_exists=orchestration.vault_exists,
                    funding_orchestration=orchestration.to_dict(),
                )
            finally:
                await bridge.close()

        return asyncio.run(_load_and_close())

    def approve(self) -> ApprovalRunSummary:
        if self._config.wallet_mode == WalletMode.MANDATED_VAULT:
            raise mandated_vault_v1_unsupported_error("wallet approve")

        sdk = self._require_sdk()
        results = sdk.set_all_approvals()
        return ApprovalRunSummary(
            standard=results["standard"],
            yield_bearing=results["yieldBearing"],
        )

    def _require_sdk(self) -> WalletSdkProtocol:
        if self._config.auth_signer_address is None:
            raise ConfigError(
                "Wallet actions require signer configuration. Set PREDICT_PRIVATE_KEY or both PREDICT_ACCOUNT_ADDRESS and PREDICT_PRIVY_PRIVATE_KEY."
            )
        return self._sdk_factory(self._config)

    def _get_mandated_status(self) -> MandatedWalletStatusSnapshot:
        bridge = self._bridge_factory(self._config)

        async def _load_and_close() -> MandatedWalletStatusSnapshot:
            await bridge.connect()
            try:
                resolution = await resolve_mandated_vault(
                    self._config,
                    bridge,
                    include_create_prepare=False,
                )
                return MandatedWalletStatusSnapshot(
                    mode=self._config.wallet_mode.value,
                    selected_chain_name=self._chain_name(),
                    selected_chain_id=self._selected_chain_id(),
                    mcp_command=self._config.mandated_mcp_command,
                    mcp_available_tools=sorted(bridge.available_tools),
                    mcp_missing_required_tools=sorted(bridge.missing_required_tools),
                    mcp_runtime_ready=bridge.runtime_ready,
                    vault_address=resolution.vault_address,
                    vault_address_source=resolution.vault_address_source,
                    vault_deployed=resolution.vault_deployed,
                    vault_health=resolution.vault_health,
                    state_changing_flows_enabled=bridge.runtime_ready,
                )
            finally:
                await bridge.close()

        return asyncio.run(_load_and_close())

    def _chain_name(self) -> str:
        return (
            "BNB Mainnet" if self._config.env == RuntimeEnv.MAINNET else "BNB Testnet"
        )

    def _selected_chain_id(self) -> int:
        return self._config.mandated_chain_id or int(self._config.chain_id)
