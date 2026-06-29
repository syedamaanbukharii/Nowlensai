"""messages (session_id, created_at) composite index

Replaces the single-column index on ``messages.session_id`` with a composite
index on ``(session_id, created_at)``. This serves the "transcript of a session,
oldest first" query directly, and its leftmost prefix still covers
session-scoped lookups, so the single-column index becomes redundant.

Revision ID: 0002_messages_session_created_idx
Revises: 0001_initial
Create Date: 2026-06-29 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0002_messages_session_created_idx"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("ix_messages_session_id", table_name="messages")
    op.create_index("ix_messages_session_created", "messages", ["session_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_messages_session_created", table_name="messages")
    op.create_index("ix_messages_session_id", "messages", ["session_id"])
