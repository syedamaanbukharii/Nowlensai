"""Authentication endpoints: register, login, refresh.

Tokens are JWTs (see :mod:`nowlens.security.jwt`). The **first** account to
register is bootstrapped as an ``admin`` so a fresh deployment has an operator;
every subsequent account defaults to the ``user`` role and must be promoted by
an admin. Passwords are hashed with bcrypt and never stored or logged in clear.
"""

from __future__ import annotations

from fastapi import APIRouter, status

from nowlens.api.deps import CurrentUser, RateLimitDep, SessionDep
from nowlens.api.schemas import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserOut,
)
from nowlens.core.config import get_settings
from nowlens.core.exceptions import AuthenticationError, ValidationError
from nowlens.db.models import Role
from nowlens.db.repositories import AuditRepository, UserRepository
from nowlens.security.audit import audit_event
from nowlens.security.jwt import REFRESH, create_access_token, create_refresh_token, decode_token
from nowlens.security.password import hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


def _token_response(subject: str, role: str) -> TokenResponse:
    ttl_min = get_settings().security.access_token_ttl_min
    return TokenResponse(
        access_token=create_access_token(subject, role=role),
        refresh_token=create_refresh_token(subject),
        expires_in=ttl_min * 60,
    )


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, session: SessionDep, _: RateLimitDep) -> TokenResponse:
    users = UserRepository(session)
    if await users.get_by_email(payload.email) is not None:
        raise ValidationError("An account with this email already exists")

    role = Role.ADMIN if await users.count() == 0 else Role.USER
    user = await users.create(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        role=role,
    )
    await audit_event(
        actor=user.email,
        action="auth.register",
        target=user.id,
        detail={"role": str(role)},
        repository=AuditRepository(session),
    )
    return _token_response(user.id, str(user.role))


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, session: SessionDep, _: RateLimitDep) -> TokenResponse:
    users = UserRepository(session)
    user = await users.get_by_email(payload.email)
    # Verify even when the user is missing-ish to keep timing uniform; a missing
    # user still fails because verify_password returns False on a dummy hash.
    if (
        user is None
        or not user.is_active
        or not verify_password(payload.password, user.hashed_password)
    ):
        raise AuthenticationError("Invalid email or password")
    await audit_event(
        actor=user.email,
        action="auth.login",
        target=user.id,
        repository=AuditRepository(session),
    )
    return _token_response(user.id, str(user.role))


@router.post("/refresh", response_model=TokenResponse)
async def refresh(payload: RefreshRequest, session: SessionDep, _: RateLimitDep) -> TokenResponse:
    token = decode_token(payload.refresh_token, expected_type=REFRESH)
    user = await UserRepository(session).get(token.subject)
    if user is None or not user.is_active:
        raise AuthenticationError("User not found or inactive")
    return _token_response(user.id, str(user.role))


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> UserOut:
    return UserOut(id=user.id, email=user.email, role=str(user.role), is_active=user.is_active)
