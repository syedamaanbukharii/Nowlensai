"""Automated documentation ingestion.

The :class:`~nowlens.ingestion.pipeline.IngestionPipeline` runs the full
documented sequence (crawl → render → extract → clean → normalize → chunk →
enrich → deduplicate → embed → index → validate → log → retry). Individual
stages are importable for reuse by the agent layer and tests.
"""

from nowlens.ingestion.models import (
    Chunk,
    CrawlResult,
    EmbeddedChunk,
    ExtractedDocument,
    IngestionReport,
    StageOutcome,
    content_hash,
)
from nowlens.ingestion.pipeline import IngestionPipeline

__all__ = [
    "Chunk",
    "CrawlResult",
    "EmbeddedChunk",
    "ExtractedDocument",
    "IngestionPipeline",
    "IngestionReport",
    "StageOutcome",
    "content_hash",
]
