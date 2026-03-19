from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

from conftest import get_predict_root
from lib.config import ConfigError, PredictConfig, WalletMode
from lib.position_storage import PositionStorage
from lib.trade_service import TradeService


def run_trade(
    *args: str, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    predict_root = get_predict_root()
    command_env = os.environ.copy()
    command_env["PREDICTCLAW_DISABLE_LOCAL_ENV"] = "1"
    if env:
        command_env.update(env)
    return subprocess.run(
        [sys.executable, str(predict_root / "scripts" / "trade.py"), *args],
        cwd=predict_root,
        env=command_env,
        capture_output=True,
        text=True,
        check=False,
    )


def write_trade_api_error_sitecustomize(tmp_path: Path) -> Path:
    patch_root = tmp_path / "trade-api-error-patch"
    patch_root.mkdir(parents=True, exist_ok=True)
    (patch_root / "sitecustomize.py").write_text(
        """
from __future__ import annotations

from lib.api import PredictApiError
import lib.trade_service as trade_service


async def _fail_buy(self, *args, **kwargs):
    raise PredictApiError(
        'predict.fun API request failed for POST /v1/orders with status 403: {"success":false,"code":403,"error":"forbidden","message":"This operation is not available in your jurisdiction"}',
        status_code=403,
        method='POST',
        path='/v1/orders',
    )


trade_service.TradeService.buy = _fail_buy
""".strip(),
        encoding="utf-8",
    )
    return patch_root


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

    def get_limit_order_amounts(self, data):
        self.limit_amount_calls.append((data.price_per_share_wei, data.quantity_wei))
        return FakeOrderAmounts(
            maker_amount=25_000_000_000_000_000_000,
            taker_amount=50_000_000_000_000_000_000,
            price_per_share=data.price_per_share_wei,
        )

    def build_order(self, strategy, data):
        assert strategy in {"MARKET", "LIMIT"}
        assert data.token_id == "1001"
        return object()

    def build_typed_data(self, _order, *, is_neg_risk, is_yield_bearing):
        assert is_neg_risk is False
        assert is_yield_bearing is False
        return object()

    def sign_typed_data_order(self, _typed_data):
        return FakeSignedOrder()

    def build_typed_data_hash(self, _typed_data):
        return "0xtypedhash"


class FakeWalletSdk:
    def __init__(
        self,
        *,
        mode: WalletMode = WalletMode.EOA,
        signer_address: str = "0x1111111111111111111111111111111111111111",
        funding_address: str = "0x1111111111111111111111111111111111111111",
        usdt_balance_wei: int = 25_000_000_000_000_000_000,
    ) -> None:
        self.mode = mode
        self.signer_address = signer_address
        self.funding_address = funding_address
        self._usdt_balance_wei = usdt_balance_wei
        self._builder = FakeBuilder()

    def get_usdt_balance_wei(self) -> int:
        return self._usdt_balance_wei


class AsyncUnsafeWalletSdk(FakeWalletSdk):
    def get_usdt_balance_wei(self) -> int:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return super().get_usdt_balance_wei()
        raise AssertionError("balance getter called inside running event loop")


@dataclass
class FakeOverlayOrchestration:
    funding_route: str = "vault-to-predict-account"
    predict_account_address: str = "0x1234567890123456789012345678901234567890"
    trade_signer_address: str = "0x7777777777777777777777777777777777777777"
    vault_address: str = "0x2222222222222222222222222222222222222222"
    vault_address_source: str = "explicit"
    vault_exists: bool = True
    account_context: dict[str, object] | None = None
    funding_policy: dict[str, object] | None = None
    funding_target: dict[str, object] | None = None
    funding_plan: dict[str, object] | None = None
    funding_session: dict[str, object] | None = None
    funding_next_step: dict[str, object] | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "fundingRoute": self.funding_route,
            "predictAccountAddress": self.predict_account_address,
            "tradeSignerAddress": self.trade_signer_address,
            "vaultAddress": self.vault_address,
            "vaultAddressSource": self.vault_address_source,
            "vaultExists": self.vault_exists,
            "accountContext": self.account_context or {"agentId": "agent"},
            "fundingPolicy": self.funding_policy or {"policyId": "policy"},
            "fundingTarget": self.funding_target
            or {
                "recipient": self.predict_account_address,
                "requiredAmountRaw": "1000000000000000000",
                "currentBalanceRaw": "0",
            },
            "fundingPlan": self.funding_plan
            or {
                "fundingRequired": True,
                "fundingTarget": {
                    "requiredAmountRaw": "1000000000000000000",
                    "currentBalanceRaw": "0",
                },
            },
            "fundingSession": self.funding_session
            or {
                "sessionId": "session-trade-overlay",
                "status": "pendingFunding",
                "currentStep": "fundTargetAccount",
            },
            "fundingNextStep": self.funding_next_step
            or {
                "task": {
                    "kind": "submitFunding",
                    "summary": "Submit vault funding transaction",
                }
            },
        }


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


class OnChainIdOnlyApiClient(FakeApiClient):
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
                OutcomeRecord(name="YES", onChainId="1001"),
                OutcomeRecord(name="NO", onChainId="1002"),
            ],
        )


class MissingOrderbookApiClient(FakeApiClient):
    async def get_orderbook(self, _market_id):
        raise AssertionError("limit order path should not request orderbook")


def test_trade_buy_api_error_fails_closed_without_traceback_in_json_mode(
    tmp_path: Path,
) -> None:
    patch_root = write_trade_api_error_sitecustomize(tmp_path)
    env = {
        "PREDICT_ENV": "testnet",
        "PREDICT_STORAGE_DIR": str(tmp_path),
        "PYTHONPATH": str(patch_root),
    }

    result = run_trade("buy", "123", "YES", "25", "--json", env=env)

    assert result.returncode == 1
    assert result.stderr == ""
    combined = result.stdout + result.stderr
    assert "Traceback" not in combined
    payload = result.stdout.strip()
    assert '"success": false' in payload
    assert '"error": "PredictApiError"' in payload
    assert '"statusCode": 403' in payload
    assert '"path": "/v1/orders"' in payload
    assert "jurisdiction" in payload.lower()


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
    assert api_client.created_orders[0] == {
        "order": {
            "salt": "1",
            "maker": "0xmaker",
            "signer": "0xsigner",
            "taker": "0x0000000000000000000000000000000000000000",
            "token_id": "1001",
            "maker_amount": "25000000000000000000",
            "taker_amount": "40000000000000000000",
            "expiration": "0",
            "nonce": "0",
            "fee_rate_bps": "100",
            "side": 0,
            "signature_type": 0,
            "signature": "0xsig",
            "hash": "0xorderhash",
        },
        "pricePerShare": "625000000000000000",
        "strategy": "MARKET",
        "slippageBps": 50,
    }
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


@pytest.mark.asyncio
async def test_buy_uses_onchain_id_when_token_id_missing() -> None:
    config = PredictConfig.from_env(
        {
            "PREDICT_ENV": "testnet",
            "PREDICT_STORAGE_DIR": "/tmp/predict",
            "PREDICT_PRIVATE_KEY": "0x59c6995e998f97a5a0044976f4d060f5d89c8b8c7f11b9aa0dbf3f0f7c7c1e01",
        }
    )
    api_client = OnChainIdOnlyApiClient()
    wallet_sdk = FakeWalletSdk()
    service = TradeService(
        config,
        api_client_factory=lambda _config, _jwt_provider: api_client,
        wallet_sdk_factory=lambda _config: wallet_sdk,
    )

    result = await service.buy("123", "YES", "25", slippage_bps=50)

    assert len(api_client.created_orders) == 1
    assert result.token_id == "1001"


@pytest.mark.asyncio
async def test_buy_limit_order_does_not_require_orderbook_lookup() -> None:
    config = PredictConfig.from_env(
        {
            "PREDICT_ENV": "testnet",
            "PREDICT_STORAGE_DIR": "/tmp/predict",
            "PREDICT_PRIVATE_KEY": "0x59c6995e998f97a5a0044976f4d060f5d89c8b8c7f11b9aa0dbf3f0f7c7c1e01",
        }
    )
    api_client = MissingOrderbookApiClient()
    wallet_sdk = FakeWalletSdk()
    service = TradeService(
        config,
        api_client_factory=lambda _config, _jwt_provider: api_client,
        wallet_sdk_factory=lambda _config: wallet_sdk,
    )

    result = await service.buy("123", "YES", "25", limit_price=0.5)

    assert wallet_sdk._builder.limit_amount_calls == [
        (500000000000000000, 25_000_000_000_000_000_000)
    ]
    assert len(api_client.created_orders) == 1
    assert api_client.created_orders[0] == {
        "order": {
            "salt": "1",
            "maker": "0xmaker",
            "signer": "0xsigner",
            "taker": "0x0000000000000000000000000000000000000000",
            "token_id": "1001",
            "maker_amount": "25000000000000000000",
            "taker_amount": "40000000000000000000",
            "expiration": "0",
            "nonce": "0",
            "fee_rate_bps": "100",
            "side": 0,
            "signature_type": 0,
            "signature": "0xsig",
            "hash": "0xorderhash",
        },
        "pricePerShare": "500000000000000000",
        "strategy": "LIMIT",
    }
    assert result.token_id == "1001"


@pytest.mark.asyncio
async def test_trade_buy_mandated_vault_fails_closed_with_v1_guidance() -> None:
    config = PredictConfig.from_env(
        {
            "PREDICT_ENV": "testnet",
            "PREDICT_STORAGE_DIR": "/tmp/predict",
            "PREDICT_WALLET_MODE": "mandated-vault",
            "ERC_MANDATED_VAULT_ADDRESS": "0x2222222222222222222222222222222222222222",
        }
    )
    service = TradeService(config)

    with pytest.raises(ConfigError) as error:
        await service.buy("123", "YES", "25")

    message = str(error.value)
    assert "unsupported-in-mandated-vault-v1" in message
    assert "protected funding/control-plane operations" in message
    assert "predict.fun trading parity" in message


@pytest.mark.asyncio
async def test_trade_buy_predict_account_overlay_uses_predict_path_when_balance_sufficient(
    tmp_path: Path,
) -> None:
    config = PredictConfig.from_env(
        {
            "PREDICT_ENV": "testnet",
            "PREDICT_STORAGE_DIR": str(tmp_path),
            "PREDICT_WALLET_MODE": "predict-account",
            "PREDICT_ACCOUNT_ADDRESS": "0x1234567890123456789012345678901234567890",
            "PREDICT_PRIVY_PRIVATE_KEY": "0x59c6995e998f97a5a0044976f4d060f5d89c8b8c7f11b9aa0dbf3f0f7c7c1e01",
            "ERC_MANDATED_FACTORY_ADDRESS": "0x1111111111111111111111111111111111111111",
            "ERC_MANDATED_VAULT_ASSET_ADDRESS": "0x4444444444444444444444444444444444444444",
            "ERC_MANDATED_VAULT_NAME": "Mandated Vault",
            "ERC_MANDATED_VAULT_SYMBOL": "MVLT",
            "ERC_MANDATED_VAULT_AUTHORITY": "0x5555555555555555555555555555555555555555",
            "ERC_MANDATED_VAULT_SALT": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        }
    )
    api_client = FakeApiClient()
    wallet_sdk = AsyncUnsafeWalletSdk(
        mode=WalletMode.PREDICT_ACCOUNT,
        signer_address="0x7777777777777777777777777777777777777777",
        funding_address="0x1234567890123456789012345678901234567890",
        usdt_balance_wei=30_000_000_000_000_000_000,
    )
    service = TradeService(
        config,
        api_client_factory=lambda _config, _jwt_provider: api_client,
        wallet_sdk_factory=lambda _config: wallet_sdk,
    )

    result = await service.buy("123", "YES", "25")
    stored = PositionStorage(config.storage_dir).list_positions()

    assert result.status == "FILLED"
    assert len(api_client.created_orders) == 1
    assert stored[0].notes is not None
    assert "vault-to-predict-account" in stored[0].notes
    assert "0x1234567890123456789012345678901234567890" in stored[0].notes


@pytest.mark.asyncio
async def test_trade_buy_predict_account_overlay_fails_with_funding_guidance_when_balance_insufficient() -> (
    None
):
    config = PredictConfig.from_env(
        {
            "PREDICT_ENV": "testnet",
            "PREDICT_STORAGE_DIR": "/tmp/predict",
            "PREDICT_WALLET_MODE": "predict-account",
            "PREDICT_ACCOUNT_ADDRESS": "0x1234567890123456789012345678901234567890",
            "PREDICT_PRIVY_PRIVATE_KEY": "0x59c6995e998f97a5a0044976f4d060f5d89c8b8c7f11b9aa0dbf3f0f7c7c1e01",
            "ERC_MANDATED_FACTORY_ADDRESS": "0x1111111111111111111111111111111111111111",
            "ERC_MANDATED_VAULT_ASSET_ADDRESS": "0x4444444444444444444444444444444444444444",
            "ERC_MANDATED_VAULT_NAME": "Mandated Vault",
            "ERC_MANDATED_VAULT_SYMBOL": "MVLT",
            "ERC_MANDATED_VAULT_AUTHORITY": "0x5555555555555555555555555555555555555555",
            "ERC_MANDATED_VAULT_SALT": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        }
    )
    api_client = FakeApiClient()
    wallet_sdk = FakeWalletSdk(
        mode=WalletMode.PREDICT_ACCOUNT,
        signer_address="0x7777777777777777777777777777777777777777",
        funding_address="0x1234567890123456789012345678901234567890",
        usdt_balance_wei=2_000_000_000_000_000_000,
    )
    orchestration = FakeOverlayOrchestration()
    service = TradeService(
        config,
        api_client_factory=lambda _config, _jwt_provider: api_client,
        wallet_sdk_factory=lambda _config: wallet_sdk,
        overlay_orchestration_factory=(
            lambda _config, _predict_account, _trade_signer, _balance: orchestration
        ),
    )

    with pytest.raises(ConfigError) as error:
        await service.buy("123", "YES", "25")

    message = str(error.value)
    assert "funding-required" in message
    assert "vault-to-predict-account" in message
    assert "requiredAmountRaw=23000000000000000000" in message
    assert "currentBalanceRaw=2000000000000000000" in message
    assert "nextStepKind=submitFunding" in message
    assert "wallet deposit --json" in message
    assert len(api_client.created_orders) == 0
