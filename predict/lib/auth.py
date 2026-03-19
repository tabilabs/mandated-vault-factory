from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from eth_account import Account
from eth_account.messages import encode_defunct
from predict_sdk import OrderBuilder, OrderBuilderOptions

from .config import ConfigError, PredictConfig, WalletMode
from .models import AuthMessageResponse, AuthRequest, JwtResponse


class AuthApiClientProtocol(Protocol):
    async def get_auth_message(self) -> AuthMessageResponse: ...
    async def get_jwt(self, auth_request: AuthRequest) -> JwtResponse: ...


class PredictAccountBuilderProtocol(Protocol):
    def sign_predict_account_message(self, message: str) -> str: ...


class PredictAuthenticator:
    def __init__(
        self,
        config: PredictConfig,
        api_client: AuthApiClientProtocol,
        *,
        account_from_key: Callable[[str], Any] = Account.from_key,
        builder_factory: Callable[[PredictConfig], PredictAccountBuilderProtocol]
        | None = None,
    ) -> None:
        self._config = config
        self._api_client = api_client
        self._account_from_key = account_from_key
        self._builder_factory = builder_factory or _make_predict_account_builder
        self._jwt_cache: dict[str, str] = {}

    async def get_jwt(self, *, force_refresh: bool = False) -> str:
        signer = self._config.auth_signer_address
        if signer is None:
            raise ConfigError(
                "Authenticated predict.fun actions require PREDICT_PRIVATE_KEY or the Predict Account credential pair."
            )

        cache_key = f"{self._config.env.value}:{signer}"
        if not force_refresh and cache_key in self._jwt_cache:
            return self._jwt_cache[cache_key]

        auth_message = await self._api_client.get_auth_message()
        auth_request = self.build_auth_request(auth_message.message)
        jwt_response = await self._api_client.get_jwt(auth_request)
        self._jwt_cache[cache_key] = jwt_response.token
        return jwt_response.token

    def build_auth_request(self, message: str) -> AuthRequest:
        if self._config.wallet_mode == WalletMode.EOA:
            if not self._config.private_key_value:
                raise ConfigError("EOA mode requires PREDICT_PRIVATE_KEY.")
            signer = self._account_from_key(self._config.private_key_value)
            signed = signer.sign_message(encode_defunct(text=message))
            return AuthRequest(
                signer=signer.address,
                message=message,
                signature=signed.signature.hex(),
            )

        if self._config.wallet_mode == WalletMode.PREDICT_ACCOUNT:
            builder = self._builder_factory(self._config)
            signature = builder.sign_predict_account_message(message)
            return AuthRequest(
                signer=self._config.predict_account_address or "",
                message=message,
                signature=signature,
            )

        raise ConfigError(
            "Authenticated predict.fun actions require PREDICT_PRIVATE_KEY or the Predict Account credential pair."
        )


def _make_predict_account_builder(
    config: PredictConfig,
) -> PredictAccountBuilderProtocol:
    if not config.privy_private_key_value or not config.predict_account_address:
        raise ConfigError(
            "Predict Account mode requires both PREDICT_ACCOUNT_ADDRESS and PREDICT_PRIVY_PRIVATE_KEY."
        )

    return OrderBuilder.make(
        config.chain_id,
        config.privy_private_key_value,
        OrderBuilderOptions(predict_account=config.predict_account_address),
    )
