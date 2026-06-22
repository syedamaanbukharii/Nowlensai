# API reference

Base URL (local): `http://localhost:8000`. Versioned endpoints live under `/api/v1`. Interactive docs are served at `/docs` (Swagger) and `/redoc`; the OpenAPI schema is at `/openapi.json`.

## Authentication

NowLens uses JWT bearer tokens. Register or log in to obtain an `access_token` (short-lived) and a `refresh_token` (long-lived), then send the access token on protected requests:

```
Authorization: Bearer <access_token>
```

The **first** account to register is bootstrapped as `admin`; every subsequent account defaults to `user` and must be promoted by an admin out of band. Roles are ranked `viewer < user < operator < admin`; endpoints state the minimum role required.

## Error envelope

Every error (domain, validation, or unexpected) returns the same shape:

```json
{ "code": "not_found", "message": "Session not found", "trace_id": "a1b2c3..." }
```

| HTTP | `code` | Cause |
|------|--------|-------|
| 401 | `authentication_error` | missing/invalid/expired token |
| 403 | `authorization_error` | role too low |
| 404 | `not_found` | unknown/unowned resource |
| 422 | `validation_error` | bad request body / params |
| 422 | `prompt_injection_detected` | input tripped the injection guard |
| 429 | `rate_limited` | per-identity budget exceeded |
| 502 | `provider_error` / `retrieval_error` | upstream LLM / Qdrant failure |
| 500 | `internal_error` | unexpected |

The `X-Trace-Id` response header carries the same id as the body for correlation with logs.

## Meta & health

| Method & path | Description |
|---|---|
| `GET /` | Service metadata (name, version, environment) |
| `GET /health/live` | Liveness — never touches dependencies |
| `GET /health/ready` | Readiness — probes DB, Qdrant, Redis; 503 if any fails |
| `GET /metrics` | Prometheus text exposition (unauthenticated by default) |

`/health/ready` reports each component independently:

```json
{ "ready": true, "components": [
  { "name": "database", "ok": true, "detail": "" },
  { "name": "qdrant", "ok": true, "detail": "" },
  { "name": "redis", "ok": true, "detail": "not configured (in-process limiting)" }
]}
```

## Auth

| Method & path | Auth | Body |
|---|---|---|
| `POST /api/v1/auth/register` | — | `{email, password}` → `201 TokenResponse` |
| `POST /api/v1/auth/login` | — | `{email, password}` → `TokenResponse` |
| `POST /api/v1/auth/refresh` | — | `{refresh_token}` → `TokenResponse` |
| `GET /api/v1/auth/me` | user | → `{id, email, role, is_active}` |

`TokenResponse`: `{access_token, refresh_token, token_type: "bearer", expires_in}`. Passwords must be 8–256 characters.

```bash
curl -s localhost:8000/api/v1/auth/register \
  -H 'content-type: application/json' \
  -d '{"email":"me@example.com","password":"change-me-please"}'
```

## Chat & search

### `POST /api/v1/chat` (user)

Runs the full agent graph and returns a structured, QA-annotated answer.

Request:

```json
{
  "message": "How should I model major incidents in ITSM?",
  "session_id": null,
  "domains": [],
  "history": [{ "role": "user", "content": "..." }],
  "final_top_k": null,
  "stream": false
}
```

`session_id` is optional — omit it to create a new session (its id is returned). `domains` optionally constrains retrieval; otherwise domains are detected. `final_top_k` (1–20) overrides the chunk budget.

Response:

```json
{
  "session_id": "…",
  "answer": "…",
  "intent": "best_practice",
  "domains": ["itsm"],
  "citations": [
    { "index": 1, "chunk_id": "…", "document_id": "…",
      "title": "…", "source_url": "…", "snippet": "…" }
  ],
  "analysis": null,
  "qa": { "grounded": true, "citations_valid": true, "verdict": "pass" },
  "grounded": true,
  "metrics": { }
}
```

`analysis` is populated for the structured specialists (business analysis, feature overlap, marketplace); it is `null` for plain best-practice/research answers.

### `POST /api/v1/chat/stream` (user)

Same request body. Returns `text/event-stream`. Event sequence:

```
event: session    data: {"session_id":"…"}
event: citations  data: {"citations":[…],"grounded":true}
event: token      data: {"delta":"…"}        (repeated)
event: done       data: {"answer":"…","grounded":true}
```

A terminal `event: error` is emitted instead of `done` if generation fails.

### `POST /api/v1/search` (user)

Hybrid retrieval with no generation — a "sources only" experience.

Request: `{ "query": "...", "domains": [], "top_k": null }`.

Response: `{ query, hits: [{chunk_id, score, title, source_url, domains, snippet, retriever}], citations: [...], metrics }`.

## Sessions

| Method & path | Auth | Description |
|---|---|---|
| `GET /api/v1/sessions` | user | List the caller's sessions (most recent first) |
| `POST /api/v1/sessions` | user | Create a session → `201` |
| `GET /api/v1/sessions/{id}` | user | Session detail |
| `GET /api/v1/sessions/{id}/messages` | user | Full transcript, oldest first |
| `DELETE /api/v1/sessions/{id}` | user | Delete → `204` |

Sessions are owned by the authenticated user; touching another user's session returns `404` (not `403`) so existence is never leaked.

## Ingestion & documents

| Method & path | Auth | Description |
|---|---|---|
| `POST /api/v1/ingest` | operator | Submit URLs |
| `GET /api/v1/documents` | operator | List ingested documents |
| `GET /api/v1/jobs` | operator | List ingestion jobs |
| `DELETE /api/v1/documents/{id}` | admin | Delete a document, its chunks, and its vectors |

`POST /ingest` body: `{ "urls": ["https://…"], "wait": false }` (1–200 URLs). With `wait: true` the pipeline runs inline and returns per-URL reports (`IngestInlineResponse`); otherwise a job is created per URL, the work runs in the background, and the job ids are returned (`IngestEnqueueResponse`) for polling via `GET /jobs`.

A report includes the per-stage outcomes:

```json
{ "url": "…", "document_id": "…", "success": true,
  "chunks_indexed": 12, "duplicates_removed": 3, "skipped": false,
  "error": null,
  "stages": [{ "name": "crawl", "ok": true, "detail": "attempt 1", "items": 24512 }, …] }
```

## Domains

| Method & path | Auth | Description |
|---|---|---|
| `GET /api/v1/domains` | user | The full domain catalogue |
| `GET /api/v1/domains/{key}` | user | One domain (`404` if unknown) |
| `POST /api/v1/domains/overlap` | user | Structural overlap between two domains |

`POST /domains/overlap` body `{domain_a, domain_b}` → `{domain_a, domain_b, related, shared_neighbours}`. Unknown domains return `404`.

## Config

`GET /api/v1/config` (operator) returns a redacted snapshot of effective configuration — provider, models, retrieval parameters, rate limit, and the supported domains. **Secrets (JWT secret, API keys, DB credentials) are never serialised.**

## Rate limiting

A sliding-window limiter applies per identity (authenticated subject when present, else client IP): `rate_limit_per_minute` requests per 60s plus a one-off `burst` allowance. State is shared via Redis when configured, otherwise per-process. Exceeding the budget returns `429` with `retry_after` in the message.
