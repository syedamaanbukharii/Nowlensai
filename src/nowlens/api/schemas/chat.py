"""Chat + search request/response schemas."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from nowlens.api.schemas.common import CitationOut


class ChatTurn(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str = Field(min_length=1, max_length=8000)


class ChatRequest(BaseModel):
    """A chat request.

    ``session_id`` is optional; when omitted a new session is created and
    returned in the response/stream so the client can continue the thread.
    """

    message: str = Field(min_length=1, max_length=8000)
    session_id: str | None = None
    domains: list[str] = Field(default_factory=list)
    history: list[ChatTurn] = Field(default_factory=list)
    stream: bool = True
    final_top_k: int | None = Field(default=None, ge=1, le=20)


class ChatResponse(BaseModel):
    """Non-streaming chat response (used when ``stream=false``)."""

    session_id: str
    answer: str
    intent: str
    domains: list[str]
    citations: list[CitationOut]
    analysis: dict[str, Any] | None = None
    qa: dict[str, Any] = Field(default_factory=dict)
    grounded: bool
    metrics: dict[str, Any] = Field(default_factory=dict)


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=8000)
    domains: list[str] = Field(default_factory=list)
    top_k: int | None = Field(default=None, ge=1, le=20)


class SearchHit(BaseModel):
    chunk_id: str
    score: float
    title: str
    source_url: str
    domains: list[str]
    snippet: str
    retriever: str


class SearchResponse(BaseModel):
    query: str
    hits: list[SearchHit]
    citations: list[CitationOut]
    metrics: dict[str, Any] = Field(default_factory=dict)
