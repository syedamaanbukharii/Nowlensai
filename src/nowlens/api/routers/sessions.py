"""Chat session management.

Sessions are owned by the authenticated user. Listing/reading/deleting is
scoped to the owner; attempting to touch another user's session yields 404 to
avoid leaking existence.
"""

from __future__ import annotations

from fastapi import APIRouter, status

from nowlens.api.deps import CurrentUser, SessionDep
from nowlens.api.schemas import MessageOut, SessionOut
from nowlens.core.exceptions import NotFoundError
from nowlens.db.models import ChatSession
from nowlens.db.repositories import MessageRepository, SessionRepository

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("", response_model=list[SessionOut])
async def list_sessions(user: CurrentUser, session: SessionDep) -> list[SessionOut]:
    rows = await SessionRepository(session).list_for_user(user.id)
    return [SessionOut.model_validate(row) for row in rows]


@router.post("", response_model=SessionOut, status_code=status.HTTP_201_CREATED)
async def create_session(user: CurrentUser, session: SessionDep) -> SessionOut:
    row = await SessionRepository(session).create(user_id=user.id)
    return SessionOut.model_validate(row)


async def _owned_session(repo: SessionRepository, session_id: str, user_id: str) -> ChatSession:
    row = await repo.get(session_id)
    if row is None or row.user_id != user_id:
        raise NotFoundError("Session not found")
    return row


@router.get("/{session_id}", response_model=SessionOut)
async def get_session_detail(session_id: str, user: CurrentUser, session: SessionDep) -> SessionOut:
    repo = SessionRepository(session)
    row = await _owned_session(repo, session_id, user.id)
    return SessionOut.model_validate(row)


@router.get("/{session_id}/messages", response_model=list[MessageOut])
async def list_messages(
    session_id: str, user: CurrentUser, session: SessionDep
) -> list[MessageOut]:
    """Return the full transcript of an owned session, oldest first."""

    await _owned_session(SessionRepository(session), session_id, user.id)
    rows = await MessageRepository(session).list_for_session(session_id)
    return [MessageOut.model_validate(row) for row in rows]


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(session_id: str, user: CurrentUser, session: SessionDep) -> None:
    repo = SessionRepository(session)
    await _owned_session(repo, session_id, user.id)
    await repo.delete(session_id)
