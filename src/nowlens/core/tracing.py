"""Lightweight trace-id propagation.

A single ``trace_id`` is bound per request (in the API middleware) or per
background task, then made available to every log record and every downstream
component without threading it through function signatures.
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar

_trace_id: ContextVar[str | None] = ContextVar("nowlens_trace_id", default=None)


def new_trace_id() -> str:
    return uuid.uuid4().hex


def set_trace_id(trace_id: str | None = None) -> str:
    tid = trace_id or new_trace_id()
    _trace_id.set(tid)
    return tid


def get_trace_id() -> str | None:
    return _trace_id.get()
