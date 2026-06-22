"""Structured logging setup.

We configure :mod:`structlog` to emit either JSON (production) or a colourised
console renderer (development), and inject the active ``trace_id`` into every
event. Standard-library logging is routed through structlog so third-party
libraries share the same format.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

from nowlens.core.config import get_settings
from nowlens.core.tracing import get_trace_id

_configured = False


def _add_trace_id(_: Any, __: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    trace_id = get_trace_id()
    if trace_id is not None:
        event_dict.setdefault("trace_id", trace_id)
    return event_dict


def configure_logging() -> None:
    """Idempotently configure logging for the whole process."""

    global _configured
    if _configured:
        return

    settings = get_settings().observability
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        _add_trace_id,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    renderer: Any = (
        structlog.processors.JSONRenderer()
        if settings.log_json
        else structlog.dev.ConsoleRenderer(colors=True)
    )

    # Logs go to stderr so that stdout is reserved for program/CLI output
    # (e.g. machine-readable JSON emitted by the ``nowlens`` commands). This is
    # 12-factor friendly: a process emits diagnostics on stderr and results on
    # stdout, so piping ``nowlens ingest ... | jq`` never breaks.
    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )

    # Route stdlib logging through the same stderr stream + level.
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stderr,
        level=level,
        force=True,
    )
    _configured = True


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    if not _configured:
        configure_logging()
    return structlog.get_logger(name)
