from __future__ import annotations

import httpx
import pytest
import respx

from lib.api import PredictApiClient, PredictApiError
from lib.config import PredictConfig
from lib.models import AuthRequest


def make_config(**overrides: str) -> PredictConfig:
    env = {
        "PREDICT_ENV": "testnet",
        "PREDICT_STORAGE_DIR": "/tmp/predict",
        "PREDICT_PRIVATE_KEY": "0x59c6995e998f97a5a0044976f4d060f5d89c8b8c7f11b9aa0dbf3f0f7c7c1e01",
    }
    env.update(overrides)
    return PredictConfig.from_env(env)


@pytest.mark.asyncio
@respx.mock
async def test_get_markets_uses_query_params_and_normalizes_response() -> None:
    route = respx.get("https://api.predict.fun/v1/markets").mock(
        return_value=httpx.Response(
            200,
            json={
                "markets": [{"id": "123", "title": "Election market", "status": "OPEN"}]
            },
        )
    )
    client = PredictApiClient(make_config())

    markets = await client.get_markets(status="OPEN", sort="VOLUME_24H_DESC", first=5)

    assert route.called
    request = route.calls.last.request
    assert request.url.params["status"] == "OPEN"
    assert request.url.params["sort"] == "VOLUME_24H_DESC"
    assert request.url.params["first"] == "5"
    assert markets[0].id == "123"
    await client.close()


@pytest.mark.asyncio
@respx.mock
async def test_authenticated_requests_attach_bearer_token() -> None:
    route = respx.get("https://api.predict.fun/v1/orders").mock(
        return_value=httpx.Response(
            200, json={"orders": [{"hash": "0xabc", "status": "OPEN"}]}
        )
    )
    client = PredictApiClient(
        make_config(), jwt_provider=lambda: _return_token("jwt-123")
    )

    orders = await client.get_orders()

    assert route.called
    request = route.calls.last.request
    assert request.headers["Authorization"] == "Bearer jwt-123"
    assert orders[0].hash == "0xabc"
    await client.close()


@pytest.mark.asyncio
@respx.mock
async def test_transient_429_is_retried_before_success() -> None:
    route = respx.get("https://api.predict.fun/v1/markets").mock(
        side_effect=[
            httpx.Response(429, json={"error": "slow down"}),
            httpx.Response(200, json={"markets": [{"id": "retry-market"}]}),
        ]
    )
    client = PredictApiClient(make_config(), sleep=_no_sleep)

    markets = await client.get_markets(status="OPEN")

    assert len(route.calls) == 2
    assert markets[0].id == "retry-market"
    await client.close()


@pytest.mark.asyncio
@respx.mock
async def test_error_messages_redact_secrets() -> None:
    secret_key = "super-secret-api-key"
    respx.post("https://api.predict.fun/v1/auth").mock(
        return_value=httpx.Response(500, text=f"boom {secret_key} Bearer jwt-abc123")
    )
    client = PredictApiClient(make_config(PREDICT_API_KEY=secret_key))

    with pytest.raises(PredictApiError) as error:
        await client.get_jwt(
            AuthRequest(signer="0x123", message="msg", signature="0xsig"),
        )

    message = str(error.value)
    assert secret_key not in message
    assert "jwt-abc123" not in message
    assert "<redacted>" in message
    await client.close()


async def _return_token(token: str) -> str:
    return token


async def _no_sleep(_seconds: float) -> None:
    return None
