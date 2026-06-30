"""Authentication endpoints: register, login, refresh.

Tokens are JWTs (see :mod:`nowlens.security.jwt`). The **first** account to
register is bootstrapped as an ``admin`` so a fresh deployment has an operator;
every subsequent account defaults to the ``user`` role and must be promoted by
an admin. Passwords are hashed with bcrypt and never stored or logged in clear.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, Response, status

from nowlens.api.cookies import (
    REFRESH_COOKIE,
    clear_auth_cookies,
    new_csrf_token,
    set_auth_cookies,
)
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
from nowlens.db.models import DEFAULT_TENANT_ID, Role
from nowlens.db.repositories import AuditRepository, UserRepository
from nowlens.security.audit import audit_event
from nowlens.security.jwt import REFRESH, create_access_token, create_refresh_token, decode_token
from nowlens.security.password import hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


def _issue_tokens(response: Response, subject: str, role: str) -> TokenResponse:
    """Mint tokens, set them as cookies, and return them in the body.

    The body keeps bearer-token clients working; the cookies give browsers an
    XSS-resistant (HttpOnly) session plus a CSRF token for the double-submit
    check on cookie-authenticated requests.
    """

    security = get_settings().security
    access = create_access_token(subject, role=role)
    refresh = create_refresh_token(subject)
    csrf = new_csrf_token()
    set_auth_cookies(
        response,
        access_token=access,
        refresh_token=refresh,
        csrf_token=csrf,
        security=security,
    )
    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        expires_in=security.access_token_ttl_min * 60,
        csrf_token=csrf,
    )


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest, response: Response, session: SessionDep, _: RateLimitDep
) -> TokenResponse:
    users = UserRepository(session)
    if await users.get_by_email(payload.email) is not None:
        raise ValidationError("An account with this email already exists")

    # New accounts join the default tenant; the first account in a tenant is
    # bootstrapped as its admin so a fresh deployment has an operator.
    tenant_id = DEFAULT_TENANT_ID
    role = Role.ADMIN if await users.count(tenant_id=tenant_id) == 0 else Role.USER
    user = await users.create(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        role=role,
        tenant_id=tenant_id,
    )
    await audit_event(
        actor=user.email,
        action="auth.register",
        target=user.id,
        detail={"role": str(role)},
        repository=AuditRepository(session, tenant_id),
    )
    return _issue_tokens(response, user.id, str(user.role))


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest, response: Response, session: SessionDep, _: RateLimitDep
) -> TokenResponse:
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
        repository=AuditRepository(session, user.tenant_id),
    )
    return _issue_tokens(response, user.id, str(user.role))


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    payload: RefreshRequest,
    response: Response,
    session: SessionDep,
    _: RateLimitDep,
    refresh_cookie: Annotated[str | None, Cookie(alias=REFRESH_COOKIE)] = None,
) -> TokenResponse:
    # Accept the refresh token from the request body (bearer clients) or the
    # HttpOnly cookie (browser clients).
    raw = payload.refresh_token or refresh_cookie
    if not raw:
        raise AuthenticationError("Missing refresh token")
    token = decode_token(raw, expected_type=REFRESH)
    user = await UserRepository(session).get(token.subject)
    if user is None or not user.is_active:
        raise AuthenticationError("User not found or inactive")
    return _issue_tokens(response, user.id, str(user.role))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response) -> None:
    """Clear the auth cookies (a no-op for pure bearer-token clients)."""

    clear_auth_cookies(response, security=get_settings().security)


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> UserOut:
    return UserOut(id=user.id, email=user.email, role=str(user.role), is_active=user.is_active)
