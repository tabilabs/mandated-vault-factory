from __future__ import annotations

import json

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
async def test_get_jwt_accepts_nested_data_token_response() -> None:
    respx.post("https://api.predict.fun/v1/auth").mock(
        return_value=httpx.Response(200, json={"success": True, "data": {"token": "jwt-123"}})
    )
    client = PredictApiClient(make_config())

    response = await client.get_jwt(
        AuthRequest(signer="0x123", message="msg", signature="0xsig")
    )

    assert response.token == "jwt-123"
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


@pytest.mark.asyncio
@respx.mock
async def test_predict_api_error_exposes_status_code_for_http_failures() -> None:
    respx.get("https://api.predict.fun/v1/markets/404/orderbook").mock(
        return_value=httpx.Response(404, json={"error": "not_found"})
    )
    client = PredictApiClient(make_config())

    with pytest.raises(PredictApiError) as error:
        await client.get_orderbook("404")

    assert error.value.status_code == 404
    assert error.value.method == "GET"
    assert error.value.path == "/v1/markets/404/orderbook"
    await client.close()


@pytest.mark.asyncio
@respx.mock
async def test_create_order_wraps_payload_under_data_and_camelizes_order_fields() -> None:
    route = respx.post("https://api.predict.fun/v1/orders").mock(
        return_value=httpx.Response(
            200, json={"order": {"hash": "0xabc", "status": "OPEN"}}
        )
    )
    client = PredictApiClient(
        make_config(), jwt_provider=lambda: _return_token("jwt-123")
    )

    await client.create_order(
        {
            "order": {
                "token_id": "1001",
                "maker_amount": "25",
                "taker_amount": "40",
                "fee_rate_bps": "100",
                "signature_type": 0,
                "signature": "0xsig",
                "hash": "0xhash",
            },
            "pricePerShare": "625000000000000000",
            "strategy": "MARKET",
            "slippageBps": 50,
        }
    )

    assert route.called
    request = route.calls.last.request
    assert request.headers["Authorization"] == "Bearer jwt-123"
    assert json.loads(request.content) == {
        "data": {
            "order": {
                "tokenId": "1001",
                "makerAmount": "25",
                "takerAmount": "40",
                "feeRateBps": "100",
                "signatureType": 0,
                "signature": "0xsig",
                "hash": "0xhash",
            },
            "pricePerShare": "625000000000000000",
            "strategy": "MARKET",
            "slippageBps": 50,
        }
    }
    await client.close()


@pytest.mark.asyncio
@respx.mock
async def test_create_order_normalizes_wrapped_data_payload() -> None:
    route = respx.post("https://api.predict.fun/v1/orders").mock(
        return_value=httpx.Response(
            200, json={"order": {"hash": "0xabc", "status": "OPEN"}}
        )
    )
    client = PredictApiClient(
        make_config(), jwt_provider=lambda: _return_token("jwt-123")
    )

    await client.create_order(
        {
            "data": {
                "order": {
                    "token_id": "1001",
                    "maker_amount": "25",
                    "hash": "0xhash",
                },
                "price_per_share": "500000000000000000",
                "strategy": "LIMIT",
                "expiration_minutes": 60,
            }
        }
    )

    assert json.loads(route.calls.last.request.content) == {
        "data": {
            "order": {
                "tokenId": "1001",
                "makerAmount": "25",
                "hash": "0xhash",
            },
            "pricePerShare": "500000000000000000",
            "strategy": "LIMIT",
            "expirationMinutes": 60,
        }
    }
    await client.close()


@pytest.mark.asyncio
@respx.mock
async def test_create_order_accepts_modern_order_hash_response_shape() -> None:
    respx.post("https://api.predict.fun/v1/orders").mock(
        return_value=httpx.Response(
            200,
            json={"data": {"code": "SUCCESS", "orderId": "ord_123", "orderHash": "0xabc"}},
        )
    )
    client = PredictApiClient(
        make_config(), jwt_provider=lambda: _return_token("jwt-123")
    )

    response = await client.create_order(
        {
            "order": {
                "token_id": "1001",
                "maker_amount": "25",
                "taker_amount": "40",
                "fee_rate_bps": "100",
                "signature": "0xsig",
            },
            "pricePerShare": "625000000000000000",
            "strategy": "MARKET",
        }
    )

    assert response.hash == "0xabc"
    await client.close()


@pytest.mark.asyncio
@respx.mock
async def test_get_positions_accepts_modern_nested_response_shape() -> None:
    respx.get("https://api.predict.fun/v1/positions").mock(
        return_value=httpx.Response(
            200,
            json={
                "success": True,
                "cursor": None,
                "data": [
                    {
                        "id": "pos_123",
                        "amount": "69999440000000000000",
                        "averageBuyPriceUsd": "0.014",
                        "market": {
                            "id": 1489,
                            "question": "Will the Los Angeles Clippers win the 2026 NBA Finals?",
                            "tradingStatus": "OPEN",
                        },
                        "outcome": {
                            "name": "Yes",
                            "onChainId": "42983634955227024919103064840361627082824364074391962525086869643328802555347",
                        },
                        "pnlUsd": "-0.07",
                        "valueUsd": "0.91",
                    }
                ],
            },
        )
    )
    client = PredictApiClient(
        make_config(), jwt_provider=lambda: _return_token("jwt-123")
    )

    positions = await client.get_positions()

    assert positions[0].positionId == "pos_123"
    assert positions[0].marketId == 1489
    assert positions[0].tokenId == "42983634955227024919103064840361627082824364074391962525086869643328802555347"
    assert positions[0].outcomeName == "Yes"
    assert positions[0].quantity == "69999440000000000000"
    assert positions[0].status == "OPEN"
    await client.close()


async def _return_token(token: str) -> str:
    return token


async def _no_sleep(_seconds: float) -> None:
    return None
