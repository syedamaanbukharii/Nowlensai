"""Langfuse integration hooks.

Tracing is optional. When ``NOWLENS_OBS_LANGFUSE_ENABLED`` is set and the
``langfuse`` extra is installed with credentials, traces are emitted; otherwise
every hook is a no-op so application code can call it unconditionally.

Usage::

    async with trace_span("chat", input={"query": q}) as span:
        ...
        span.update(output={"answer": answer})
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from nowlens.core.config import get_settings
from nowlens.core.logging import get_logger

log = get_logger(__name__)

_client: Any | None = None
_initialised = False


def _get_client() -> Any | None:
    """Lazily construct the Langfuse client if enabled + available."""

    global _client, _initialised
    if _initialised:
        return _client
    _initialised = True

    cfg = get_settings().observability
    if not cfg.langfuse_enabled:
        return None
    if not (cfg.langfuse_public_key and cfg.langfuse_secret_key):
        log.warning("langfuse.enabled_but_unconfigured")
        return None
    try:
        from langfuse import Langfuse

        _client = Langfuse(
            public_key=cfg.langfuse_public_key,
            secret_key=cfg.langfuse_secret_key,
            host=cfg.langfuse_host,
        )
        log.info("langfuse.initialised", host=cfg.langfuse_host)
    except Exception as exc:  # noqa: BLE001 - missing extra / bad creds must not crash
        log.warning("langfuse.init_failed", error=str(exc))
        _client = None
    return _client


class _NoOpSpan:
    def update(self, **_: Any) -> None: ...

    def end(self, **_: Any) -> None: ...


@asynccontextmanager
async def trace_span(name: str, **payload: Any):  # type: ignore[no-untyped-def]
    """Context manager yielding a span (real Langfuse span or a no-op)."""

    client = _get_client()
    if client is None:
        yield _NoOpSpan()
        return

    span = None
    try:
        span = client.trace(name=name, **payload)
        yield span
    finally:
        try:
            if span is not None:
                span.update()
            client.flush()
        except Exception as exc:  # noqa: BLE001
            log.debug("langfuse.flush_failed", error=str(exc))


def is_enabled() -> bool:
    return _get_client() is not None
