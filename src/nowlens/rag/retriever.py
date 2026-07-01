"""Hybrid retriever — the public RAG entry point.

Pipeline::

    query
      ├─ embed ──────────────▶ Qdrant vector search ┐
      └─ (raw) ──────────────▶ lexical search        ├─▶ RRF fusion
                                                      ┘
        ▶ rerank ▶ context compression ▶ citations ▶ RetrievalResult

Each stage is independently testable; this class only wires them and records
metrics (latency + per-stage candidate counts) for observability.
"""

from __future__ import annotations

import time
from collections.abc import Sequence

from nowlens.core.config import RAGSettings
from nowlens.core.logging import get_logger
from nowlens.llm.base import EmbeddingProvider
from nowlens.rag.base import VectorStore
from nowlens.rag.citations import build_citations, format_context
from nowlens.rag.compression import compress_chunks
from nowlens.rag.fusion import reciprocal_rank_fusion
from nowlens.rag.lexical import LexicalRetriever
from nowlens.rag.reranker import Reranker
from nowlens.rag.types import RetrievalResult

log = get_logger(__name__)


class HybridRetriever:
    def __init__(
        self,
        *,
        embedder: EmbeddingProvider,
        vector_store: VectorStore,
        lexical: LexicalRetriever,
        reranker: Reranker,
        settings: RAGSettings,
        tenant_id: str | None = None,
    ) -> None:
        self._embedder = embedder
        self._vectors = vector_store
        self._lexical = lexical
        self._reranker = reranker
        self._cfg = settings
        # Bound at construction (request scope) so every retrieval is scoped to
        # the caller's tenant without the call sites having to pass it through.
        self._tenant_id = tenant_id

    async def retrieve(
        self,
        query: str,
        *,
        domains: Sequence[str] | None = None,
        final_top_k: int | None = None,
    ) -> RetrievalResult:
        started = time.perf_counter()
        metrics: dict[str, object] = {}

        # 1. Vector search.
        t0 = time.perf_counter()
        query_vector = await self._embedder.embed_one(query)
        metrics["embed_ms"] = round((time.perf_counter() - t0) * 1000, 2)

        t0 = time.perf_counter()
        vector_hits = await self._vectors.search(
            query_vector,
            top_k=self._cfg.vector_top_k,
            domains=domains,
            tenant_id=self._tenant_id,
        )
        metrics["vector_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        metrics["vector_hits"] = len(vector_hits)

        # 2. Lexical search.
        t0 = time.perf_counter()
        lexical_hits = await self._lexical.search(
            query, top_k=self._cfg.lexical_top_k, domains=domains, tenant_id=self._tenant_id
        )
        metrics["lexical_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        metrics["lexical_hits"] = len(lexical_hits)

        # 3. Fuse.
        fused = reciprocal_rank_fusion(
            [vector_hits, lexical_hits],
            k=self._cfg.rrf_k,
            top_k=self._cfg.rerank_candidates,
        )
        metrics["fused_candidates"] = len(fused)

        if not fused:
            return RetrievalResult(
                chunks=[], citations=[], context="", query=query, metrics=metrics
            )

        # 4. Rerank.
        t0 = time.perf_counter()
        final_k = final_top_k or self._cfg.final_top_k
        reranked = await self._reranker.rerank(query, fused, top_k=final_k)
        metrics["rerank_ms"] = round((time.perf_counter() - t0) * 1000, 2)

        # 5. Context compression.
        if self._cfg.compression_enabled:
            reranked = compress_chunks(reranked, query, ratio=self._cfg.compression_ratio)

        # 6. Citations + context.
        citations, chunk_to_index = build_citations(reranked)
        context = format_context(reranked, chunk_to_index)

        metrics["final_chunks"] = len(reranked)
        metrics["total_ms"] = round((time.perf_counter() - started) * 1000, 2)
        log.info("rag.retrieve", query_chars=len(query), **metrics)

        return RetrievalResult(
            chunks=reranked,
            citations=citations,
            context=context,
            query=query,
            metrics=metrics,
        )


def adaptive_top_k(query: str, *, base: int, minimum: int = 3, maximum: int = 12) -> int:
    """Adaptive chunk budget based on query complexity.

    Longer / multi-clause questions get more context; short lookups get less.
    Used by the chat orchestrator to tune ``final_top_k`` per request.
    """

    words = len(query.split())
    clauses = query.count(",") + query.count(" and ") + query.count(" vs ") + 1
    estimate = base + (words // 25) + (clauses - 1)
    return max(minimum, min(maximum, estimate))
