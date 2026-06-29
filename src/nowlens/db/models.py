"""ORM models.

PostgreSQL is the system of record for *metadata*: users, chat sessions and
messages, ingestion jobs, document/chunk metadata, and the audit log. Vector
embeddings live in Qdrant — ``document_chunks`` mirrors the chunk metadata and
adds a generated ``tsv`` column powering the lexical (full-text) retriever.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    Computed,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from nowlens.db.base import Base

# Well-known seed tenant. Every pre-multi-tenant row is backfilled to it by the
# migration, and single-tenant call sites (the CLI, bootstrap) use it as the
# default. It is a fixed UUID so the value is stable across environments.
DEFAULT_TENANT_ID = "00000000-0000-0000-0000-000000000000"
DEFAULT_TENANT_SLUG = "default"


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


class Role(StrEnum):
    """RBAC roles, ordered from least to most privileged in :data:`ROLE_RANK`."""

    VIEWER = "viewer"
    USER = "user"
    OPERATOR = "operator"
    ADMIN = "admin"


class JobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


class Tenant(Base):
    """A customer/workspace boundary. Every tenant-scoped row references one.

    Data isolation is enforced at the repository and retrieval layers by
    filtering on ``tenant_id``; this table is the catalogue of valid tenants.
    """

    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    # Email stays globally unique so login-by-email is unambiguous; the tenant is
    # derived from the resolved user record.
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    tenant_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        default=DEFAULT_TENANT_ID,
        index=True,
    )
    hashed_password: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default=Role.USER.value)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    sessions: Mapped[list[ChatSession]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        default=DEFAULT_TENANT_ID,
        index=True,
    )
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(255), default="New conversation")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    user: Mapped[User | None] = relationship(back_populates="sessions")
    messages: Mapped[list[Message]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        default=DEFAULT_TENANT_ID,
        index=True,
    )
    session_id: Mapped[str] = mapped_column(ForeignKey("chat_sessions.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(20))  # user | assistant | system
    content: Mapped[str] = mapped_column(Text)
    # Citations / intent / qa verdict for assistant turns.
    meta: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    session: Mapped[ChatSession] = relationship(back_populates="messages")


class Document(Base):
    """One ingested source document. ``content_hash`` drives incremental skips."""

    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        default=DEFAULT_TENANT_ID,
        index=True,
    )
    # URL is unique *within a tenant* (a composite constraint), so different
    # tenants can independently ingest the same source.
    url: Mapped[str] = mapped_column(String(2048), index=True)
    title: Mapped[str] = mapped_column(String(512), default="")
    content_hash: Mapped[str] = mapped_column(String(64), default="")
    domains: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    last_ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    __table_args__ = (UniqueConstraint("tenant_id", "url", name="uq_documents_tenant_url"),)


class DocumentChunk(Base):
    """Chunk-level metadata + full-text vector for lexical retrieval.

    The ``tsv`` column is a database-generated ``tsvector`` over title + text;
    a GIN index on it backs :class:`~nowlens.rag.lexical.PostgresFTSRetriever`.
    A GIN index on ``domains`` backs metadata filtering.
    """

    __tablename__ = "document_chunks"

    chunk_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        default=DEFAULT_TENANT_ID,
    )
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    text: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(String(512), default="")
    source_url: Mapped[str] = mapped_column(String(2048), default="")
    domains: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    keywords: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    has_code: Mapped[bool] = mapped_column(Boolean, default=False)
    index: Mapped[int] = mapped_column(Integer, default=0)
    meta: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    tsv: Mapped[str] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('english', coalesce(title,'') || ' ' || text)", persisted=True),
    )

    __table_args__ = (
        Index("ix_document_chunks_tsv", "tsv", postgresql_using="gin"),
        Index("ix_document_chunks_domains", "domains", postgresql_using="gin"),
        Index("ix_document_chunks_tenant", "tenant_id"),
    )


class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        default=DEFAULT_TENANT_ID,
        index=True,
    )
    url: Mapped[str] = mapped_column(String(2048), index=True)
    status: Mapped[str] = mapped_column(String(20), default=JobStatus.PENDING.value, index=True)
    detail: Mapped[str] = mapped_column(Text, default="")
    chunks_indexed: Mapped[int] = mapped_column(Integer, default=0)
    duplicates_removed: Mapped[int] = mapped_column(Integer, default=0)
    # Per-stage outcomes for the admin UI.
    stages: Mapped[list] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        default=DEFAULT_TENANT_ID,
        index=True,
    )
    actor: Mapped[str] = mapped_column(String(320), default="anonymous", index=True)
    action: Mapped[str] = mapped_column(String(128), index=True)
    target: Mapped[str] = mapped_column(String(512), default="")
    detail: Mapped[dict] = mapped_column(JSONB, default=dict)
    trace_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)


# Time-ordered index for fetching a user's most recent sessions.
Index("ix_chat_sessions_user_updated", ChatSession.user_id, ChatSession.updated_at.desc())

# Composite index for "messages of a session, oldest first". Its leftmost prefix
# (session_id) also serves session-scoped lookups, so no separate single-column
# index on session_id is needed.
Index("ix_messages_session_created", Message.session_id, Message.created_at)
