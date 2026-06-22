"""Provider factory.

Resolves the configured providers without exposing concrete classes to callers.

* The *chat* provider follows ``NOWLENS_LLM_PROVIDER`` (ollama | groq).
* The *embedding* provider is always Ollama, because Groq has no embeddings
  endpoint. This keeps embeddings stable even when the chat backend is hosted,
  and is the documented behaviour (see ``docs/ARCHITECTURE.md``). Adding a
  hosted embedding provider later is a localised change here.

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
    # Reuse an Ollama instance for embeddings regardless of chat provider.
    return OllamaProvider(
        base_url=cfg.ollama_base_url,
        chat_model=cfg.ollama_chat_model,
        embed_model=cfg.ollama_embed_model,
        embedding_dim=cfg.embedding_dim,
        timeout_s=cfg.request_timeout_s,
        max_retries=cfg.max_retries,
        default_temperature=cfg.temperature,
    )


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
