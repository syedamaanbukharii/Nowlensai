"""Reranking.

After fusion we have a candidate set whose ordering blends lexical and semantic
signal. Reranking re-scores those candidates against the query with a stronger
relevance model:

* :class:`LexicalOverlapReranker` — dependency-free token-overlap + coverage
  scoring. Deterministic, instant, and a sensible default.
* :class:`CrossEncoderReranker` — a sentence-transformers cross-encoder for
  high-quality semantic reranking (requires the ``rerank`` extra). Loaded lazily
  so the import cost is only paid when enabled.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from nowlens.core.logging import get_logger
from nowlens.rag.lexical import tokenize
from nowlens.rag.types import RetrievedChunk

log = get_logger(__name__)


@runtime_checkable
class Reranker(Protocol):
    async def rerank(
        self, query: str, chunks: Sequence[RetrievedChunk], *, top_k: int
    ) -> list[RetrievedChunk]: ...


class LexicalOverlapReranker:
    """Score = Jaccard-like overlap weighted by query-term coverage."""

    async def rerank(
        self, query: str, chunks: Sequence[RetrievedChunk], *, top_k: int
    ) -> list[RetrievedChunk]:
        q_tokens = set(tokenize(query))
        if not q_tokens:
            return list(chunks)[:top_k]

        rescored: list[RetrievedChunk] = []
        for chunk in chunks:
            c_tokens = set(tokenize(chunk.text))
            if not c_tokens:
                score = 0.0
            else:
                intersection = q_tokens & c_tokens
                coverage = len(intersection) / len(q_tokens)
                density = len(intersection) / len(c_tokens)
                score = 0.7 * coverage + 0.3 * density
            rescored.append(chunk.copy_with_score(score, retriever="rerank:lexical"))

        rescored.sort(key=lambda c: c.score, reverse=True)
        return rescored[:top_k]


class CrossEncoderReranker:
    """Cross-encoder reranker (lazy-loaded sentence-transformers model)."""

    def __init__(self, model_name: str) -> None:
        self._model_name = model_name
        self._model: object | None = None

    def _ensure_model(self) -> object:
        if self._model is None:
            try:
                from sentence_transformers import CrossEncoder
            except ImportError as exc:  # pragma: no cover - optional dep
                raise RuntimeError(
                    "CrossEncoderReranker requires the 'rerank' extra: "
                    "pip install 'nowlens-ai[rerank]'"
                ) from exc
            log.info("reranker.loading_cross_encoder", model=self._model_name)
            self._model = CrossEncoder(self._model_name)
        return self._model

    async def rerank(
        self, query: str, chunks: Sequence[RetrievedChunk], *, top_k: int
    ) -> list[RetrievedChunk]:
        if not chunks:
            return []
        model = self._ensure_model()
        pairs = [(query, c.text) for c in chunks]
        scores = model.predict(pairs)  # type: ignore[attr-defined]
        rescored = [
            chunk.copy_with_score(float(score), retriever="rerank:cross-encoder")
            for chunk, score in zip(chunks, scores, strict=True)
        ]
        rescored.sort(key=lambda c: c.score, reverse=True)
        return rescored[:top_k]


def build_reranker(*, use_cross_encoder: bool, cross_encoder_model: str) -> Reranker:
    if use_cross_encoder:
        return CrossEncoderReranker(cross_encoder_model)
    return LexicalOverlapReranker()
