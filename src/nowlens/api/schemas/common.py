"""Shared response/request schema fragments."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    """Base for models populated directly from SQLAlchemy ORM objects."""

    model_config = ConfigDict(from_attributes=True)


class CitationOut(BaseModel):
    """A numbered citation rendered alongside an answer."""

    index: int
    chunk_id: str
    document_id: str
    title: str
    source_url: str
    snippet: str


class MessageOut(ORMModel):
    id: str
    role: str
    content: str
    meta: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class SessionOut(ORMModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime


class JobOut(ORMModel):
    id: str
    url: str
    status: str
    detail: str = ""
    chunks_indexed: int = 0
    duplicates_removed: int = 0
    created_at: datetime
    updated_at: datetime


class DocumentOut(ORMModel):
    id: str
    url: str
    title: str
    domains: list[str] = Field(default_factory=list)
    chunk_count: int = 0
    last_ingested_at: datetime | None = None


class AuditOut(ORMModel):
    id: str
    actor: str
    action: str
    target: str
    detail: dict[str, Any] = Field(default_factory=dict)
    trace_id: str | None = None
    created_at: datetime


class ErrorOut(BaseModel):
    """Uniform error envelope emitted by the exception handlers."""

    code: str
    message: str
    trace_id: str | None = None
