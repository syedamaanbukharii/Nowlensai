"""Database layer: models, async sessions, and repositories.

PostgreSQL stores all metadata (users, sessions, messages, documents, chunk
metadata + full-text vectors, ingestion jobs, audit log). Embeddings live in
Qdrant. Schema is managed by Alembic (``alembic upgrade head``).
"""

from nowlens.db.base import Base
from nowlens.db.models import (
    AuditLog,
    ChatSession,
    Document,
    DocumentChunk,
    IngestionJob,
    JobStatus,
    Message,
    Role,
    User,
)
from nowlens.db.repositories import (
    AuditRepository,
    ChunkRepository,
    DocumentRepository,
    IngestionJobRepository,
    MessageRepository,
    SessionRepository,
    UserRepository,
)
from nowlens.db.session import (
    dispose_engine,
    get_engine,
    get_session,
    get_sessionmaker,
    session_scope,
)

__all__ = [
    "AuditLog",
    "AuditRepository",
    "Base",
    "ChatSession",
    "ChunkRepository",
    "Document",
    "DocumentChunk",
    "DocumentRepository",
    "IngestionJob",
    "IngestionJobRepository",
    "JobStatus",
    "Message",
    "MessageRepository",
    "Role",
    "SessionRepository",
    "User",
    "UserRepository",
    "dispose_engine",
    "get_engine",
    "get_session",
    "get_sessionmaker",
    "session_scope",
]
