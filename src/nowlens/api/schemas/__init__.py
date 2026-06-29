"""Pydantic request/response schemas for the API."""

from __future__ import annotations

from nowlens.api.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserOut,
)
from nowlens.api.schemas.chat import (
    ChatRequest,
    ChatResponse,
    ChatTurn,
    SearchHit,
    SearchRequest,
    SearchResponse,
)
from nowlens.api.schemas.common import (
    AuditOut,
    CitationOut,
    DocumentOut,
    ErrorOut,
    JobOut,
    MessageOut,
    SessionOut,
)
from nowlens.api.schemas.ingestion import (
    ConfigResponse,
    HealthResponse,
    IngestEnqueueResponse,
    IngestInlineResponse,
    IngestReportOut,
    IngestRequest,
    ReadinessComponent,
    ReadinessResponse,
)
from nowlens.api.schemas.tenant import TenantCreate, TenantOut, TenantUserCreate

__all__ = [
    "AuditOut",
    "ChatRequest",
    "ChatResponse",
    "ChatTurn",
    "CitationOut",
    "ConfigResponse",
    "DocumentOut",
    "ErrorOut",
    "HealthResponse",
    "IngestEnqueueResponse",
    "IngestInlineResponse",
    "IngestReportOut",
    "IngestRequest",
    "JobOut",
    "LoginRequest",
    "MessageOut",
    "ReadinessComponent",
    "ReadinessResponse",
    "RefreshRequest",
    "RegisterRequest",
    "SearchHit",
    "SearchRequest",
    "SearchResponse",
    "SessionOut",
    "TenantCreate",
    "TenantOut",
    "TenantUserCreate",
    "TokenResponse",
    "UserOut",
]
