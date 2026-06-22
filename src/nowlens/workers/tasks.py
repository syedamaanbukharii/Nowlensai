"""Background ingestion job execution.

Ingestion is potentially long-running (network crawl + embedding), so the API
never runs it inline by default. :func:`run_ingestion_job` is the single source
of truth for "process this URL and record the outcome"; it is invoked two ways:

* **In-process** via FastAPI ``BackgroundTasks`` (zero extra infrastructure —
  the default), and
* **Out-of-process** by the optional :mod:`nowlens.workers.arq_worker` (the
  ``worker`` extra), which lets ingestion scale independently of the API.

The job opens its *own* database session via :func:`session_scope` because the
request-scoped session is already closed by the time a background task runs.
"""

from __future__ import annotations

from nowlens.core.logging import get_logger
from nowlens.db.models import JobStatus
from nowlens.db.repositories import IngestionJobRepository
from nowlens.db.session import session_scope
from nowlens.ingestion.models import IngestionReport, StageOutcome
from nowlens.observability.metrics import observe_ingestion
from nowlens.services import build_ingestion_pipeline

log = get_logger(__name__)


def _stage_dict(stage: StageOutcome) -> dict[str, object]:
    return {"name": stage.name, "ok": stage.ok, "detail": stage.detail, "items": stage.items}


def _status_for(report: IngestionReport) -> JobStatus:
    if report.skipped:
        return JobStatus.SKIPPED
    return JobStatus.SUCCEEDED if report.success else JobStatus.FAILED


async def run_ingestion_job(job_id: str, url: str) -> IngestionReport:
    """Run the ingestion pipeline for ``url`` and persist the job outcome."""

    async with session_scope() as session:
        jobs = IngestionJobRepository(session)
        await jobs.mark(job_id, status=JobStatus.RUNNING)

    # Fresh session for the actual work so the RUNNING marker is committed first
    # (gives the admin UI immediate feedback while a long crawl proceeds).
    async with session_scope() as session:
        pipeline = build_ingestion_pipeline(session)
        try:
            report = await pipeline.ingest_url(url)
        finally:
            await pipeline.aclose()

        jobs = IngestionJobRepository(session)
        await jobs.mark(
            job_id,
            status=_status_for(report),
            detail=report.error or ("skipped (unchanged)" if report.skipped else "ok"),
            chunks_indexed=report.chunks_indexed,
            duplicates_removed=report.duplicates_removed,
            stages=[_stage_dict(s) for s in report.stages],
        )

    result = "skipped" if report.skipped else ("success" if report.success else "failed")
    observe_ingestion(result=result, chunks_indexed=report.chunks_indexed)
    log.info(
        "worker.ingestion_job",
        job_id=job_id,
        url=url,
        status=result,
        chunks_indexed=report.chunks_indexed,
    )
    return report
