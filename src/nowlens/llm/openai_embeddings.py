"""OpenAI-compatible embedding provider (hosted).

Talks to any service exposing the OpenAI ``POST /embeddings`` API — OpenAI,
Azure OpenAI (behind an OpenAI-style gateway), Together, a local vLLM server,
etc. — selected via ``NOWLENS_LLM__EMBEDDING_PROVIDER=openai``.

Unlike Ollama, the OpenAI API embeds a whole batch in one request, so ``embed``
sends all texts at once. The configured ``embedding_dim`` is passed through as
the ``dimensions`` parameter (supported by the text-embedding-3-* family), so
the output stays aligned with the Qdrant collection's vector size.
"""

from __future__ import annotations

from collections.abc import Sequence

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from nowlens.core.exceptions import ConfigurationError, ProviderError
from nowlens.core.logging import get_logger
from nowlens.llm.base import EmbeddingProvider

log = get_logger(__name__)

_RETRYABLE = (httpx.TransportError, httpx.HTTPStatusError)


class OpenAIEmbeddingProvider(EmbeddingProvider):
    name = "openai"

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None,
        model: str,
        embedding_dim: int,
        timeout_s: float = 120.0,
        max_retries: int = 3,
    ) -> None:
        if not api_key:
            raise ConfigurationError(
                "OpenAI embedding provider selected but NOWLENS_LLM__OPENAI_API_KEY is not set."
            )
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.dimension = embedding_dim
        self._max_retries = max_retries
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=timeout_s,
            headers={"Authorization": f"Bearer {api_key}"},
        )

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        payload = {
            "model": self.model,
            "input": list(texts),
            "dimensions": self.dimension,
        }

        @retry(
            stop=stop_after_attempt(self._max_retries),
            wait=wait_exponential(multiplier=0.5, max=8),
            retry=retry_if_exception_type(_RETRYABLE),
            reraise=True,
        )
        async def _call() -> dict:
            resp = await self._client.post("/embeddings", json=payload)
            resp.raise_for_status()
            return resp.json()

        try:
            data = await _call()
        except Exception as exc:
            raise ProviderError(f"OpenAI embeddings failed: {exc}") from exc

        # The API may return items out of order; sort by the echoed index.
        items = sorted(data["data"], key=lambda item: item["index"])
        return [item["embedding"] for item in items]

    async def aclose(self) -> None:
        await self._client.aclose()
