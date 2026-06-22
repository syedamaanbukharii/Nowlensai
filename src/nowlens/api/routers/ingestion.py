"""Ingestion + document administration endpoints.

* ``POST /ingest`` submits URLs. With ``wait=true`` the pipeline runs inline and
  the per-URL reports are returned (handy for scripts and small jobs); otherwise
  a job row is created per URL and the work runs in a background task, returning
  the job ids to poll via ``GET /jobs``.
* ``GET /documents`` / ``GET /jobs`` power the admin console.
* ``DELETE /documents/{id}`` removes a document, its chunk rows (FK cascade), and
  its vectors from Qdrant.

Submitting/inspecting requires the ``operator`` role; deletion requires
``admin``.
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks

from nowlens.api.deps import IngestionPipelineDep, RequireAdmin, RequireOperator, SessionDep
from nowlens.api.schemas import (
    DocumentOut,
    IngestEnqueueResponse,
    IngestInlineResponse,
    IngestReportOut,
    IngestRequest,
    JobOut,
)
from nowlens.core.exceptions import NotFoundError
from nowlens.core.logging import get_logger
from nowlens.db.models import JobStatus
from nowlens.db.repositories import (
    AuditRepository,
    ChunkRepository,
    DocumentRepository,
    IngestionJobRepository,
)
from nowlens.ingestion.models import IngestionReport
from nowlens.observability.metrics import observe_ingestion
from nowlens.security.audit import audit_event
from nowlens.services import get_vector_store
from nowlens.workers.tasks import run_ingestion_job

log = get_logger(__name__)

router = APIRouter(tags=["ingestion"])


def _report_out(report: IngestionReport) -> IngestReportOut:
    return IngestReportOut(
        url=report.url,
        document_id=report.document_id or None,
        success=report.success,
        chunks_indexed=report.chunks_indexed,
        duplicates_removed=report.duplicates_removed,
        skipped=report.skipped,
        error=report.error,
        stages=[
            {"name": s.name, "ok": s.ok, "detail": s.detail, "items": s.items}
            for s in report.stages
        ],
    )


def _status_for(report: IngestionReport) -> JobStatus:
    if report.skipped:
        return JobStatus.SKIPPED
    return JobStatus.SUCCEEDED if report.success else JobStatus.FAILED


@router.post("/ingest", response_model=None)
async def ingest(
    payload: IngestRequest,
    background: BackgroundTasks,
    operator: RequireOperator,
    session: SessionDep,
    pipeline: IngestionPipelineDep,
) -> IngestInlineResponse | IngestEnqueueResponse:
    """Submit URLs for ingestion (inline when ``wait`` else enqueued)."""

    jobs = IngestionJobRepository(session)
    urls = [str(u) for u in payload.urls]
    job_ids = [(await jobs.create(url)).id for url in urls]

    await audit_event(
        actor=operator.email,
        action="ingestion.submit",
        detail={"urls": len(urls), "wait": payload.wait},
        repository=AuditRepository(session),
    )

    if payload.wait:
        reports: list[IngestReportOut] = []
        for job_id, url in zip(job_ids, urls, strict=True):
            await jobs.mark(job_id, status=JobStatus.RUNNING)
            report = await pipeline.ingest_url(url)
            await jobs.mark(
                job_id,
                status=_status_for(report),
                detail=report.error or ("skipped (unchanged)" if report.skipped else "ok"),
                chunks_indexed=report.chunks_indexed,
                duplicates_removed=report.duplicates_removed,
                stages=[
                    {"name": s.name, "ok": s.ok, "detail": s.detail, "items": s.items}
                    for s in report.stages
                ],
            )
            result = "skipped" if report.skipped else ("success" if report.success else "failed")
            observe_ingestion(result=result, chunks_indexed=report.chunks_indexed)
            reports.append(_report_out(report))
        return IngestInlineResponse(reports=reports)

    # Enqueue: run each job in a background task (its own DB session).
    for job_id, url in zip(job_ids, urls, strict=True):
        background.add_task(run_ingestion_job, job_id, url)
    return IngestEnqueueResponse(enqueued=urls, job_ids=job_ids)


@router.get("/documents", response_model=list[DocumentOut])
async def list_documents(
    _: RequireOperator, session: SessionDep, limit: int = 50
) -> list[DocumentOut]:
    rows = await DocumentRepository(session).list_recent(limit=min(max(limit, 1), 200))
    return [DocumentOut.model_validate(row) for row in rows]


@router.get("/jobs", response_model=list[JobOut])
async def list_jobs(_: RequireOperator, session: SessionDep, limit: int = 50) -> list[JobOut]:
    rows = await IngestionJobRepository(session).list_recent(limit=min(max(limit, 1), 200))
    return [JobOut.model_validate(row) for row in rows]


@router.delete("/documents/{document_id}", status_code=204)
async def delete_document(document_id: str, admin: RequireAdmin, session: SessionDep) -> None:
    documents = DocumentRepository(session)
    if await documents.get(document_id) is None:
        raise NotFoundError("Document not found")

    await ChunkRepository(session).delete_for_document(document_id)
    await documents.delete(document_id)
    # Remove vectors from Qdrant (best-effort; the metadata is already gone).
    try:
        await get_vector_store().delete_document(document_id)
    except Exception as exc:  # noqa: BLE001 - log, the row deletion already succeeded
        log.warning("ingestion.vector_delete_failed", document_id=document_id, error=str(exc))

    await audit_event(
        actor=admin.email,
        action="ingestion.delete_document",
        target=document_id,
        repository=AuditRepository(session),
    )
