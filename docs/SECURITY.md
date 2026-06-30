# Security

This document describes NowLens's security model and the controls in `nowlens.security`. For how to report a vulnerability, see [../SECURITY.md](../SECURITY.md).

## Authentication

- **JWT bearer tokens.** Access tokens are short-lived and carry the subject (user id) and role; refresh tokens are long-lived and carry only the subject plus a `type` claim. All timestamps are UTC. Secret, algorithm, and TTLs come from `SecuritySettings`.
- **Token validation** (`security.jwt.decode_token`) checks the signature, expiry, expected token type, and presence of a subject, raising `AuthenticationError` (→ 401) on any failure.
- **Cookie or bearer.** `register`/`login`/`refresh` set the access and refresh JWTs as **HttpOnly** cookies (so JavaScript — and thus XSS — cannot read them) *and* return them in the JSON body. `current_user` accepts the token from either the `Authorization: Bearer` header (API clients) or the access cookie (browsers), header first. `logout` clears the cookies. This is fully backward compatible: existing bearer-token clients are unaffected.
- **CSRF.** Because cookies are sent automatically, cookie-authenticated *writes* (unsafe methods) require a double-submit CSRF token — a readable `nowlens_csrf` cookie (also returned in the login body) echoed back in the `X-CSRF-Token` header (`deps.csrf_protect`, applied to the whole `/api/v1` surface). Bearer-authenticated requests are exempt (a cross-site page cannot set the `Authorization` header), as are the auth-establishment endpoints. Cookie scope is tunable via `NOWLENS_SECURITY__COOKIE_*` (Secure, SameSite, Domain) for same-site vs cross-site frontends.
- **First-user bootstrap.** The first registered account becomes `admin` so a fresh deployment has an operator; subsequent accounts default to `user`.

> **Production:** set a strong `NOWLENS_SECURITY__JWT_SECRET`. When `NOWLENS_ENVIRONMENT=production`, the application **refuses to start** if the secret is the built-in placeholder or shorter than 32 characters — a forgeable signing key is a fail-closed condition, not a warning.

## Passwords

- Hashed with **bcrypt** via passlib (`security.password`). Plaintext never leaves the module and is never logged.
- `verify_password` is constant-time and treats malformed hashes as failed verification. `needs_rehash` allows transparent upgrades when cost parameters change.
- passlib 1.7.4 is incompatible with bcrypt ≥ 4.1, so the dependency is pinned to the 4.0.x line (`bcrypt>=4.0,<4.1`).

## Authorisation (RBAC)

Roles are ranked `viewer (0) < user (1) < operator (2) < admin (3)` (`security.rbac.ROLE_RANK`). Checks are pure functions (`has_required_role`, `ensure_role`) so the rules are unit-tested and free of web-framework coupling; the FastAPI dependency `require_role(min)` enforces them per endpoint. Current policy:

- **user** — chat, search, sessions, domains.
- **operator** — ingestion submission, document/job listing, the config snapshot.
- **admin** — document deletion (and is the default for the first user in a tenant).

## Multi-tenancy & data isolation

Every tenant-scoped table (`users`, `chat_sessions`, `messages`, `documents`, `document_chunks`, `ingestion_jobs`, `audit_logs`) carries a non-null `tenant_id`. Isolation is enforced in depth:

- **Repositories** are constructed with a `tenant_id` and filter every read and write by it (`db.repositories`). A repository for tenant A cannot read, update, or delete tenant B's rows — covered by `tests/test_tenancy.py`.
- **Retrieval** is tenant-bound: Qdrant searches filter on an indexed `tenant_id` payload field, and the Postgres full-text query adds a tenant predicate, so a tenant only ever retrieves its own indexed documentation.
- **Tenant resolution** comes from the authenticated user's record (`deps.current_tenant_id`), so it travels with the verified identity — there is no client-supplied tenant header to spoof. The JWT format is unchanged.
- **Email is globally unique**, so login-by-email is unambiguous and the tenant is derived from the resolved user.
- **Platform vs tenant admin.** Tenant creation and cross-tenant user provisioning (`/api/v1/tenants`) are restricted to **platform admins** — admins of the seed `default` tenant (`deps.platform_admin`). A tenant's own admin manages only their tenant's data through the regular, already-scoped endpoints.

## Rate limiting

A sliding-window limiter (`security.rate_limit`) keyed by identity (authenticated subject, else client IP) allows `rate_limit_per_minute` requests per 60s plus a one-off `burst`. It uses a Redis sorted set when a client is available (so limits hold across processes) and falls back to a deterministic in-process window otherwise. Redis failures are logged and fall back to local state rather than failing open silently.

Identity is the **decoded token subject** when a valid bearer access token is present, else the client IP — so the budget follows a user across token refreshes rather than resetting each time. Rate-limited responses carry an RFC 6585 `Retry-After` header so clients can back off.

## Input handling and prompt injection

Defence-in-depth, not a guarantee:

- **Length + injection guard** (`guard_user_input`) runs at the API boundary on all free-text input. It enforces `max_input_chars` and blocks high-severity injection/jailbreak attempts (instruction override, role hijack, system-prompt or secret exfiltration, refusal bypass). Lower-severity hits are reported for logging rather than blocked, so benign mentions (e.g. a doc that discusses "system prompts") aren't rejected outright.
- **Indirect-injection scanning.** The chat path also scans retrieved *document* content (`scan_retrieved_context`) because instructions hidden in a crawled page are the more dangerous vector for a RAG system. Retrieved content is treated as data: a high score is logged and surfaced, not executed.
- **Sanitisation** (`security.sanitize`) provides a strict HTML cleaner (nh3 allow-list, scripts/handlers dropped, `rel` managed via `link_rel`), a plain-text stripper, and a control-character/Unicode normaliser for free text.

## Auditing

Security-relevant actions (register, login, chat answers, etc.) are recorded via `security.audit.audit_event`, which always logs a structured event and best-effort persists to the `audit_logs` table with the current trace id. Audit-store failures never break the audited action.

## Transport and data

- The API emits an `X-Trace-Id` per request for correlation; logs are structured (JSON in production).
- **Security headers** are attached to every response by `SecurityHeadersMiddleware`: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, and a restrictive `Permissions-Policy`. `Strict-Transport-Security` is added in production. Content-Security-Policy is intentionally left to the HTML-serving frontend (the API serves JSON plus the Swagger/ReDoc UIs).
- CORS is locked down to explicit methods (`GET, POST, DELETE, OPTIONS`) and headers (`Authorization, Content-Type, X-Trace-Id`) for the configured origins — no wildcards. Credentials are allowed only for those origins.
- The crawler caps each fetched response body at `NOWLENS_INGEST__MAX_DOCUMENT_BYTES` (default 5 MB), streaming and rejecting oversized responses instead of buffering them.
- Secrets are never serialised by the `/config` endpoint.
- The runtime container runs as a non-root user.

## Hardening checklist (production)

- [ ] Strong, unique `JWT_SECRET`; rotate periodically.
- [ ] TLS terminated at a reverse proxy/load balancer in front of the API.
- [ ] Restrict `/metrics` via network policy or place it behind auth if metrics are sensitive.
- [ ] Lock CORS to your real frontend origin(s).
- [ ] Provision Redis so rate limits are shared across replicas.
- [ ] Run migrations with a least-privilege DB role; the app role should not own DDL.
- [ ] Keep dependencies patched; the CI gate runs lint, type-check, and tests on every change.
