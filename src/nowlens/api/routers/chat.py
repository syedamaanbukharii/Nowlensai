"""Chat, streaming chat, and search endpoints.

Two answering paths are exposed:

* ``POST /chat`` runs the **full LangGraph agent graph** (route → retrieve →
  specialist → quality-assurance) and returns a structured, QA-annotated answer
  in a single JSON response.
* ``POST /chat/stream`` is a **single-pass grounded stream** (retrieve →
  best-practice generation) that emits Server-Sent Events so the UI can render
  tokens as they arrive. It intentionally skips the specialist/QA fan-out to
  keep latency low; clients wanting the full analysis use the non-streaming
  endpoint.

``POST /search`` exposes the hybrid retriever directly (no generation) for a
"sources only" experience.

Both chat paths persist the turn to the caller's :class:`ChatSession` so a
conversation can be resumed; an absent ``session_id`` creates a new session and
returns its id (in the response body, or the first ``session`` SSE event).
"""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from nowlens.agents.base import AgentContext, citations_payload
from nowlens.agents.graph import run_answer
from nowlens.agents.prompts import BEST_PRACTICE_SYSTEM
from nowlens.api.deps import AgentContextDep, CurrentUser, RateLimitDep, SessionDep
from nowlens.api.schemas import (
    ChatRequest,
    ChatResponse,
    CitationOut,
    SearchHit,
    SearchRequest,
    SearchResponse,
)
from nowlens.core.exceptions import NotFoundError
from nowlens.core.logging import get_logger
from nowlens.db.models import User
from nowlens.db.repositories import (
    AuditRepository,
    MessageRepository,
    SessionRepository,
)
from nowlens.llm.base import ChatMessage
from nowlens.observability.metrics import observe_agent_run, observe_retrieval
from nowlens.rag.retriever import adaptive_top_k
from nowlens.rag.types import RetrievalResult
from nowlens.security.audit import audit_event
from nowlens.security.prompt_injection import guard_user_input, scan_retrieved_context

log = get_logger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])
search_router = APIRouter(prefix="/search", tags=["search"])


def _citation_out(data: dict[str, object]) -> CitationOut:
    index = data.get("index", 0)
    return CitationOut(
        index=index if isinstance(index, int) else 0,
        chunk_id=str(data.get("chunk_id", "")),
        document_id=str(data.get("document_id", "")),
        title=str(data.get("title", "")),
        source_url=str(data.get("source_url", "")),
        snippet=str(data.get("snippet", "")),
    )


def _history_dicts(payload: ChatRequest) -> list[dict[str, str]]:
    return [{"role": turn.role, "content": turn.content} for turn in payload.history]


async def _resolve_session(
    sessions: SessionRepository, *, session_id: str | None, user: User
) -> str:
    """Return an owned session id, creating one when none was supplied."""

    if session_id is None:
        created = await sessions.create(user_id=user.id)
        return created.id
    existing = await sessions.get(session_id)
    if existing is None or existing.user_id != user.id:
        # 404 (not 403) so we never leak which session ids exist.
        raise NotFoundError("Session not found")
    return existing.id


def _best_practice_prompt(query: str, context: str, *, grounded: bool) -> str:
    """Mirror the best-practices node so streaming and graph stay consistent."""

    if grounded:
        return (
            f"Numbered context passages:\n{context}\n\n"
            f"Question: {query}\n\n"
            "Answer with best-practice guidance, citing passages as [n]."
        )
    return (
        f"Question: {query}\n\n"
        "No retrieved documentation was available. Answer from general "
        "ServiceNow expertise, and begin by noting that this answer is not "
        "grounded in indexed documentation."
    )


@router.post("", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    user: CurrentUser,
    session: SessionDep,
    ctx: AgentContextDep,
    _: RateLimitDep,
) -> ChatResponse:
    """Answer a question with the full agent graph (non-streaming)."""

    guard_user_input(payload.message)

    sessions = SessionRepository(session)
    messages = MessageRepository(session)
    session_id = await _resolve_session(sessions, session_id=payload.session_id, user=user)
    await messages.add(session_id=session_id, role="user", content=payload.message)

    started = time.perf_counter()
    result = await run_answer(
        ctx,
        payload.message,
        history=_history_dicts(payload),
        requested_domains=payload.domains,
        final_top_k=payload.final_top_k,
    )
    observe_agent_run(
        result.get("intent", ""),
        latency_seconds=time.perf_counter() - started,
        ok=not result.get("errors"),
    )

    citations = [_citation_out(c) for c in result.get("citations", [])]
    await messages.add(
        session_id=session_id,
        role="assistant",
        content=result.get("answer", ""),
        meta={
            "intent": result.get("intent", ""),
            "grounded": result.get("grounded", False),
            "citations": result.get("citations", []),
            "qa": result.get("qa", {}),
        },
    )
    await sessions.touch(session_id)
    await audit_event(
        actor=user.email,
        action="chat.answer",
        target=session_id,
        detail={"intent": result.get("intent", ""), "grounded": result.get("grounded", False)},
        repository=AuditRepository(session),
    )

    return ChatResponse(
        session_id=session_id,
        answer=result.get("answer", ""),
        intent=result.get("intent", ""),
        domains=list(result.get("domains", [])),
        citations=citations,
        analysis=result.get("analysis"),
        qa=result.get("qa", {}),
        grounded=bool(result.get("grounded", False)),
        metrics=result.get("metrics", {}),
    )


def _sse(event: str, data: dict[str, object]) -> dict[str, str]:
    return {"event": event, "data": json.dumps(data, ensure_ascii=False)}


async def _stream_events(
    *,
    ctx: AgentContext,
    message: str,
    payload: ChatRequest,
    session_id: str,
    session: SessionDep,
    user: User,
) -> AsyncIterator[dict[str, str]]:
    messages = MessageRepository(session)
    sessions = SessionRepository(session)

    yield _sse("session", {"session_id": session_id})

    # 1. Retrieve (or run degraded if no knowledge base is wired in).
    context = ""
    grounded = False
    citation_dicts: list[dict[str, object]] = []
    if ctx.retriever is not None:
        base = payload.final_top_k or adaptive_top_k(message, base=_configured_top_k(ctx))
        result: RetrievalResult = await ctx.retriever.retrieve(
            message, domains=payload.domains or None, final_top_k=base
        )
        context = result.context
        grounded = bool(result.chunks)
        citation_dicts = citations_payload(result.citations)
        observe_retrieval(float(result.metrics.get("total_ms", 0.0)) / 1000.0, len(result.chunks))
        # Indirect-injection signal on retrieved content (report-only).
        assessment = scan_retrieved_context(context)
        if assessment.flagged:
            log.warning(
                "chat.retrieved_injection_signal",
                severity=assessment.severity,
                categories=assessment.categories,
            )

    yield _sse(
        "citations",
        {"citations": citation_dicts, "grounded": grounded},
    )

    # 2. Stream the grounded best-practice answer.
    chat_messages = [
        ChatMessage(role="system", content=BEST_PRACTICE_SYSTEM),
        ChatMessage(
            role="user", content=_best_practice_prompt(message, context, grounded=grounded)
        ),
    ]
    chunks: list[str] = []
    started = time.perf_counter()
    try:
        async for chunk in ctx.chat.stream_chat(chat_messages, max_tokens=ctx.max_answer_tokens):
            if chunk.delta:
                chunks.append(chunk.delta)
                yield _sse("token", {"delta": chunk.delta})
    except Exception as exc:
        log.exception("chat.stream_failed")
        yield _sse("error", {"message": "generation failed", "detail": str(exc)})
        return

    answer = "".join(chunks).strip()
    observe_agent_run("best_practice", latency_seconds=time.perf_counter() - started, ok=True)

    # 3. Persist + finalise.
    await messages.add(
        session_id=session_id,
        role="assistant",
        content=answer,
        meta={
            "intent": "best_practice",
            "grounded": grounded,
            "citations": citation_dicts,
            "streamed": True,
        },
    )
    await sessions.touch(session_id)
    await audit_event(
        actor=user.email,
        action="chat.answer.stream",
        target=session_id,
        detail={"grounded": grounded},
        repository=AuditRepository(session),
    )
    yield _sse("done", {"answer": answer, "grounded": grounded})


def _configured_top_k(ctx: AgentContext) -> int:
    cfg = getattr(ctx.retriever, "_cfg", None)
    return int(getattr(cfg, "final_top_k", 6)) if cfg is not None else 6


@router.post("/stream")
async def chat_stream(
    payload: ChatRequest,
    user: CurrentUser,
    session: SessionDep,
    ctx: AgentContextDep,
    _: RateLimitDep,
) -> EventSourceResponse:
    """Stream a grounded answer as Server-Sent Events.

    Event sequence: ``session`` → ``citations`` → many ``token`` → ``done``
    (or a terminal ``error``). Validation, injection guarding, and session
    resolution happen before streaming begins so failures are normal HTTP
    errors rather than mid-stream surprises.
    """

    guard_user_input(payload.message)
    sessions = SessionRepository(session)
    messages = MessageRepository(session)
    session_id = await _resolve_session(sessions, session_id=payload.session_id, user=user)
    await messages.add(session_id=session_id, role="user", content=payload.message)

    return EventSourceResponse(
        _stream_events(
            ctx=ctx,
            message=payload.message,
            payload=payload,
            session_id=session_id,
            session=session,
            user=user,
        )
    )


@search_router.post("", response_model=SearchResponse)
async def search(
    payload: SearchRequest,
    user: CurrentUser,
    ctx: AgentContextDep,
    _: RateLimitDep,
) -> SearchResponse:
    """Hybrid retrieval without generation — returns ranked chunks + citations."""

    guard_user_input(payload.query)
    if ctx.retriever is None:
        return SearchResponse(query=payload.query, hits=[], citations=[], metrics={})

    top_k = payload.top_k or adaptive_top_k(payload.query, base=_configured_top_k(ctx))
    result = await ctx.retriever.retrieve(
        payload.query, domains=payload.domains or None, final_top_k=top_k
    )
    observe_retrieval(float(result.metrics.get("total_ms", 0.0)) / 1000.0, len(result.chunks))

    hits = [
        SearchHit(
            chunk_id=chunk.chunk_id,
            score=round(float(chunk.score), 6),
            title=chunk.title or chunk.source_url or "Untitled source",
            source_url=chunk.source_url,
            domains=list(chunk.domains),
            snippet=chunk.text[:240],
            retriever=chunk.retriever,
        )
        for chunk in result.chunks
    ]
    citations = [
        CitationOut(
            index=c.index,
            chunk_id=c.chunk_id,
            document_id=c.document_id,
            title=c.title,
            source_url=c.source_url,
            snippet=c.snippet,
        )
        for c in result.citations
    ]
    log.info("search.done", query_chars=len(payload.query), hits=len(hits))
    return SearchResponse(
        query=payload.query, hits=hits, citations=citations, metrics=result.metrics
    )
