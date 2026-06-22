"""Password hashing.

Uses bcrypt via passlib. Hashing parameters are centralised here so cost can be
tuned in one place. Plaintext passwords never leave this module.
"""

from __future__ import annotations

from passlib.context import CryptContext

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Return a bcrypt hash for ``password``."""

    return _pwd_context.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    """Constant-time verification of ``password`` against ``hashed``."""

    try:
        return _pwd_context.verify(password, hashed)
    except ValueError:
        # Malformed/unknown hash format — treat as a failed verification.
        return False


def needs_rehash(hashed: str) -> bool:
    """Whether a stored hash should be upgraded to current parameters."""

    return _pwd_context.needs_update(hashed)
