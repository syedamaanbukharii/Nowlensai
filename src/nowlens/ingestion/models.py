"""Data structures passed between ingestion stages."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


def _now() -> datetime:
    return datetime.now(UTC)


def content_hash(text: str) -> str:
    """Stable hash used for incremental ingestion + exact-duplicate detection."""

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class CrawlResult:
    url: str
    status_code: int
    html: str
    content_type: str = "text/html"
    rendered: bool = False
    fetched_at: datetime = field(default_factory=_now)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and 200 <= self.status_code < 300 and bool(self.html)


@dataclass
class ExtractedDocument:
    url: str
    title: str
    text: str
    language: str = "en"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Chunk:
    chunk_id: str
    document_id: str
    text: str
    index: int
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class EmbeddedChunk:
    chunk: Chunk
    embedding: list[float]


@dataclass
class StageOutcome:
    name: str
    ok: bool
    detail: str = ""
    items: int = 0


@dataclass
class IngestionReport:
    url: str
    document_id: str
    success: bool
    stages: list[StageOutcome] = field(default_factory=list)
    chunks_indexed: int = 0
    duplicates_removed: int = 0
    skipped: bool = False
    error: str | None = None
    started_at: datetime = field(default_factory=_now)
    finished_at: datetime | None = None

    def record(self, outcome: StageOutcome) -> None:
        self.stages.append(outcome)
