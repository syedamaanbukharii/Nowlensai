# NowLens AI

**A multi-agent, multi-platform enterprise intelligence platform: pluggable Domain Packs, automatic platform detection, hybrid RAG retrieval, a LangGraph agent graph, and an automated ingestion pipeline — behind a typed, observable FastAPI.**

NowLens answers deep questions about enterprise platforms — **ServiceNow, Salesforce, and Jira today, more via plugins** — by retrieving from a curated corpus and reasoning over it with a graph of specialist agents. The platform core is platform-agnostic: each ecosystem is a **Domain Pack** discovered at runtime, and the system **automatically detects the platform, module, and user role** from the question — the user never selects one. It is provider-agnostic (chat via Ollama or Groq; embeddings via Ollama or any OpenAI-compatible service), stores vectors in Qdrant and metadata in PostgreSQL, and ships as a **multi-tenant**, cloud-agnostic SaaS platform: HttpOnly-cookie auth with CSRF, RBAC, tenant data isolation, rate limiting, prompt-injection defences, security headers, Prometheus metrics, a Next.js frontend, and Kubernetes manifests.

---

## Table of contents

- [Why NowLens](#why-nowlens)
- [Architecture](#architecture)
- [Quickstart (Docker)](#quickstart-docker)
- [Local development](#local-development)
- [Configuration](#configuration)
- [CLI](#cli)
- [API surface](#api-surface)
- [Testing & quality](#testing--quality)
- [Project layout](#project-layout)
- [What is verified vs. what needs services](#what-is-verified-vs-what-needs-services)
- [Documentation](#documentation)
- [License](#license)

---

## Why NowLens

Enterprise platforms are broad and numerous: a single question ("should we use CSM or ITSM?", "how do I write an Apex trigger?", "build a JQL filter for my board") spans many products, constructs, and *platforms*. NowLens treats this as a plugin-plus-retrieval-plus-reasoning problem:

- **Domain Packs** — each platform (ServiceNow, Salesforce, Jira, …) is a self-contained pack the core discovers via Python entry-points. **Adding a platform requires only installing a pack — no change to the core.** See [docs/DOMAIN_PACKS.md](docs/DOMAIN_PACKS.md).
- **Automatic detection** — the agent graph resolves the **platform** (via the pack registry), the **module** within it, and the user's **role** from the question, then routes accordingly. No manual platform selection.
- **Hybrid retrieval** — dense vector search (Qdrant) fused with lexical search (BM25 / PostgreSQL full-text) via Reciprocal Rank Fusion, then reranked and compressed, so answers are grounded in real documentation with citations.
- **Specialist agents** — a deterministic router dispatches each question to the right specialist (best practices, business analysis, feature overlap, marketplace assessment, research), and a quality-assurance node checks grounding and citation validity before the answer is returned.
- **Automated ingestion** — a documented crawl → extract → clean → normalize → chunk → enrich → dedup → embed → validate → index pipeline keeps the corpus fresh, with incremental re-crawls and per-stage reporting.

Everything depends only on provider-agnostic interfaces, so swapping Ollama for Groq, pointing embeddings at a hosted OpenAI-compatible service, adding a platform pack, or adding a backend is a configuration/plugin change — never a core rewrite.

### Enterprise / production readiness

- **Pluggable platforms (Domain Packs)** — the core owns no platform data. Packs (ServiceNow, Salesforce, Jira) are discovered via the `nowlens.domain_packs` entry-point group; a new platform ships as a distribution, and detection distinguishes them automatically. See [docs/DOMAIN_PACKS.md](docs/DOMAIN_PACKS.md).
- **Multi-tenant isolation** — every tenant-scoped table carries a `tenant_id`; repositories and hybrid retrieval (Qdrant payload filter + Postgres FTS predicate) scope all reads and writes to the caller's tenant. Platform admins provision tenants and users via `/api/v1/tenants`. The tenant is resolved from the authenticated user, so the token format is unchanged.
- **Browser-safe auth** — access/refresh JWTs are issued as **HttpOnly cookies** (XSS-resistant) with double-submit **CSRF** protection, while the bearer-token flow stays fully supported for API clients.
- **Security by default** — production refuses to boot with a weak JWT secret; responses carry hardening headers; CORS is locked to explicit methods/headers; rate limiting keys on the user; crawled responses are size-capped.
- **Cloud-agnostic deployment** — multi-stage Docker images, Docker Compose, and Kubernetes manifests (`k8s/`) run unchanged on AWS/Azure/GCP; only backing-service endpoints differ. CI verifies lint, types, tests (Python 3.11 + 3.12), the frontend build, and both Docker images.

## Architecture

```
                    ┌──────────────┐
   HTTP  ──────────▶│   FastAPI    │  auth · RBAC · rate limit · tracing · metrics
                    └──────┬───────┘
                           │
          ┌────────────────┼─────────────────────┐
          ▼                ▼                     ▼
   ┌────────────┐   ┌──────────────┐      ┌──────────────┐
   │  Agent     │   │  Hybrid      │      │  Ingestion   │
   │  graph     │──▶│  retriever   │      │  pipeline    │
   │ (LangGraph)│   │  (RRF+rerank)│      │ (crawl→index)│
   └─────┬──────┘   └──────┬───────┘      └──────┬───────┘
         │                 │                     │
         ▼                 ▼                     ▼
   ┌────────────┐   ┌──────────────┐      ┌──────────────┐
   │ LLM (Ollama│   │   Qdrant     │      │ PostgreSQL   │
   │  / Groq)   │   │  (vectors)   │      │ (metadata +  │
   └────────────┘   └──────────────┘      │  full-text)  │
                                          └──────────────┘
```

The agent graph is a single forward pass: `detect → route → knowledge_retrieval → <specialist> → quality_assurance`, where `detect` resolves platform/module/role. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full design.

## Quickstart (Docker)

The compose stack runs the API, PostgreSQL, Qdrant, Redis, Prometheus, Grafana, and an Ollama container.

```bash
cp .env.example .env          # adjust if you like (defaults work for local)
docker compose up -d --build  # start everything

# Pull the default models into the Ollama container (first run only):
docker compose exec ollama ollama pull llama3.1:8b
docker compose exec ollama ollama pull nomic-embed-text

# Apply database migrations and create the Qdrant collection:
docker compose exec api alembic upgrade head
docker compose exec api nowlens bootstrap

# Smoke test:
curl -s localhost:8000/health/ready | jq
```

Then register the first user (bootstrapped as `admin`), and ingest a few pages:

```bash
# Register (first account becomes admin):
curl -s localhost:8000/api/v1/auth/register \
  -H 'content-type: application/json' \
  -d '{"email":"me@example.com","password":"change-me-please"}' | jq

# Ingest seed URLs (operator role; inline mode returns reports):
curl -s localhost:8000/api/v1/ingest \
  -H "authorization: Bearer $TOKEN" -H 'content-type: application/json' \
  -d '{"urls":["https://www.servicenow.com/docs"],"wait":true}' | jq
```

| Service     | URL                          |
|-------------|------------------------------|
| API         | http://localhost:8000        |
| API docs    | http://localhost:8000/docs   |
| Frontend    | http://localhost:3000        |
| Qdrant      | http://localhost:6333        |
| Prometheus  | http://localhost:9090        |
| Grafana     | http://localhost:3001        |

## Local development

Requires Python 3.11+.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"           # core + dev tooling
# optional extras: ".[rerank]" (cross-encoder), ".[render]" (JS rendering),
#                  ".[worker]" (arq queue), ".[langfuse]" (tracing)

# Run the checks:
make lint        # ruff
make typecheck   # mypy
make test        # pytest (fully offline — no external services needed)
make format      # black + ruff --fix

# Run the API against local Postgres/Qdrant/Ollama:
nowlens serve --reload
```

The entire test suite runs offline against in-memory fakes (see [Testing & quality](#testing--quality)).

## Configuration

All configuration is environment-driven through a single typed `Settings` object (`nowlens.core.config`); nothing reads `os.environ` directly. Variables use the `NOWLENS_` prefix, and nested groups use `__` (e.g. `NOWLENS_RAG__FINAL_TOP_K=8`). See [docs/CONFIGURATION.md](docs/CONFIGURATION.md) and [`.env.example`](.env.example) for the full reference. Highlights:

| Variable | Default | Purpose |
|----------|---------|---------|
| `NOWLENS_LLM__PROVIDER` | `ollama` | Chat backend: `ollama` or `groq` |
| `NOWLENS_LLM__EMBEDDING_PROVIDER` | `ollama` | Embedding backend: `ollama` or `openai` (OpenAI-compatible) |
| `NOWLENS_PACKS__ENABLED` | _(all)_ | Comma-separated allow-list of Domain Packs to load; empty loads all discovered |
| `NOWLENS_PACKS__DEFAULT` | `servicenow` | Platform assumed when detection is inconclusive |
| `NOWLENS_LLM__OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama endpoint |
| `NOWLENS_DATABASE_URL` | `postgresql+asyncpg://nowlens:nowlens@localhost:5432/nowlens` | Postgres DSN |
| `NOWLENS_QDRANT_URL` | `http://localhost:6333` | Qdrant endpoint |
| `NOWLENS_REDIS_URL` | `redis://localhost:6379/0` | Redis (rate-limit sharing) |
| `NOWLENS_SECURITY__JWT_SECRET` | _dev default_ | **set a strong secret in production** (boot fails otherwise) |
| `NOWLENS_SECURITY__COOKIE_SECURE` | `false` | Mark auth cookies `Secure`; set `true` in production |
| `NOWLENS_RAG__FINAL_TOP_K` | `6` | Chunks fed to the generator |

## CLI

Installed as `nowlens` (entry point `nowlens.cli:main`). JSON goes to stdout; logs go to stderr, so output is pipeable.

```bash
nowlens serve [--host --port --reload --workers]   # run the API (uvicorn)
nowlens bootstrap                                   # create the Qdrant collection
nowlens init-db                                     # create tables (dev; prod uses Alembic)
nowlens ingest URL [URL ...] | --file urls.txt      # ingest docs, prints JSON reports
nowlens ask "how do I model incidents?" [--json]    # query the agent graph
nowlens version
```

## API surface

Base path `/api/v1`. Full request/response details in [docs/API.md](docs/API.md).

| Method & path | Auth | Description |
|---------------|------|-------------|
| `GET /` | — | Service metadata |
| `GET /health/live` | — | Liveness |
| `GET /health/ready` | — | Readiness (DB, Qdrant, Redis) |
| `GET /metrics` | — | Prometheus metrics |
| `POST /api/v1/auth/register` | — | Register (first user per tenant → admin); sets auth cookies |
| `POST /api/v1/auth/login` | — | Obtain tokens; sets HttpOnly cookies + CSRF |
| `POST /api/v1/auth/refresh` | — | Refresh (token from cookie or body) |
| `POST /api/v1/auth/logout` | — | Clear auth cookies |
| `GET /api/v1/auth/me` | user | Current user |
| `POST /api/v1/chat` | user | Full agent graph (non-streaming) |
| `POST /api/v1/chat/stream` | user | Grounded answer over SSE |
| `POST /api/v1/search` | user | Hybrid retrieval (no generation) |
| `GET /api/v1/sessions` | user | List sessions |
| `POST /api/v1/sessions` | user | Create session |
| `GET /api/v1/sessions/{id}` | user | Session detail |
| `GET /api/v1/sessions/{id}/messages` | user | Session transcript |
| `DELETE /api/v1/sessions/{id}` | user | Delete session |
| `POST /api/v1/ingest` | operator | Submit URLs (inline or queued) |
| `GET /api/v1/documents` | operator | List ingested documents |
| `GET /api/v1/jobs` | operator | List ingestion jobs |
| `DELETE /api/v1/documents/{id}` | admin | Delete a document + vectors |
| `GET /api/v1/domains` | user | Domain catalogue |
| `GET /api/v1/domains/{key}` | user | Domain detail |
| `POST /api/v1/domains/overlap` | user | Structural overlap analysis |
| `GET /api/v1/config` | operator | Redacted config snapshot |
| `POST /api/v1/tenants` | platform&nbsp;admin | Create a tenant |
| `GET /api/v1/tenants` | platform&nbsp;admin | List tenants |
| `POST /api/v1/tenants/{id}/users` | platform&nbsp;admin | Provision a user in a tenant |

Authentication accepts either an `Authorization: Bearer` token (API clients) or the HttpOnly access cookie (browsers); cookie-authenticated writes require the `X-CSRF-Token` header. *Platform admin* = an admin of the seed `default` tenant. Errors use a uniform envelope: `{"code": "...", "message": "...", "trace_id": "..."}`.

## Testing & quality

```bash
make test          # pytest, fully offline
make test-cov      # with coverage
make check         # lint + typecheck + test (the CI gate)
```

The suite (187 tests) covers pure logic (fusion, compression, citations, chunking, SimHash dedup, normalization, enrichment, validation, BM25, domains), the Domain Pack framework (registry, entry-point discovery, the ServiceNow/Salesforce/Jira packs, and automatic platform/module/role detection across all three), security (passwords, JWT, sanitisation, RBAC, rate limiting, prompt injection, the production-secret guard, security headers, cookie auth + CSRF), multi-tenant isolation, the OpenAI-compatible embedding provider (via mock transport), configuration parsing, the hybrid retriever, the ingestion pipeline end-to-end, the agent graph (including concurrency isolation), and the API via `TestClient`. External systems are replaced with in-memory fakes: a deterministic chat/embedding provider, an in-memory vector store, and an in-memory SQLite database for the persistence-backed endpoints. No network, Qdrant, Postgres, Ollama, or Groq is required to run the tests.

## Project layout

```
src/nowlens/
  core/          config, exceptions, logging, tracing, platform-neutral domain utils
  domain_packs/  Domain Pack framework + registry; servicenow / salesforce / jira packs
  llm/           provider-agnostic chat/embedding interfaces (Ollama, Groq, OpenAI)
  rag/           vector store, lexical, fusion, rerank, compression, retriever
  ingestion/     pipeline + stages (crawl…index)
  agents/        LangGraph nodes, detection (platform/module/role), prompts, graph wiring
  db/            SQLAlchemy models (multi-tenant), repositories, session, Alembic migrations
  security/      JWT, passwords, RBAC, rate limiting, sanitisation, injection
  observability/ Prometheus metrics, optional Langfuse tracing
  api/           FastAPI app, deps, middleware, cookies, routers, schemas
  workers/       background ingestion task (+ optional arq worker)
  cli.py         command-line interface
tests/           offline test suite
docs/            architecture, API, ingestion, security, deployment, config
frontend/        Next.js (App Router) UI
k8s/             cloud-agnostic Kubernetes manifests (kubectl apply -k k8s/)
```

## What is verified vs. what needs services

**Verified offline in this repo's tests:** all pure logic, the hybrid retriever, the ingestion pipeline, the agent graph, the API (via `TestClient` with fakes + SQLite), the CLI imports, and full `ruff` / `black` / `mypy` cleanliness. The frontend also builds cleanly (`npm run build`), type-checks (`tsc --noEmit`), and lints with no warnings.

**Requires live services / extras (exercised in deployment, not in unit tests):** Qdrant, PostgreSQL (asyncpg), Redis, Ollama/Groq generation, the optional `arq` queue, Playwright JS rendering (`render` extra), and the sentence-transformers cross-encoder (`rerank` extra).

## Documentation

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — components, data flow, design decisions
- [docs/DOMAIN_PACKS.md](docs/DOMAIN_PACKS.md) — the Domain Pack framework + authoring a pack
- [docs/API.md](docs/API.md) — endpoint reference
- [docs/INGESTION.md](docs/INGESTION.md) — the ingestion pipeline
- [docs/SECURITY.md](docs/SECURITY.md) — auth, RBAC, hardening
- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) — Docker, migrations, scaling, workers, Kubernetes
- [docs/CONFIGURATION.md](docs/CONFIGURATION.md) — every setting
- [k8s/README.md](k8s/README.md) — Kubernetes manifests (EKS/AKS/GKE)
- [CONTRIBUTING.md](CONTRIBUTING.md) · [SECURITY.md](SECURITY.md) · [CHANGELOG.md](CHANGELOG.md)

## License

Apache-2.0 — see [LICENSE](LICENSE).
