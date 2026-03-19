from __future__ import annotations

import pytest
from predict_sdk import ChainId

from lib.config import ConfigError, PredictConfig, WalletMode


def test_mainnet_requires_api_key() -> None:
    with pytest.raises(
        ConfigError, match="PREDICT_API_KEY is required for mainnet"
    ) as error:
        PredictConfig.from_env(
            {
                "PREDICT_ENV": "mainnet",
                "PREDICT_STORAGE_DIR": "/tmp/predict",
                "PREDICT_PRIVATE_KEY": "0x59c6995e998f97a5a0044976f4d060f5d89c8b8c7f11b9aa0dbf3f0f7c7c1e01",
            }
        )

    assert "59c6995e" not in str(error.value)


def test_testnet_eoa_configuration_uses_bnb_testnet() -> None:
    config = PredictConfig.from_env(
        {
            "PREDICT_ENV": "testnet",
            "PREDICT_STORAGE_DIR": "/tmp/predict",
            "PREDICT_PRIVATE_KEY": "0x59c6995e998f97a5a0044976f4d060f5d89c8b8c7f11b9aa0dbf3f0f7c7c1e01",
        }
    )

    assert config.wallet_mode == WalletMode.EOA
    assert config.chain_id == ChainId.BNB_TESTNET
    assert config.auth_signer_address is not None


def test_predict_account_mode_requires_both_fields() -> None:
    with pytest.raises(ConfigError, match="Predict Account mode requires both"):
        PredictConfig.from_env(
            {
                "PREDICT_ENV": "testnet",
                "PREDICT_STORAGE_DIR": "/tmp/predict",
                "PREDICT_ACCOUNT_ADDRESS": "0x1234567890123456789012345678901234567890",
            }
        )
