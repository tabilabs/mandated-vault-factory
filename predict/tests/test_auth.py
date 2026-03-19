from __future__ import annotations

from dataclasses import dataclass

import pytest
from eth_account import Account
from eth_account.messages import encode_defunct

from lib.auth import PredictAuthenticator
from lib.config import PredictConfig
from lib.models import AuthMessageResponse, AuthRequest, JwtResponse


class StubAuthApiClient:
    def __init__(self) -> None:
        self.requests: list[AuthRequest] = []

    async def get_auth_message(self) -> AuthMessageResponse:
        return AuthMessageResponse(message="Sign into predict.fun")

    async def get_jwt(self, auth_request: AuthRequest) -> JwtResponse:
        self.requests.append(auth_request)
        return JwtResponse(token="jwt-token")


@dataclass
class FakePredictAccountBuilder:
    signature: str

    def sign_predict_account_message(self, message: str) -> str:
        assert message == "Sign into predict.fun"
        return self.signature


@pytest.mark.asyncio
async def test_get_jwt_for_eoa_and_predict_account(tmp_path) -> None:
    api_client = StubAuthApiClient()
    private_key = "0x59c6995e998f97a5a0044976f4d060f5d89c8b8c7f11b9aa0dbf3f0f7c7c1e01"
    expected_address = Account.from_key(private_key).address

    eoa_config = PredictConfig.from_env(
        {
            "PREDICT_ENV": "testnet",
            "PREDICT_STORAGE_DIR": str(tmp_path),
            "PREDICT_PRIVATE_KEY": private_key,
        }
    )
    authenticator = PredictAuthenticator(eoa_config, api_client)

    first_token = await authenticator.get_jwt()
    second_token = await authenticator.get_jwt()
    request = api_client.requests[0]

    assert first_token == "jwt-token"
    assert second_token == "jwt-token"
    assert len(api_client.requests) == 1
    assert request.signer == expected_address
    assert request.message == "Sign into predict.fun"

    signed = Account.from_key(private_key).sign_message(
        encode_defunct(text="Sign into predict.fun")
    )
    assert request.signature == signed.signature.hex()
    assert list(tmp_path.iterdir()) == []

    predict_account_calls: list[PredictConfig] = []

    def builder_factory(config: PredictConfig) -> FakePredictAccountBuilder:
        predict_account_calls.append(config)
        return FakePredictAccountBuilder(signature="0xpredictsig")

    predict_account_config = PredictConfig.from_env(
        {
            "PREDICT_ENV": "testnet",
            "PREDICT_STORAGE_DIR": str(tmp_path),
            "PREDICT_ACCOUNT_ADDRESS": "0x1234567890123456789012345678901234567890",
            "PREDICT_PRIVY_PRIVATE_KEY": private_key,
        }
    )
    predict_account_api_client = StubAuthApiClient()
    predict_account_auth = PredictAuthenticator(
        predict_account_config,
        predict_account_api_client,
        builder_factory=builder_factory,
    )

    predict_token = await predict_account_auth.get_jwt()
    predict_request = predict_account_api_client.requests[0]

    assert predict_token == "jwt-token"
    assert len(predict_account_calls) == 1
    assert predict_account_calls[0].wallet_mode.value == "predict-account"
    assert predict_request.signer == "0x1234567890123456789012345678901234567890"
    assert predict_request.signature == "0xpredictsig"
