from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Awaitable, Callable, Protocol, cast

from predict_sdk import BuildOrderInput, LimitHelperInput, MarketHelperValueInput, Side

from .api import PredictApiClient
from .auth import PredictAuthenticator
from .config import ConfigError, PredictConfig, RuntimeEnv
from .fixture_api import FixturePredictApiClient
from .orderbook import orderbook_record_to_sdk_book, resolve_outcome
from .position_storage import LocalPosition, PositionStorage
from .wallet_manager import FixtureWalletSdk, PredictSdkWallet, make_wallet_sdk


@dataclass
class TradeResult:
    market_id: str
    outcome: str
    strategy: str
    order_hash: str
    status: str
    fill_amount: str | None
    token_id: str
    maker_amount: str
    taker_amount: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class TradeApiClientProtocol(Protocol):
    _jwt_provider: Callable[[], Awaitable[str]] | None

    async def get_market(self, market_id: str) -> Any: ...

    async def get_orderbook(self, market_id: str) -> Any: ...

    async def create_order(self, order_payload: dict[str, Any]) -> Any: ...

    async def get_order(self, order_hash: str) -> Any: ...

    async def get_auth_message(self) -> Any: ...

    async def get_jwt(self, auth_request: Any) -> Any: ...


class TradeService:
    def __init__(
        self,
        config: PredictConfig,
        *,
        api_client_factory: Callable[
            [PredictConfig, Callable[[], Awaitable[str]] | None], Any
        ]
        | None = None,
        wallet_sdk_factory: Callable[[PredictConfig], Any] = make_wallet_sdk,
        sleep: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        self._config = config
        self._api_client_factory = api_client_factory or _default_api_client_factory
        self._wallet_sdk_factory = wallet_sdk_factory
        self._sleep = sleep or asyncio.sleep

    async def buy(
        self,
        market_id: str,
        outcome_label: str,
        amount_usdt: str,
        *,
        limit_price: float | None = None,
        slippage_bps: int | None = None,
        expiration_minutes: int | None = None,
    ) -> TradeResult:
        sdk = self._wallet_sdk_factory(self._config)
        if (
            isinstance(sdk, FixtureWalletSdk)
            or self._config.env == RuntimeEnv.TEST_FIXTURE
        ):
            return await self._buy_fixture(
                market_id, outcome_label, amount_usdt, limit_price=limit_price
            )

        if not hasattr(sdk, "_builder"):
            raise ConfigError("Trading requires an SDK-backed wallet context.")

        builder = sdk._builder
        api_client = cast(
            TradeApiClientProtocol,
            self._api_client_factory(self._config, None),
        )
        authenticator = PredictAuthenticator(self._config, api_client)
        api_client._jwt_provider = (
            authenticator.get_jwt
        )  # align authenticated calls with this session

        market = await api_client.get_market(market_id)
        outcome = resolve_outcome(market, outcome_label)
        orderbook = await api_client.get_orderbook(market_id)
        sdk_book = orderbook_record_to_sdk_book(orderbook)

        strategy = "LIMIT" if limit_price is not None else "MARKET"
        amount_wei = _parse_amount_to_wei(amount_usdt)
        if amount_wei <= 0:
            raise ConfigError("Trade amount must be greater than zero.")

        if strategy == "MARKET":
            order_amounts = builder.get_market_order_amounts(
                MarketHelperValueInput(
                    side=Side.BUY,
                    value_wei=amount_wei,
                    slippage_bps=slippage_bps or 0,
                ),
                sdk_book,
            )
        else:
            assert limit_price is not None
            limit_price_wei = int(limit_price * 10**18)
            order_amounts = builder.get_limit_order_amounts(
                LimitHelperInput(
                    side=Side.BUY,
                    price_per_share_wei=limit_price_wei,
                    quantity_wei=amount_wei,
                )
            )

        order = builder.build_order(
            strategy,
            BuildOrderInput(
                side=Side.BUY,
                token_id=outcome.token_id,
                maker_amount=str(order_amounts.maker_amount),
                taker_amount=str(order_amounts.taker_amount),
                fee_rate_bps=str(market.feeRateBps or 0),
            ),
        )
        typed_data = builder.build_typed_data(
            order,
            is_neg_risk=bool(market.isNegRisk),
            is_yield_bearing=bool(market.isYieldBearing),
        )
        signed_order = builder.sign_typed_data_order(typed_data)
        created = await api_client.create_order(
            {
                **asdict(signed_order),
                **({"slippageBps": slippage_bps} if slippage_bps is not None else {}),
                **(
                    {"expirationMinutes": expiration_minutes}
                    if expiration_minutes is not None
                    else {}
                ),
            }
        )

        order_hash = created.hash or signed_order.hash or ""
        polled = created
        if order_hash:
            for _ in range(15):
                polled = await api_client.get_order(order_hash)
                if (polled.status or "").upper() in {"FILLED", "OPEN"}:
                    break
                await self._sleep(2.0)

        self._persist_local_position(
            market_id=str(market_id),
            question=market.question or market.title or "",
            outcome=outcome.label,
            token_id=outcome.token_id,
            strategy=strategy,
            entry_price=(order_amounts.maker_amount / order_amounts.taker_amount)
            if order_amounts.taker_amount
            else 0.0,
            quantity=str(order_amounts.taker_amount),
            notional_usdt=float(amount_usdt),
            order_hash=order_hash,
            order_status=(polled.status or created.status or "OPEN").upper(),
            fill_amount=_extract_fill_amount(polled),
            fee_rate_bps=int(market.feeRateBps or 0),
        )

        return TradeResult(
            market_id=str(market_id),
            outcome=outcome.label,
            strategy=strategy,
            order_hash=order_hash,
            status=(polled.status or created.status or "OPEN").upper(),
            fill_amount=_extract_fill_amount(polled),
            token_id=outcome.token_id,
            maker_amount=str(order_amounts.maker_amount),
            taker_amount=str(order_amounts.taker_amount),
        )

    def _persist_local_position(
        self,
        *,
        market_id: str,
        question: str,
        outcome: str,
        token_id: str,
        strategy: str,
        entry_price: float,
        quantity: str,
        notional_usdt: float,
        order_hash: str,
        order_status: str,
        fill_amount: str | None,
        fee_rate_bps: int,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        position_id = f"pos-{market_id}-{outcome.lower()}"
        storage = PositionStorage(self._config.storage_dir)
        storage.upsert(
            LocalPosition(
                position_id=position_id,
                market_id=market_id,
                question=question,
                outcome_name=outcome,
                token_id=token_id,
                side="BUY",
                strategy=strategy,
                entry_time=now,
                entry_price=float(entry_price),
                quantity=quantity,
                notional_usdt=notional_usdt,
                order_hash=order_hash,
                order_status=order_status,
                fill_amount=fill_amount,
                fee_rate_bps=fee_rate_bps,
                source="tracked",
                status="OPEN",
            )
        )

    async def _buy_fixture(
        self,
        market_id: str,
        outcome_label: str,
        amount_usdt: str,
        *,
        limit_price: float | None,
    ) -> TradeResult:
        api_client = FixturePredictApiClient()
        market = await api_client.get_market(market_id)
        outcome = resolve_outcome(market, outcome_label)
        strategy = "LIMIT" if limit_price is not None else "MARKET"
        amount_wei = _parse_amount_to_wei(amount_usdt)
        self._persist_local_position(
            market_id=str(market_id),
            question=market.question or market.title or "",
            outcome=outcome.label,
            token_id=outcome.token_id,
            strategy=strategy,
            entry_price=1.0,
            quantity=str(amount_wei),
            notional_usdt=float(amount_usdt),
            order_hash="0xfixture-order",
            order_status="FILLED",
            fill_amount=str(amount_wei),
            fee_rate_bps=int(market.feeRateBps or 0),
        )
        return TradeResult(
            market_id=str(market_id),
            outcome=outcome.label,
            strategy=strategy,
            order_hash="0xfixture-order",
            status="FILLED",
            fill_amount=str(amount_wei),
            token_id=outcome.token_id,
            maker_amount=str(amount_wei),
            taker_amount=str(amount_wei),
        )


def _default_api_client_factory(
    config: PredictConfig,
    jwt_provider: Callable[[], Awaitable[str]] | None,
) -> PredictApiClient:
    return PredictApiClient(config, jwt_provider=jwt_provider)


def _parse_amount_to_wei(raw_amount: str) -> int:
    try:
        amount = Decimal(raw_amount)
    except InvalidOperation as error:
        raise ConfigError("Trade amount must be numeric.") from error
    if amount <= 0:
        return 0
    return int(amount * (Decimal(10) ** 18))


def _extract_fill_amount(order: Any) -> str | None:
    for key in ("fillAmount", "filledAmount", "matchedAmount"):
        value = getattr(order, key, None)
        if value is not None:
            return str(value)
    return None


async def _async_no_sleep(_seconds: float) -> None:
    return None
