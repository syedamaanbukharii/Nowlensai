"""Cookie-based auth + CSRF tests (SQLite-backed).

Verifies the HttpOnly-cookie session path layered on top of the existing
bearer-token flow: login sets cookies, cookie-authenticated writes require the
double-submit CSRF header, bearer requests bypass CSRF, and logout clears the
session.
"""

from __future__ import annotations

import pytest

from nowlens.api.cookies import ACCESS_COOKIE, CSRF_COOKIE, REFRESH_COOKIE


def _register(client, email: str = "cookie@example.com", password: str = "password123"):
    return client.post("/api/v1/auth/register", json={"email": email, "password": password})


def test_register_sets_auth_cookies(db_client) -> None:
    resp = _register(db_client)
    assert resp.status_code == 201
    # Tokens are still in the body (bearer clients) AND set as cookies.
    assert resp.json()["access_token"]
    assert resp.json()["csrf_token"]
    for name in (ACCESS_COOKIE, REFRESH_COOKIE, CSRF_COOKIE):
        assert name in db_client.cookies


def test_cookie_auth_works_for_safe_request(db_client) -> None:
    _register(db_client)
    # No Authorization header — the access cookie alone authenticates a GET.
    me = db_client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == "cookie@example.com"


def test_cookie_write_requires_csrf_header(db_client) -> None:
    _register(db_client)
    # Cookie-authenticated POST without the CSRF header is rejected.
    blocked = db_client.post("/api/v1/chat", json={"message": "hello there", "stream": False})
    assert blocked.status_code == 403
    assert blocked.json()["code"] == "authorization_error"

    # With the matching X-CSRF-Token header it succeeds.
    csrf = db_client.cookies.get(CSRF_COOKIE)
    ok = db_client.post(
        "/api/v1/chat",
        json={"message": "hello there", "stream": False},
        headers={"x-csrf-token": csrf},
    )
    assert ok.status_code == 200


def test_bearer_request_bypasses_csrf(db_client) -> None:
    token = _register(db_client).json()["access_token"]
    # Bearer auth can't be forged cross-site, so no CSRF header is required.
    resp = db_client.post(
        "/api/v1/chat",
        json={"message": "hello there", "stream": False},
        headers={"authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200


def test_logout_clears_cookies_and_session(db_client) -> None:
    _register(db_client)
    assert db_client.get("/api/v1/auth/me").status_code == 200

    out = db_client.post("/api/v1/auth/logout")
    assert out.status_code == 204
    assert db_client.cookies.get(ACCESS_COOKIE) in (None, "")

    # Session is gone: with cookies cleared, /me is unauthorized.
    assert db_client.get("/api/v1/auth/me").status_code == 401


def test_refresh_via_cookie_without_body(db_client) -> None:
    _register(db_client)
    # Browser clients hold the refresh token only in the cookie; an empty body
    # still refreshes and re-issues cookies.
    resp = db_client.post("/api/v1/auth/refresh", json={})
    assert resp.status_code == 200
    assert resp.json()["access_token"]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
