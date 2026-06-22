"""Role-based access control helpers.

Pure functions over role strings so the rules are unit-testable and free of any
web-framework coupling. The FastAPI dependency that calls :func:`ensure_role`
lives in :mod:`nowlens.api.deps`.
"""

from __future__ import annotations

from nowlens.core.exceptions import AuthorizationError
from nowlens.db.models import Role

# Higher number = more privilege. Used for "at least this role" checks.
ROLE_RANK: dict[str, int] = {
    Role.VIEWER.value: 0,
    Role.USER.value: 1,
    Role.OPERATOR.value: 2,
    Role.ADMIN.value: 3,
}


def role_rank(role: str) -> int:
    return ROLE_RANK.get(role, -1)


def has_required_role(user_role: str, required: Role) -> bool:
    return role_rank(user_role) >= role_rank(required.value)


def ensure_role(user_role: str, required: Role) -> None:
    """Raise :class:`AuthorizationError` unless ``user_role`` meets ``required``."""

    if not has_required_role(user_role, required):
        raise AuthorizationError(f"Requires '{required.value}' role or higher (have '{user_role}')")
