"""Typed exceptions.

Each error carries an HTTP status and a stable machine-readable ``code`` so the
API layer can translate domain failures into consistent JSON envelopes without
leaking internals.
"""

from __future__ import annotations


class NowLensError(Exception):
    """Base class for all application errors."""

    status_code: int = 500
    code: str = "internal_error"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code


class ConfigurationError(NowLensError):
    status_code = 500
    code = "configuration_error"


class ProviderError(NowLensError):
    """Raised when an LLM/embedding provider call fails."""

    status_code = 502
    code = "provider_error"


class RetrievalError(NowLensError):
    status_code = 502
    code = "retrieval_error"


class IngestionError(NowLensError):
    status_code = 500
    code = "ingestion_error"


class ValidationError(NowLensError):
    status_code = 422
    code = "validation_error"


class AuthenticationError(NowLensError):
    status_code = 401
    code = "authentication_error"


class AuthorizationError(NowLensError):
    status_code = 403
    code = "authorization_error"


class RateLimitError(NowLensError):
    status_code = 429
    code = "rate_limited"

    def __init__(
        self, message: str, *, retry_after: float | None = None, code: str | None = None
    ) -> None:
        super().__init__(message, code=code)
        # Seconds the client should wait before retrying; surfaced as the
        # RFC 6585 ``Retry-After`` response header by the API exception handler.
        self.retry_after = retry_after


class NotFoundError(NowLensError):
    status_code = 404
    code = "not_found"


class PromptInjectionError(ValidationError):
    code = "prompt_injection_detected"
