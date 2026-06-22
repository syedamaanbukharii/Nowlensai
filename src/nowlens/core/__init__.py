"""Core utilities: config, logging, tracing, errors, domain registry."""

from nowlens.core.config import Settings, get_settings
from nowlens.core.exceptions import NowLensError
from nowlens.core.logging import configure_logging, get_logger
from nowlens.core.tracing import get_trace_id, new_trace_id, set_trace_id

__all__ = [
    "NowLensError",
    "Settings",
    "configure_logging",
    "get_logger",
    "get_settings",
    "get_trace_id",
    "new_trace_id",
    "set_trace_id",
]
