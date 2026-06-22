"""Shared retrieval types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RetrievedChunk:
    """A chunk returned by a retriever, carrying provenance + score."""

    chunk_id: str
    text: str
    score: float
    document_id: str = ""
    source_url: str = ""
    title: str = ""
    domains: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    # Populated by rerankers / fusion for observability.
    retriever: str = ""

    def copy_with_score(self, score: float, *, retriever: str | None = None) -> RetrievedChunk:
        return RetrievedChunk(
            chunk_id=self.chunk_id,
            text=self.text,
            score=score,
            document_id=self.document_id,
            source_url=self.source_url,
            title=self.title,
            domains=list(self.domains),
            metadata=dict(self.metadata),
            retriever=retriever if retriever is not None else self.retriever,
        )


@dataclass
class Citation:
    """A numbered citation a UI can render alongside an answer."""

    index: int
    chunk_id: str
    document_id: str
    title: str
    source_url: str
    snippet: str


@dataclass
class RetrievalResult:
    chunks: list[RetrievedChunk]
    citations: list[Citation]
    context: str
    query: str
    metrics: dict[str, Any] = field(default_factory=dict)
