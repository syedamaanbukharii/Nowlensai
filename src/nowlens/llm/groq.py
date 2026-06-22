"""Groq provider (optional, hosted).

Uses Groq's OpenAI-compatible Chat Completions API. Groq does not expose an
embeddings endpoint, so embedding generation is delegated to the dedicated
embedding provider (see :mod:`nowlens.llm.factory`). This separation keeps the
chat/embedding concerns independent and provider-agnostic.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Sequence

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from nowlens.core.exceptions import ConfigurationError, ProviderError
from nowlens.llm.base import ChatChunk, ChatMessage, ChatResult, ChatUsage, LLMProvider

_RETRYABLE = (httpx.TransportError, httpx.HTTPStatusError)


class GroqProvider(LLMProvider):
    name = "groq"

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None,
        chat_model: str,
        timeout_s: float = 120.0,
        max_retries: int = 3,
        default_temperature: float = 0.1,
    ) -> None:
        if not api_key:
            raise ConfigurationError(
                "Groq provider selected but NOWLENS_LLM_GROQ_API_KEY is not set."
            )
        self.base_url = base_url.rstrip("/")
        self.chat_model = chat_model
        self._default_temperature = default_temperature
        self._max_retries = max_retries
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=timeout_s,
            headers={"Authorization": f"Bearer {api_key}"},
        )

    async def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> ChatResult:
        payload = self._payload(messages, temperature, max_tokens, stream=False)

        @retry(
            stop=stop_after_attempt(self._max_retries),
            wait=wait_exponential(multiplier=0.5, max=8),
            retry=retry_if_exception_type(_RETRYABLE),
            reraise=True,
        )
        async def _call() -> dict:
            resp = await self._client.post("/chat/completions", json=payload)
            resp.raise_for_status()
            return resp.json()

        try:
            data = await _call()
        except Exception as exc:
            raise ProviderError(f"Groq chat failed: {exc}") from exc

        choice = data["choices"][0]
        usage = data.get("usage", {})
        return ChatResult(
            content=choice["message"]["content"],
            model=data.get("model", self.chat_model),
            provider=self.name,
            usage=ChatUsage(
                prompt_tokens=int(usage.get("prompt_tokens", 0) or 0),
                completion_tokens=int(usage.get("completion_tokens", 0) or 0),
            ),
            finish_reason=choice.get("finish_reason"),
        )

    async def stream_chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[ChatChunk]:
        payload = self._payload(messages, temperature, max_tokens, stream=True)
        try:
            async with self._client.stream("POST", "/chat/completions", json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    line = line.strip()
                    if not line or not line.startswith("data:"):
                        continue
                    data_str = line[len("data:") :].strip()
                    if data_str == "[DONE]":
                        yield ChatChunk(delta="", done=True)
                        return
                    event = json.loads(data_str)
                    delta = event["choices"][0].get("delta", {}).get("content", "")
                    if delta:
                        yield ChatChunk(delta=delta, done=False)
        except Exception as exc:
            raise ProviderError(f"Groq streaming failed: {exc}") from exc

    def _payload(
        self,
        messages: Sequence[ChatMessage],
        temperature: float | None,
        max_tokens: int | None,
        *,
        stream: bool,
    ) -> dict:
        payload: dict[str, object] = {
            "model": self.chat_model,
            "messages": [m.as_dict() for m in messages],
            "temperature": temperature if temperature is not None else self._default_temperature,
            "stream": stream,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        return payload

    async def aclose(self) -> None:
        await self._client.aclose()
