# Deployment

NowLens ships with a Docker Compose stack for local/single-host use and is straightforward to run on any container platform. This guide covers the stack, database migrations, the optional background worker, and production considerations.

## Components

| Service | Purpose | Default port |
|---|---|---|
| `api` | FastAPI app (uvicorn) | 8000 |
| `frontend` | Next.js UI | 3000 |
| `postgres` | Metadata + full-text search | 5432 |
| `qdrant` | Vector store | 6333 / 6334 |
| `redis` | Shared rate-limit state, optional queue | 6379 |
| `ollama` | Local LLM + embeddings | 11434 |
| `prometheus` | Metrics scraping | 9090 |
| `grafana` | Dashboards | 3001 |

## Quickstart

```bash
cp .env.example .env
docker compose up -d --build

# Pull models into Ollama (first run only):
docker compose exec ollama ollama pull llama3.1:8b
docker compose exec ollama ollama pull nomic-embed-text

# Initialise stores:
docker compose exec api alembic upgrade head
docker compose exec api nowlens bootstrap

docker compose exec api curl -fsS localhost:8000/health/ready
```

## Database migrations

Schema is managed with **Alembic** (`alembic.ini` → `src/nowlens/db/migrations`). The initial migration is `0001_initial`.

```bash
alembic upgrade head            # apply all migrations
alembic revision --autogenerate -m "describe change"   # create a new migration
alembic downgrade -1            # roll back one
```

`nowlens init-db` creates tables directly via `Base.metadata.create_all` — convenient for local development, but **production should always use Alembic** so schema changes are versioned and reviewable.

> **Note on `document_chunks`.** Its `tsv` column is a database-generated `tsvector` with a GIN index, and `domains`/`keywords` are PostgreSQL arrays — these require PostgreSQL. SQLite is used only in the test suite (with the full-text table omitted), never in deployment.

## Configuration in production

Provide configuration via environment variables (see [CONFIGURATION.md](CONFIGURATION.md)). At minimum:

- `NOWLENS_ENVIRONMENT=production`
- A strong `NOWLENS_SECURITY__JWT_SECRET`
- `NOWLENS_DATABASE_URL`, `NOWLENS_QDRANT_URL`, `NOWLENS_REDIS_URL` pointing at managed services
- `NOWLENS_LLM__PROVIDER` and the matching model/endpoint settings (set `NOWLENS_LLM__GROQ_API_KEY` if using Groq)
- `NOWLENS_CORS_ORIGINS` set to your real frontend origin(s)

`embedding_dim` **must** match both the embedding model and the Qdrant collection vector size (nomic-embed-text → 768). Changing the embedding model means recreating the collection and re-ingesting.

## Background ingestion worker (optional)

By default, queued ingestion runs as a FastAPI `BackgroundTask` in the API process — fine for light use. For a durable, horizontally-scalable queue, install the `worker` extra and run the arq worker against Redis:

```bash
pip install -e ".[worker]"
arq nowlens.workers.arq_worker.WorkerSettings
```

The worker module is import-safe without arq installed (the queue settings are only constructed when arq is present), so the API and tests don't require it.

## Kubernetes

Cloud-agnostic manifests live in [`k8s/`](../k8s) (see [`k8s/README.md`](../k8s/README.md)). They cover the API and frontend Deployments + Services, a ConfigMap, a Secret template, an HPA, an Ingress, and a one-shot migration/bootstrap Job — applied with `kubectl apply -k k8s/`. Postgres, Qdrant, and Redis are referenced by URL and expected to be provided as managed services or deployed separately, which keeps the same manifests portable across EKS/AKS/GKE: only endpoints, the ingress class, and the image registry differ between clouds.

```bash
kubectl apply -f k8s/namespace.yaml
kubectl -n nowlens create secret generic nowlens-secrets \
  --from-literal=NOWLENS_SECURITY__JWT_SECRET="$(python -c 'import secrets;print(secrets.token_urlsafe(48))')" \
  --from-literal=NOWLENS_DATABASE_URL="postgresql+asyncpg://user:pass@host:5432/nowlens"
kubectl apply -k k8s/
kubectl -n nowlens wait --for=condition=complete job/nowlens-migrate --timeout=300s
```

## Scaling

- **API** is stateless — run multiple replicas behind a load balancer. Provision Redis so the rate limiter shares state across replicas (otherwise each replica enforces its own budget).
- **Qdrant** and **PostgreSQL** should be managed/clustered per their own guidance for HA.
- **Generation** is the latency bottleneck. Use Groq or a GPU-backed Ollama for production throughput; tune `NOWLENS_RAG__FINAL_TOP_K` and enable context compression to control prompt size.
- The uvicorn worker count is set via `nowlens serve --workers N` (or run one process per container and scale containers).

## Observability

- **Metrics** at `/metrics` (Prometheus format) — request volume/latency (by route template), retrieval latency and chunk counts, agent runs by intent, ingestion counters, and LLM token usage. Prometheus is pre-configured to scrape `api:8000`; a starter Grafana dashboard is provisioned.
- **Tracing.** Every request carries an `X-Trace-Id` (propagated from inbound headers if present) that appears on every log line and in error envelopes. Optional Langfuse tracing can be enabled with the `langfuse` extra.
- **Logs** are structured (JSON when `LOG_JSON=true`) and written to stderr.

## Health & readiness

- `GET /health/live` — liveness; never touches dependencies. Use for container liveness probes.
- `GET /health/ready` — readiness; probes DB, Qdrant, and Redis and returns 503 if any required component is down. Use for load-balancer/orchestrator readiness gates.

## Backups & DR

- Back up PostgreSQL (system of record for metadata) and Qdrant storage (vectors). Because the corpus is rebuildable by re-ingesting source URLs, Qdrant can also be reconstructed from PostgreSQL chunk rows + re-embedding if needed.
- Keep the list of seed URLs (e.g. `data/sample/seed_urls.txt`) under version control so the knowledge base is reproducible.
