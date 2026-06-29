"""FastAPI application factory.

Builds the ASGI app: structured logging, observability middleware (trace ids +
metrics), CORS, the router tree, and a uniform exception-handling layer that
turns every :class:`~nowlens.core.exceptions.NowLensError` (and validation /
unexpected errors) into the same ``{code, message, trace_id}`` JSON envelope.

A lazy lifespan keeps startup robust: external dependencies (Qdrant) are probed
best-effort so the process still boots — and serves ``/health/ready`` honestly —
when a backing service is temporarily unavailable. Provider HTTP clients, cached
singletons, and the database engine are released on shutdown.
"""

from __future__ import annotations

import math
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from nowlens import __version__
from nowlens.api.middleware import ObservabilityMiddleware, SecurityHeadersMiddleware
from nowlens.api.routers import api_router, health_router, metrics_router
from nowlens.api.schemas import ErrorOut
from nowlens.core.config import Settings, get_settings
from nowlens.core.exceptions import NowLensError
from nowlens.core.logging import configure_logging, get_logger
from nowlens.core.tracing import get_trace_id

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    log.info("app.startup", environment=settings.environment, version=__version__)

    # Best-effort: ensure the vector collection exists. A missing/unreachable
    # Qdrant must not stop the API from booting (readiness will report it).
    try:
        from nowlens.services import get_vector_store

        await get_vector_store().ensure_collection()
        log.info("app.qdrant_ready", collection=settings.rag.collection)
    except Exception as exc:  # noqa: BLE001 - degrade gracefully, surface via /health/ready
        log.warning("app.qdrant_unavailable", error=str(exc))

    try:
        yield
    finally:
        # Release resources in reverse order of acquisition.
        from nowlens.db.session import dispose_engine
        from nowlens.llm.factory import close_providers
        from nowlens.services import reset_singletons

        for name, closer in (
            ("providers", close_providers),
            ("singletons", reset_singletons),
            ("engine", dispose_engine),
        ):
            try:
                await closer()
            except Exception as exc:  # noqa: BLE001 - shutdown must not raise
                log.warning("app.shutdown_cleanup_failed", component=name, error=str(exc))
        log.info("app.shutdown")


def _error_response(status_code: int, code: str, message: str) -> JSONResponse:
    body = ErrorOut(code=code, message=message, trace_id=get_trace_id())
    return JSONResponse(status_code=status_code, content=body.model_dump())


def _register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(NowLensError)
    async def _handle_nowlens(_: Request, exc: NowLensError) -> JSONResponse:
        # 5xx are unexpected enough to warrant a stack; 4xx are client errors.
        if exc.status_code >= 500:
            log.error("error.domain", code=exc.code, message=exc.message)
        response = _error_response(exc.status_code, exc.code, exc.message)
        # RFC 6585: advertise when a rate-limited client may retry.
        retry_after = getattr(exc, "retry_after", None)
        if retry_after is not None:
            response.headers["Retry-After"] = str(max(1, math.ceil(retry_after)))
        return response

    @app.exception_handler(RequestValidationError)
    async def _handle_validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = exc.errors()
        first = errors[0] if errors else {}
        loc = ".".join(str(p) for p in first.get("loc", ()) if p != "body")
        message = first.get("msg", "Invalid request")
        detail = f"{loc}: {message}" if loc else message
        return _error_response(422, "validation_error", detail)

    @app.exception_handler(Exception)
    async def _handle_unexpected(_: Request, exc: Exception) -> JSONResponse:
        log.exception("error.unhandled")
        return _error_response(500, "internal_error", "Internal server error")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Construct and configure the FastAPI application."""

    configure_logging()
    settings = settings or get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        description=(
            "Multi-agent ServiceNow expert: hybrid RAG retrieval, a LangGraph "
            "agent graph (routing, specialist analysis, quality assurance), and "
            "an automated documentation ingestion pipeline."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # Middleware is applied bottom-up, so the last added is the outermost.
    # Order (outermost → innermost): CORS → Observability → SecurityHeaders.
    app.add_middleware(SecurityHeadersMiddleware, enable_hsts=settings.is_production)
    app.add_middleware(ObservabilityMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        # Explicit allow-lists rather than wildcards: only the verbs and headers
        # the API actually uses, so the cross-origin surface stays minimal.
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Trace-Id"],
        expose_headers=["X-Trace-Id", "Retry-After"],
    )

    _register_exception_handlers(app)

    app.include_router(health_router)
    app.include_router(metrics_router)
    app.include_router(api_router)

    @app.get("/", tags=["meta"], summary="Service metadata")
    async def root() -> dict[str, str]:
        return {
            "name": settings.app_name,
            "version": __version__,
            "environment": settings.environment,
            "docs": "/docs",
            "health": "/health/ready",
        }

    log.info("app.created", routes=len(app.routes))
    return app


app = create_app()
