from __future__ import annotations

import asyncio
import json
import re
from typing import Any

import httpx

from .config import ConfigError, PredictConfig, redact_text

LLM_TIMEOUT = 60.0
LLM_MAX_RETRIES = 3


def extract_json_from_response(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", stripped)
    candidates = []
    if fenced:
        candidates.append(fenced.group(1))
    candidates.append(stripped)
    wrapped = re.search(r"(\{[\s\S]*\})", stripped)
    if wrapped:
        candidates.append(wrapped.group(1))
    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return None


class OpenRouterLLMClient:
    def __init__(
        self, config: PredictConfig, *, client: httpx.AsyncClient | None = None
    ) -> None:
        self._config = config
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url="https://openrouter.ai/api/v1", timeout=LLM_TIMEOUT
        )

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def complete_json(
        self, prompt: str, *, system_prompt: str, model: str | None = None
    ) -> dict[str, Any] | None:
        if not self._config.openrouter_api_key:
            raise ConfigError("OPENROUTER_API_KEY is required for hedge analysis.")
        payload = {
            "model": model
            or self._config.model_name
            or "openrouter/openai/gpt-4.1-mini",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            "response_format": {"type": "json_object"},
        }
        for attempt in range(LLM_MAX_RETRIES):
            try:
                response = await self._client.post(
                    "/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self._config.openrouter_api_key.get_secret_value()}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                if response.is_error:
                    raise OpenRouterLLMError(
                        redact_text(
                            f"OpenRouter request failed with status {response.status_code}: {response.text[:180]}",
                            [self._config.openrouter_api_key.get_secret_value()],
                        )
                    )
                raw = response.json()["choices"][0]["message"]["content"]
                if not isinstance(raw, str):
                    return None
                return extract_json_from_response(raw)
            except (httpx.RequestError, OpenRouterLLMError):
                if attempt == LLM_MAX_RETRIES - 1:
                    raise
                await asyncio.sleep(attempt + 1)
        return None


class OpenRouterLLMError(RuntimeError):
    pass
