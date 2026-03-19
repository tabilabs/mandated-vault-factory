from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

import httpx

from .config import PredictConfig, redact_text
from .models import (
    AuthMessageResponse,
    AuthRequest,
    JwtResponse,
    LastSaleRecord,
    MarketRecord,
    MarketStatsRecord,
    OrderBookRecord,
    OrderRecord,
    PositionRecord,
    extract_list,
    extract_object,
)


class PredictApiError(RuntimeError):
    """Raised when the predict.fun REST API returns an error or cannot be reached."""


class PredictApiClient:
    def __init__(
        self,
        config: PredictConfig,
        *,
        client: httpx.AsyncClient | None = None,
        jwt_provider: Callable[[], Awaitable[str]] | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._config = config
        self._jwt_provider = jwt_provider
        self._sleep = sleep
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=config.api_base_url,
            timeout=config.http_timeout_seconds,
        )

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def get_auth_message(self) -> AuthMessageResponse:
        payload = await self._request_json("GET", "/v1/auth/message")
        return AuthMessageResponse.from_api(payload)

    async def get_jwt(self, auth_request: AuthRequest) -> JwtResponse:
        payload = await self._request_json(
            "POST",
            "/v1/auth",
            json=auth_request.model_dump(),
        )
        return JwtResponse.from_api(payload)

    async def get_markets(self, **params: Any) -> list[MarketRecord]:
        payload = await self._request_json("GET", "/v1/markets", params=params)
        return [
            MarketRecord.model_validate(item)
            for item in extract_list(payload, "markets", "items")
        ]

    async def get_market(self, market_id: str | int) -> MarketRecord:
        payload = await self._request_json("GET", f"/v1/markets/{market_id}")
        return MarketRecord.model_validate(extract_object(payload, "market", "data"))

    async def get_market_stats(self, market_id: str | int) -> MarketStatsRecord:
        payload = await self._request_json("GET", f"/v1/markets/{market_id}/stats")
        return MarketStatsRecord.model_validate(
            extract_object(payload, "stats", "data")
        )

    async def get_market_last_sale(self, market_id: str | int) -> LastSaleRecord:
        payload = await self._request_json("GET", f"/v1/markets/{market_id}/last-sale")
        return LastSaleRecord.model_validate(
            extract_object(payload, "lastSale", "data")
        )

    async def get_orderbook(self, market_id: str | int) -> OrderBookRecord:
        payload = await self._request_json("GET", f"/v1/orderbook/{market_id}")
        return OrderBookRecord.model_validate(extract_object(payload, "book", "data"))

    async def get_order(self, order_hash: str) -> OrderRecord:
        payload = await self._request_json(
            "GET",
            f"/v1/orders/{order_hash}",
            authenticated=True,
        )
        return OrderRecord.model_validate(extract_object(payload, "order", "data"))

    async def get_orders(self) -> list[OrderRecord]:
        payload = await self._request_json("GET", "/v1/orders", authenticated=True)
        return [
            OrderRecord.model_validate(item)
            for item in extract_list(payload, "orders", "items")
        ]

    async def create_order(self, order_payload: Mapping[str, Any]) -> OrderRecord:
        payload = await self._request_json(
            "POST",
            "/v1/orders",
            json=dict(order_payload),
            authenticated=True,
        )
        return OrderRecord.model_validate(extract_object(payload, "order", "data"))

    async def get_positions(self) -> list[PositionRecord]:
        payload = await self._request_json("GET", "/v1/positions", authenticated=True)
        return [
            PositionRecord.model_validate(item)
            for item in extract_list(payload, "positions", "items")
        ]

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        authenticated: bool = False,
        params: Mapping[str, Any] | None = None,
        json: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        headers = await self._build_headers(authenticated=authenticated)
        attempts = self._config.retry_attempts

        for attempt in range(attempts):
            try:
                response = await self._client.request(
                    method,
                    path,
                    headers=headers,
                    params=params,
                    json=json,
                )
            except httpx.HTTPError as error:
                if attempt < attempts - 1:
                    await self._sleep(
                        self._config.retry_backoff_seconds * (attempt + 1)
                    )
                    continue
                raise PredictApiError(
                    self._format_transport_error(method, path, error)
                ) from error

            if response.status_code == 429 or 500 <= response.status_code < 600:
                if attempt < attempts - 1:
                    await self._sleep(
                        self._config.retry_backoff_seconds * (attempt + 1)
                    )
                    continue

            if response.is_error:
                raise PredictApiError(
                    self._format_response_error(method, path, response)
                )

            payload = response.json()
            if isinstance(payload, dict):
                return payload
            return {"data": payload}

        raise PredictApiError(
            f"predict.fun API request exhausted retries: {method} {path}"
        )

    async def _build_headers(self, *, authenticated: bool) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self._config.api_key:
            headers["X-API-Key"] = self._config.api_key.get_secret_value()
        if authenticated:
            if self._jwt_provider is None:
                raise PredictApiError(
                    "Authenticated predict.fun request requires a JWT provider."
                )
            headers["Authorization"] = f"Bearer {await self._jwt_provider()}"
        return headers

    def _format_transport_error(self, method: str, path: str, error: Exception) -> str:
        message = f"predict.fun API transport error during {method} {path}: {error}"
        return redact_text(message, self._secrets())

    def _format_response_error(
        self, method: str, path: str, response: httpx.Response
    ) -> str:
        body = response.text[:240]
        message = f"predict.fun API request failed for {method} {path} with status {response.status_code}: {body}"
        return redact_text(message, self._secrets())

    def _secrets(self) -> list[str | None]:
        return [
            self._config.api_key.get_secret_value() if self._config.api_key else None,
            self._config.private_key_value,
            self._config.privy_private_key_value,
            self._config.openrouter_api_key.get_secret_value()
            if self._config.openrouter_api_key
            else None,
        ]
