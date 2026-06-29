"""ASGI middleware: trace ids, structured access logs, and HTTP metrics.

A single middleware does three things per request:

1. Establishes a trace id (from the inbound ``X-Trace-Id`` header if present,
   otherwise freshly generated) and binds it to the contextvar so every log
   line emitted while handling the request carries it. The id is echoed back
   in the response header for client-side correlation.
2. Emits a structured access log with method, path, status, and duration.
3. Records Prometheus counters/histograms for request volume and latency,
   using the *route template* (e.g. ``/sessions/{session_id}``) rather than the
   concrete path so label cardinality stays bounded.
"""

from __future__ import annotations

import time

from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from nowlens.core.logging import get_logger
from nowlens.core.tracing import new_trace_id, set_trace_id
from nowlens.observability.metrics import HTTP_LATENCY, HTTP_REQUESTS

log = get_logger(__name__)

TRACE_HEADER = "x-trace-id"


def _route_template(request: Request) -> str:
    """Return the matched route path template, falling back to the raw path."""

    route = request.scope.get("route")
    path = getattr(route, "path", None)
    if isinstance(path, str) and path:
        return path
    return request.url.path


class ObservabilityMiddleware:
    """Pure-ASGI middleware (works with streaming responses, unlike BaseHTTP)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):  # type: ignore[no-untyped-def]
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive=receive)
        inbound = request.headers.get(TRACE_HEADER)
        trace_id = inbound or new_trace_id()
        set_trace_id(trace_id)

        start = time.perf_counter()
        status_code = 500

        async def send_wrapper(message):  # type: ignore[no-untyped-def]
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = message.setdefault("headers", [])
                headers.append((TRACE_HEADER.encode(), trace_id.encode()))
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            # Let the exception propagate to the registered handlers/Starlette,
            # but still record metrics + a log line for the failed request.
            duration = time.perf_counter() - start
            template = _route_template(request)
            HTTP_REQUESTS.labels(request.method, template, "500").inc()
            HTTP_LATENCY.labels(request.method, template).observe(duration)
            log.exception(
                "http.request.error",
                method=request.method,
                path=request.url.path,
                duration_ms=round(duration * 1000, 2),
            )
            raise
        else:
            duration = time.perf_counter() - start
            template = _route_template(request)
            HTTP_REQUESTS.labels(request.method, template, str(status_code)).inc()
            HTTP_LATENCY.labels(request.method, template).observe(duration)
            log.info(
                "http.request",
                method=request.method,
                path=request.url.path,
                status=status_code,
                duration_ms=round(duration * 1000, 2),
            )


def trace_id_of(response: Response) -> str | None:
    return response.headers.get(TRACE_HEADER)


# Static, response-independent hardening headers. CSP is intentionally omitted:
# this process serves JSON plus the Swagger/ReDoc UIs (which need inline scripts
# and a CDN), and the HTML-serving surface is the frontend, where CSP belongs.
_BASE_SECURITY_HEADERS: tuple[tuple[bytes, bytes], ...] = (
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"no-referrer"),
    (b"permissions-policy", b"geolocation=(), microphone=(), camera=()"),
)
# Tell browsers to pin HTTPS for a year (incl. subdomains). Only meaningful over
# TLS, so it is applied only in production where the app is served behind HTTPS.
_HSTS_HEADER: tuple[bytes, bytes] = (
    b"strict-transport-security",
    b"max-age=31536000; includeSubDomains",
)


class SecurityHeadersMiddleware:
    """Attach baseline security headers to every HTTP response (pure-ASGI)."""

    def __init__(self, app: ASGIApp, *, enable_hsts: bool = False) -> None:
        self.app = app
        self._headers = list(_BASE_SECURITY_HEADERS)
        if enable_hsts:
            self._headers.append(_HSTS_HEADER)

    async def __call__(self, scope, receive, send):  # type: ignore[no-untyped-def]
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message):  # type: ignore[no-untyped-def]
            if message["type"] == "http.response.start":
                headers = message.setdefault("headers", [])
                existing = {name.lower() for name, _ in headers}
                for name, value in self._headers:
                    if name not in existing:
                        headers.append((name, value))
            await send(message)

        await self.app(scope, receive, send_wrapper)
