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
    "PREDICT_API_BASE_URL",
    "PREDICT_API_KEY",
    "PREDICT_PRIVATE_KEY",
    "PREDICT_ACCOUNT_ADDRESS",
    "PREDICT_PRIVY_PRIVATE_KEY",
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
