from __future__ import annotations

import pytest
from eth_account import Account
from predict_sdk import ChainId

from lib.config import (
    ConfigError,
    MANDATED_ALLOWED_ADAPTERS_ROOT_DEFAULT,
    PredictConfig,
    WalletMode,
)


EOA_PRIVATE_KEY = "0x59c6995e998f97a5a0044976f4d060f5d89c8b8c7f11b9aa0dbf3f0f7c7c1e01"
PREDICT_ACCOUNT_ADDRESS = "0x1234567890123456789012345678901234567890"
PREDICT_PRIVY_PRIVATE_KEY = (
    "0x8b3a350cf5c34c9194ca0f4e664f9f47d8f8be06d87564ce4b64f59b8d66c1f0"
)
MANDATED_VAULT_ADDRESS = "0xabcdefabcdefabcdefabcdefabcdefabcdefabcd"
MANDATED_AUTHORITY_PRIVATE_KEY = (
    "0x4f3edf983ac636a65a842ce7c78d9aa706d3b113bce036f5f4f6f0e34c0a3f8d"
)
MANDATED_EXECUTOR_PRIVATE_KEY = (
    "0x6c87575d3f0c7c0d9f95f4f61a4b8721e6b7d5f2d75f5ef1a304681140f64f57"
)


def base_env() -> dict[str, str]:
    return {
        "PREDICT_ENV": "testnet",
        "PREDICT_STORAGE_DIR": "/tmp/predict",
    }


def test_mainnet_requires_api_key() -> None:
    with pytest.raises(
        ConfigError, match="PREDICT_API_KEY is required for mainnet"
    ) as error:
        PredictConfig.from_env(
            {
                **base_env(),
                "PREDICT_ENV": "mainnet",
                "PREDICT_PRIVATE_KEY": EOA_PRIVATE_KEY,
            }
        )

    assert "59c6995e" not in str(error.value)
    assert "test-fixture" in str(error.value)
    assert "api-testnet.predict.fun" in str(error.value)


def test_testnet_eoa_configuration_uses_bnb_testnet() -> None:
    config = PredictConfig.from_env(
        {
            **base_env(),
            "PREDICT_PRIVATE_KEY": EOA_PRIVATE_KEY,
        }
    )

    assert config.wallet_mode == WalletMode.EOA
    assert config.chain_id == ChainId.BNB_TESTNET
    assert config.auth_signer_address is not None
    assert config.api_base_url == "https://api-testnet.predict.fun"


def test_mainnet_defaults_to_mainnet_api_base_url() -> None:
    config = PredictConfig.from_env(
        {
            **base_env(),
            "PREDICT_ENV": "mainnet",
            "PREDICT_API_KEY": "test-api-key",
            "PREDICT_PRIVATE_KEY": EOA_PRIVATE_KEY,
        }
    )

    assert config.api_base_url == "https://api.predict.fun"


def test_mandated_transport_defaults_do_not_force_overlay_mode() -> None:
    config = PredictConfig.from_env(
        {
            **base_env(),
            "PREDICT_WALLET_MODE": "read-only",
            "ERC_MANDATED_MCP_COMMAND": "erc-mandated-mcp",
            "ERC_MANDATED_CONTRACT_VERSION": "v0.3.0-agent-contract",
        }
    )

    assert config.wallet_mode == WalletMode.READ_ONLY
    assert config.mandated_mcp_command == "erc-mandated-mcp"
    assert config.mandated_contract_version == "v0.3.0-agent-contract"


def test_predict_account_mode_requires_both_fields() -> None:
    with pytest.raises(ConfigError, match="Predict Account mode requires both"):
        PredictConfig.from_env(
            {
                **base_env(),
                "PREDICT_ACCOUNT_ADDRESS": PREDICT_ACCOUNT_ADDRESS,
            }
        )


@pytest.mark.parametrize(
    ("wallet_mode", "extra_env", "expected_mode"),
    [
        ("read-only", {}, WalletMode.READ_ONLY),
        ("eoa", {"PREDICT_PRIVATE_KEY": EOA_PRIVATE_KEY}, WalletMode.EOA),
        (
            "predict-account",
            {
                "PREDICT_ACCOUNT_ADDRESS": PREDICT_ACCOUNT_ADDRESS,
                "PREDICT_PRIVY_PRIVATE_KEY": PREDICT_PRIVY_PRIVATE_KEY,
            },
            WalletMode.PREDICT_ACCOUNT,
        ),
    ],
)
def test_explicit_wallet_mode_uses_requested_mode(
    wallet_mode: str, extra_env: dict[str, str], expected_mode: WalletMode
) -> None:
    config = PredictConfig.from_env(
        {
            **base_env(),
            "PREDICT_WALLET_MODE": wallet_mode,
            **extra_env,
        }
    )

    assert config.wallet_mode == expected_mode


def test_unset_wallet_mode_preserves_predict_account_inference() -> None:
    config = PredictConfig.from_env(
        {
            **base_env(),
            "PREDICT_ACCOUNT_ADDRESS": PREDICT_ACCOUNT_ADDRESS,
            "PREDICT_PRIVY_PRIVATE_KEY": PREDICT_PRIVY_PRIVATE_KEY,
        }
    )

    assert config.wallet_mode == WalletMode.PREDICT_ACCOUNT
    assert config.auth_signer_address == PREDICT_ACCOUNT_ADDRESS


def test_explicit_predict_account_mode_allows_mandated_vault_overlay() -> None:
    config = PredictConfig.from_env(
        {
            **base_env(),
            "PREDICT_WALLET_MODE": "predict-account",
            "PREDICT_ACCOUNT_ADDRESS": PREDICT_ACCOUNT_ADDRESS,
            "PREDICT_PRIVY_PRIVATE_KEY": PREDICT_PRIVY_PRIVATE_KEY,
            "ERC_MANDATED_VAULT_ADDRESS": MANDATED_VAULT_ADDRESS,
            "ERC_MANDATED_MCP_COMMAND": "overlay-mcp",
            "ERC_MANDATED_CHAIN_ID": "56",
        }
    )

    assert config.wallet_mode == WalletMode.PREDICT_ACCOUNT
    assert config.auth_signer_address == PREDICT_ACCOUNT_ADDRESS
    assert config.mandated_vault_address == MANDATED_VAULT_ADDRESS
    assert config.mandated_mcp_command == "overlay-mcp"
    assert config.mandated_chain_id == 56


def test_predict_account_overlay_reads_optional_funding_policy_limits() -> None:
    config = PredictConfig.from_env(
        {
            **base_env(),
            "PREDICT_WALLET_MODE": "predict-account",
            "PREDICT_ACCOUNT_ADDRESS": PREDICT_ACCOUNT_ADDRESS,
            "PREDICT_PRIVY_PRIVATE_KEY": PREDICT_PRIVY_PRIVATE_KEY,
            "ERC_MANDATED_VAULT_ADDRESS": MANDATED_VAULT_ADDRESS,
            "ERC_MANDATED_FUNDING_MAX_AMOUNT_PER_TX": "5000000000000000000",
            "ERC_MANDATED_FUNDING_MAX_AMOUNT_PER_WINDOW": "10000000000000000000",
            "ERC_MANDATED_FUNDING_WINDOW_SECONDS": "3600",
        }
    )

    assert config.mandated_funding_max_amount_per_tx == "5000000000000000000"
    assert config.mandated_funding_max_amount_per_window == "10000000000000000000"
    assert config.mandated_funding_window_seconds == 3600


def test_predict_account_overlay_defaults_allowed_adapters_root() -> None:
    config = PredictConfig.from_env(
        {
            **base_env(),
            "PREDICT_WALLET_MODE": "predict-account",
            "PREDICT_ACCOUNT_ADDRESS": PREDICT_ACCOUNT_ADDRESS,
            "PREDICT_PRIVY_PRIVATE_KEY": PREDICT_PRIVY_PRIVATE_KEY,
            "ERC_MANDATED_VAULT_ADDRESS": MANDATED_VAULT_ADDRESS,
        }
    )

    assert (
        config.mandated_allowed_adapters_root == MANDATED_ALLOWED_ADAPTERS_ROOT_DEFAULT
    )


def test_predict_account_overlay_accepts_explicit_allowed_adapters_root() -> None:
    root = "0x" + "aa" * 32
    config = PredictConfig.from_env(
        {
            **base_env(),
            "PREDICT_WALLET_MODE": "predict-account",
            "PREDICT_ACCOUNT_ADDRESS": PREDICT_ACCOUNT_ADDRESS,
            "PREDICT_PRIVY_PRIVATE_KEY": PREDICT_PRIVY_PRIVATE_KEY,
            "ERC_MANDATED_VAULT_ADDRESS": MANDATED_VAULT_ADDRESS,
            "ERC_MANDATED_ALLOWED_ADAPTERS_ROOT": root,
        }
    )

    assert config.mandated_allowed_adapters_root == root


def test_predict_account_overlay_rejects_invalid_allowed_adapters_root() -> None:
    with pytest.raises(
        ConfigError,
        match="ERC_MANDATED_ALLOWED_ADAPTERS_ROOT must be a 32-byte hex string",
    ):
        PredictConfig.from_env(
            {
                **base_env(),
                "PREDICT_WALLET_MODE": "predict-account",
                "PREDICT_ACCOUNT_ADDRESS": PREDICT_ACCOUNT_ADDRESS,
                "PREDICT_PRIVY_PRIVATE_KEY": PREDICT_PRIVY_PRIVATE_KEY,
                "ERC_MANDATED_VAULT_ADDRESS": MANDATED_VAULT_ADDRESS,
                "ERC_MANDATED_ALLOWED_ADAPTERS_ROOT": "0x1234",
            }
        )


def test_predict_account_overlay_requires_address_or_full_derivation() -> None:
    with pytest.raises(ConfigError, match="requires ERC_MANDATED_VAULT_ADDRESS"):
        PredictConfig.from_env(
            {
                **base_env(),
                "PREDICT_WALLET_MODE": "predict-account",
                "PREDICT_ACCOUNT_ADDRESS": PREDICT_ACCOUNT_ADDRESS,
                "PREDICT_PRIVY_PRIVATE_KEY": PREDICT_PRIVY_PRIVATE_KEY,
                "ERC_MANDATED_FACTORY_ADDRESS": "0x1111111111111111111111111111111111111111",
            }
        )


def test_predict_account_overlay_defaults_executor_key_to_authority_key() -> None:
    config = PredictConfig.from_env(
        {
            **base_env(),
            "PREDICT_WALLET_MODE": "predict-account",
            "PREDICT_ACCOUNT_ADDRESS": PREDICT_ACCOUNT_ADDRESS,
            "PREDICT_PRIVY_PRIVATE_KEY": PREDICT_PRIVY_PRIVATE_KEY,
            "ERC_MANDATED_VAULT_ADDRESS": MANDATED_VAULT_ADDRESS,
            "ERC_MANDATED_AUTHORITY_PRIVATE_KEY": MANDATED_AUTHORITY_PRIVATE_KEY,
        }
    )

    assert config.wallet_mode == WalletMode.PREDICT_ACCOUNT
    assert config.mandated_authority_private_key_value == MANDATED_AUTHORITY_PRIVATE_KEY
    assert config.mandated_executor_private_key_value == MANDATED_AUTHORITY_PRIVATE_KEY
    assert (
        config.mandated_executor_address
        == Account.from_key(MANDATED_AUTHORITY_PRIVATE_KEY).address
    )


def test_dedicated_mandated_executor_key_overrides_authority_fallback() -> None:
    config = PredictConfig.from_env(
        {
            **base_env(),
            "PREDICT_WALLET_MODE": "mandated-vault",
            "ERC_MANDATED_VAULT_ADDRESS": MANDATED_VAULT_ADDRESS,
            "ERC_MANDATED_AUTHORITY_PRIVATE_KEY": MANDATED_AUTHORITY_PRIVATE_KEY,
            "ERC_MANDATED_EXECUTOR_PRIVATE_KEY": MANDATED_EXECUTOR_PRIVATE_KEY,
        }
    )

    assert config.wallet_mode == WalletMode.MANDATED_VAULT
    assert config.mandated_authority_private_key_value == MANDATED_AUTHORITY_PRIVATE_KEY
    assert config.mandated_executor_private_key_value == MANDATED_EXECUTOR_PRIVATE_KEY
    assert (
        config.mandated_executor_address
        == Account.from_key(MANDATED_EXECUTOR_PRIVATE_KEY).address
    )


def test_explicit_mandated_vault_mode_uses_address_and_defaults() -> None:
    config = PredictConfig.from_env(
        {
            **base_env(),
            "PREDICT_WALLET_MODE": "mandated-vault",
            "ERC_MANDATED_VAULT_ADDRESS": MANDATED_VAULT_ADDRESS,
        }
    )

    assert config.wallet_mode == WalletMode.MANDATED_VAULT
    assert config.auth_signer_address is None
    assert config.mandated_vault_address == MANDATED_VAULT_ADDRESS
    assert config.mandated_mcp_command == "erc-mandated-mcp"
    assert config.mandated_contract_version == "v0.3.0-agent-contract"
    assert config.mandated_chain_id is None


def test_explicit_mandated_vault_mode_accepts_full_derivation_inputs() -> None:
    config = PredictConfig.from_env(
        {
            **base_env(),
            "PREDICT_WALLET_MODE": "mandated-vault",
            "ERC_MANDATED_FACTORY_ADDRESS": "0x1111111111111111111111111111111111111111",
            "ERC_MANDATED_VAULT_ASSET_ADDRESS": "0x2222222222222222222222222222222222222222",
            "ERC_MANDATED_VAULT_NAME": "Mandated USDC Vault",
            "ERC_MANDATED_VAULT_SYMBOL": "mUSDC",
            "ERC_MANDATED_VAULT_AUTHORITY": "0x3333333333333333333333333333333333333333",
            "ERC_MANDATED_VAULT_SALT": "vault-salt",
        }
    )

    assert config.wallet_mode == WalletMode.MANDATED_VAULT
    assert config.mandated_vault_address is None
    assert config.mandated_chain_id is None


def test_explicit_mandated_vault_mode_requires_address_or_full_derivation() -> None:
    with pytest.raises(ConfigError, match="requires ERC_MANDATED_VAULT_ADDRESS"):
        PredictConfig.from_env(
            {
                **base_env(),
                "PREDICT_WALLET_MODE": "mandated-vault",
                "ERC_MANDATED_FACTORY_ADDRESS": "0x1111111111111111111111111111111111111111",
            }
        )


def test_explicit_mandated_vault_mode_rejects_other_wallet_credentials() -> None:
    with pytest.raises(ConfigError, match="does not allow EOA or Predict Account"):
        PredictConfig.from_env(
            {
                **base_env(),
                "PREDICT_WALLET_MODE": "mandated-vault",
                "ERC_MANDATED_VAULT_ADDRESS": MANDATED_VAULT_ADDRESS,
                "PREDICT_PRIVATE_KEY": EOA_PRIVATE_KEY,
            }
        )


def test_mandated_vault_env_without_explicit_mode_fails_closed() -> None:
    with pytest.raises(
        ConfigError,
        match="Mandated vault configuration requires an explicit PREDICT_WALLET_MODE",
    ):
        PredictConfig.from_env(
            {
                **base_env(),
                "ERC_MANDATED_VAULT_ADDRESS": MANDATED_VAULT_ADDRESS,
            }
        )


def test_mandated_signer_env_without_explicit_mode_fails_closed_without_leaking_key() -> (
    None
):
    with pytest.raises(
        ConfigError,
        match="Mandated vault configuration requires an explicit PREDICT_WALLET_MODE",
    ) as error:
        PredictConfig.from_env(
            {
                **base_env(),
                "ERC_MANDATED_AUTHORITY_PRIVATE_KEY": MANDATED_AUTHORITY_PRIVATE_KEY,
            }
        )

    assert MANDATED_AUTHORITY_PRIVATE_KEY not in str(error.value)


def test_mandated_vault_env_does_not_silently_fallback_into_eoa() -> None:
    with pytest.raises(
        ConfigError,
        match="Mandated vault configuration requires an explicit PREDICT_WALLET_MODE",
    ):
        PredictConfig.from_env(
            {
                **base_env(),
                "PREDICT_PRIVATE_KEY": EOA_PRIVATE_KEY,
                "ERC_MANDATED_VAULT_ADDRESS": MANDATED_VAULT_ADDRESS,
            }
        )


def test_predict_account_overlay_without_explicit_mode_fails_closed() -> None:
    with pytest.raises(
        ConfigError,
        match="Mandated vault configuration requires an explicit PREDICT_WALLET_MODE",
    ):
        PredictConfig.from_env(
            {
                **base_env(),
                "PREDICT_ACCOUNT_ADDRESS": PREDICT_ACCOUNT_ADDRESS,
                "PREDICT_PRIVY_PRIVATE_KEY": PREDICT_PRIVY_PRIVATE_KEY,
                "ERC_MANDATED_VAULT_ADDRESS": MANDATED_VAULT_ADDRESS,
            }
        )
