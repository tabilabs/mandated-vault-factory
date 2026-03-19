from __future__ import annotations

import os
import re
from enum import Enum
from pathlib import Path
from typing import Mapping

from eth_account import Account
from pydantic import BaseModel, ConfigDict, SecretStr, ValidationError, model_validator
from predict_sdk import ChainId


class RuntimeEnv(str, Enum):
    MAINNET = "mainnet"
    TESTNET = "testnet"
    TEST_FIXTURE = "test-fixture"


class WalletMode(str, Enum):
    READ_ONLY = "read-only"
    EOA = "eoa"
    PREDICT_ACCOUNT = "predict-account"


class ConfigError(ValueError):
    """Raised when predict runtime configuration is invalid."""


def redact_text(text: str, secrets: list[str | None]) -> str:
    redacted = text
    for secret in secrets:
        if secret:
            redacted = redacted.replace(secret, "<redacted>")
    redacted = re.sub(r"Bearer\s+[A-Za-z0-9._-]+", "Bearer <redacted>", redacted)
    redacted = re.sub(r"0x[a-fA-F0-9]{64}", "0x<redacted>", redacted)
    return redacted


class PredictConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    env: RuntimeEnv = RuntimeEnv.TESTNET
    storage_dir: Path = Path("~/.openclaw/predict").expanduser()
    api_key: SecretStr | None = None
    private_key: SecretStr | None = None
    predict_account_address: str | None = None
    privy_private_key: SecretStr | None = None
    openrouter_api_key: SecretStr | None = None
    model_name: str | None = None
    api_base_url: str = "https://api.predict.fun"
    http_timeout_seconds: float = 15.0
    retry_attempts: int = 3
    retry_backoff_seconds: float = 0.25

    @model_validator(mode="after")
    def validate_runtime_contract(self) -> "PredictConfig":
        if self.env == RuntimeEnv.MAINNET and not self.api_key:
            raise ValueError("PREDICT_API_KEY is required for mainnet.")

        has_eoa = self.private_key is not None
        has_predict_account_address = bool(self.predict_account_address)
        has_privy_key = self.privy_private_key is not None

        if has_predict_account_address != has_privy_key:
            raise ValueError(
                "Predict Account mode requires both PREDICT_ACCOUNT_ADDRESS and PREDICT_PRIVY_PRIVATE_KEY."
            )

        if has_eoa and has_predict_account_address:
            raise ValueError(
                "Use either PREDICT_PRIVATE_KEY for EOA mode or the Predict Account pair, not both."
            )

        return self

    @property
    def wallet_mode(self) -> WalletMode:
        if self.predict_account_address and self.privy_private_key:
            return WalletMode.PREDICT_ACCOUNT
        if self.private_key:
            return WalletMode.EOA
        return WalletMode.READ_ONLY

    @property
    def chain_id(self) -> ChainId:
        if self.env == RuntimeEnv.MAINNET:
            return ChainId.BNB_MAINNET
        return ChainId.BNB_TESTNET

    @property
    def private_key_value(self) -> str | None:
        return self.private_key.get_secret_value() if self.private_key else None

    @property
    def privy_private_key_value(self) -> str | None:
        return (
            self.privy_private_key.get_secret_value()
            if self.privy_private_key
            else None
        )

    @property
    def auth_signer_address(self) -> str | None:
        if self.wallet_mode == WalletMode.PREDICT_ACCOUNT:
            return self.predict_account_address
        if self.wallet_mode == WalletMode.EOA and self.private_key_value:
            return Account.from_key(self.private_key_value).address
        return None

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "PredictConfig":
        source = env or os.environ
        try:
            return cls(
                env=RuntimeEnv(source.get("PREDICT_ENV", RuntimeEnv.TESTNET.value)),
                storage_dir=Path(
                    source.get("PREDICT_STORAGE_DIR", "~/.openclaw/predict")
                ).expanduser(),
                api_key=_secret_or_none(source.get("PREDICT_API_KEY")),
                private_key=_secret_or_none(source.get("PREDICT_PRIVATE_KEY")),
                predict_account_address=_value_or_none(
                    source.get("PREDICT_ACCOUNT_ADDRESS")
                ),
                privy_private_key=_secret_or_none(
                    source.get("PREDICT_PRIVY_PRIVATE_KEY")
                ),
                openrouter_api_key=_secret_or_none(source.get("OPENROUTER_API_KEY")),
                model_name=_value_or_none(source.get("PREDICT_MODEL")),
                api_base_url=source.get(
                    "PREDICT_API_BASE_URL", "https://api.predict.fun"
                ),
            )
        except (ValidationError, ValueError) as error:
            raise ConfigError(
                redact_text(
                    str(error),
                    [
                        source.get("PREDICT_API_KEY"),
                        source.get("PREDICT_PRIVATE_KEY"),
                        source.get("PREDICT_PRIVY_PRIVATE_KEY"),
                        source.get("OPENROUTER_API_KEY"),
                    ],
                )
            ) from error


def _value_or_none(raw: str | None) -> str | None:
    if raw is None:
        return None
    value = raw.strip()
    return value or None


def _secret_or_none(raw: str | None) -> SecretStr | None:
    value = _value_or_none(raw)
    return SecretStr(value) if value else None
