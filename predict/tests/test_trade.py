from __future__ import annotations

from dataclasses import dataclass

import pytest

from lib.config import ConfigError, PredictConfig, WalletMode
from lib.trade_service import TradeService


@dataclass
class FakeOrderAmounts:
    maker_amount: int
    taker_amount: int
    price_per_share: int


@dataclass
class FakeSignedOrder:
    salt: str = "1"
    maker: str = "0xmaker"
    signer: str = "0xsigner"
    taker: str = "0x0000000000000000000000000000000000000000"
    token_id: str = "1001"
    maker_amount: str = "25000000000000000000"
    taker_amount: str = "40000000000000000000"
    expiration: str = "0"
    nonce: str = "0"
    fee_rate_bps: str = "100"
    side: int = 0
    signature_type: int = 0
    signature: str = "0xsig"
    hash: str | None = "0xorderhash"


class FakeBuilder:
    def __init__(self) -> None:
        self.market_amount_calls: list[tuple[int, int | None]] = []
        self.limit_amount_calls: list[object] = []

    def get_market_order_amounts(self, data, _book):
        self.market_amount_calls.append((data.value_wei, data.slippage_bps))
        return FakeOrderAmounts(
            maker_amount=25_000_000_000_000_000_000,
            taker_amount=40_000_000_000_000_000_000,
            price_per_share=625_000_000_000_000_000,
        )

    def build_order(self, strategy, data):
        assert strategy == "MARKET"
        assert data.token_id == "1001"
        return object()

    def build_typed_data(self, _order, *, is_neg_risk, is_yield_bearing):
        assert is_neg_risk is False
        assert is_yield_bearing is False
        return object()

    def sign_typed_data_order(self, _typed_data):
        return FakeSignedOrder()


class FakeWalletSdk:
    def __init__(self) -> None:
        self.mode = WalletMode.EOA
        self._builder = FakeBuilder()


class FakeApiClient:
    def __init__(self) -> None:
        self.created_orders: list[dict[str, object]] = []
        self.order_polls: int = 0

    async def get_market(self, market_id):
        from lib.models import MarketRecord, OutcomeRecord

        return MarketRecord(
            id=market_id,
            title="Fixture market",
            question="Fixture question",
            feeRateBps=100,
            isNegRisk=False,
            isYieldBearing=False,
            outcomes=[
                OutcomeRecord(name="YES", tokenId="1001"),
                OutcomeRecord(name="NO", tokenId="1002"),
            ],
        )

    async def get_orderbook(self, _market_id):
        from lib.models import OrderBookRecord

        return OrderBookRecord(
            marketId="123",
            updateTimestampMs=1,
            asks=[[0.62, 10.0]],
            bids=[[0.58, 8.0]],
        )

    async def create_order(self, order_payload):
        from lib.models import OrderRecord

        self.created_orders.append(order_payload)
        return OrderRecord(hash="0xorderhash", status="OPEN")

    async def get_order(self, _order_hash):
        from lib.models import OrderRecord

        self.order_polls += 1
        return OrderRecord(hash="0xorderhash", status="FILLED")

    async def get_auth_message(self):
        from lib.models import AuthMessageResponse

        return AuthMessageResponse(message="sign")

    async def get_jwt(self, _auth_request):
        from lib.models import JwtResponse

        return JwtResponse(token="jwt")


@pytest.mark.asyncio
async def test_buy_market_order_builds_submits_and_polls_status() -> None:
    config = PredictConfig.from_env(
        {
            "PREDICT_ENV": "testnet",
            "PREDICT_STORAGE_DIR": "/tmp/predict",
            "PREDICT_PRIVATE_KEY": "0x59c6995e998f97a5a0044976f4d060f5d89c8b8c7f11b9aa0dbf3f0f7c7c1e01",
        }
    )
    api_client = FakeApiClient()
    wallet_sdk = FakeWalletSdk()
    service = TradeService(
        config,
        api_client_factory=lambda _config, _jwt_provider: api_client,
        wallet_sdk_factory=lambda _config: wallet_sdk,
    )

    result = await service.buy("123", "YES", "25", slippage_bps=50)

    assert wallet_sdk._builder.market_amount_calls == [(25_000_000_000_000_000_000, 50)]
    assert len(api_client.created_orders) == 1
    assert api_client.order_polls == 1
    assert result.status == "FILLED"
    assert result.token_id == "1001"


@pytest.mark.asyncio
async def test_trade_rejects_invalid_outcome_before_network_call() -> None:
    config = PredictConfig.from_env(
        {
            "PREDICT_ENV": "testnet",
            "PREDICT_STORAGE_DIR": "/tmp/predict",
            "PREDICT_PRIVATE_KEY": "0x59c6995e998f97a5a0044976f4d060f5d89c8b8c7f11b9aa0dbf3f0f7c7c1e01",
        }
    )
    api_client = FakeApiClient()
    service = TradeService(
        config,
        api_client_factory=lambda _config, _jwt_provider: api_client,
        wallet_sdk_factory=lambda _config: FakeWalletSdk(),
    )

    with pytest.raises(ConfigError, match="Outcome MAYBE is not available"):
        await service.buy("123", "MAYBE", "25")

    assert api_client.created_orders == []
