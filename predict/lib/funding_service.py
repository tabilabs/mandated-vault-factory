from __future__ import annotations

import asyncio
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Protocol, cast

from predict_sdk._internal.contracts import make_contract
from predict_sdk.abis import KERNEL_ABI
from web3 import Web3

from .config import (
    ConfigError,
    PredictConfig,
    WalletMode,
    mandated_vault_v1_unsupported_error,
)
from .mandated_mcp_bridge import MandatedVaultMcpBridge
from .wallet_manager import (
    FixtureWalletSdk,
    MandatedVaultBridgeProtocol,
    PredictSdkWallet,
    WalletSdkProtocol,
    build_vault_to_predict_account_orchestration,
    load_wallet_bnb_balance_wei,
    load_wallet_usdt_balance_wei,
    make_wallet_sdk,
    resolve_mandated_vault,
)


TOKEN_DECIMALS = {"usdt": 18, "bnb": 18}
MIN_GAS_HEADROOM_WEI = 100_000_000_000_000


@dataclass
class DepositDetails:
    mode: str
    funding_address: str
    signer_address: str
    chain: str
    accepted_assets: list[str]
    bnb_balance_wei: int
    usdt_balance_wei: int
    vault_address_source: str | None = None
    vault_exists: bool | None = None
    create_vault_preparation: dict[str, object] | None = None
    funding_route: str | None = None
    predict_account_address: str | None = None
    trade_signer_address: str | None = None
    vault_address: str | None = None
    funding_orchestration: dict[str, object] | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "mode": self.mode,
            "fundingAddress": self.funding_address,
            "signerAddress": self.signer_address,
            "chain": self.chain,
            "acceptedAssets": self.accepted_assets,
            "bnbBalanceWei": self.bnb_balance_wei,
            "usdtBalanceWei": self.usdt_balance_wei,
        }
        if self.vault_address_source is not None:
            payload["vaultAddressSource"] = self.vault_address_source
        if self.vault_exists is not None:
            payload["vaultExists"] = self.vault_exists
        if self.vault_exists is not None:
            payload["createVaultPreparation"] = self.create_vault_preparation
        elif self.create_vault_preparation is not None:
            payload["createVaultPreparation"] = self.create_vault_preparation
        if self.funding_route is not None:
            payload["fundingRoute"] = self.funding_route
            payload["predictAccountAddress"] = self.predict_account_address
            payload["tradeSignerAddress"] = self.trade_signer_address
            payload["vaultAddress"] = self.vault_address
            payload["fundingOrchestration"] = self.funding_orchestration
        return payload


@dataclass
class WithdrawalResult:
    asset: str
    amount_wei: int
    destination: str
    result: Any

    def to_dict(self) -> dict[str, object]:
        return {
            "asset": self.asset,
            "amountWei": self.amount_wei,
            "destination": self.destination,
            "result": self.result,
        }


class TransferCapableWallet(Protocol):
    @property
    def mode(self) -> object: ...

    @property
    def signer_address(self) -> str: ...

    @property
    def funding_address(self) -> str: ...

    @property
    def chain_name(self) -> str: ...

    def get_bnb_balance_wei(self) -> int: ...

    def get_usdt_balance_wei(self) -> int: ...


class FundingService:
    def __init__(
        self,
        config: PredictConfig,
        *,
        sdk_factory: Callable[[PredictConfig], TransferCapableWallet] = make_wallet_sdk,
        bridge_factory: Callable[
            [PredictConfig], MandatedVaultBridgeProtocol
        ] = MandatedVaultMcpBridge,
    ) -> None:
        self._config = config
        self._sdk_factory = sdk_factory
        self._bridge_factory = bridge_factory

    def get_deposit_details(self) -> DepositDetails:
        if self._config.wallet_mode.value == "mandated-vault":
            return self._get_mandated_deposit_details()

        sdk = self._require_sdk()
        if (
            self._config.wallet_mode == WalletMode.PREDICT_ACCOUNT
            and self._config.has_mandated_config_input
        ):
            return self._get_predict_account_overlay_deposit_details(sdk)

        return DepositDetails(
            mode=str(getattr(sdk.mode, "value", sdk.mode)),
            funding_address=sdk.funding_address,
            signer_address=sdk.signer_address,
            chain=sdk.chain_name,
            accepted_assets=["BNB", "USDT"],
            bnb_balance_wei=sdk.get_bnb_balance_wei(),
            usdt_balance_wei=sdk.get_usdt_balance_wei(),
        )

    def _get_predict_account_overlay_deposit_details(
        self, sdk: TransferCapableWallet
    ) -> DepositDetails:
        bridge = self._bridge_factory(self._config)

        async def _load_and_close() -> DepositDetails:
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
                return DepositDetails(
                    mode=str(getattr(sdk.mode, "value", sdk.mode)),
                    funding_address=sdk.funding_address,
                    signer_address=sdk.signer_address,
                    chain=sdk.chain_name,
                    accepted_assets=["BNB", "USDT"],
                    bnb_balance_wei=bnb_balance,
                    usdt_balance_wei=usdt_balance,
                    vault_address_source=orchestration.vault_address_source,
                    vault_exists=orchestration.vault_exists,
                    funding_route=orchestration.funding_route,
                    predict_account_address=orchestration.predict_account_address,
                    trade_signer_address=orchestration.trade_signer_address,
                    vault_address=orchestration.vault_address,
                    funding_orchestration=orchestration.to_dict(),
                )
            finally:
                await bridge.close()

        return asyncio.run(_load_and_close())

    def _get_mandated_deposit_details(self) -> DepositDetails:
        bridge = self._bridge_factory(self._config)

        async def _load_and_close() -> DepositDetails:
            await bridge.connect()
            try:
                resolution = await resolve_mandated_vault(
                    self._config,
                    bridge,
                    include_create_prepare=True,
                )
                preparation: dict[str, object] | None = None
                if (
                    not resolution.vault_deployed
                    and resolution.create_vault_prepare is not None
                ):
                    tx = resolution.create_vault_prepare.txRequest
                    preparation = {
                        "predictedVault": resolution.create_vault_prepare.predictedVault,
                        "txSummary": {
                            "from": tx.from_address,
                            "to": tx.to,
                            "data": tx.data,
                            "value": tx.value,
                            "gas": tx.gas,
                        },
                        "broadcast": "manual-only",
                    }

                return DepositDetails(
                    mode=self._config.wallet_mode.value,
                    funding_address=resolution.vault_address,
                    signer_address=self._config.mandated_vault_authority
                    or "not-required",
                    chain=(
                        "BNB Mainnet"
                        if self._config.env.value == "mainnet"
                        else "BNB Testnet"
                    ),
                    accepted_assets=["BNB", "USDT"],
                    bnb_balance_wei=0,
                    usdt_balance_wei=0,
                    vault_address_source=resolution.vault_address_source,
                    vault_exists=resolution.vault_deployed,
                    create_vault_preparation=preparation,
                )
            finally:
                await bridge.close()

        return asyncio.run(_load_and_close())

    def withdraw(
        self, asset: str, amount: str, destination: str, *, withdraw_all: bool = False
    ) -> WithdrawalResult:
        if self._config.wallet_mode == WalletMode.MANDATED_VAULT:
            raise mandated_vault_v1_unsupported_error("wallet withdraw")

        sdk = self._require_sdk()
        asset_key = asset.lower()
        if asset_key not in TOKEN_DECIMALS:
            raise ConfigError("Withdraw only supports BNB and USDT.")
        if not Web3.is_checksum_address(destination):
            raise ConfigError("Destination address must be a checksum address.")

        bnb_balance = sdk.get_bnb_balance_wei()
        usdt_balance = sdk.get_usdt_balance_wei()

        if withdraw_all:
            available = (
                usdt_balance
                if asset_key == "usdt"
                else max(bnb_balance - MIN_GAS_HEADROOM_WEI, 0)
            )
            amount_wei = available
        else:
            amount_wei = _parse_amount_to_wei(amount, TOKEN_DECIMALS[asset_key])

        if amount_wei <= 0:
            raise ConfigError("Withdrawal amount must be greater than zero.")
        if bnb_balance <= MIN_GAS_HEADROOM_WEI:
            raise ConfigError("Insufficient BNB gas headroom for withdrawal.")

        if asset_key == "usdt":
            if usdt_balance < amount_wei:
                raise ConfigError("Insufficient USDT balance for withdrawal.")
            result = _transfer_usdt(sdk, destination, amount_wei)
        else:
            if bnb_balance - MIN_GAS_HEADROOM_WEI < amount_wei:
                raise ConfigError(
                    "Insufficient BNB balance after reserving gas headroom."
                )
            result = _transfer_bnb(sdk, destination, amount_wei)

        return WithdrawalResult(
            asset=asset_key,
            amount_wei=amount_wei,
            destination=destination,
            result=result,
        )

    def _require_sdk(self) -> TransferCapableWallet:
        if self._config.auth_signer_address is None:
            raise ConfigError(
                "Wallet actions require signer configuration. Set PREDICT_PRIVATE_KEY or both PREDICT_ACCOUNT_ADDRESS and PREDICT_PRIVY_PRIVATE_KEY."
            )
        return self._sdk_factory(self._config)


def _parse_amount_to_wei(raw_amount: str, decimals: int) -> int:
    try:
        amount = Decimal(raw_amount)
    except InvalidOperation as error:
        raise ConfigError("Withdrawal amount must be numeric.") from error

    if amount <= 0:
        return 0
    scale = Decimal(10) ** decimals
    return int(amount * scale)


def _transfer_usdt(
    sdk: TransferCapableWallet, destination: str, amount_wei: int
) -> Any:
    if hasattr(sdk, "transfer_usdt"):
        return cast(Any, getattr(sdk, "transfer_usdt"))(destination, amount_wei)

    if isinstance(sdk, FixtureWalletSdk):
        return {"success": True, "txHash": "0xfixture-usdt"}

    if not isinstance(sdk, PredictSdkWallet):
        raise ConfigError("Wallet SDK does not support USDT withdrawals.")

    builder = sdk._builder
    contracts = builder.contracts
    if contracts is None:
        raise ConfigError("USDT withdrawal requires initialized predict.fun contracts.")

    checksum_to = Web3.to_checksum_address(destination)
    if sdk.mode.value == "predict-account":
        encoded = contracts.usdt.encode_abi(
            abi_element_identifier="transfer",
            args=[checksum_to, amount_wei],
        )
        calldata = builder._encode_execution_calldata(
            contracts.usdt.address, encoded, value=0
        )
        web3 = getattr(builder, "_web3", None)
        predict_account = getattr(builder, "_predict_account", None)
        execution_mode = getattr(builder, "_execution_mode", None)
        if web3 is None or predict_account is None or execution_mode is None:
            raise ConfigError(
                "Predict Account withdrawal requires initialized Kernel execution state."
            )
        kernel = make_contract(web3, predict_account, KERNEL_ABI)
        return builder._run_async(
            builder._handle_transaction_async(
                kernel, "execute", execution_mode, calldata
            )
        )

    return builder._run_async(
        builder._handle_transaction_async(
            contracts.usdt, "transfer", checksum_to, amount_wei
        )
    )


def _transfer_bnb(sdk: TransferCapableWallet, destination: str, amount_wei: int) -> Any:
    if hasattr(sdk, "transfer_bnb"):
        return cast(Any, getattr(sdk, "transfer_bnb"))(destination, amount_wei)

    if isinstance(sdk, FixtureWalletSdk):
        return {"success": True, "txHash": "0xfixture-bnb"}

    if not isinstance(sdk, PredictSdkWallet):
        raise ConfigError("Wallet SDK does not support BNB withdrawals.")

    builder = sdk._builder
    checksum_to = Web3.to_checksum_address(destination)
    if sdk.mode.value == "predict-account":
        web3 = getattr(builder, "_web3", None)
        predict_account = getattr(builder, "_predict_account", None)
        execution_mode = getattr(builder, "_execution_mode", None)
        if web3 is None or predict_account is None or execution_mode is None:
            raise ConfigError(
                "Predict Account withdrawal requires initialized Kernel execution state."
            )
        calldata = builder._encode_execution_calldata(
            checksum_to, "0x", value=amount_wei
        )
        kernel = make_contract(web3, predict_account, KERNEL_ABI)
        return builder._run_async(
            builder._handle_transaction_async(
                kernel, "execute", execution_mode, calldata
            )
        )

    web3 = getattr(builder, "_web3", None)
    signer = getattr(builder, "_signer", None)
    if web3 is None or signer is None or not sdk._config.private_key_value:
        raise ConfigError("EOA BNB withdrawal requires initialized signer state.")

    tx = {
        "from": signer.address,
        "to": checksum_to,
        "value": amount_wei,
        "nonce": web3.eth.get_transaction_count(signer.address),
        "gasPrice": web3.eth.gas_price,
        "chainId": web3.eth.chain_id,
    }
    estimated_gas = web3.eth.estimate_gas(tx)
    tx["gas"] = (estimated_gas * 125) // 100
    signed = web3.eth.account.sign_transaction(tx, sdk._config.private_key_value)
    tx_hash = web3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = web3.eth.wait_for_transaction_receipt(tx_hash)
    return {"success": True, "txHash": tx_hash.hex(), "receipt": dict(receipt)}
