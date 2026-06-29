"""Optional arq worker for out-of-process ingestion.

Requires the ``worker`` extra (``pip install 'nowlens-ai[worker]'``) and a Redis
instance. ``arq`` is imported defensively so the rest of the package — and the
API's in-process background-task path — never depends on it; the module still
imports cleanly when arq is absent.

Run it with::

    arq nowlens.workers.arq_worker.WorkerSettings

The API can enqueue with arq instead of in-process tasks by creating a pool and
calling ``await pool.enqueue_job("ingest", job_id, url)`` — see DEPLOYMENT.md.
"""

from __future__ import annotations

from typing import Any

from nowlens.core.config import get_settings
from nowlens.core.logging import configure_logging, get_logger
from nowlens.workers.tasks import run_ingestion_job

log = get_logger(__name__)

try:  # arq is an optional extra; the module must import without it.
    from arq.connections import RedisSettings
except Exception:  # noqa: BLE001 - any import failure means "arq not available"
    RedisSettings = None


async def ingest(ctx: dict[str, Any], job_id: str, url: str, tenant_id: str) -> str:
    """arq task entrypoint: process one ingestion job."""

    report = await run_ingestion_job(job_id, url, tenant_id)
    return "skipped" if report.skipped else ("success" if report.success else "failed")


async def _on_startup(ctx: dict[str, Any]) -> None:
    configure_logging()
    log.info("arq.worker_started")


async def _on_shutdown(ctx: dict[str, Any]) -> None:
    from nowlens.llm.factory import close_providers
    from nowlens.services import reset_singletons

    await close_providers()
    await reset_singletons()
    log.info("arq.worker_stopped")


class WorkerSettings:
    """arq ``WorkerSettings`` (attributes are read by the arq CLI)."""

    functions = [ingest]
    on_startup = _on_startup
    on_shutdown = _on_shutdown
    max_jobs = 4
    job_timeout = 600

    if RedisSettings is not None:  # set only when arq is installed
        redis_settings = RedisSettings.from_dsn(str(get_settings().redis_url))
