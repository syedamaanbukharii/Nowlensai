"""Reciprocal Rank Fusion (RRF).

Combines multiple ranked lists (e.g. vector + lexical) into a single ranking
using ``score = sum(1 / (k + rank))`` across lists. RRF is robust because it
relies only on ranks, so it never has to reconcile incomparable raw scores
(cosine similarity vs BM25). Pure function — fully unit-tested.
"""

from __future__ import annotations

from collections.abc import Sequence

from nowlens.rag.types import RetrievedChunk


def reciprocal_rank_fusion(
    ranked_lists: Sequence[Sequence[RetrievedChunk]],
    *,
    k: int = 60,
    top_k: int | None = None,
) -> list[RetrievedChunk]:
    """Fuse ranked lists by chunk id.

    Args:
        ranked_lists: each inner sequence is ordered best-first.
        k: RRF damping constant (larger => flatter contribution curve).
        top_k: optional cap on the returned list length.
    """

    fused_scores: dict[str, float] = {}
    representative: dict[str, RetrievedChunk] = {}

    for ranked in ranked_lists:
        for rank, chunk in enumerate(ranked):
            contribution = 1.0 / (k + rank + 1)
            fused_scores[chunk.chunk_id] = fused_scores.get(chunk.chunk_id, 0.0) + contribution
            # Keep the first representative we see (they carry identical text).
            representative.setdefault(chunk.chunk_id, chunk)

    ordered_ids = sorted(fused_scores, key=lambda cid: fused_scores[cid], reverse=True)
    results = [
        representative[cid].copy_with_score(fused_scores[cid], retriever="rrf")
        for cid in ordered_ids
    ]
    if top_k is not None:
        results = results[:top_k]
    return results
