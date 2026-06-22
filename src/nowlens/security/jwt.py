"""JWT issuance and verification.

Access tokens are short-lived and carry the subject (user id) and role; refresh
tokens are long-lived and carry only the subject + a ``type`` claim. All times
are UTC. Secret/algorithm/TTLs come from :class:`SecuritySettings`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from nowlens.core.config import SecuritySettings, get_settings
from nowlens.core.exceptions import AuthenticationError

ACCESS = "access"
REFRESH = "refresh"


@dataclass(slots=True)
class TokenData:
    subject: str
    role: str
    token_type: str
    expires_at: datetime


def _cfg() -> SecuritySettings:
    return get_settings().security


def _encode(payload: dict[str, Any], cfg: SecuritySettings) -> str:
    return jwt.encode(payload, cfg.jwt_secret, algorithm=cfg.jwt_algorithm)


def create_access_token(subject: str, *, role: str, extra: dict[str, Any] | None = None) -> str:
    cfg = _cfg()
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "role": role,
        "type": ACCESS,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=cfg.access_token_ttl_min)).timestamp()),
    }
    if extra:
        payload.update(extra)
    return _encode(payload, cfg)


def create_refresh_token(subject: str) -> str:
    cfg = _cfg()
    now = datetime.now(UTC)
    payload = {
        "sub": subject,
        "type": REFRESH,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=cfg.refresh_token_ttl_days)).timestamp()),
    }
    return _encode(payload, cfg)


def decode_token(token: str, *, expected_type: str | None = None) -> TokenData:
    """Decode + validate a token, raising :class:`AuthenticationError` on failure."""

    cfg = _cfg()
    try:
        payload = jwt.decode(token, cfg.jwt_secret, algorithms=[cfg.jwt_algorithm])
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError("Token has expired") from exc
    except jwt.PyJWTError as exc:
        raise AuthenticationError("Invalid authentication token") from exc

    token_type = str(payload.get("type", ""))
    if expected_type is not None and token_type != expected_type:
        raise AuthenticationError(f"Expected a {expected_type} token")

    subject = payload.get("sub")
    if not subject:
        raise AuthenticationError("Token missing subject")

    return TokenData(
        subject=str(subject),
        role=str(payload.get("role", "user")),
        token_type=token_type,
        expires_at=datetime.fromtimestamp(int(payload.get("exp", 0)), tz=UTC),
    )
