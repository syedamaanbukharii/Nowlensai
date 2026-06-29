"""multi-tenancy: tenants table + tenant_id on all scoped tables

Introduces the ``tenants`` catalogue and adds a non-null ``tenant_id`` foreign
key to every tenant-scoped table. Existing rows are backfilled to a seeded
"default" tenant via a column server default, so the upgrade is safe on a
populated database. ``documents`` moves from a globally-unique ``url`` to a
``(tenant_id, url)`` composite unique so tenants can ingest the same source
independently.

Revision ID: 0003_multi_tenancy
Revises: 0002_messages_session_created_idx
Create Date: 2026-06-29 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from nowlens.db.models import DEFAULT_TENANT_ID, DEFAULT_TENANT_SLUG

revision: str = "0003_multi_tenancy"
down_revision: str | None = "0002_messages_session_created_idx"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Tables that get an auto-named ``ix_<table>_tenant_id`` index (matching the
# ORM's ``index=True`` on the column). ``document_chunks`` uses a distinct index
# name and is handled separately below.
_AUTO_INDEX_TABLES = (
    "users",
    "chat_sessions",
    "messages",
    "documents",
    "ingestion_jobs",
    "audit_logs",
)


def _add_tenant_column(table: str) -> None:
    op.add_column(
        table,
        sa.Column(
            "tenant_id",
            sa.String(length=36),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
            server_default=DEFAULT_TENANT_ID,
        ),
    )


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_tenants_slug", "tenants", ["slug"], unique=True)

    # Seed the default tenant first so the backfilled foreign keys resolve.
    op.execute(
        "INSERT INTO tenants (id, slug, name, is_active, created_at) "
        f"VALUES ('{DEFAULT_TENANT_ID}', '{DEFAULT_TENANT_SLUG}', 'Default', true, now())"
    )

    for table in _AUTO_INDEX_TABLES:
        _add_tenant_column(table)
        op.create_index(f"ix_{table}_tenant_id", table, ["tenant_id"])

    _add_tenant_column("document_chunks")
    op.create_index("ix_document_chunks_tenant", "document_chunks", ["tenant_id"])

    # documents.url was globally unique; make it unique per tenant instead.
    op.drop_index("ix_documents_url", table_name="documents")
    op.create_index("ix_documents_url", "documents", ["url"])
    op.create_unique_constraint("uq_documents_tenant_url", "documents", ["tenant_id", "url"])


def downgrade() -> None:
    op.drop_constraint("uq_documents_tenant_url", "documents", type_="unique")
    op.drop_index("ix_documents_url", table_name="documents")
    op.create_index("ix_documents_url", "documents", ["url"], unique=True)

    op.drop_index("ix_document_chunks_tenant", table_name="document_chunks")
    op.drop_column("document_chunks", "tenant_id")

    for table in reversed(_AUTO_INDEX_TABLES):
        op.drop_index(f"ix_{table}_tenant_id", table_name=table)
        op.drop_column(table, "tenant_id")

    op.drop_index("ix_tenants_slug", table_name="tenants")
    op.drop_table("tenants")
