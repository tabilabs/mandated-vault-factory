from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from inspect import isawaitable
from typing import Any, Awaitable, Callable, Protocol, cast

from predict_sdk import BuildOrderInput, LimitHelperInput, MarketHelperValueInput, Side

from .api import PredictApiClient
from .auth import PredictAuthenticator
from .config import (
    ConfigError,
    PredictConfig,
    RuntimeEnv,
    WalletMode,
    mandated_vault_v1_unsupported_error,
)
from .fixture_api import FixturePredictApiClient
from .orderbook import orderbook_record_to_sdk_book, resolve_outcome
from .position_storage import LocalPosition, PositionStorage
from .wallet_manager import (
    FixtureWalletSdk,
    MandatedVaultBridgeProtocol,
    PredictSdkWallet,
    VaultToPredictAccountFundingOrchestration,
    build_vault_to_predict_account_orchestration,
    load_wallet_usdt_balance_wei,
    make_wallet_sdk,
)
from .mandated_mcp_bridge import MandatedVaultMcpBridge


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


class OverlayOrchestrationProtocol(Protocol):
    def to_dict(self) -> dict[str, object]: ...


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
        bridge_factory: Callable[
            [PredictConfig], MandatedVaultBridgeProtocol
        ] = MandatedVaultMcpBridge,
        overlay_orchestration_factory: Callable[
            [PredictConfig, str, str, int],
            Awaitable[OverlayOrchestrationProtocol] | OverlayOrchestrationProtocol,
        ]
        | None = None,
        sleep: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        self._config = config
        self._api_client_factory = api_client_factory or _default_api_client_factory
        self._wallet_sdk_factory = wallet_sdk_factory
        self._bridge_factory = bridge_factory
        self._overlay_orchestration_factory = overlay_orchestration_factory
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
        if self._config.wallet_mode == WalletMode.MANDATED_VAULT:
            raise mandated_vault_v1_unsupported_error("buy")

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

        amount_wei = _parse_amount_to_wei(amount_usdt)
        if amount_wei <= 0:
            raise ConfigError("Trade amount must be greater than zero.")

        position_notes: str | None = None
        if _has_predict_account_overlay(self._config):
            usdt_balance = await _sdk_usdt_balance_wei(sdk)
            if usdt_balance < amount_wei:
                orchestration = await self._build_overlay_orchestration(
                    predict_account_address=sdk.funding_address,
                    trade_signer_address=sdk.signer_address,
                    current_usdt_balance_wei=usdt_balance,
                    wallet_sdk=sdk,
                )
                raise ConfigError(
                    _format_overlay_funding_required_error(
                        orchestration,
                        attempted_buy_amount_raw=amount_wei,
                        current_balance_raw=usdt_balance,
                    )
                )
            position_notes = _overlay_position_notes(
                predict_account_address=sdk.funding_address,
                trade_signer_address=sdk.signer_address,
            )

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

        strategy = "LIMIT" if limit_price is not None else "MARKET"

        if strategy == "MARKET":
            orderbook = await api_client.get_orderbook(market_id)
            sdk_book = orderbook_record_to_sdk_book(orderbook)
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
        signed_order_payload = asdict(signed_order)
        if not signed_order_payload.get("hash") and hasattr(builder, "build_typed_data_hash"):
            signed_order_payload["hash"] = builder.build_typed_data_hash(typed_data)
        created = await api_client.create_order(
            {
                "order": signed_order_payload,
                "pricePerShare": str(order_amounts.price_per_share),
                "strategy": strategy,
                **({"slippageBps": slippage_bps} if slippage_bps is not None else {}),
                **(
                    {"expirationMinutes": expiration_minutes}
                    if expiration_minutes is not None
                    else {}
                ),
            }
        )

        order_hash = created.hash or signed_order_payload.get("hash") or signed_order.hash or ""
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
            notes=position_notes,
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
        notes: str | None = None,
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
                notes=notes,
                status="OPEN",
            )
        )

    async def _build_overlay_orchestration(
        self,
        *,
        predict_account_address: str,
        trade_signer_address: str,
        current_usdt_balance_wei: int,
        wallet_sdk: Any | None = None,
    ) -> OverlayOrchestrationProtocol:
        if self._overlay_orchestration_factory is not None:
            maybe = self._overlay_orchestration_factory(
                self._config,
                predict_account_address,
                trade_signer_address,
                current_usdt_balance_wei,
            )
            return await maybe if isawaitable(maybe) else maybe

        bridge = self._bridge_factory(self._config)
        await bridge.connect()
        try:
            return await build_vault_to_predict_account_orchestration(
                self._config,
                bridge,
                predict_account_address=predict_account_address,
                trade_signer_address=trade_signer_address,
                current_usdt_balance_wei=current_usdt_balance_wei,
                wallet_sdk=wallet_sdk,
            )
        finally:
            await bridge.close()

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


def _has_predict_account_overlay(config: PredictConfig) -> bool:
    return (
        config.wallet_mode == WalletMode.PREDICT_ACCOUNT
        and config.has_mandated_config_input
    )


async def _sdk_usdt_balance_wei(sdk: Any) -> int:
    getter = getattr(sdk, "get_usdt_balance_wei", None)
    if not callable(getter):
        raise ConfigError(
            "Predict-account + vault overlay buy requires a wallet SDK that reports USDT balance."
        )
    value = await load_wallet_usdt_balance_wei(cast(Any, sdk))
    try:
        return int(cast(Any, value))
    except (TypeError, ValueError) as error:
        raise ConfigError(
            "Predict-account + vault overlay buy requires a numeric USDT balance from wallet SDK."
        ) from error


def _overlay_position_notes(
    *,
    predict_account_address: str,
    trade_signer_address: str,
) -> str:
    return json.dumps(
        {
            "fundingRoute": "vault-to-predict-account",
            "predictAccountAddress": predict_account_address,
            "tradeSignerAddress": trade_signer_address,
            "overlayActive": True,
        },
        separators=(",", ":"),
    )


def _format_overlay_funding_required_error(
    orchestration: OverlayOrchestrationProtocol,
    *,
    attempted_buy_amount_raw: int,
    current_balance_raw: int,
) -> str:
    payload = orchestration.to_dict()
    funding_target = payload.get("fundingTarget", {})
    if not isinstance(funding_target, dict):
        funding_target = {}
    shortfall_raw = max(attempted_buy_amount_raw - max(current_balance_raw, 0), 0)
    route = str(payload.get("fundingRoute", "vault-to-predict-account"))
    required = str(shortfall_raw)
    current = str(max(current_balance_raw, 0))
    recipient = str(
        funding_target.get(
            "recipient",
            payload.get("predictAccountAddress", "unknown"),
        )
    )
    next_step = payload.get("fundingNextStep", {})
    if not isinstance(next_step, dict):
        next_step = {}
    task = next_step.get("task", {})
    if not isinstance(task, dict):
        task = {}
    next_step_kind = str(task.get("kind", "unknown"))
    session_status, current_step, session_outcome = _overlay_session_state(payload)
    return (
        "buy: funding-required for predict-account overlay. "
        f"attemptedBuyAmountRaw={attempted_buy_amount_raw} "
        f"route={route} recipient={recipient} "
        f"requiredAmountRaw={required} currentBalanceRaw={current} "
        f"nextStepKind={next_step_kind} "
        f"sessionStatus={session_status} currentStep={current_step} "
        f"sessionOutcome={session_outcome}. "
        "Vault funding automation is not enabled in this local signer context; "
        "run `wallet deposit --json` and execute the returned session-backed next step before retrying buy."
    )


def _overlay_session_state(payload: dict[str, object]) -> tuple[str, str, str]:
    session = payload.get("fundingSession", {})
    if not isinstance(session, dict):
        session = {}
    session_status = str(session.get("status", "unknown"))
    current_step = str(session.get("currentStep", "unknown"))

    funding_step = session.get("fundingStep", {})
    if not isinstance(funding_step, dict):
        funding_step = {}
    follow_up_step = session.get("followUpStep", {})
    if not isinstance(follow_up_step, dict):
        follow_up_step = {}

    funding_target = payload.get("fundingTarget", {})
    if not isinstance(funding_target, dict):
        funding_target = {}

    if _overlay_balance_snapshot_is_stale(payload, funding_target):
        return session_status, current_step, "stale-balance"
    if session_status == "failed" and funding_step.get("status") == "failed":
        return session_status, current_step, "funding-failed"
    if session_status == "failed" and follow_up_step.get("status") == "failed":
        return session_status, current_step, "follow-up-failed"
    if session_status == "pendingFunding":
        return session_status, current_step, "pending-funding"
    if session_status == "pendingFollowUp":
        return session_status, current_step, "pending-follow-up"
    if session_status in {"succeeded", "failed", "skipped"}:
        return session_status, current_step, session_status
    return session_status, current_step, "unknown"


def _overlay_balance_snapshot_is_stale(
    payload: dict[str, object],
    funding_target: dict[str, object],
) -> bool:
    for snapshot_target, evaluated_at_raw in _overlay_snapshot_sources(
        payload, funding_target
    ):
        balance_snapshot = snapshot_target.get("balanceSnapshot", {})
        if not isinstance(balance_snapshot, dict):
            continue
        snapshot_at = _parse_overlay_timestamp(balance_snapshot.get("snapshotAt"))
        evaluated_at = _parse_overlay_timestamp(evaluated_at_raw)
        if snapshot_at is None or evaluated_at is None:
            continue
        try:
            max_staleness_seconds = int(balance_snapshot.get("maxStalenessSeconds", 0))
        except (TypeError, ValueError):
            continue
        if (evaluated_at - snapshot_at).total_seconds() > max_staleness_seconds:
            return True
    return False


def _overlay_snapshot_sources(
    payload: dict[str, object],
    funding_target: dict[str, object],
) -> list[tuple[dict[str, object], object]]:
    sources: list[tuple[dict[str, object], object]] = []

    session = payload.get("fundingSession", {})
    if isinstance(session, dict):
        plan = session.get("fundAndActionPlan", {})
        if isinstance(plan, dict):
            session_target = plan.get("fundingTarget", {})
            if isinstance(session_target, dict):
                sources.append((session_target, plan.get("evaluatedAt")))

    plan_payload = payload.get("fundingPlan", {})
    if isinstance(plan_payload, dict):
        plan_target = plan_payload.get("fundingTarget", {})
        if isinstance(plan_target, dict):
            sources.append((plan_target, plan_payload.get("evaluatedAt")))

    sources.append((funding_target, payload.get("evaluatedAt")))
    return sources


def _parse_overlay_timestamp(raw: object) -> datetime | None:
    if not isinstance(raw, str) or not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


async def _async_no_sleep(_seconds: float) -> None:
    return None
