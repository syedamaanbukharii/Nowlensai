"""Composition root.

Assembles runtime objects from configuration and the provider factory so the
API layer and the workers share one wiring path. Process-global, stateless
singletons (vector store, reranker) are cached here; request/job-scoped objects
(retriever with a Postgres lexical leg, ingestion pipeline with a DB sink) are
built per call against a supplied session.
"""

from __future__ import annotations

from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncSession

from nowlens.agents.base import AgentContext
from nowlens.core.config import get_settings
from nowlens.db.repositories import ChunkRepository, DocumentRepository
from nowlens.ingestion.pipeline import IngestionPipeline
from nowlens.ingestion.stages.clean import AICleaner
from nowlens.llm.factory import get_chat_provider, get_embedding_provider
from nowlens.rag.base import VectorStore
from nowlens.rag.lexical import PostgresFTSRetriever
from nowlens.rag.reranker import Reranker, build_reranker
from nowlens.rag.retriever import HybridRetriever
from nowlens.rag.vector_store import QdrantVectorStore


@lru_cache
def get_vector_store() -> VectorStore:
    """Construct the configured vector store (Qdrant today) as a ``VectorStore``.

    Callers depend on the protocol, not the concrete backend, so swapping the
    vector database is a change here only.
    """

    settings = get_settings()
    return QdrantVectorStore(
        url=settings.qdrant_url,
        collection=settings.rag.collection,
        vector_size=settings.llm.embedding_dim,
        api_key=settings.qdrant_api_key,
    )


@lru_cache
def get_reranker() -> Reranker:
    rag = get_settings().rag
    return build_reranker(
        use_cross_encoder=rag.use_cross_encoder, cross_encoder_model=rag.cross_encoder_model
    )


def build_retriever(session: AsyncSession, tenant_id: str) -> HybridRetriever:
    """Hybrid retriever using Postgres FTS as the lexical leg, scoped to a tenant."""

    settings = get_settings()
    return HybridRetriever(
        embedder=get_embedding_provider(),
        vector_store=get_vector_store(),
        lexical=PostgresFTSRetriever(session),
        reranker=get_reranker(),
        settings=settings.rag,
        tenant_id=tenant_id,
    )


def build_agent_context(session: AsyncSession, tenant_id: str) -> AgentContext:
    return AgentContext(chat=get_chat_provider(), retriever=build_retriever(session, tenant_id))


def build_ingestion_pipeline(session: AsyncSession, tenant_id: str) -> IngestionPipeline:
    """Pipeline wired to persist chunk metadata and honour incremental skips."""

    settings = get_settings()
    documents = DocumentRepository(session, tenant_id)
    ai_cleaner = AICleaner(get_chat_provider()) if settings.ingestion.ai_cleaning else None
    return IngestionPipeline(
        settings=settings.ingestion,
        embedder=get_embedding_provider(),
        vector_store=get_vector_store(),
        expected_dim=settings.llm.embedding_dim,
        tenant_id=tenant_id,
        ai_cleaner=ai_cleaner,
        chunk_sink=ChunkRepository(session, tenant_id),
        unchanged=documents.is_unchanged,
    )


async def reset_singletons() -> None:
    """Close + clear cached singletons (used on shutdown / in tests)."""

    if get_vector_store.cache_info().currsize:
        await get_vector_store().aclose()
    get_vector_store.cache_clear()
    get_reranker.cache_clear()
