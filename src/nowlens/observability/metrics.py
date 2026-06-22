"""Prometheus metrics.

A single registry holds the platform's metrics so the ``/metrics`` endpoint can
expose them. Helper functions wrap the metric objects so call sites stay terse
and consistent. All metrics are safe to import even when nothing is scraping.
"""

from __future__ import annotations

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
)

REGISTRY = CollectorRegistry()

# -- HTTP ------------------------------------------------------------------
HTTP_REQUESTS = Counter(
    "nowlens_http_requests_total",
    "HTTP requests processed.",
    labelnames=("method", "path", "status"),
    registry=REGISTRY,
)
HTTP_LATENCY = Histogram(
    "nowlens_http_request_seconds",
    "HTTP request latency in seconds.",
    labelnames=("method", "path"),
    registry=REGISTRY,
)

# -- Retrieval -------------------------------------------------------------
RETRIEVAL_LATENCY = Histogram(
    "nowlens_retrieval_seconds",
    "End-to-end hybrid retrieval latency in seconds.",
    registry=REGISTRY,
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)
RETRIEVAL_CHUNKS = Histogram(
    "nowlens_retrieval_chunks",
    "Number of chunks returned by retrieval.",
    registry=REGISTRY,
    buckets=(0, 1, 2, 4, 6, 8, 12, 20),
)

# -- Agents ----------------------------------------------------------------
AGENT_RUNS = Counter(
    "nowlens_agent_runs_total",
    "Agent graph runs by resolved intent and outcome.",
    labelnames=("intent", "outcome"),
    registry=REGISTRY,
)
AGENT_LATENCY = Histogram(
    "nowlens_agent_run_seconds",
    "Agent graph end-to-end latency in seconds.",
    labelnames=("intent",),
    registry=REGISTRY,
)

# -- Ingestion -------------------------------------------------------------
INGESTION_DOCS = Counter(
    "nowlens_ingestion_documents_total",
    "Documents processed by the ingestion pipeline by result.",
    labelnames=("result",),  # success | skipped | failed
    registry=REGISTRY,
)
INGESTION_CHUNKS = Counter(
    "nowlens_ingestion_chunks_indexed_total",
    "Chunks indexed by the ingestion pipeline.",
    registry=REGISTRY,
)

# -- LLM -------------------------------------------------------------------
LLM_TOKENS = Counter(
    "nowlens_llm_tokens_total",
    "LLM tokens consumed by provider and kind.",
    labelnames=("provider", "kind"),  # kind: prompt | completion
    registry=REGISTRY,
)


def observe_retrieval(latency_seconds: float, chunk_count: int) -> None:
    RETRIEVAL_LATENCY.observe(latency_seconds)
    RETRIEVAL_CHUNKS.observe(chunk_count)


def observe_agent_run(intent: str, *, latency_seconds: float, ok: bool) -> None:
    AGENT_RUNS.labels(intent=intent or "unknown", outcome="ok" if ok else "error").inc()
    AGENT_LATENCY.labels(intent=intent or "unknown").observe(latency_seconds)


def observe_ingestion(*, result: str, chunks_indexed: int = 0) -> None:
    INGESTION_DOCS.labels(result=result).inc()
    if chunks_indexed:
        INGESTION_CHUNKS.inc(chunks_indexed)


def record_tokens(provider: str, *, prompt: int = 0, completion: int = 0) -> None:
    if prompt:
        LLM_TOKENS.labels(provider=provider, kind="prompt").inc(prompt)
    if completion:
        LLM_TOKENS.labels(provider=provider, kind="completion").inc(completion)


def render_latest() -> tuple[bytes, str]:
    """Return ``(payload, content_type)`` for the metrics endpoint."""

    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST
