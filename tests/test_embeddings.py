"""Embedding-provider tests.

The OpenAI-compatible provider is exercised fully offline with an
``httpx.MockTransport``; the factory selection is verified against explicit
settings so no live service or environment is required.
"""

from __future__ import annotations

import json

import httpx
import pytest

from nowlens.core.config import Settings
from nowlens.core.exceptions import ConfigurationError
from nowlens.llm.factory import _build_embedding_provider
from nowlens.llm.openai_embeddings import OpenAIEmbeddingProvider


def _mock_provider(handler) -> OpenAIEmbeddingProvider:  # type: ignore[no-untyped-def]
    provider = OpenAIEmbeddingProvider(
        base_url="https://api.openai.com/v1",
        api_key="sk-test",
        model="text-embedding-3-small",
        embedding_dim=4,
    )
    provider._client = httpx.AsyncClient(
        base_url=provider.base_url, transport=httpx.MockTransport(handler)
    )
    return provider


# --------------------------------------------------------------------------- #
# OpenAI-compatible provider
# --------------------------------------------------------------------------- #


async def test_openai_embed_batches_and_sorts_by_index() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.update(body)
        # Return items deliberately out of order to prove we sort by index.
        data = [
            {"index": i, "embedding": [float(i)] * body["dimensions"]}
            for i in reversed(range(len(body["input"])))
        ]
        return httpx.Response(200, json={"data": data, "model": body["model"]})

    provider = _mock_provider(handler)
    vectors = await provider.embed(["a", "b", "c"])
    await provider.aclose()

    # One request carrying the whole batch + the dimensions parameter.
    assert seen["input"] == ["a", "b", "c"]
    assert seen["dimensions"] == 4
    assert seen["model"] == "text-embedding-3-small"
    # Restored to input order, each the right width.
    assert vectors == [[0.0] * 4, [1.0] * 4, [2.0] * 4]
    assert provider.dimension == 4


async def test_openai_embed_one() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [0.5, 0.5, 0.5, 0.5]}]})

    provider = _mock_provider(handler)
    vector = await provider.embed_one("hello")
    await provider.aclose()
    assert vector == [0.5, 0.5, 0.5, 0.5]


async def test_openai_embed_empty_input_is_noop() -> None:
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover - never called
        raise AssertionError("no request should be made for empty input")

    provider = _mock_provider(handler)
    assert await provider.embed([]) == []
    await provider.aclose()


def test_openai_provider_requires_api_key() -> None:
    with pytest.raises(ConfigurationError):
        OpenAIEmbeddingProvider(
            base_url="https://api.openai.com/v1",
            api_key=None,
            model="text-embedding-3-small",
            embedding_dim=4,
        )


# --------------------------------------------------------------------------- #
# factory selection
# --------------------------------------------------------------------------- #


async def test_factory_defaults_to_ollama_embeddings() -> None:
    provider = _build_embedding_provider(Settings(_env_file=None))
    assert provider.name == "ollama"
    await provider.aclose()


async def test_factory_selects_openai_embeddings() -> None:
    settings = Settings(
        _env_file=None,
        llm={"embedding_provider": "openai", "openai_api_key": "sk-test"},
    )
    provider = _build_embedding_provider(settings)
    assert provider.name == "openai"
    assert provider.dimension == settings.llm.embedding_dim
    await provider.aclose()


def test_factory_openai_without_key_raises() -> None:
    settings = Settings(_env_file=None, llm={"embedding_provider": "openai"})
    with pytest.raises(ConfigurationError):
        _build_embedding_provider(settings)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
