"""Health + readiness endpoints.

* ``/health/live`` — process liveness; never touches dependencies.
* ``/health/ready`` — readiness probe that checks the things the app needs to
  serve traffic (database, Qdrant, Redis). Each component is probed
  independently and failures are reported per-component so orchestrators get an
  actionable signal. A failing readiness check returns HTTP 503.
"""

from __future__ import annotations

from fastapi import APIRouter, Response
from sqlalchemy import text

from nowlens import __version__
from nowlens.api.deps import SettingsDep, _get_redis
from nowlens.api.schemas import HealthResponse, ReadinessComponent, ReadinessResponse
from nowlens.db.session import get_sessionmaker
from nowlens.services import get_vector_store

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live", response_model=HealthResponse)
async def live(settings: SettingsDep) -> HealthResponse:
    return HealthResponse(status="ok", version=__version__, environment=settings.environment)


async def _check_database() -> ReadinessComponent:
    try:
        maker = get_sessionmaker()
        async with maker() as session:
            await session.execute(text("SELECT 1"))
        return ReadinessComponent(name="database", ok=True)
    except Exception as exc:  # noqa: BLE001 - report, don't raise
        return ReadinessComponent(name="database", ok=False, detail=str(exc))


async def _check_qdrant() -> ReadinessComponent:
    try:
        await get_vector_store().count()
        return ReadinessComponent(name="qdrant", ok=True)
    except Exception as exc:  # noqa: BLE001
        return ReadinessComponent(name="qdrant", ok=False, detail=str(exc))


async def _check_redis() -> ReadinessComponent:
    client = _get_redis()
    if client is None:
        return ReadinessComponent(
            name="redis", ok=True, detail="not configured (in-process limiting)"
        )
    try:
        await client.ping()
        return ReadinessComponent(name="redis", ok=True)
    except Exception as exc:  # noqa: BLE001
        return ReadinessComponent(name="redis", ok=False, detail=str(exc))


@router.get("/ready", response_model=ReadinessResponse)
async def ready(response: Response) -> ReadinessResponse:
    components = [
        await _check_database(),
        await _check_qdrant(),
        await _check_redis(),
    ]
    all_ok = all(c.ok for c in components)
    if not all_ok:
        response.status_code = 503
    return ReadinessResponse(ready=all_ok, components=components)
