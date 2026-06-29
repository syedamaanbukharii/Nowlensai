"""Multi-tenant isolation tests (SQLite-backed, offline).

Proves the core security property of the tenancy foundation: a repository
constructed for one tenant can neither read nor mutate another tenant's rows.
Uses ORM-based repositories (sessions, ingestion jobs) so the assertions run on
SQLite without the PostgreSQL-only upsert path.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from nowlens.db.base import Base
from nowlens.db.models import DEFAULT_TENANT_ID
from nowlens.db.repositories import (
    IngestionJobRepository,
    SessionRepository,
    TenantRepository,
)

_TABLES = ("tenants", "users", "chat_sessions", "messages", "ingestion_jobs", "audit_logs")


@pytest.fixture
async def maker() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    factory = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)
    tables = [Base.metadata.tables[name] for name in _TABLES]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield factory
    await engine.dispose()


async def _two_tenants(maker: async_sessionmaker[AsyncSession]) -> str:
    """Seed the default tenant + an 'acme' tenant; return acme's id."""

    async with maker() as session:
        await TenantRepository(session).ensure_default()
        acme = await TenantRepository(session).create(slug="acme", name="Acme")
        await session.commit()
        return acme.id


async def test_session_isolation_between_tenants(maker) -> None:
    acme_id = await _two_tenants(maker)

    async with maker() as session:
        default_session = await SessionRepository(session, DEFAULT_TENANT_ID).create(
            user_id=None, title="default"
        )
        acme_session = await SessionRepository(session, acme_id).create(user_id=None, title="acme")
        await session.commit()
        default_id, acme_session_id = default_session.id, acme_session.id

    async with maker() as session:
        # Each tenant lists only its own sessions.
        default_list = await SessionRepository(session, DEFAULT_TENANT_ID).list_for_user(None)
        acme_list = await SessionRepository(session, acme_id).list_for_user(None)
        assert {s.id for s in default_list} == {default_id}
        assert {s.id for s in acme_list} == {acme_session_id}

        # A cross-tenant fetch is denied (returns None), never leaking the row.
        assert await SessionRepository(session, DEFAULT_TENANT_ID).get(acme_session_id) is None
        assert await SessionRepository(session, acme_id).get(default_id) is None
        # In-tenant fetch still works.
        assert await SessionRepository(session, acme_id).get(acme_session_id) is not None


async def test_cross_tenant_delete_is_a_noop(maker) -> None:
    acme_id = await _two_tenants(maker)

    async with maker() as session:
        acme_session = await SessionRepository(session, acme_id).create(user_id=None, title="acme")
        await session.commit()
        acme_session_id = acme_session.id

    # The default tenant attempts to delete acme's session — must not affect it.
    async with maker() as session:
        await SessionRepository(session, DEFAULT_TENANT_ID).delete(acme_session_id)
        await session.commit()

    async with maker() as session:
        assert await SessionRepository(session, acme_id).get(acme_session_id) is not None


async def test_ingestion_job_isolation(maker) -> None:
    acme_id = await _two_tenants(maker)

    async with maker() as session:
        await IngestionJobRepository(session, DEFAULT_TENANT_ID).create("https://x/default")
        await IngestionJobRepository(session, acme_id).create("https://x/acme")
        await session.commit()

    async with maker() as session:
        default_jobs = await IngestionJobRepository(session, DEFAULT_TENANT_ID).list_recent()
        acme_jobs = await IngestionJobRepository(session, acme_id).list_recent()
        assert {j.url for j in default_jobs} == {"https://x/default"}
        assert {j.url for j in acme_jobs} == {"https://x/acme"}


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
