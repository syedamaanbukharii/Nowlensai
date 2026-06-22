"""Security primitives: auth, RBAC, rate limiting, input defence, auditing."""

from nowlens.security.audit import audit_event
from nowlens.security.jwt import (
    ACCESS,
    REFRESH,
    TokenData,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from nowlens.security.password import hash_password, needs_rehash, verify_password
from nowlens.security.prompt_injection import (
    InjectionAssessment,
    guard_user_input,
    scan,
    scan_retrieved_context,
)
from nowlens.security.rate_limit import RateLimitDecision, RateLimiter
from nowlens.security.rbac import ROLE_RANK, ensure_role, has_required_role, role_rank
from nowlens.security.sanitize import clean_user_text, sanitize_html, strip_html

__all__ = [
    "ACCESS",
    "REFRESH",
    "ROLE_RANK",
    "InjectionAssessment",
    "RateLimitDecision",
    "RateLimiter",
    "TokenData",
    "audit_event",
    "clean_user_text",
    "create_access_token",
    "create_refresh_token",
    "decode_token",
    "ensure_role",
    "guard_user_input",
    "has_required_role",
    "hash_password",
    "needs_rehash",
    "role_rank",
    "sanitize_html",
    "scan",
    "scan_retrieved_context",
    "strip_html",
    "verify_password",
]
