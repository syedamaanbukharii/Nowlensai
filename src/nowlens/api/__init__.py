"""HTTP API layer (FastAPI).

The API is a thin transport over the domain services in
:mod:`nowlens.services` and the agent graph in :mod:`nowlens.agents`. Routers
validate input with Pydantic schemas, resolve dependencies (auth, DB session,
rate limiting) via :mod:`nowlens.api.deps`, and translate domain objects to
response models. All error handling funnels through the exception handlers
registered in :func:`nowlens.api.app.create_app`.
"""

from __future__ import annotations

from nowlens.api.app import create_app

__all__ = ["create_app"]
