from __future__ import annotations

import os

import pytest

from lib.api import PredictApiClient
from lib.auth import PredictAuthenticator
from lib.config import PredictConfig
from lib.funding_service import FundingService


def _smoke_env_or_skip() -> dict[str, str]:
    required = ["PREDICT_SMOKE_ENV"]
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        pytest.skip(f"Smoke env not configured; missing: {', '.join(missing)}")
    return {
        "PREDICT_ENV": os.getenv("PREDICT_SMOKE_ENV", "testnet"),
        "PREDICT_STORAGE_DIR": os.getenv("PREDICT_STORAGE_DIR", "/tmp/predict-smoke"),
        "PREDICT_API_KEY": os.getenv("PREDICT_SMOKE_API_KEY", ""),
        "PREDICT_PRIVATE_KEY": os.getenv("PREDICT_SMOKE_PRIVATE_KEY", ""),
        "PREDICT_ACCOUNT_ADDRESS": os.getenv("PREDICT_SMOKE_ACCOUNT_ADDRESS", ""),
        "PREDICT_PRIVY_PRIVATE_KEY": os.getenv("PREDICT_SMOKE_PRIVY_PRIVATE_KEY", ""),
        "PREDICT_API_BASE_URL": os.getenv(
            "PREDICT_SMOKE_API_BASE_URL", "https://dev.predict.fun"
        ),
    }


@pytest.mark.asyncio
async def test_testnet_smoke() -> None:
    config = PredictConfig.from_env(_smoke_env_or_skip())
    client = PredictApiClient(config)

    try:
        auth_message = await client.get_auth_message()
        assert auth_message.message

        funding = FundingService(config)
        if config.auth_signer_address is not None:
            deposit = funding.get_deposit_details()
            assert deposit.funding_address
            authenticator = PredictAuthenticator(config, client)
            client._jwt_provider = authenticator.get_jwt
            token = await authenticator.get_jwt(force_refresh=True)
            assert token

        markets = await client.get_markets(status="OPEN", first=5)
        assert markets
        orderbook = await client.get_orderbook(markets[0].id)
        assert orderbook.marketId is not None

        if config.auth_signer_address is not None:
            positions = await client.get_positions()
            assert positions is not None
    finally:
        await client.close()
