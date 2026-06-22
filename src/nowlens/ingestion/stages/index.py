"""Index stage.

Writes embedded chunks to both stores that power hybrid retrieval:

* **Qdrant** — vectors + payload (text, metadata) for semantic search.
* **PostgreSQL** — the ``document_chunks`` row (text + ``tsvector`` + domains)
  for lexical full-text search and as the source of truth for metadata.

The Postgres sink is injected as an optional repository so the embed→index path
is exercisable without a database (e.g. in tests / vector-only deployments).
"""

from __future__ import annotations

from typing import Protocol

from nowlens.core.logging import get_logger
from nowlens.ingestion.models import EmbeddedChunk
from nowlens.rag.vector_store import QdrantVectorStore

log = get_logger(__name__)


class ChunkSink(Protocol):
    """Persists chunk rows (implemented by the DB chunk repository)."""

    async def upsert_chunks(self, embedded: list[EmbeddedChunk]) -> int: ...


def _to_point(embedded: EmbeddedChunk) -> dict:
    chunk = embedded.chunk
    md = chunk.metadata
    return {
        "id": chunk.chunk_id,
        "vector": embedded.embedding,
        "payload": {
            "chunk_id": chunk.chunk_id,
            "document_id": chunk.document_id,
            "text": chunk.text,
            "title": md.get("title", ""),
            "source_url": md.get("source_url", ""),
            "domains": md.get("domains", []),
            "headings": md.get("headings", []),
            "has_code": md.get("has_code", False),
            "keywords": md.get("keywords", []),
            "index": chunk.index,
        },
    }


async def index_chunks(
    embedded: list[EmbeddedChunk],
    vector_store: QdrantVectorStore,
    *,
    sink: ChunkSink | None = None,
) -> int:
    if not embedded:
        return 0
    points = [_to_point(e) for e in embedded]
    written = await vector_store.upsert(points)
    if sink is not None:
        await sink.upsert_chunks(embedded)
    log.info("index.upserted", count=written, persisted_metadata=sink is not None)
    return written
