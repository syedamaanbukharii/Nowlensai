"""Vector store abstraction.

Business logic (the hybrid retriever, the ingestion pipeline, the API) depends
only on this :class:`VectorStore` protocol — never on Qdrant directly — so the
backend is swappable via the ``services`` composition root. ``QdrantVectorStore``
is one implementation; the test suite provides an in-memory one.

The protocol models exactly the surface consumers use; Qdrant-specific extras
(e.g. ``scroll_all``) stay on the concrete class.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol, runtime_checkable

from nowlens.rag.types import RetrievedChunk


@runtime_checkable
class VectorStore(Protocol):
    """Async vector store contract used across retrieval, ingestion, and the API."""

    async def ensure_collection(self) -> None:
        """Create the underlying collection/index if it does not exist."""
        ...

    async def upsert(self, points: Sequence[dict[str, Any]]) -> int:
        """Insert/update points; returns the number written."""
        ...

    async def search(
        self,
        vector: Sequence[float],
        *,
        top_k: int,
        domains: Sequence[str] | None = None,
        tenant_id: str | None = None,
    ) -> list[RetrievedChunk]:
        """Nearest-neighbour search, optionally filtered by domain and tenant."""
        ...

    async def delete_document(self, document_id: str, *, tenant_id: str | None = None) -> None:
        """Delete all vectors for a document (optionally within a tenant)."""
        ...

    async def count(self) -> int:
        """Total number of stored vectors."""
        ...

    async def aclose(self) -> None:
        """Release any held resources (clients, connections)."""
        ...
