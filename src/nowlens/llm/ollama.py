"""Ollama provider (default).

Talks to a local Ollama daemon's REST API:

* ``POST /api/chat``       chat completions (streaming + non-streaming)
* ``POST /api/embeddings`` text embeddings

Requires Ollama running and the configured models pulled, e.g.::

    ollama pull llama3.1:8b
    ollama pull nomic-embed-text
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

from nowlens.core.exceptions import ProviderError
from nowlens.core.logging import get_logger
from nowlens.llm.base import (
    ChatChunk,
    ChatMessage,
    ChatResult,
    ChatUsage,
    EmbeddingProvider,
    LLMProvider,
)

log = get_logger(__name__)

_RETRYABLE = (httpx.TransportError, httpx.HTTPStatusError)


class OllamaProvider(LLMProvider, EmbeddingProvider):
    name = "ollama"

    def __init__(
        self,
        *,
        base_url: str,
        chat_model: str,
        embed_model: str,
        embedding_dim: int,
        timeout_s: float = 120.0,
        max_retries: int = 3,
        default_temperature: float = 0.1,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.chat_model = chat_model
        self.embed_model = embed_model
        self.dimension = embedding_dim
        self._default_temperature = default_temperature
        self._max_retries = max_retries
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=timeout_s)

    # -- chat ---------------------------------------------------------------

    async def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> ChatResult:
        payload = self._chat_payload(messages, temperature, max_tokens, stream=False)

        @retry(
            stop=stop_after_attempt(self._max_retries),
            wait=wait_exponential(multiplier=0.5, max=8),
            retry=retry_if_exception_type(_RETRYABLE),
            reraise=True,
        )
        async def _call() -> dict:
            resp = await self._client.post("/api/chat", json=payload)
            resp.raise_for_status()
            return resp.json()

        try:
            data = await _call()
        except Exception as exc:
            raise ProviderError(f"Ollama chat failed: {exc}") from exc

        message = data.get("message", {})
        return ChatResult(
            content=message.get("content", ""),
            model=data.get("model", self.chat_model),
            provider=self.name,
            usage=ChatUsage(
                prompt_tokens=int(data.get("prompt_eval_count", 0) or 0),
                completion_tokens=int(data.get("eval_count", 0) or 0),
            ),
            finish_reason=data.get("done_reason"),
        )

    async def stream_chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[ChatChunk]:
        payload = self._chat_payload(messages, temperature, max_tokens, stream=True)
        try:
            async with self._client.stream("POST", "/api/chat", json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    event = json.loads(line)
                    delta = event.get("message", {}).get("content", "")
                    done = bool(event.get("done"))
                    usage = None
                    if done:
                        usage = ChatUsage(
                            prompt_tokens=int(event.get("prompt_eval_count", 0) or 0),
                            completion_tokens=int(event.get("eval_count", 0) or 0),
                        )
                    yield ChatChunk(delta=delta, done=done, usage=usage)
        except Exception as exc:
            raise ProviderError(f"Ollama streaming failed: {exc}") from exc

    # -- embeddings ---------------------------------------------------------

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        # Ollama's embeddings endpoint accepts a single prompt; batch client-side.
        vectors: list[list[float]] = []

        @retry(
            stop=stop_after_attempt(self._max_retries),
            wait=wait_exponential(multiplier=0.5, max=8),
            retry=retry_if_exception_type(_RETRYABLE),
            reraise=True,
        )
        async def _embed_one(prompt: str) -> list[float]:
            resp = await self._client.post(
                "/api/embeddings",
                json={"model": self.embed_model, "prompt": prompt},
            )
            resp.raise_for_status()
            return resp.json()["embedding"]

        try:
            for text in texts:
                vectors.append(await _embed_one(text))
        except Exception as exc:
            raise ProviderError(f"Ollama embeddings failed: {exc}") from exc
        return vectors

    # -- helpers ------------------------------------------------------------

    def _chat_payload(
        self,
        messages: Sequence[ChatMessage],
        temperature: float | None,
        max_tokens: int | None,
        *,
        stream: bool,
    ) -> dict:
        options: dict[str, object] = {
            "temperature": temperature if temperature is not None else self._default_temperature
        }
        if max_tokens is not None:
            options["num_predict"] = max_tokens
        return {
            "model": self.chat_model,
            "messages": [m.as_dict() for m in messages],
            "stream": stream,
            "options": options,
        }

    async def aclose(self) -> None:
        await self._client.aclose()
