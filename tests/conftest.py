"""Shared test fixtures and offline fakes.

Everything here is dependency-free: no live Qdrant, Postgres, Redis, Ollama, or
Groq is required. The fakes implement exactly the provider/store interfaces the
system depends on, so retrieval, ingestion, the agent graph, and the API can all
be exercised end-to-end in-process.

The DB-backed API fixtures run against an in-memory SQLite database. The ORM
models target PostgreSQL (JSONB / ARRAY / TSVECTOR / generated columns), so we
register small DDL compiler shims for SQLite and create only the tables the
exercised endpoints touch (the full-text ``document_chunks`` table is omitted —
its generated ``tsvector`` column has no SQLite equivalent and lexical search is
covered separately with the in-memory BM25 retriever).
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import AsyncIterator, Iterator, Sequence

import pytest
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.pool import StaticPool

from nowlens.core.config import RAGSettings
from nowlens.llm.base import ChatChunk, ChatMessage, ChatResult, ChatUsage, EmbeddingProvider
from nowlens.rag.lexical import BM25Retriever
from nowlens.rag.reranker import LexicalOverlapReranker
from nowlens.rag.retriever import HybridRetriever
from nowlens.rag.types import RetrievedChunk

# --------------------------------------------------------------------------- #
# SQLite DDL shims for the PostgreSQL-specific column types.
# Registered at import time; they only affect the SQLite dialect, so production
# (PostgreSQL) behaviour is untouched.
# --------------------------------------------------------------------------- #


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(element, compiler, **kw):  # type: ignore[no-untyped-def]
    return "JSON"


@compiles(ARRAY, "sqlite")
def _compile_array_sqlite(element, compiler, **kw):  # type: ignore[no-untyped-def]
    return "JSON"


@compiles(TSVECTOR, "sqlite")
def _compile_tsvector_sqlite(element, compiler, **kw):  # type: ignore[no-untyped-def]
    return "TEXT"


# --------------------------------------------------------------------------- #
# Fake providers
# --------------------------------------------------------------------------- #

EMBED_DIM = 16


class FakeEmbeddingProvider(EmbeddingProvider):
    """Deterministic, dependency-free embeddings.

    Maps each token to a bucket via a stable hash and L2-normalises, so texts
    sharing vocabulary land near each other under cosine similarity — enough
    structure for the hybrid retriever's vector half to behave sensibly.
    """

    name = "fake-embed"

    def __init__(self, dimension: int = EMBED_DIM) -> None:
        self.dimension = dimension
        self.calls = 0

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        self.calls += 1
        return [self._vector(text) for text in texts]

    def _vector(self, text: str) -> list[float]:
        vec = [0.0] * self.dimension
        for token in text.lower().split():
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).hexdigest()
            vec[int(digest, 16) % self.dimension] += 1.0
        norm = math.sqrt(sum(value * value for value in vec)) or 1.0
        return [value / norm for value in vec]


_DEFAULT_JSON = {
    "summary": "Structured analysis summary.",
    "primary_domains": ["itsm"],
    "stakeholders": ["IT operations"],
    "business_outcomes": ["faster resolution"],
    "key_processes": ["incident"],
    "recommended_capabilities": ["flow designer"],
    "risks": ["scope creep"],
    "success_metrics": ["MTTR"],
    "domains": ["itsm", "csm"],
    "overlap": ["case-like records"],
    "differences": ["internal vs external"],
    "decision_guidance": "Use ITSM for internal IT, CSM for external customers.",
    "anti_patterns": ["one table for both"],
    "fit": "good",
    "considerations": ["AppSec scan"],
    "findings": ["recent release notes"],
}

_DEFAULT_QA = {
    "grounded": True,
    "citations_valid": True,
    "answers_question": True,
    "issues": [],
    "verdict": "pass",
}


class FakeChatProvider:
    """Configurable, deterministic chat provider.

    Branches on the *system* prompt so a single instance drives every node in
    the agent graph: QA prompts get QA JSON, ``STRICT JSON`` prompts get a
    structured-analysis object, everything else gets prose containing a ``[1]``
    citation marker.
    """

    name = "fake-chat"

    def __init__(
        self,
        *,
        text: str = "Grounded best-practice guidance, per the documentation [1].",
        json_payload: dict | None = None,
        qa_payload: dict | None = None,
    ) -> None:
        self._text = text
        self._json = json_payload if json_payload is not None else dict(_DEFAULT_JSON)
        self._qa = qa_payload if qa_payload is not None else dict(_DEFAULT_QA)
        self.systems: list[str] = []

    def _content_for(self, messages: Sequence[ChatMessage]) -> str:
        system = next((m.content for m in messages if m.role == "system"), "")
        self.systems.append(system)
        if "verdict" in system:
            return json.dumps(self._qa)
        if "STRICT JSON" in system:
            return json.dumps(self._json)
        return self._text

    async def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> ChatResult:
        return ChatResult(
            content=self._content_for(messages),
            model="fake",
            provider=self.name,
            usage=ChatUsage(prompt_tokens=12, completion_tokens=24),
        )

    async def stream_chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[ChatChunk]:
        content = self._content_for(messages)
        for index, word in enumerate(content.split()):
            yield ChatChunk(delta=word if index == 0 else f" {word}")
        yield ChatChunk(
            delta="", done=True, usage=ChatUsage(prompt_tokens=12, completion_tokens=24)
        )

    async def aclose(self) -> None:
        return None


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


class InMemoryVectorStore:
    """In-process stand-in for :class:`QdrantVectorStore` (duck-typed)."""

    def __init__(self, vector_size: int = EMBED_DIM) -> None:
        self._vector_size = vector_size
        self._points: dict[str, tuple[list[float], dict]] = {}

    async def ensure_collection(self) -> None:
        return None

    async def upsert(self, points: Sequence[dict]) -> int:
        for point in points:
            self._points[str(point["id"])] = (list(point["vector"]), dict(point["payload"]))
        return len(points)

    async def search(
        self,
        vector: Sequence[float],
        *,
        top_k: int,
        domains: Sequence[str] | None = None,
        tenant_id: str | None = None,
    ) -> list[RetrievedChunk]:
        domain_set = set(domains) if domains else None
        scored: list[tuple[float, dict]] = []
        for stored_vector, payload in self._points.values():
            if domain_set and not (domain_set & set(payload.get("domains") or [])):
                continue
            scored.append((_cosine(vector, stored_vector), payload))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [
            RetrievedChunk(
                chunk_id=str(payload["chunk_id"]),
                text=str(payload["text"]),
                score=float(score),
                document_id=str(payload.get("document_id", "")),
                source_url=str(payload.get("source_url", "")),
                title=str(payload.get("title", "")),
                domains=list(payload.get("domains") or []),
                retriever="vector",
            )
            for score, payload in scored[:top_k]
        ]

    async def count(self) -> int:
        return len(self._points)

    async def delete_document(self, document_id: str) -> int:
        to_remove = [
            cid
            for cid, (_, payload) in self._points.items()
            if payload.get("document_id") == document_id
        ]
        for cid in to_remove:
            del self._points[cid]
        return len(to_remove)

    async def aclose(self) -> None:
        return None


# --------------------------------------------------------------------------- #
# Sample data
# --------------------------------------------------------------------------- #

SAMPLE_CHUNKS: list[RetrievedChunk] = [
    RetrievedChunk(
        chunk_id="c1",
        text=(
            "Incident management in ITSM coordinates the response to "
            "unplanned disruptions. Use the incident table and assignment "
            "rules to route work to the right group."
        ),
        score=0.0,
        document_id="d1",
        source_url="https://docs.example.com/itsm/incident",
        title="ITSM Incident Management",
        domains=["itsm"],
    ),
    RetrievedChunk(
        chunk_id="c2",
        text=(
            "Customer Service Management (CSM) handles external customer cases "
            "with accounts and contacts. Cases differ from internal incidents."
        ),
        score=0.0,
        document_id="d2",
        source_url="https://docs.example.com/csm/cases",
        title="CSM Cases",
        domains=["csm"],
    ),
    RetrievedChunk(
        chunk_id="c3",
        text=(
            "Flow Designer provides no-code automation. Build flows, subflows, "
            "and actions to automate incident and request processes."
        ),
        score=0.0,
        document_id="d3",
        source_url="https://docs.example.com/flow/designer",
        title="Flow Designer",
        domains=["flow_designer"],
    ),
]


@pytest.fixture
def embedder() -> FakeEmbeddingProvider:
    return FakeEmbeddingProvider()


@pytest.fixture
def vector_store() -> InMemoryVectorStore:
    return InMemoryVectorStore()


@pytest.fixture
def rag_settings() -> RAGSettings:
    return RAGSettings()


@pytest.fixture
async def seeded_retriever(
    embedder: FakeEmbeddingProvider,
    vector_store: InMemoryVectorStore,
    rag_settings: RAGSettings,
) -> HybridRetriever:
    """A hybrid retriever wired to fakes and seeded with sample chunks."""

    points = []
    for chunk in SAMPLE_CHUNKS:
        vector = (await embedder.embed([chunk.text]))[0]
        points.append(
            {
                "id": chunk.chunk_id,
                "vector": vector,
                "payload": {
                    "chunk_id": chunk.chunk_id,
                    "document_id": chunk.document_id,
                    "text": chunk.text,
                    "title": chunk.title,
                    "source_url": chunk.source_url,
                    "domains": chunk.domains,
                },
            }
        )
    await vector_store.upsert(points)
    lexical = BM25Retriever(SAMPLE_CHUNKS)
    return HybridRetriever(
        embedder=embedder,
        vector_store=vector_store,  # type: ignore[arg-type]
        lexical=lexical,
        reranker=LexicalOverlapReranker(),
        settings=rag_settings,
    )


# --------------------------------------------------------------------------- #
# API fixtures
# --------------------------------------------------------------------------- #


def _make_user(role: str = "admin"):  # type: ignore[no-untyped-def]
    from nowlens.db.models import DEFAULT_TENANT_ID, User

    return User(
        id="user-test-1",
        email="tester@example.com",
        tenant_id=DEFAULT_TENANT_ID,
        hashed_password="x",
        role=role,
        is_active=True,
    )


@pytest.fixture
def fake_chat() -> FakeChatProvider:
    return FakeChatProvider()


@pytest.fixture
def client(fake_chat: FakeChatProvider, seeded_retriever: HybridRetriever) -> Iterator:
    """TestClient with auth + services overridden; no database required.

    ``current_user`` is forced to an admin, the agent context uses the fake
    chat provider and the seeded retriever, and rate limiting is disabled so
    tests don't interfere with each other.
    """

    from fastapi.testclient import TestClient

    from nowlens.agents.base import AgentContext
    from nowlens.api.app import create_app
    from nowlens.api.deps import current_user, get_agent_context, rate_limit

    app = create_app()
    ctx = AgentContext(chat=fake_chat, retriever=seeded_retriever)

    app.dependency_overrides[current_user] = lambda: _make_user("admin")
    app.dependency_overrides[get_agent_context] = lambda: ctx
    app.dependency_overrides[rate_limit] = lambda: None

    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def db_client(fake_chat: FakeChatProvider) -> Iterator:
    """TestClient backed by SQLite for real auth/session/chat persistence.

    Authentication is *not* overridden here (so register/login/JWT are exercised
    for real); only the database session, the agent context (no live retriever),
    and rate limiting are swapped for offline equivalents.

    The async engine and its tables are created inside the TestClient's event
    loop (via its portal) so every connection lives on the same loop the app
    runs on — sharing an aiosqlite engine across loops would otherwise fail.
    """

    from fastapi.testclient import TestClient

    from nowlens.agents.base import AgentContext
    from nowlens.api.app import create_app
    from nowlens.api.deps import get_agent_context, rate_limit
    from nowlens.db.base import Base
    from nowlens.db.session import get_session

    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    maker = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)
    table_names = (
        "tenants",
        "users",
        "chat_sessions",
        "messages",
        "audit_logs",
        "ingestion_jobs",
    )
    tables = [Base.metadata.tables[name] for name in table_names]

    async def _create_tables() -> None:
        from nowlens.db.repositories import TenantRepository

        async with engine.begin() as conn:
            await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
        # Seed the default tenant so register/login satisfy the tenant FK.
        async with maker() as session:
            await TenantRepository(session).ensure_default()
            await session.commit()

    async def _dispose() -> None:
        await engine.dispose()

    async def _override_session() -> AsyncIterator[AsyncSession]:
        async with maker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app = create_app()
    ctx = AgentContext(chat=fake_chat, retriever=None)
    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[get_agent_context] = lambda: ctx
    app.dependency_overrides[rate_limit] = lambda: None

    with TestClient(app, raise_server_exceptions=False) as test_client:
        test_client.portal.call(_create_tables)
        yield test_client
        test_client.portal.call(_dispose)
    app.dependency_overrides.clear()
