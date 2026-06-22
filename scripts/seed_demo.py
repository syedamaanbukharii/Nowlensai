#!/usr/bin/env python
"""Seed a running NowLens stack with demo content and show retrieval working.

Ingests the local ``data/sample/sample_page.html`` fixture into the configured
Qdrant collection (using the configured embedding provider), then runs a couple
of vector searches so you can see grounded retrieval end-to-end. Requires the
embedding provider (e.g. Ollama) and Qdrant to be reachable — run it after
``docker compose up`` and ``nowlens bootstrap``.

Database/Postgres is NOT required: this seeds the vector store only.

Usage:
    python scripts/seed_demo.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

# Make `src/` importable when run directly from the repo root.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from nowlens.core.config import get_settings  # noqa: E402
from nowlens.ingestion.models import CrawlResult  # noqa: E402
from nowlens.ingestion.pipeline import IngestionPipeline  # noqa: E402
from nowlens.llm.factory import close_providers, get_embedding_provider  # noqa: E402
from nowlens.services import get_vector_store  # noqa: E402

SAMPLE = ROOT / "data" / "sample" / "sample_page.html"
DEMO_URL = "https://docs.example.com/itsm/incident-management"
QUERIES = [
    "how do I route incidents to the right group",
    "automate the incident lifecycle",
]


class LocalFileCrawler:
    """A crawler that serves a local HTML file instead of hitting the network."""

    def __init__(self, html: str) -> None:
        self._html = html

    async def fetch(self, url: str) -> CrawlResult:
        return CrawlResult(url=url, status_code=200, html=self._html)

    async def aclose(self) -> None:
        return None


async def main() -> int:
    if not SAMPLE.exists():
        print(f"Sample fixture not found: {SAMPLE}", file=sys.stderr)
        return 1

    settings = get_settings()
    store = get_vector_store()
    embedder = get_embedding_provider()

    print("==> Ensuring Qdrant collection exists")
    await store.ensure_collection()

    print(f"==> Ingesting sample document as {DEMO_URL}")
    pipeline = IngestionPipeline(
        settings=settings.ingestion,
        embedder=embedder,
        vector_store=store,
        expected_dim=settings.llm.embedding_dim,
        crawler=LocalFileCrawler(SAMPLE.read_text(encoding="utf-8")),
        max_attempts=1,
    )
    report = await pipeline.ingest_url(DEMO_URL)
    await pipeline.aclose()
    print(
        json.dumps(
            {
                "success": report.success,
                "chunks_indexed": report.chunks_indexed,
                "duplicates_removed": report.duplicates_removed,
                "error": report.error,
                "stages": [s.name for s in report.stages],
            },
            indent=2,
        )
    )

    if not report.success:
        return 1

    print("\n==> Retrieval demo")
    for query in QUERIES:
        vector = await embedder.embed_one(query)
        hits = await store.search(vector, top_k=3)
        print(f"\nQ: {query}")
        for hit in hits:
            print(f"  - [{hit.score:.3f}] {hit.title}")

    await store.aclose()
    await close_providers()
    print("\n==> Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
