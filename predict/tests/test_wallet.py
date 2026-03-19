from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import pytest

from lib.config import ConfigError, PredictConfig, WalletMode
from lib.wallet_manager import ApprovalSnapshot, WalletManager, WalletSdkProtocol


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
