"""Router registry.

Functional routers are grouped under the ``/api/v1`` prefix via
:data:`api_router`. Operational endpoints (health probes, Prometheus metrics)
are exposed at the root — unversioned — because orchestrators and scrapers
expect stable, prefix-free paths; they are re-exported here for the app factory
to mount directly.
"""

from __future__ import annotations

from fastapi import APIRouter

from nowlens.api.routers import (
    auth,
    chat,
    config,
    domains,
    health,
    ingestion,
    metrics,
    sessions,
    tenants,
)

# Root-mounted operational routers.
health_router = health.router
metrics_router = metrics.router

# Versioned application surface.
api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(tenants.router)
api_router.include_router(sessions.router)
api_router.include_router(chat.router)
api_router.include_router(chat.search_router)
api_router.include_router(ingestion.router)
api_router.include_router(domains.router)
api_router.include_router(config.router)

__all__ = ["api_router", "health_router", "metrics_router"]
