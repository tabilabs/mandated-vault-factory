from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol

from eth_account import Account
from predict_sdk import OrderBuilder, OrderBuilderOptions
from predict_sdk._internal.contracts import (
    get_conditional_tokens_contract,
    get_exchange_contract,
    get_neg_risk_adapter_contract,
)

from .config import ConfigError, PredictConfig, RuntimeEnv, WalletMode


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

    def to_dict(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "signerAddress": self.signer_address,
            "fundingAddress": self.funding_address,
            "chain": self.chain,
            "bnbBalanceWei": self.bnb_balance_wei,
            "usdtBalanceWei": self.usdt_balance_wei,
            "authReady": self.auth_ready,
            "approvals": self.approvals.to_dict(),
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


class WalletManager:
    def __init__(
        self,
        config: PredictConfig,
        *,
        sdk_factory: Callable[[PredictConfig], WalletSdkProtocol] = make_wallet_sdk,
    ) -> None:
        self._config = config
        self._sdk_factory = sdk_factory

    def get_status(self) -> WalletStatusSnapshot:
        sdk = self._require_sdk()
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

    def approve(self) -> ApprovalRunSummary:
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
