"""Prometheus metrics endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Response

from nowlens.observability.metrics import render_latest

router = APIRouter(tags=["metrics"])


@router.get("/metrics")
async def metrics() -> Response:
    """Expose metrics in the Prometheus text exposition format.

    Left unauthenticated by default so a scraper can reach it; restrict via
    network policy / reverse proxy in production, or place behind the auth
    dependency if metrics are considered sensitive in your deployment.
    """

    payload, content_type = render_latest()
    return Response(content=payload, media_type=content_type)
