"""Repositories — the only place that talks SQL.

Keeping persistence logic here (rather than in routers or the pipeline) means
the ingestion :class:`~nowlens.ingestion.stages.index.ChunkSink` protocol, the
chat history endpoints, and the admin views all share one well-tested data
access layer.

**Tenant isolation.** Every tenant-scoped repository is constructed with a
``tenant_id`` and scopes all of its reads and writes to it, so a caller can
never reach another tenant's rows through these classes. :class:`UserRepository`
is deliberately *not* tenant-bound: login resolves a user by globally-unique
email before any tenant is known, and the tenant is then read from the user.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from nowlens.db.models import (
    DEFAULT_TENANT_ID,
    AuditLog,
    ChatSession,
    Document,
    DocumentChunk,
    IngestionJob,
    JobStatus,
    Message,
    Role,
    Tenant,
    User,
)
from nowlens.ingestion.models import EmbeddedChunk


def _now() -> datetime:
    return datetime.now(UTC)


class TenantRepository:
    """The tenant catalogue. Not itself tenant-scoped."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, tenant_id: str) -> Tenant | None:
        return await self._session.get(Tenant, tenant_id)

    async def get_by_slug(self, slug: str) -> Tenant | None:
        return await self._session.scalar(select(Tenant).where(Tenant.slug == slug.lower()))

    async def create(self, *, slug: str, name: str = "") -> Tenant:
        tenant = Tenant(slug=slug.lower(), name=name or slug)
        self._session.add(tenant)
        await self._session.flush()
        return tenant

    async def ensure_default(self) -> Tenant:
        """Idempotently ensure the seed ``default`` tenant exists."""

        existing = await self.get(DEFAULT_TENANT_ID)
        if existing is not None:
            return existing
        tenant = Tenant(id=DEFAULT_TENANT_ID, slug="default", name="Default")
        self._session.add(tenant)
        await self._session.flush()
        return tenant

    async def list_all(self, *, limit: int = 100) -> list[Tenant]:
        rows = await self._session.scalars(
            select(Tenant).order_by(Tenant.created_at.desc()).limit(limit)
        )
        return list(rows)


class ChunkRepository:
    """Persists chunk metadata; implements the ingestion ``ChunkSink`` protocol.

    Embeddings stay in Qdrant; here we upsert the searchable metadata + text so
    the Postgres full-text retriever and admin views have a row per chunk.
    """

    def __init__(self, session: AsyncSession, tenant_id: str) -> None:
        self._session = session
        self._tenant_id = tenant_id

    async def upsert_chunks(self, embedded: list[EmbeddedChunk]) -> int:
        if not embedded:
            return 0
        rows = []
        for item in embedded:
            chunk = item.chunk
            md = chunk.metadata
            rows.append(
                {
                    "chunk_id": chunk.chunk_id,
                    "tenant_id": self._tenant_id,
                    "document_id": chunk.document_id,
                    "text": chunk.text,
                    "title": md.get("title", ""),
                    "source_url": md.get("source_url", ""),
                    "domains": list(md.get("domains", [])),
                    "keywords": list(md.get("keywords", [])),
                    "has_code": bool(md.get("has_code", False)),
                    "index": int(chunk.index),
                    "meta": {
                        k: v
                        for k, v in md.items()
                        if k not in {"title", "source_url", "domains", "keywords", "has_code"}
                    },
                }
            )
        stmt = pg_insert(DocumentChunk).values(rows)
        update_cols = {
            c.name: stmt.excluded[c.name]
            for c in DocumentChunk.__table__.columns
            if c.name not in {"chunk_id", "created_at", "tsv", "tenant_id"}
        }
        stmt = stmt.on_conflict_do_update(index_elements=["chunk_id"], set_=update_cols)
        await self._session.execute(stmt)
        return len(rows)

    async def delete_for_document(self, document_id: str) -> int:
        result = await self._session.execute(
            delete(DocumentChunk).where(
                DocumentChunk.document_id == document_id,
                DocumentChunk.tenant_id == self._tenant_id,
            )
        )
        return int(result.rowcount or 0)  # type: ignore[attr-defined]


class DocumentRepository:
    def __init__(self, session: AsyncSession, tenant_id: str) -> None:
        self._session = session
        self._tenant_id = tenant_id

    async def content_hash_for(self, url: str) -> str | None:
        return await self._session.scalar(
            select(Document.content_hash).where(
                Document.url == url, Document.tenant_id == self._tenant_id
            )
        )

    async def is_unchanged(self, url: str, content_hash: str) -> bool:
        """Predicate for incremental ingestion (matches ``UnchangedPredicate``)."""

        existing = await self.content_hash_for(url)
        return existing is not None and existing == content_hash

    async def upsert(
        self, *, url: str, title: str, content_hash: str, domains: Sequence[str], chunk_count: int
    ) -> Document:
        insert_stmt = pg_insert(Document).values(
            tenant_id=self._tenant_id,
            url=url,
            title=title,
            content_hash=content_hash,
            domains=list(domains),
            chunk_count=chunk_count,
            last_ingested_at=_now(),
        )
        stmt = insert_stmt.on_conflict_do_update(
            index_elements=["tenant_id", "url"],
            set_={
                "title": insert_stmt.excluded.title,
                "content_hash": insert_stmt.excluded.content_hash,
                "domains": insert_stmt.excluded.domains,
                "chunk_count": insert_stmt.excluded.chunk_count,
                "last_ingested_at": insert_stmt.excluded.last_ingested_at,
            },
        ).returning(Document)
        return (await self._session.execute(stmt)).scalar_one()

    async def list_recent(self, *, limit: int = 50) -> list[Document]:
        rows = await self._session.scalars(
            select(Document)
            .where(Document.tenant_id == self._tenant_id)
            .order_by(Document.last_ingested_at.desc())
            .limit(limit)
        )
        return list(rows)

    async def count(self) -> int:
        return int(
            await self._session.scalar(
                select(func.count())
                .select_from(Document)
                .where(Document.tenant_id == self._tenant_id)
            )
            or 0
        )

    async def get(self, document_id: str) -> Document | None:
        return await self._session.scalar(
            select(Document).where(
                Document.id == document_id, Document.tenant_id == self._tenant_id
            )
        )

    async def delete(self, document_id: str) -> None:
        """Delete a document row. Cascades to its chunks via the FK constraint."""

        await self._session.execute(
            delete(Document).where(
                Document.id == document_id, Document.tenant_id == self._tenant_id
            )
        )


class SessionRepository:
    def __init__(self, session: AsyncSession, tenant_id: str) -> None:
        self._session = session
        self._tenant_id = tenant_id

    async def create(self, *, user_id: str | None, title: str = "New conversation") -> ChatSession:
        chat = ChatSession(tenant_id=self._tenant_id, user_id=user_id, title=title)
        self._session.add(chat)
        await self._session.flush()
        return chat

    async def get(self, session_id: str) -> ChatSession | None:
        return await self._session.scalar(
            select(ChatSession).where(
                ChatSession.id == session_id, ChatSession.tenant_id == self._tenant_id
            )
        )

    async def list_for_user(self, user_id: str | None, *, limit: int = 50) -> list[ChatSession]:
        stmt = (
            select(ChatSession)
            .where(ChatSession.tenant_id == self._tenant_id)
            .order_by(ChatSession.updated_at.desc())
            .limit(limit)
        )
        stmt = stmt.where(ChatSession.user_id == user_id) if user_id else stmt
        return list(await self._session.scalars(stmt))

    async def touch(self, session_id: str) -> None:
        await self._session.execute(
            update(ChatSession)
            .where(ChatSession.id == session_id, ChatSession.tenant_id == self._tenant_id)
            .values(updated_at=_now())
        )

    async def delete(self, session_id: str) -> None:
        await self._session.execute(
            delete(ChatSession).where(
                ChatSession.id == session_id, ChatSession.tenant_id == self._tenant_id
            )
        )


class MessageRepository:
    def __init__(self, session: AsyncSession, tenant_id: str) -> None:
        self._session = session
        self._tenant_id = tenant_id

    async def add(
        self, *, session_id: str, role: str, content: str, meta: dict | None = None
    ) -> Message:
        msg = Message(
            tenant_id=self._tenant_id,
            session_id=session_id,
            role=role,
            content=content,
            meta=meta or {},
        )
        self._session.add(msg)
        await self._session.flush()
        return msg

    async def list_for_session(self, session_id: str) -> list[Message]:
        rows = await self._session.scalars(
            select(Message)
            .where(Message.session_id == session_id, Message.tenant_id == self._tenant_id)
            .order_by(Message.created_at)
        )
        return list(rows)


class IngestionJobRepository:
    def __init__(self, session: AsyncSession, tenant_id: str) -> None:
        self._session = session
        self._tenant_id = tenant_id

    async def create(self, url: str) -> IngestionJob:
        job = IngestionJob(tenant_id=self._tenant_id, url=url, status=JobStatus.PENDING.value)
        self._session.add(job)
        await self._session.flush()
        return job

    async def mark(
        self,
        job_id: str,
        *,
        status: JobStatus,
        detail: str = "",
        chunks_indexed: int = 0,
        duplicates_removed: int = 0,
        stages: list | None = None,
    ) -> None:
        await self._session.execute(
            update(IngestionJob)
            .where(IngestionJob.id == job_id, IngestionJob.tenant_id == self._tenant_id)
            .values(
                status=status.value,
                detail=detail,
                chunks_indexed=chunks_indexed,
                duplicates_removed=duplicates_removed,
                stages=stages or [],
                updated_at=_now(),
            )
        )

    async def list_recent(self, *, limit: int = 50) -> list[IngestionJob]:
        rows = await self._session.scalars(
            select(IngestionJob)
            .where(IngestionJob.tenant_id == self._tenant_id)
            .order_by(IngestionJob.created_at.desc())
            .limit(limit)
        )
        return list(rows)


class UserRepository:
    """Not tenant-bound: email is globally unique and resolves the tenant."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_email(self, email: str) -> User | None:
        return await self._session.scalar(select(User).where(User.email == email.lower()))

    async def get(self, user_id: str) -> User | None:
        return await self._session.get(User, user_id)

    async def create(
        self,
        *,
        email: str,
        hashed_password: str,
        role: Role = Role.USER,
        tenant_id: str = DEFAULT_TENANT_ID,
    ) -> User:
        user = User(
            email=email.lower(),
            hashed_password=hashed_password,
            role=role.value,
            tenant_id=tenant_id,
        )
        self._session.add(user)
        await self._session.flush()
        return user

    async def count(self, *, tenant_id: str) -> int:
        return int(
            await self._session.scalar(
                select(func.count()).select_from(User).where(User.tenant_id == tenant_id)
            )
            or 0
        )


class AuditRepository:
    def __init__(self, session: AsyncSession, tenant_id: str) -> None:
        self._session = session
        self._tenant_id = tenant_id

    async def record(
        self,
        *,
        actor: str,
        action: str,
        target: str = "",
        detail: dict | None = None,
        trace_id: str | None = None,
    ) -> None:
        self._session.add(
            AuditLog(
                tenant_id=self._tenant_id,
                actor=actor,
                action=action,
                target=target,
                detail=detail or {},
                trace_id=trace_id,
            )
        )

    async def list_recent(self, *, limit: int = 100) -> list[AuditLog]:
        rows = await self._session.scalars(
            select(AuditLog)
            .where(AuditLog.tenant_id == self._tenant_id)
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
        )
        return list(rows)
