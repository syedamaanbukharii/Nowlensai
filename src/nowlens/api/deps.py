"""FastAPI dependency providers.

Centralises dependency-injection wiring so routers stay declarative:

* ``SessionDep`` — async DB session (commit/rollback handled by the provider).
* ``current_user`` / ``CurrentUser`` — decode the bearer access token and load
  the active user.
* ``require_role`` — factory producing a dependency that enforces a minimum
  role via :func:`nowlens.security.rbac.ensure_role`.
* ``RateLimitDep`` — per-identity sliding-window rate limit (shared via Redis
  when configured, otherwise in-process).
* ``RetrieverDep`` / ``AgentContextDep`` / ``IngestionPipelineDep`` — request
  scoped service objects from the composition root.

Redis is optional: if a client cannot be created the limiter degrades to
in-process state, and the dependency reflects that without failing requests.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from nowlens.agents.base import AgentContext
from nowlens.core.config import Settings, get_settings
from nowlens.core.exceptions import AuthenticationError, RateLimitError
from nowlens.core.logging import get_logger
from nowlens.db.models import Role, User
from nowlens.db.repositories import UserRepository
from nowlens.db.session import get_session
from nowlens.ingestion.pipeline import IngestionPipeline
from nowlens.rag.retriever import HybridRetriever
from nowlens.security.jwt import ACCESS, decode_token
from nowlens.security.rate_limit import RateLimiter
from nowlens.security.rbac import ensure_role
from nowlens.services import build_agent_context, build_ingestion_pipeline, build_retriever

log = get_logger(__name__)

# auto_error=False so we can raise our normalised AuthenticationError rather
# than Starlette's default 403 with a different shape.
_bearer = HTTPBearer(auto_error=False)


def settings_dep() -> Settings:
    return get_settings()


SettingsDep = Annotated[Settings, Depends(settings_dep)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]


@lru_cache
def _get_redis():  # type: ignore[no-untyped-def]
    """Best-effort Redis client for shared rate-limit state.

    Returns ``None`` (in-process limiting) if the redis client library is
    unavailable; connection errors surface lazily on first use and the limiter
    falls back to local state, so this never blocks startup.
    """

    settings = get_settings()
    try:
        from redis.asyncio import Redis

        return Redis.from_url(str(settings.redis_url), encoding="utf-8", decode_responses=True)
    except Exception as exc:  # noqa: BLE001 - redis is optional
        log.warning("redis.unavailable", error=str(exc))
        return None


@lru_cache
def _get_limiter() -> RateLimiter:
    return RateLimiter.from_settings(get_settings().security, redis=_get_redis())


def _rate_limit_identity(request: Request) -> str:
    """Stable rate-limit identity: the token subject, else the client IP.

    Keying on the raw ``Authorization`` header is wrong because the token
    rotates on every refresh, which would reset a user's budget. We decode the
    bearer access token (best effort) and key on its subject so the limit
    follows the user across token refreshes; unauthenticated/invalid requests
    fall back to the client IP.
    """

    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
        try:
            return f"user:{decode_token(token, expected_type=ACCESS).subject}"
        except AuthenticationError:
            pass
    client_host = request.client.host if request.client else "anonymous"
    return f"ip:{client_host}"


async def rate_limit(request: Request) -> None:
    """Enforce the per-client request budget."""

    limiter = _get_limiter()
    decision = await limiter.check(_rate_limit_identity(request))
    if not decision.allowed:
        raise RateLimitError(
            f"Rate limit exceeded; retry in {decision.retry_after:.1f}s",
            retry_after=decision.retry_after,
        )


RateLimitDep = Annotated[None, Depends(rate_limit)]


async def current_user(
    session: SessionDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    """Resolve the active user from a bearer access token."""

    if credentials is None or not credentials.credentials:
        raise AuthenticationError("Missing bearer token")
    token = decode_token(credentials.credentials, expected_type=ACCESS)
    user = await UserRepository(session).get(token.subject)
    if user is None or not user.is_active:
        raise AuthenticationError("User not found or inactive")
    return user


CurrentUser = Annotated[User, Depends(current_user)]


def require_role(minimum: Role):  # type: ignore[no-untyped-def]
    """Return a dependency enforcing ``minimum`` role on the current user."""

    async def _dependency(user: CurrentUser) -> User:
        ensure_role(user.role, minimum)
        return user

    return _dependency


RequireOperator = Annotated[User, Depends(require_role(Role.OPERATOR))]
RequireAdmin = Annotated[User, Depends(require_role(Role.ADMIN))]


async def get_retriever(session: SessionDep) -> HybridRetriever:
    return build_retriever(session)


async def get_agent_context(session: SessionDep) -> AgentContext:
    return build_agent_context(session)


async def get_ingestion_pipeline(session: SessionDep) -> AsyncIterator[IngestionPipeline]:
    pipeline = build_ingestion_pipeline(session)
    try:
        yield pipeline
    finally:
        await pipeline.aclose()


RetrieverDep = Annotated[HybridRetriever, Depends(get_retriever)]
AgentContextDep = Annotated[AgentContext, Depends(get_agent_context)]
IngestionPipelineDep = Annotated[IngestionPipeline, Depends(get_ingestion_pipeline)]
