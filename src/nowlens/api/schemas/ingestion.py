"""Ingestion, configuration, and health schemas."""

from __future__ import annotations

from typing import Any

from pydantic import AnyHttpUrl, BaseModel, Field


class IngestRequest(BaseModel):
    """Submit one or more URLs for ingestion.

    ``wait`` runs the pipeline inline and returns the report (useful for small
    jobs / scripts); otherwise the work is enqueued and a job id is returned.
    """

    urls: list[AnyHttpUrl] = Field(min_length=1, max_length=200)
    wait: bool = False


class IngestEnqueueResponse(BaseModel):
    enqueued: list[str]
    job_ids: list[str]


class IngestReportOut(BaseModel):
    url: str
    document_id: str | None
    success: bool
    chunks_indexed: int
    duplicates_removed: int
    skipped: bool
    error: str | None = None
    stages: list[dict[str, Any]] = Field(default_factory=list)


class IngestInlineResponse(BaseModel):
    reports: list[IngestReportOut]


class HealthResponse(BaseModel):
    status: str
    version: str
    environment: str


class ReadinessComponent(BaseModel):
    name: str
    ok: bool
    detail: str = ""


class ReadinessResponse(BaseModel):
    ready: bool
    components: list[ReadinessComponent]


class ConfigResponse(BaseModel):
    """Redacted, read-only view of effective configuration.

    Secrets (JWT secret, API keys, DB credentials) are never included.
    """

    environment: str
    version: str
    llm_provider: str
    chat_model: str
    embedding_model: str
    embedding_dim: int
    vector_collection: str
    final_top_k: int
    rerank_cross_encoder: bool
    ai_cleaning: bool
    rate_limit_per_minute: int
    langfuse_enabled: bool
    supported_domains: list[str]
