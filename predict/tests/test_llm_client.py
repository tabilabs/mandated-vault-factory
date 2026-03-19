from __future__ import annotations

import pytest

from lib.config import PredictConfig
from lib.llm_client import (
    OpenRouterLLMClient,
    OpenRouterLLMError,
    extract_json_from_response,
)


def test_extract_json_rejects_invalid_or_empty_llm_output() -> None:
    assert extract_json_from_response("") is None
    assert extract_json_from_response("no json here") is None
    assert extract_json_from_response('```json\n{"coverage": 0.95}\n```') == {
        "coverage": 0.95
    }
    assert extract_json_from_response('wrapped text {"tier": 2} trailing') == {
        "tier": 2
    }


@pytest.mark.asyncio
async def test_openrouter_requires_api_key() -> None:
    config = PredictConfig.from_env(
        {
            "PREDICT_ENV": "testnet",
            "PREDICT_STORAGE_DIR": "/tmp/predict",
        }
    )
    client = OpenRouterLLMClient(config)
    with pytest.raises(Exception):
        await client.complete_json("{}", system_prompt="test")
    await client.close()
