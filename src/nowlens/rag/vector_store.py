"""Qdrant vector store.

Thin async wrapper around ``qdrant-client`` covering exactly what the platform
needs: collection bootstrap, idempotent upsert of embedded chunks (with rich
payloads for metadata filtering), filtered vector search, scroll (for building
the in-memory BM25 index), and deletion by document.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from qdrant_client import AsyncQdrantClient, models

from nowlens.core.exceptions import RetrievalError
from nowlens.core.logging import get_logger
from nowlens.rag.types import RetrievedChunk

log = get_logger(__name__)


class QdrantVectorStore:
    def __init__(
        self,
        *,
        url: str,
        collection: str,
        vector_size: int,
        api_key: str | None = None,
    ) -> None:
        self._client = AsyncQdrantClient(url=url, api_key=api_key)
        self._collection = collection
        self._vector_size = vector_size

    async def ensure_collection(self) -> None:
        """Create the collection if missing (cosine distance)."""

        try:
            exists = await self._client.collection_exists(self._collection)
            if not exists:
                await self._client.create_collection(
                    collection_name=self._collection,
                    vectors_config=models.VectorParams(
                        size=self._vector_size,
                        distance=models.Distance.COSINE,
                    ),
                )
                # Payload indexes that we filter on frequently.
                await self._client.create_payload_index(
                    self._collection, "domains", models.PayloadSchemaType.KEYWORD
                )
                await self._client.create_payload_index(
                    self._collection, "document_id", models.PayloadSchemaType.KEYWORD
                )
                log.info("qdrant.collection_created", collection=self._collection)
        except Exception as exc:
            raise RetrievalError(f"Qdrant ensure_collection failed: {exc}") from exc

    async def upsert(self, points: Sequence[dict[str, Any]]) -> int:
        """Upsert points.

        Each point dict must contain ``id`` (uuid/int), ``vector`` (list[float]),
        and ``payload`` (dict). Returns the number of points written.
        """

        if not points:
            return 0
        try:
            await self._client.upsert(
                collection_name=self._collection,
                points=[
                    models.PointStruct(id=p["id"], vector=p["vector"], payload=p["payload"])
                    for p in points
                ],
                wait=True,
            )
        except Exception as exc:
            raise RetrievalError(f"Qdrant upsert failed: {exc}") from exc
        return len(points)

    async def search(
        self,
        vector: Sequence[float],
        *,
        top_k: int,
        domains: Sequence[str] | None = None,
    ) -> list[RetrievedChunk]:
        query_filter = None
        if domains:
            query_filter = models.Filter(
                must=[
                    models.FieldCondition(
                        key="domains",
                        match=models.MatchAny(any=list(domains)),
                    )
                ]
            )
        try:
            hits = await self._client.search(  # type: ignore[attr-defined]
                collection_name=self._collection,
                query_vector=list(vector),
                limit=top_k,
                query_filter=query_filter,
                with_payload=True,
            )
        except Exception as exc:
            raise RetrievalError(f"Qdrant search failed: {exc}") from exc

        results: list[RetrievedChunk] = []
        for hit in hits:
            payload = hit.payload or {}
            results.append(
                RetrievedChunk(
                    chunk_id=str(payload.get("chunk_id", hit.id)),
                    text=payload.get("text", ""),
                    score=float(hit.score),
                    document_id=str(payload.get("document_id", "")),
                    source_url=payload.get("source_url", ""),
                    title=payload.get("title", ""),
                    domains=list(payload.get("domains", [])),
                    metadata={
                        k: v
                        for k, v in payload.items()
                        if k
                        not in {"text", "chunk_id", "document_id", "source_url", "title", "domains"}
                    },
                    retriever="qdrant",
                )
            )
        return results

    async def scroll_all(self, *, batch: int = 256) -> list[RetrievedChunk]:
        """Stream every stored chunk (used to build the in-memory BM25 index)."""

        results: list[RetrievedChunk] = []
        offset: Any = None
        try:
            while True:
                points, offset = await self._client.scroll(
                    collection_name=self._collection,
                    limit=batch,
                    offset=offset,
                    with_payload=True,
                    with_vectors=False,
                )
                for point in points:
                    payload = point.payload or {}
                    results.append(
                        RetrievedChunk(
                            chunk_id=str(payload.get("chunk_id", point.id)),
                            text=payload.get("text", ""),
                            score=0.0,
                            document_id=str(payload.get("document_id", "")),
                            source_url=payload.get("source_url", ""),
                            title=payload.get("title", ""),
                            domains=list(payload.get("domains", [])),
                        )
                    )
                if offset is None:
                    break
        except Exception as exc:
            raise RetrievalError(f"Qdrant scroll failed: {exc}") from exc
        return results

    async def delete_document(self, document_id: str) -> None:
        try:
            await self._client.delete(
                collection_name=self._collection,
                points_selector=models.FilterSelector(
                    filter=models.Filter(
                        must=[
                            models.FieldCondition(
                                key="document_id",
                                match=models.MatchValue(value=document_id),
                            )
                        ]
                    )
                ),
                wait=True,
            )
        except Exception as exc:
            raise RetrievalError(f"Qdrant delete failed: {exc}") from exc

    async def count(self) -> int:
        try:
            result = await self._client.count(self._collection, exact=True)
            return int(result.count)
        except Exception as exc:
            raise RetrievalError(f"Qdrant count failed: {exc}") from exc

    async def aclose(self) -> None:
        await self._client.close()
