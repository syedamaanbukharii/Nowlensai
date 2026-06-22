"""Observability: Prometheus metrics + optional Langfuse tracing."""

from nowlens.observability.langfuse import is_enabled, trace_span
from nowlens.observability.metrics import (
    observe_agent_run,
    observe_ingestion,
    observe_retrieval,
    record_tokens,
    render_latest,
)

__all__ = [
    "is_enabled",
    "observe_agent_run",
    "observe_ingestion",
    "observe_retrieval",
    "record_tokens",
    "render_latest",
    "trace_span",
]
