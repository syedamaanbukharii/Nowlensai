# NowLens AI

**A multi-agent ServiceNow expert: hybrid RAG retrieval, a LangGraph agent graph, and an automated documentation ingestion pipeline — behind a typed, observable FastAPI.**

NowLens answers ServiceNow questions (best practices, business analysis, feature overlap, marketplace readiness, research) by retrieving from a curated corpus of ingested documentation and reasoning over it with a graph of specialist agents. It is provider-agnostic (Ollama or Groq), stores vectors in Qdrant and metadata in PostgreSQL, and ships with authentication, RBAC, rate limiting, prompt-injection defences, Prometheus metrics, and a Next.js frontend.

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

ServiceNow is broad: a single question ("should we use CSM or ITSM for this?", "how do I publish a scoped app to the Store?", "what changed in the last release?") can span many products and platform constructs. NowLens treats this as a retrieval-plus-reasoning problem:

- **Hybrid retrieval** — dense vector search (Qdrant) fused with lexical search (BM25 / PostgreSQL full-text) via Reciprocal Rank Fusion, then reranked and compressed, so answers are grounded in real documentation with citations.
- **Specialist agents** — a deterministic router dispatches each question to the right specialist (best practices, business analysis, feature overlap, marketplace assessment, research), and a quality-assurance node checks grounding and citation validity before the answer is returned.
- **Automated ingestion** — a documented crawl → extract → clean → normalize → chunk → enrich → dedup → embed → validate → index pipeline keeps the corpus fresh, with incremental re-crawls and per-stage reporting.

Everything depends only on provider-agnostic interfaces, so swapping Ollama for Groq (or adding a backend) is a configuration change.

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

The agent graph is a single forward pass: `route → knowledge_retrieval → <specialist> → quality_assurance`. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full design.

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
| `NOWLENS_LLM__PROVIDER` | `ollama` | `ollama` or `groq` |
| `NOWLENS_LLM__OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama endpoint |
| `NOWLENS_DATABASE_URL` | `postgresql+asyncpg://nowlens:nowlens@localhost:5432/nowlens` | Postgres DSN |
| `NOWLENS_QDRANT_URL` | `http://localhost:6333` | Qdrant endpoint |
| `NOWLENS_REDIS_URL` | `redis://localhost:6379/0` | Redis (rate-limit sharing) |
| `NOWLENS_SECURITY__JWT_SECRET` | _dev default_ | **set a strong secret in production** |
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
| `POST /api/v1/auth/register` | — | Register (first user → admin) |
| `POST /api/v1/auth/login` | — | Obtain tokens |
| `POST /api/v1/auth/refresh` | — | Refresh access token |
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

Errors use a uniform envelope: `{"code": "...", "message": "...", "trace_id": "..."}`.

## Testing & quality

```bash
make test          # pytest, fully offline
make test-cov      # with coverage
make check         # lint + typecheck + test (the CI gate)
```

The suite (129 tests) covers pure logic (fusion, compression, citations, chunking, SimHash dedup, normalization, enrichment, validation, BM25, domains), security (passwords, JWT, sanitisation, RBAC, rate limiting, prompt injection), configuration parsing, the hybrid retriever, the ingestion pipeline end-to-end, the agent graph, and the API via `TestClient`. External systems are replaced with in-memory fakes: a deterministic chat/embedding provider, an in-memory vector store, and an in-memory SQLite database for the persistence-backed endpoints. No network, Qdrant, Postgres, Ollama, or Groq is required to run the tests.

## Project layout

```
src/nowlens/
  core/          config, exceptions, logging, tracing, domain registry
  llm/           provider-agnostic chat/embedding interfaces (Ollama, Groq)
  rag/           vector store, lexical, fusion, rerank, compression, retriever
  ingestion/     pipeline + stages (crawl…index)
  agents/        LangGraph nodes, prompts, graph wiring
  db/            SQLAlchemy models, repositories, session, Alembic migrations
  security/      JWT, passwords, RBAC, rate limiting, sanitisation, injection
  observability/ Prometheus metrics, optional Langfuse tracing
  api/           FastAPI app, deps, middleware, routers, schemas
  workers/       background ingestion task (+ optional arq worker)
  cli.py         command-line interface
tests/           offline test suite
docs/            architecture, API, ingestion, security, deployment, config
frontend/        Next.js (App Router) UI
```

## What is verified vs. what needs services

**Verified offline in this repo's tests:** all pure logic, the hybrid retriever, the ingestion pipeline, the agent graph, the API (via `TestClient` with fakes + SQLite), the CLI imports, and full `ruff` / `black` / `mypy` cleanliness. The frontend also builds cleanly (`npm run build`), type-checks (`tsc --noEmit`), and lints with no warnings.

**Requires live services / extras (exercised in deployment, not in unit tests):** Qdrant, PostgreSQL (asyncpg), Redis, Ollama/Groq generation, the optional `arq` queue, Playwright JS rendering (`render` extra), and the sentence-transformers cross-encoder (`rerank` extra).

## Documentation

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — components, data flow, design decisions
- [docs/API.md](docs/API.md) — endpoint reference
- [docs/INGESTION.md](docs/INGESTION.md) — the ingestion pipeline
- [docs/SECURITY.md](docs/SECURITY.md) — auth, RBAC, hardening
- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) — Docker, migrations, scaling, workers
- [docs/CONFIGURATION.md](docs/CONFIGURATION.md) — every setting
- [CONTRIBUTING.md](CONTRIBUTING.md) · [SECURITY.md](SECURITY.md) · [CHANGELOG.md](CHANGELOG.md)

## License

Apache-2.0 — see [LICENSE](LICENSE).
# Nowlensai
