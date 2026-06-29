"""Lexical retrieval.

Two interchangeable implementations behind a common protocol:

* :class:`BM25Retriever` — in-memory Okapi BM25 over a provided corpus.
  Dependency-light, deterministic, and unit-testable; used when no database is
  available and as the lexical half of hybrid search for small corpora.
* :class:`PostgresFTSRetriever` — PostgreSQL ``ts_rank`` full-text search over
  the persisted ``document_chunks`` table; the production lexical backend.

Both return :class:`RetrievedChunk` lists ordered best-first.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from rank_bm25 import BM25Okapi
from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession

from nowlens.rag.types import RetrievedChunk

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


@runtime_checkable
class LexicalRetriever(Protocol):
    async def search(
        self,
        query: str,
        *,
        top_k: int,
        domains: Sequence[str] | None = None,
        tenant_id: str | None = None,
    ) -> list[RetrievedChunk]: ...


class BM25Retriever:
    """In-memory BM25. Build once from a corpus, then query repeatedly."""

    def __init__(self, chunks: Sequence[RetrievedChunk]) -> None:
        self._chunks = list(chunks)
        self._tokenized = [tokenize(c.text) for c in self._chunks]
        # BM25Okapi requires a non-empty corpus.
        self._bm25 = BM25Okapi(self._tokenized) if self._tokenized else None

    async def search(
        self,
        query: str,
        *,
        top_k: int,
        domains: Sequence[str] | None = None,
        tenant_id: str | None = None,
    ) -> list[RetrievedChunk]:
        # In-memory BM25 is built per-corpus (already tenant-scoped by the
        # caller), so ``tenant_id`` is accepted for protocol parity but unused.
        if self._bm25 is None:
            return []
        scores = self._bm25.get_scores(tokenize(query))
        order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        results: list[RetrievedChunk] = []
        domain_set = set(domains) if domains else None
        for idx in order:
            if scores[idx] <= 0:
                continue
            chunk = self._chunks[idx]
            if domain_set and not (domain_set & set(chunk.domains)):
                continue
            results.append(chunk.copy_with_score(float(scores[idx]), retriever="bm25"))
            if len(results) >= top_k:
                break
        return results


class PostgresFTSRetriever:
    """PostgreSQL full-text lexical retriever.

    Relies on a generated ``tsv`` ``tsvector`` column (see the migration) and a
    GIN index. Domain filtering uses the ``domains`` text[] column.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def search(
        self,
        query: str,
        *,
        top_k: int,
        domains: Sequence[str] | None = None,
        tenant_id: str | None = None,
    ) -> list[RetrievedChunk]:
        # websearch_to_tsquery safely parses arbitrary user input.
        stmt = sql_text("""
            SELECT chunk_id, document_id, text, title, source_url, domains,
                   ts_rank(tsv, websearch_to_tsquery('english', :q)) AS rank
            FROM document_chunks
            WHERE tsv @@ websearch_to_tsquery('english', :q)
              AND (:no_tenant OR tenant_id = :tenant_id)
              AND (:no_domains OR domains && :domains)
            ORDER BY rank DESC
            LIMIT :top_k
            """)
        params = {
            "q": query,
            "top_k": top_k,
            "no_tenant": tenant_id is None,
            "tenant_id": tenant_id or "",
            "no_domains": domains is None or len(domains) == 0,
            "domains": list(domains) if domains else [],
        }
        rows = (await self._session.execute(stmt, params)).mappings().all()
        return [
            RetrievedChunk(
                chunk_id=row["chunk_id"],
                text=row["text"],
                score=float(row["rank"]),
                document_id=row["document_id"],
                source_url=row["source_url"] or "",
                title=row["title"] or "",
                domains=list(row["domains"] or []),
                retriever="postgres_fts",
            )
            for row in rows
        ]
