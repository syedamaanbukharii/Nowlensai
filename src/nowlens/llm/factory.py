"""Provider factory.

Resolves the configured providers without exposing concrete classes to callers.

* The *chat* provider follows ``NOWLENS_LLM__PROVIDER`` (ollama | groq).
* The *embedding* provider follows ``NOWLENS_LLM__EMBEDDING_PROVIDER``
  (ollama | openai), independently of the chat provider — so a hosted chat
  backend (e.g. Groq, which has no embeddings endpoint) can be paired with
  local Ollama or a hosted OpenAI-compatible embedding service.

Providers are cached per-event-loop-process via :func:`functools.lru_cache`;
they hold pooled ``httpx`` clients and should be closed on shutdown via
:func:`close_providers`.
"""

from __future__ import annotations

from functools import lru_cache

from nowlens.core.config import Settings, get_settings
from nowlens.core.exceptions import ConfigurationError
from nowlens.llm.base import EmbeddingProvider, LLMProvider
from nowlens.llm.groq import GroqProvider
from nowlens.llm.ollama import OllamaProvider
from nowlens.llm.openai_embeddings import OpenAIEmbeddingProvider


def _build_chat_provider(settings: Settings) -> LLMProvider:
    cfg = settings.llm
    if cfg.provider == "ollama":
        return OllamaProvider(
            base_url=cfg.ollama_base_url,
            chat_model=cfg.ollama_chat_model,
            embed_model=cfg.ollama_embed_model,
            embedding_dim=cfg.embedding_dim,
            timeout_s=cfg.request_timeout_s,
            max_retries=cfg.max_retries,
            default_temperature=cfg.temperature,
        )
    if cfg.provider == "groq":
        return GroqProvider(
            base_url=cfg.groq_base_url,
            api_key=cfg.groq_api_key,
            chat_model=cfg.groq_chat_model,
            timeout_s=cfg.request_timeout_s,
            max_retries=cfg.max_retries,
            default_temperature=cfg.temperature,
        )
    raise ConfigurationError(f"Unknown LLM provider: {cfg.provider!r}")


def _build_embedding_provider(settings: Settings) -> EmbeddingProvider:
    cfg = settings.llm
    if cfg.embedding_provider == "ollama":
        return OllamaProvider(
            base_url=cfg.ollama_base_url,
            chat_model=cfg.ollama_chat_model,
            embed_model=cfg.ollama_embed_model,
            embedding_dim=cfg.embedding_dim,
            timeout_s=cfg.request_timeout_s,
            max_retries=cfg.max_retries,
            default_temperature=cfg.temperature,
        )
    if cfg.embedding_provider == "openai":
        return OpenAIEmbeddingProvider(
            base_url=cfg.openai_embed_base_url,
            api_key=cfg.openai_api_key,
            model=cfg.openai_embed_model,
            embedding_dim=cfg.embedding_dim,
            timeout_s=cfg.request_timeout_s,
            max_retries=cfg.max_retries,
        )
    raise ConfigurationError(f"Unknown embedding provider: {cfg.embedding_provider!r}")


@lru_cache
def get_chat_provider() -> LLMProvider:
    return _build_chat_provider(get_settings())


@lru_cache
def get_embedding_provider() -> EmbeddingProvider:
    return _build_embedding_provider(get_settings())


async def close_providers() -> None:
    """Close cached providers and reset the caches (used on app shutdown)."""

    for getter in (get_chat_provider, get_embedding_provider):
        cached = getter.cache_info()
        if cached.currsize:
            provider = getter()
            await provider.aclose()
        getter.cache_clear()
