"""Audit logging.

A thin helper that emits a structured audit event to the logs (always) and
persists it to the ``audit_logs`` table when a repository is supplied. Persisting
is best-effort: an audit-store failure must never break the audited action, so
write errors are logged and swallowed.
"""

from __future__ import annotations

from typing import Any

from nowlens.core.logging import get_logger
from nowlens.core.tracing import get_trace_id
from nowlens.db.repositories import AuditRepository

log = get_logger("nowlens.audit")


async def audit_event(
    *,
    actor: str,
    action: str,
    target: str = "",
    detail: dict[str, Any] | None = None,
    repository: AuditRepository | None = None,
) -> None:
    """Record an audit event to logs and (optionally) the database."""

    trace_id = get_trace_id()
    log.info("audit", actor=actor, action=action, target=target, detail=detail or {})
    if repository is not None:
        try:
            await repository.record(
                actor=actor, action=action, target=target, detail=detail or {}, trace_id=trace_id
            )
        except Exception as exc:  # noqa: BLE001 - audit must not break the request
            log.warning("audit.persist_failed", action=action, error=str(exc))
