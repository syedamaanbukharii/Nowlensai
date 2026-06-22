"""Application configuration.

All runtime configuration is funnelled through :class:`Settings`, which reads
from environment variables (and an optional ``.env`` file). Nothing in the
codebase reads ``os.environ`` directly — call :func:`get_settings` instead so
that configuration is validated, typed, and cached in one place.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Literal, cast

from pydantic import Field, PostgresDsn, RedisDsn, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

LLMProviderName = Literal["ollama", "groq"]
Environment = Literal["development", "staging", "production"]


class LLMSettings(BaseSettings):
    """Provider-agnostic LLM configuration.

    ``provider`` selects the *default* chat/embedding backend. Business logic
    never references a concrete provider — it asks the factory for whatever
    ``provider`` resolves to. Adding a provider is a config + factory change,
    not an application change.
    """

    model_config = SettingsConfigDict(env_prefix="NOWLENS_LLM_", extra="ignore")

    provider: LLMProviderName = "ollama"
    request_timeout_s: float = 120.0
    max_retries: int = 3
    temperature: float = 0.1

    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    ollama_chat_model: str = "llama3.1:8b"
    ollama_embed_model: str = "nomic-embed-text"

    # Groq (OpenAI-compatible endpoint)
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_api_key: str | None = None
    groq_chat_model: str = "llama-3.1-70b-versatile"

    # Embeddings dimensionality — must match the embedding model and the
    # Qdrant collection vector size. nomic-embed-text => 768.
    embedding_dim: int = 768


class RAGSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NOWLENS_RAG_", extra="ignore")

    collection: str = "nowlens_docs"
    # Hybrid retrieval fan-out before fusion.
    vector_top_k: int = 20
    lexical_top_k: int = 20
    # Reciprocal-rank-fusion constant.
    rrf_k: int = 60
    # How many fused candidates to rerank.
    rerank_candidates: int = 20
    # Final number of chunks handed to the generator.
    final_top_k: int = 6
    # Enable cross-encoder reranking (requires the ``rerank`` extra).
    use_cross_encoder: bool = False
    cross_encoder_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    # Context compression: keep sentences scoring above this fraction of the
    # top sentence score within a chunk.
    compression_ratio: float = 0.6
    compression_enabled: bool = True


class IngestionSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NOWLENS_INGEST_", extra="ignore")

    user_agent: str = "NowLensBot/0.1 (+https://example.com/nowlens)"
    request_timeout_s: float = 30.0
    max_concurrency: int = 5
    crawl_delay_s: float = 0.5
    # Respect robots.txt during crawling.
    respect_robots: bool = True
    # Chunking (token-approximate via characters).
    chunk_size: int = 1200
    chunk_overlap: int = 200
    min_chunk_chars: int = 120
    # Near-duplicate threshold: max Hamming distance between 64-bit simhashes.
    simhash_max_distance: int = 3
    # Enable the JS-render stage (requires the ``render`` extra + browsers).
    render_javascript: bool = False
    # Enable AI-assisted cleaning (uses the configured LLM).
    ai_cleaning: bool = True


class SecuritySettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NOWLENS_SECURITY_", extra="ignore")

    jwt_secret: str = "change-me-in-production-this-is-not-secret"
    jwt_algorithm: str = "HS256"
    access_token_ttl_min: int = 30
    refresh_token_ttl_days: int = 14
    # Per-identity request budget for the sliding-window limiter.
    rate_limit_per_minute: int = 60
    rate_limit_burst: int = 20
    # Maximum accepted size for free-text user input (defence in depth).
    max_input_chars: int = 8000


class ObservabilitySettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NOWLENS_OBS_", extra="ignore")

    log_level: str = "INFO"
    log_json: bool = True
    # Langfuse is optional; hooks are no-ops unless configured + extra installed.
    langfuse_enabled: bool = False
    langfuse_host: str = "https://cloud.langfuse.com"
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None


class Settings(BaseSettings):
    """Root settings object aggregating every configuration group."""

    model_config = SettingsConfigDict(
        env_prefix="NOWLENS_",
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )

    environment: Environment = "development"
    app_name: str = "NowLens AI"
    debug: bool = False

    # Comma-separated list of allowed CORS origins. ``NoDecode`` keeps
    # pydantic-settings from trying to JSON-decode the env value first, so the
    # ``_split_origins`` validator below receives the raw comma-separated string.
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000"]
    )

    database_url: PostgresDsn = Field(
        default=cast(PostgresDsn, "postgresql+asyncpg://nowlens:nowlens@localhost:5432/nowlens")
    )
    redis_url: RedisDsn = Field(default=cast(RedisDsn, "redis://localhost:6379/0"))
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str | None = None

    llm: LLMSettings = Field(default_factory=LLMSettings)
    rag: RAGSettings = Field(default_factory=RAGSettings)
    ingestion: IngestionSettings = Field(default_factory=IngestionSettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    observability: ObservabilitySettings = Field(default_factory=ObservabilitySettings)

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide, cached settings instance."""

    return Settings()
