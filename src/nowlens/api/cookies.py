"""Auth cookie helpers.

Issues the access + refresh JWTs as **HttpOnly** cookies (so JavaScript — and
thus XSS — cannot read them) plus a readable CSRF token for the double-submit
defence. Tokens are still returned in the JSON body, so existing bearer-token
API clients keep working unchanged.
"""

from __future__ import annotations

import secrets

from fastapi import Response

from nowlens.core.config import SecuritySettings

ACCESS_COOKIE = "nowlens_access"
REFRESH_COOKIE = "nowlens_refresh"
# Readable by JS on purpose: the SPA echoes it back in the X-CSRF-Token header.
CSRF_COOKIE = "nowlens_csrf"
CSRF_HEADER = "x-csrf-token"


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def set_auth_cookies(
    response: Response,
    *,
    access_token: str,
    refresh_token: str,
    csrf_token: str,
    security: SecuritySettings,
) -> None:
    """Attach the access/refresh (HttpOnly) and CSRF (readable) cookies."""

    access_max_age = security.access_token_ttl_min * 60
    refresh_max_age = security.refresh_token_ttl_days * 24 * 3600
    secure = security.cookie_secure
    samesite = security.cookie_samesite
    domain = security.cookie_domain
    response.set_cookie(
        ACCESS_COOKIE,
        access_token,
        max_age=access_max_age,
        path="/",
        domain=domain,
        secure=secure,
        httponly=True,
        samesite=samesite,
    )
    response.set_cookie(
        REFRESH_COOKIE,
        refresh_token,
        max_age=refresh_max_age,
        path="/",
        domain=domain,
        secure=secure,
        httponly=True,
        samesite=samesite,
    )
    # Not HttpOnly: the SPA must read it to populate the CSRF header.
    response.set_cookie(
        CSRF_COOKIE,
        csrf_token,
        max_age=refresh_max_age,
        path="/",
        domain=domain,
        secure=secure,
        httponly=False,
        samesite=samesite,
    )


def clear_auth_cookies(response: Response, *, security: SecuritySettings) -> None:
    for name in (ACCESS_COOKIE, REFRESH_COOKIE, CSRF_COOKIE):
        response.delete_cookie(
            name,
            path="/",
            domain=security.cookie_domain,
            secure=security.cookie_secure,
            samesite=security.cookie_samesite,
        )
