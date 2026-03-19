from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class PredictModel(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)


class AuthRequest(PredictModel):
    signer: str
    message: str
    signature: str


class AuthMessageResponse(PredictModel):
    message: str

    @classmethod
    def from_api(cls, payload: dict[str, Any]) -> "AuthMessageResponse":
        message = payload.get("message") or payload.get("data", {}).get("message")
        if not isinstance(message, str) or not message.strip():
            raise ValueError(
                "predict.fun auth message response did not include a message string"
            )
        return cls(message=message)


class JwtResponse(PredictModel):
    token: str

    @classmethod
    def from_api(cls, payload: dict[str, Any]) -> "JwtResponse":
        data = payload.get("data", {})
        if not isinstance(data, dict):
            data = {}
        token = (
            payload.get("token")
            or payload.get("jwt")
            or payload.get("accessToken")
            or data.get("token")
            or data.get("jwt")
            or data.get("accessToken")
        )
        if not isinstance(token, str) or not token.strip():
            raise ValueError("predict.fun auth response did not include a JWT token")
        return cls(token=token)


class OutcomeRecord(PredictModel):
    id: str | int | None = None
    name: str | None = None
    tokenId: str | None = None
    onChainId: str | None = None


class MarketRecord(PredictModel):
    id: str | int
    title: str | None = None
    question: str | None = None
    status: str | None = None
    categorySlug: str | None = None
    decimalPrecision: int | None = None
    feeRateBps: int | None = None
    volume24hUsd: float | None = None
    isNegRisk: bool | None = None
    isYieldBearing: bool | None = None
    outcomes: list[OutcomeRecord] | None = None


class MarketStatsRecord(PredictModel):
    marketId: str | int | None = None
    volume24hUsd: float | None = None
    liquidityUsd: float | None = None


class LastSaleRecord(PredictModel):
    marketId: str | int | None = None
    price: float | None = None
    side: str | None = None


class OrderBookRecord(PredictModel):
    marketId: str | int | None = None
    asks: list[list[float]] | list[tuple[float, float]] | None = None
    bids: list[list[float]] | list[tuple[float, float]] | None = None
    updateTimestampMs: int | None = None


class OrderRecord(PredictModel):
    hash: str | None = None
    status: str | None = None
    marketId: str | int | None = None


class PositionRecord(PredictModel):
    positionId: str | None = None
    marketId: str | int | None = None
    tokenId: str | None = None
    outcomeName: str | None = None
    quantity: str | float | None = None
    status: str | None = None


def extract_object(payload: dict[str, Any], *candidate_keys: str) -> dict[str, Any]:
    for key in candidate_keys:
        candidate = payload.get(key)
        if isinstance(candidate, dict):
            return candidate
    return payload


def extract_list(
    payload: dict[str, Any] | list[dict[str, Any]], *candidate_keys: str
) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return payload

    for key in candidate_keys:
        candidate = payload.get(key)
        if isinstance(candidate, list):
            return [item for item in candidate if isinstance(item, dict)]

    data = payload.get("data")
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]

    return []
