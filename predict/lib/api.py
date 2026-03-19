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

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        method: str | None = None,
        path: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.method = method
        self.path = path


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
        payload = await self._request_json("GET", f"/v1/markets/{market_id}/orderbook")
        return OrderBookRecord.model_validate(extract_object(payload, "book", "data"))

    async def get_order(self, order_hash: str) -> OrderRecord:
        payload = await self._request_json(
            "GET",
            f"/v1/orders/{order_hash}",
            authenticated=True,
        )
        return _parse_order_record(payload)

    async def get_orders(self) -> list[OrderRecord]:
        payload = await self._request_json("GET", "/v1/orders", authenticated=True)
        return [_normalize_order_record(item) for item in extract_list(payload, "orders", "items")]

    async def create_order(self, order_payload: Mapping[str, Any]) -> OrderRecord:
        payload = await self._request_json(
            "POST",
            "/v1/orders",
            json=_serialize_create_order_payload(order_payload),
            authenticated=True,
        )
        return _parse_order_record(payload)

    async def get_positions(self) -> list[PositionRecord]:
        payload = await self._request_json("GET", "/v1/positions", authenticated=True)
        return [
            _normalize_position_record(item)
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
                    self._format_transport_error(method, path, error),
                    method=method,
                    path=path,
                ) from error

            if response.status_code == 429 or 500 <= response.status_code < 600:
                if attempt < attempts - 1:
                    await self._sleep(
                        self._config.retry_backoff_seconds * (attempt + 1)
                    )
                    continue

            if response.is_error:
                raise PredictApiError(
                    self._format_response_error(method, path, response),
                    status_code=response.status_code,
                    method=method,
                    path=path,
                )

            payload = response.json()
            if isinstance(payload, dict):
                return payload
            return {"data": payload}

        raise PredictApiError(
            f"predict.fun API request exhausted retries: {method} {path}",
            method=method,
            path=path,
        )

    async def _build_headers(self, *, authenticated: bool) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self._config.api_key:
            headers["X-API-Key"] = self._config.api_key.get_secret_value()
        if authenticated:
            if self._jwt_provider is None:
                raise PredictApiError(
                    "Authenticated predict.fun request requires a JWT provider.",
                    method="AUTH",
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


_CREATE_ORDER_META_FIELD_MAP = {
    "pricePerShare": "pricePerShare",
    "price_per_share": "pricePerShare",
    "strategy": "strategy",
    "slippageBps": "slippageBps",
    "slippage_bps": "slippageBps",
    "expirationMinutes": "expirationMinutes",
    "expiration_minutes": "expirationMinutes",
}


def _serialize_create_order_payload(order_payload: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(order_payload)
    if isinstance(payload.get("data"), Mapping):
        return {**payload, "data": _normalize_create_order_data(payload["data"])}
    return {"data": _normalize_create_order_data(payload)}


def _normalize_create_order_data(data: Mapping[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    order_value = data.get("order")

    if isinstance(order_value, Mapping):
        normalized["order"] = _camelize_order_payload(order_value)
    else:
        normalized["order"] = _camelize_order_payload(data)

    for source_key, target_key in _CREATE_ORDER_META_FIELD_MAP.items():
        value = data.get(source_key)
        if value is not None:
            normalized[target_key] = value

    return _drop_none(normalized)


def _camelize_order_payload(order_payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        _camelize_key(key): value
        for key, value in order_payload.items()
        if value is not None and key not in _CREATE_ORDER_META_FIELD_MAP
    }


def _camelize_key(key: str) -> str:
    if "_" not in key:
        return key
    head, *tail = key.split("_")
    return head + "".join(part[:1].upper() + part[1:] for part in tail)


def _drop_none(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            key: _drop_none(item)
            for key, item in value.items()
            if item is not None
        }
    if isinstance(value, list):
        return [_drop_none(item) for item in value if item is not None]
    return value


def _parse_order_record(payload: Mapping[str, Any]) -> OrderRecord:
    return _normalize_order_record(extract_object(dict(payload), "order", "data"))


def _normalize_order_record(payload: Mapping[str, Any]) -> OrderRecord:
    normalized = dict(payload)
    if "hash" not in normalized and isinstance(normalized.get("orderHash"), str):
        normalized["hash"] = normalized["orderHash"]
    if "status" not in normalized and isinstance(normalized.get("orderStatus"), str):
        normalized["status"] = normalized["orderStatus"]
    if "marketId" not in normalized and normalized.get("market_id") is not None:
        normalized["marketId"] = normalized["market_id"]
    return OrderRecord.model_validate(normalized)


def _normalize_position_record(payload: Mapping[str, Any]) -> PositionRecord:
    normalized = dict(payload)
    market = normalized.get("market")
    outcome = normalized.get("outcome")

    if "positionId" not in normalized and isinstance(normalized.get("id"), str):
        normalized["positionId"] = normalized["id"]
    if "marketId" not in normalized and isinstance(market, Mapping):
        normalized["marketId"] = market.get("id")
    if "tokenId" not in normalized and isinstance(outcome, Mapping):
        normalized["tokenId"] = outcome.get("onChainId") or outcome.get("tokenId")
    if "outcomeName" not in normalized and isinstance(outcome, Mapping):
        normalized["outcomeName"] = outcome.get("name")
    if "quantity" not in normalized and normalized.get("amount") is not None:
        normalized["quantity"] = normalized["amount"]
    if "status" not in normalized:
        if isinstance(market, Mapping) and isinstance(market.get("tradingStatus"), str):
            normalized["status"] = market.get("tradingStatus")
        elif isinstance(market, Mapping) and isinstance(market.get("status"), str):
            normalized["status"] = market.get("status")
    return PositionRecord.model_validate(normalized)
