from __future__ import annotations

from dataclasses import dataclass

import lib
import pytest

from lib.config import ConfigError, PredictConfig, WalletMode

FundingService = getattr(lib, "FundingService")


@dataclass
class FakeFundingSdk:
    mode: WalletMode = WalletMode.EOA
    signer_address: str = "0xb30741673D351135Cf96564dfD15f8e135f9C310"
    funding_address: str = "0xb30741673D351135Cf96564dfD15f8e135f9C310"
    chain_name: str = "BNB Testnet"
    bnb_balance_wei: int = 2_000_000_000_000_000_000
    usdt_balance_wei: int = 25_000_000_000_000_000_000
    transfer_calls: list[tuple[str, str, int]] | None = None

    def get_bnb_balance_wei(self) -> int:
        return self.bnb_balance_wei

    def get_usdt_balance_wei(self) -> int:
        return self.usdt_balance_wei

    def transfer_usdt(self, destination: str, amount_wei: int) -> dict[str, object]:
        if self.transfer_calls is not None:
            self.transfer_calls.append(("usdt", destination, amount_wei))
        return {"success": True, "txHash": "0xusdt"}

    def transfer_bnb(self, destination: str, amount_wei: int) -> dict[str, object]:
        if self.transfer_calls is not None:
            self.transfer_calls.append(("bnb", destination, amount_wei))
        return {"success": True, "txHash": "0xbnb"}


def test_wallet_deposit_reports_eoa_vs_predict_account_address() -> None:
    eoa_config = PredictConfig.from_env(
        {
            "PREDICT_ENV": "testnet",
            "PREDICT_STORAGE_DIR": "/tmp/predict",
            "PREDICT_PRIVATE_KEY": "0x59c6995e998f97a5a0044976f4d060f5d89c8b8c7f11b9aa0dbf3f0f7c7c1e01",
        }
    )
    eoa_service = FundingService(
        eoa_config, sdk_factory=lambda _config: FakeFundingSdk()
    )
    eoa_details = eoa_service.get_deposit_details().to_dict()

    predict_account_config = PredictConfig.from_env(
        {
            "PREDICT_ENV": "testnet",
            "PREDICT_STORAGE_DIR": "/tmp/predict",
            "PREDICT_ACCOUNT_ADDRESS": "0x1234567890123456789012345678901234567890",
            "PREDICT_PRIVY_PRIVATE_KEY": "0x59c6995e998f97a5a0044976f4d060f5d89c8b8c7f11b9aa0dbf3f0f7c7c1e01",
        }
    )
    predict_account_service = FundingService(
        predict_account_config,
        sdk_factory=lambda _config: FakeFundingSdk(
            mode=WalletMode.PREDICT_ACCOUNT,
            funding_address="0x1234567890123456789012345678901234567890",
        ),
    )
    predict_account_details = predict_account_service.get_deposit_details().to_dict()

    assert eoa_details["mode"] == "eoa"
    assert eoa_details["fundingAddress"] == eoa_details["signerAddress"]
    assert predict_account_details["mode"] == "predict-account"
    assert (
        predict_account_details["fundingAddress"]
        == "0x1234567890123456789012345678901234567890"
    )
    assert predict_account_details["chain"] == "BNB Testnet"
    assert predict_account_details["acceptedAssets"] == ["BNB", "USDT"]


def test_withdraw_rejects_invalid_destination_or_insufficient_balance() -> None:
    config = PredictConfig.from_env(
        {
            "PREDICT_ENV": "testnet",
            "PREDICT_STORAGE_DIR": "/tmp/predict",
            "PREDICT_PRIVATE_KEY": "0x59c6995e998f97a5a0044976f4d060f5d89c8b8c7f11b9aa0dbf3f0f7c7c1e01",
        }
    )
    calls: list[tuple[str, str, int]] = []
    service = FundingService(
        config,
        sdk_factory=lambda _config: FakeFundingSdk(transfer_calls=calls),
    )

    with pytest.raises(ConfigError, match="checksum address"):
        service.withdraw("usdt", "1", "0xnot-checksummed")

    with pytest.raises(ConfigError, match="greater than zero"):
        service.withdraw("usdt", "0", "0xb30741673D351135Cf96564dfD15f8e135f9C310")

    with pytest.raises(ConfigError, match="Insufficient USDT balance"):
        service.withdraw("usdt", "1000", "0xb30741673D351135Cf96564dfD15f8e135f9C310")

    gas_starved_service = FundingService(
        config,
        sdk_factory=lambda _config: FakeFundingSdk(
            bnb_balance_wei=50_000_000_000_000,
            transfer_calls=calls,
        ),
    )
    with pytest.raises(ConfigError, match="gas headroom"):
        gas_starved_service.withdraw(
            "bnb", "0.1", "0xb30741673D351135Cf96564dfD15f8e135f9C310"
        )

    assert calls == []
