"""Ingestion pipeline orchestrator.

Runs the full documented sequence per URL::

    crawl → render → extract → clean → normalize → chunk → enrich
          → deduplicate → embed → index → validate → log → retry

Design notes:

* **Retry** — transient crawl failures (network errors / 5xx / empty body) are
  retried with backoff up to ``max_attempts``. Provider calls have their own
  retry inside the LLM/embedding clients.
* **Incremental** — an optional ``unchanged`` predicate lets the caller skip
  pages whose content hash matches a prior run, so re-crawls are cheap.
* **Validation gate** — only chunks passing :func:`validate_embedded` are
  indexed; the rest are reported, never silently dropped.
* Every stage records a :class:`StageOutcome` so the admin API/UI can show
  exactly where a document succeeded or failed.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime

from nowlens.core.config import IngestionSettings
from nowlens.core.logging import get_logger
from nowlens.ingestion.models import (
    CrawlResult,
    IngestionReport,
    StageOutcome,
    content_hash,
)
from nowlens.ingestion.stages.chunk import chunk_document
from nowlens.ingestion.stages.clean import AICleaner, rule_clean
from nowlens.ingestion.stages.crawl import Crawler
from nowlens.ingestion.stages.dedup import deduplicate
from nowlens.ingestion.stages.embed import embed_chunks
from nowlens.ingestion.stages.enrich import enrich_chunks
from nowlens.ingestion.stages.extract import extract
from nowlens.ingestion.stages.index import ChunkSink, index_chunks
from nowlens.ingestion.stages.normalize import normalize
from nowlens.ingestion.stages.render import Renderer
from nowlens.ingestion.stages.validate import validate_embedded
from nowlens.llm.base import EmbeddingProvider
from nowlens.rag.vector_store import QdrantVectorStore

log = get_logger(__name__)

UnchangedPredicate = Callable[[str, str], Awaitable[bool]]


class IngestionPipeline:
    def __init__(
        self,
        *,
        settings: IngestionSettings,
        embedder: EmbeddingProvider,
        vector_store: QdrantVectorStore,
        expected_dim: int,
        tenant_id: str,
        crawler: Crawler | None = None,
        renderer: Renderer | None = None,
        ai_cleaner: AICleaner | None = None,
        chunk_sink: ChunkSink | None = None,
        unchanged: UnchangedPredicate | None = None,
        max_attempts: int = 3,
    ) -> None:
        self._cfg = settings
        self._embedder = embedder
        self._vectors = vector_store
        self._expected_dim = expected_dim
        self._tenant_id = tenant_id
        self._crawler = crawler or Crawler(settings)
        self._renderer = renderer or Renderer(settings)
        self._ai_cleaner = ai_cleaner
        self._sink = chunk_sink
        self._unchanged = unchanged
        self._max_attempts = max_attempts

    async def ingest_url(self, url: str) -> IngestionReport:
        document_id = str(uuid.uuid4())
        report = IngestionReport(url=url, document_id=document_id, success=False)
        try:
            await self._run(url, report)
            report.success = report.error is None
        except Exception as exc:  # noqa: BLE001 - capture, never crash the worker
            report.error = str(exc)
            log.error("ingest.failed", url=url, error=str(exc))
        finally:
            report.finished_at = datetime.now(UTC)
        return report

    async def ingest_urls(self, urls: Sequence[str]) -> list[IngestionReport]:
        # The crawler enforces concurrency; gather keeps the pipeline simple.
        return await asyncio.gather(*(self.ingest_url(u) for u in urls))

    # -- internals ----------------------------------------------------------

    async def _run(self, url: str, report: IngestionReport) -> None:
        # 1-2. Crawl (+ optional render) with retry on transient failures.
        crawl_result = await self._crawl_with_retry(url, report)
        if crawl_result is None:
            return
        crawl_result = await self._renderer.render(crawl_result)

        # 3. Extract.
        doc = extract(crawl_result)
        if not doc.text.strip():
            report.record(StageOutcome("extract", ok=False, detail="no extractable text"))
            report.error = "no extractable text"
            return
        report.record(StageOutcome("extract", ok=True, items=len(doc.text)))

        # 4. Clean (rules always; AI optional).
        doc.text = rule_clean(doc.text)
        if self._cfg.ai_cleaning and self._ai_cleaner is not None:
            doc.text = await self._ai_cleaner.clean(doc.text)
            report.record(StageOutcome("clean", ok=True, detail="rule+ai"))
        else:
            report.record(StageOutcome("clean", ok=True, detail="rule"))

        # 5. Normalize.
        doc.text = normalize(doc.text)

        # Incremental skip check after we have canonical content.
        doc_hash = content_hash(doc.text)
        if self._unchanged is not None and await self._unchanged(url, doc_hash):
            report.skipped = True
            report.success = True
            report.record(StageOutcome("incremental", ok=True, detail="unchanged; skipped"))
            log.info("ingest.skipped_unchanged", url=url)
            return
        doc.metadata["content_hash"] = doc_hash
        report.record(StageOutcome("normalize", ok=True, items=len(doc.text)))

        # 6. Chunk.
        chunks = chunk_document(
            doc,
            report.document_id,
            chunk_size=self._cfg.chunk_size,
            overlap=self._cfg.chunk_overlap,
            min_chunk_chars=self._cfg.min_chunk_chars,
        )
        report.record(StageOutcome("chunk", ok=bool(chunks), items=len(chunks)))
        if not chunks:
            report.error = "no chunks produced"
            return

        # 7. Enrich.
        chunks = enrich_chunks(chunks)
        report.record(StageOutcome("enrich", ok=True, items=len(chunks)))

        # 8. Deduplicate.
        chunks, removed = deduplicate(chunks, max_distance=self._cfg.simhash_max_distance)
        report.duplicates_removed = removed
        report.record(StageOutcome("deduplicate", ok=True, items=len(chunks), detail=f"-{removed}"))

        # 9. Embed.
        embedded = await embed_chunks(chunks, self._embedder)
        report.record(StageOutcome("embed", ok=True, items=len(embedded)))

        # 11. Validate (before indexing).
        valid, problems = validate_embedded(embedded, expected_dim=self._expected_dim)
        report.record(
            StageOutcome(
                "validate", ok=not problems, items=len(valid), detail="; ".join(problems[:3])
            )
        )

        # 10. Index.
        indexed = await index_chunks(
            valid, self._vectors, tenant_id=self._tenant_id, sink=self._sink
        )
        report.chunks_indexed = indexed
        report.record(StageOutcome("index", ok=indexed > 0, items=indexed))

    async def _crawl_with_retry(self, url: str, report: IngestionReport) -> CrawlResult | None:
        last_error = "unknown"
        for attempt in range(1, self._max_attempts + 1):
            result = await self._crawler.fetch(url)
            if result.ok:
                report.record(
                    StageOutcome(
                        "crawl", ok=True, detail=f"attempt {attempt}", items=len(result.html)
                    )
                )
                return result
            last_error = result.error or f"status {result.status_code}"
            # Non-retryable: explicit robots disallow.
            if result.error and "robots" in result.error:
                break
            await asyncio.sleep(min(2**attempt, 10))
        report.record(StageOutcome("crawl", ok=False, detail=last_error))
        report.error = f"crawl failed: {last_error}"
        return None

    async def aclose(self) -> None:
        await self._crawler.aclose()
