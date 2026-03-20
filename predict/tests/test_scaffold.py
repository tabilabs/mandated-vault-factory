from __future__ import annotations

import tomllib
from pathlib import Path

from conftest import get_predict_root, parse_env_file_keys


REQUIRED_LAYOUT = {
    "pyproject.toml",
    ".gitignore",
    "template.env",
    "template.readonly.env",
    "template.eoa.env",
    "template.predict-account.env",
    "template.mandated-vault.env",
    ".env.example",
    ".env.readonly.example",
    ".env.eoa.example",
    ".env.predict-account.example",
    ".env.mandated-vault.example",
    "README.md",
    "lib/__init__.py",
    "tests/conftest.py",
    "tests/fixtures",
}

REQUIRED_DEPENDENCIES = {
    "predict-sdk>=0.0.15",
    "httpx>=0.28.0",
    "python-dotenv>=1.0.0",
    "pydantic>=2.11.0",
    "pytest>=8.0.0",
    "pytest-asyncio>=0.24.0",
    "respx>=0.22.0",
}

REQUIRED_ENV_KEYS = {
    "PREDICT_STORAGE_DIR",
    "PREDICT_ENV",
    "PREDICT_API_KEY",
    "PREDICT_PRIVATE_KEY",
    "PREDICT_ACCOUNT_ADDRESS",
    "PREDICT_PRIVY_PRIVATE_KEY",
    "OPENROUTER_API_KEY",
    "PREDICT_SMOKE_ENV",
    "PREDICT_SMOKE_PRIVATE_KEY",
    "PREDICT_SMOKE_ACCOUNT_ADDRESS",
    "PREDICT_SMOKE_PRIVY_PRIVATE_KEY",
    "PREDICT_SMOKE_API_KEY",
}


def test_project_metadata_and_layout() -> None:
    predict_root = get_predict_root()
    missing_paths = [
        path for path in REQUIRED_LAYOUT if not (predict_root / path).exists()
    ]
    assert missing_paths == []

    pyproject = tomllib.loads((predict_root / "pyproject.toml").read_text())
    project = pyproject["project"]
    build_system = pyproject["build-system"]
    wheel_target = pyproject["tool"]["hatch"]["build"]["targets"]["wheel"]

    assert project["name"] == "predictclaw"
    assert project["requires-python"] == ">=3.11"
    assert set(project["dependencies"]) >= REQUIRED_DEPENDENCIES
    assert build_system["build-backend"] == "hatchling.build"
    assert build_system["requires"] == ["hatchling"]
    assert "lib" in wheel_target["packages"]


def test_env_example_contains_required_predict_keys() -> None:
    predict_root = get_predict_root()
    env_path = predict_root / "template.env"
    keys = parse_env_file_keys(env_path)

    missing = sorted(REQUIRED_ENV_KEYS - keys)
    assert missing == []


def test_gitignore_excludes_clawhub_incompatible_artifacts() -> None:
    predict_root = get_predict_root()
    gitignore = (predict_root / ".gitignore").read_text()

    assert "artifacts/" in gitignore


def test_default_env_example_is_bootstrap_safe_for_first_install() -> None:
    predict_root = get_predict_root()
    env_text = (predict_root / "template.env").read_text()

    assert "PREDICT_ENV=test-fixture" in env_text
    assert "PREDICT_WALLET_MODE=read-only" in env_text
    assert "template.readonly.env" in env_text
    assert "template.eoa.env" in env_text
    assert "template.predict-account.env" in env_text
    assert "template.mandated-vault.env" in env_text


def test_legacy_dotenv_examples_match_publish_safe_templates() -> None:
    predict_root = get_predict_root()
    template_pairs = {
        ".env.example": "template.env",
        ".env.readonly.example": "template.readonly.env",
        ".env.eoa.example": "template.eoa.env",
        ".env.predict-account.example": "template.predict-account.env",
        ".env.mandated-vault.example": "template.mandated-vault.env",
    }

    for legacy_name, publish_safe_name in template_pairs.items():
        legacy_text = (predict_root / legacy_name).read_text()
        publish_safe_text = (predict_root / publish_safe_name).read_text()
        assert legacy_text == publish_safe_text
