"""End-to-end ingestion pipeline test, fully offline.

A fake crawler returns canned HTML, a fake embedder produces deterministic
vectors, and an in-memory store stands in for Qdrant — so the documented
crawl -> extract -> clean -> normalize -> chunk -> enrich -> dedup -> embed ->
validate -> index sequence runs with no external services.
"""

from __future__ import annotations

import pytest

from conftest import EMBED_DIM, FakeEmbeddingProvider, InMemoryVectorStore
from nowlens.core.config import IngestionSettings
from nowlens.ingestion.models import CrawlResult
from nowlens.ingestion.pipeline import IngestionPipeline

SAMPLE_HTML = """
<html lang="en"><head><title>ITSM Incident Management</title></head>
<body>
  <nav>home > docs > itsm — navigation chrome to be stripped out</nav>
  <main>
    <h1>Incident Management</h1>
    <p>Incident management coordinates the response to unplanned disruptions in
    IT service management. Use assignment rules to route incidents to the right
    support group, and link related problems for root-cause analysis.</p>
    <h2>Automation</h2>
    <p>Flow Designer automates incident handling with no-code flows, subflows,
    and actions, reducing manual effort across the incident lifecycle for teams.</p>
    <pre><code>var gr = new GlideRecord('incident');
gr.addQuery('active', true);
gr.query();</code></pre>
    <p>Copyright 2025 ACME Corp. All rights reserved.</p>
  </main>
</body></html>
"""


class FakeCrawler:
    def __init__(self, result: CrawlResult) -> None:
        self._result = result
        self.closed = False

    async def fetch(self, url: str) -> CrawlResult:
        return CrawlResult(
            url=url,
            status_code=self._result.status_code,
            html=self._result.html,
            content_type=self._result.content_type,
            error=self._result.error,
        )

    async def aclose(self) -> None:
        self.closed = True


def _pipeline(
    crawler: FakeCrawler,
    *,
    unchanged=None,
) -> IngestionPipeline:
    return IngestionPipeline(
        settings=IngestionSettings(),
        embedder=FakeEmbeddingProvider(),
        vector_store=InMemoryVectorStore(),  # type: ignore[arg-type]
        expected_dim=EMBED_DIM,
        tenant_id="tenant-test",
        crawler=crawler,  # type: ignore[arg-type]
        unchanged=unchanged,
        max_attempts=1,
    )


async def test_pipeline_happy_path() -> None:
    crawler = FakeCrawler(CrawlResult(url="u", status_code=200, html=SAMPLE_HTML))
    store = InMemoryVectorStore()
    pipeline = IngestionPipeline(
        settings=IngestionSettings(),
        embedder=FakeEmbeddingProvider(),
        vector_store=store,  # type: ignore[arg-type]
        expected_dim=EMBED_DIM,
        tenant_id="tenant-test",
        crawler=crawler,  # type: ignore[arg-type]
        max_attempts=1,
    )
    report = await pipeline.ingest_url("https://docs.example.com/itsm/incident")

    assert report.success is True
    assert report.error is None
    assert report.chunks_indexed > 0
    assert await store.count() == report.chunks_indexed
    stage_names = {s.name for s in report.stages}
    assert {"crawl", "extract", "clean", "normalize", "chunk", "enrich", "index"} <= stage_names
    await pipeline.aclose()
    assert crawler.closed is True


async def test_pipeline_crawl_failure_reported() -> None:
    crawler = FakeCrawler(CrawlResult(url="u", status_code=500, html="", error="boom"))
    pipeline = _pipeline(crawler)
    report = await pipeline.ingest_url("https://docs.example.com/bad")
    assert report.success is False
    assert report.error is not None
    assert report.chunks_indexed == 0


async def test_pipeline_incremental_skip() -> None:
    crawler = FakeCrawler(CrawlResult(url="u", status_code=200, html=SAMPLE_HTML))

    async def _always_unchanged(url: str, content_hash: str) -> bool:
        return True

    pipeline = _pipeline(crawler, unchanged=_always_unchanged)
    report = await pipeline.ingest_url("https://docs.example.com/itsm/incident")
    assert report.skipped is True
    assert report.success is True
    assert report.chunks_indexed == 0


async def test_pipeline_no_extractable_text() -> None:
    crawler = FakeCrawler(CrawlResult(url="u", status_code=200, html="<html><body></body></html>"))
    pipeline = _pipeline(crawler)
    report = await pipeline.ingest_url("https://docs.example.com/empty")
    assert report.success is False
    assert report.error is not None


async def test_pipeline_ingest_urls_batch() -> None:
    crawler = FakeCrawler(CrawlResult(url="u", status_code=200, html=SAMPLE_HTML))
    pipeline = _pipeline(crawler)
    reports = await pipeline.ingest_urls(
        ["https://docs.example.com/a", "https://docs.example.com/b"]
    )
    assert len(reports) == 2
    assert all(r.success for r in reports)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
