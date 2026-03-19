from __future__ import annotations

from typing import Any

import httpx

from .config import ConfigError, PredictConfig, redact_text


class OpenRouterError(RuntimeError):
    """Raised when OpenRouter completion requests fail."""


class OpenRouterClient:
    def __init__(
        self, config: PredictConfig, *, client: httpx.AsyncClient | None = None
    ) -> None:
        self._config = config
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url="https://openrouter.ai/api/v1",
            timeout=config.http_timeout_seconds,
        )

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def complete_json(
        self, prompt: str, *, model: str | None = None
    ) -> dict[str, Any]:
        if not self._config.openrouter_api_key:
            raise ConfigError("OPENROUTER_API_KEY is required for hedge analysis.")

        response = await self._client.post(
            "/chat/completions",
            headers={
                "Authorization": f"Bearer {self._config.openrouter_api_key.get_secret_value()}",
                "Content-Type": "application/json",
            },
            json={
                "model": model
                or self._config.model_name
                or "openrouter/openai/gpt-4.1-mini",
                "response_format": {"type": "json_object"},
                "messages": [
                    {
                        "role": "system",
                        "content": "Return valid JSON only. Evaluate hedge overlap and directional offset between prediction markets.",
                    },
                    {
                        "role": "user",
                        "content": prompt,
                    },
                ],
            },
        )
        if response.is_error:
            message = redact_text(
                f"OpenRouter request failed with status {response.status_code}: {response.text[:240]}",
                [self._config.openrouter_api_key.get_secret_value()],
            )
            raise OpenRouterError(message)

        payload = response.json()
        content = payload["choices"][0]["message"]["content"]
        if isinstance(content, str):
            return httpx.Response(200, text=content).json()
        raise OpenRouterError("OpenRouter returned a non-string content payload.")
