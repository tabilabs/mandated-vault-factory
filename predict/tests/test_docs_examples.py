from __future__ import annotations

from conftest import get_predict_root, parse_env_file_keys


DOC_COMMANDS = [
    "markets trending",
    "markets search",
    "market 123",
    "wallet status",
    "wallet approve",
    "wallet deposit",
    "wallet withdraw usdt",
    "wallet withdraw bnb",
    "buy 123 YES 25",
    "positions",
    "position pos-123-yes",
    "hedge scan",
    "hedge analyze 101 202",
]

DOC_ENV_VARS = {
    "PREDICT_STORAGE_DIR",
    "PREDICT_ENV",
    "PREDICT_WALLET_MODE",
    "PREDICT_API_BASE_URL",
    "PREDICT_API_KEY",
    "PREDICT_PRIVATE_KEY",
    "PREDICT_ACCOUNT_ADDRESS",
    "PREDICT_PRIVY_PRIVATE_KEY",
    "ERC_MANDATED_VAULT_ADDRESS",
    "ERC_MANDATED_FACTORY_ADDRESS",
    "ERC_MANDATED_VAULT_ASSET_ADDRESS",
    "ERC_MANDATED_VAULT_NAME",
    "ERC_MANDATED_VAULT_SYMBOL",
    "ERC_MANDATED_VAULT_AUTHORITY",
    "ERC_MANDATED_VAULT_SALT",
    "ERC_MANDATED_AUTHORITY_PRIVATE_KEY",
    "ERC_MANDATED_EXECUTOR_PRIVATE_KEY",
    "ERC_MANDATED_MCP_COMMAND",
    "ERC_MANDATED_CONTRACT_VERSION",
    "ERC_MANDATED_CHAIN_ID",
    "ERC_MANDATED_ALLOWED_ADAPTERS_ROOT",
    "ERC_MANDATED_FUNDING_MAX_AMOUNT_PER_TX",
    "ERC_MANDATED_FUNDING_MAX_AMOUNT_PER_WINDOW",
    "ERC_MANDATED_FUNDING_WINDOW_SECONDS",
    "OPENROUTER_API_KEY",
    "PREDICT_MODEL",
    "PREDICT_SMOKE_ENV",
    "PREDICT_SMOKE_API_BASE_URL",
    "PREDICT_SMOKE_PRIVATE_KEY",
    "PREDICT_SMOKE_ACCOUNT_ADDRESS",
    "PREDICT_SMOKE_PRIVY_PRIVATE_KEY",
    "PREDICT_SMOKE_API_KEY",
}


def test_documented_commands_exist_in_cli_help() -> None:
    predict_root = get_predict_root()
    readme = (predict_root / "README.md").read_text()
    skill = (predict_root / "SKILL.md").read_text()

    for command in DOC_COMMANDS:
        assert command in readme
        assert command in skill


def test_documented_env_vars_match_env_example() -> None:
    predict_root = get_predict_root()
    env_keys = parse_env_file_keys(predict_root / ".env.example")
    readme = (predict_root / "README.md").read_text()
    skill = (predict_root / "SKILL.md").read_text()

    assert env_keys == DOC_ENV_VARS
    for key in DOC_ENV_VARS:
        assert key in readme
        assert key in skill


def test_packaged_install_docs_inline_env_setup() -> None:
    predict_root = get_predict_root()
    readme = (predict_root / "README.md").read_text()
    skill = (predict_root / "SKILL.md").read_text()
    chinese = (predict_root / "README.zh-CN.md").read_text()
    root_readme = (predict_root.parent / "README.md").read_text()
    onboarding = (predict_root.parent / "docs" / "onboarding.md").read_text()

    for text in [readme, skill, chinese, root_readme, onboarding]:
        assert ".env.example" in text


def test_docs_cover_wallet_modes_and_mandated_vault_boundaries() -> None:
    predict_root = get_predict_root()
    readme = (predict_root / "README.md").read_text()
    skill = (predict_root / "SKILL.md").read_text()
    root_readme = (predict_root.parent / "README.md").read_text()
    onboarding = (predict_root.parent / "docs" / "onboarding.md").read_text()

    for text in [readme, skill, root_readme, onboarding]:
        assert "mandated-vault" in text
        assert "vault-to-predict-account" in text

    for text in [readme, skill]:
        for mode in ["read-only", "eoa", "predict-account", "mandated-vault"]:
            assert mode in text
        assert "PREDICT_WALLET_MODE" in text
        assert "ERC_MANDATED_VAULT_ADDRESS" in text
        assert "ERC_MANDATED_FACTORY_ADDRESS" in text
        assert "ERC_MANDATED_VAULT_ASSET_ADDRESS" in text
        assert "ERC_MANDATED_VAULT_NAME" in text
        assert "ERC_MANDATED_VAULT_SYMBOL" in text
        assert "ERC_MANDATED_VAULT_AUTHORITY" in text
        assert "ERC_MANDATED_VAULT_SALT" in text
        assert "ERC_MANDATED_MCP_COMMAND" in text
        assert "ERC_MANDATED_CONTRACT_VERSION" in text
        assert "ERC_MANDATED_CHAIN_ID" in text
        assert "manual-only" in text
        assert "unsupported-in-mandated-vault-v1" in text
        assert "vault contract policy authorizes" in text.lower()
        assert "funding-required" in text
        assert "Predict Account remains" in text

    for text in [root_readme, onboarding]:
        assert "PREDICT_WALLET_MODE=mandated-vault" in text
        assert "PREDICT_WALLET_MODE=predict-account" in text
        assert "unsupported-in-mandated-vault-v1" in text


def test_docs_explain_flat_metadata_vs_mode_specific_runtime_requirements() -> None:
    predict_root = get_predict_root()
    readme = (predict_root / "README.md").read_text()
    skill = (predict_root / "SKILL.md").read_text()
    readme_zh = (predict_root / "README.zh-CN.md").read_text()

    for text in [readme, skill]:
        assert "metadata intentionally lists only the universal entry variables" in text
        assert "OpenClaw's runtime metadata is flat rather than mode-aware" in text
        assert (
            "mode-specific requirements are documented below and enforced by the runtime config validator"
            in text
        )

    assert "metadata 里故意只声明通用入口变量" in readme_zh
    assert "OpenClaw 当前的 runtime metadata 是扁平的，不是按 mode 感知的" in readme_zh
    assert "各模式自己的必填项以下面的示例和运行时配置校验为准" in readme_zh


def test_docs_explain_first_install_bootstrap_layers() -> None:
    predict_root = get_predict_root()
    readme = (predict_root / "README.md").read_text()
    skill = (predict_root / "SKILL.md").read_text()
    readme_zh = (predict_root / "README.zh-CN.md").read_text()

    for text in [readme, skill]:
        assert ".env.readonly.example" in text
        assert ".env.eoa.example" in text
        assert ".env.predict-account.example" in text
        assert ".env.mandated-vault.example" in text
        assert "api-testnet.predict.fun" in text
        assert "wallet status requires signer configuration" in text
        assert "mainnet market reads require PREDICT_API_KEY" in text
        assert "test-fixture" in text

    assert ".env.readonly.example" in readme_zh
    assert ".env.eoa.example" in readme_zh
    assert ".env.predict-account.example" in readme_zh
    assert ".env.mandated-vault.example" in readme_zh
    assert "api-testnet.predict.fun" in readme_zh
    assert "wallet status 需要 signer 配置" in readme_zh
    assert "mainnet 的市场读取需要 PREDICT_API_KEY" in readme_zh
