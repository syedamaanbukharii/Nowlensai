# Configuration reference

All configuration is read through a single typed `Settings` object (`nowlens.core.config`) from environment variables and an optional `.env` file. Nothing in the codebase reads `os.environ` directly — call `get_settings()` (process-cached) instead.

## Conventions

- Every variable is prefixed `NOWLENS_`.
- Nested settings groups use a **double underscore**: `NOWLENS_<GROUP>__<FIELD>`, e.g. `NOWLENS_RAG__FINAL_TOP_K=8`.
- Booleans accept `true`/`false` (case-insensitive). `NOWLENS_CORS_ORIGINS` is a comma-separated string.
- Values are validated and typed on load; invalid values fail fast at startup.

See [`.env.example`](../.env.example) for a ready-to-copy template.

## Core

| Variable | Type | Default | Notes |
|---|---|---|---|
| `NOWLENS_ENVIRONMENT` | enum | `development` | `development` \| `staging` \| `production` |
| `NOWLENS_APP_NAME` | str | `NowLens AI` | Shown in API metadata/title |
| `NOWLENS_DEBUG` | bool | `false` | Enables SQL echo and verbose behaviour |
| `NOWLENS_CORS_ORIGINS` | csv | `http://localhost:3000` | Allowed CORS origins |
| `NOWLENS_DATABASE_URL` | dsn | `postgresql+asyncpg://nowlens:nowlens@localhost:5432/nowlens` | Async PostgreSQL DSN |
| `NOWLENS_REDIS_URL` | dsn | `redis://localhost:6379/0` | Used for shared rate-limit state / optional queue |
| `NOWLENS_QDRANT_URL` | str | `http://localhost:6333` | Qdrant endpoint |
| `NOWLENS_QDRANT_API_KEY` | str? | — | Qdrant API key (if secured) |

## LLM (`NOWLENS_LLM__…`)

| Variable | Type | Default | Notes |
|---|---|---|---|
| `PROVIDER` | enum | `ollama` | `ollama` \| `groq` |
| `REQUEST_TIMEOUT_S` | float | `120.0` | Provider request timeout |
| `MAX_RETRIES` | int | `3` | Provider-level retries |
| `TEMPERATURE` | float | `0.1` | Default generation temperature |
| `OLLAMA_BASE_URL` | str | `http://localhost:11434` | |
| `OLLAMA_CHAT_MODEL` | str | `llama3.1:8b` | |
| `OLLAMA_EMBED_MODEL` | str | `nomic-embed-text` | |
| `GROQ_BASE_URL` | str | `https://api.groq.com/openai/v1` | OpenAI-compatible |
| `GROQ_API_KEY` | str? | — | Required when `PROVIDER=groq` |
| `GROQ_CHAT_MODEL` | str | `llama-3.1-70b-versatile` | |
| `EMBEDDING_DIM` | int | `768` | **Must match the embed model and the Qdrant collection size** |

## Retrieval (`NOWLENS_RAG__…`)

| Variable | Type | Default | Notes |
|---|---|---|---|
| `COLLECTION` | str | `nowlens_docs` | Qdrant collection name |
| `VECTOR_TOP_K` | int | `20` | Vector candidates before fusion |
| `LEXICAL_TOP_K` | int | `20` | Lexical candidates before fusion |
| `RRF_K` | int | `60` | Reciprocal-rank-fusion constant |
| `RERANK_CANDIDATES` | int | `20` | Fused candidates passed to rerank |
| `FINAL_TOP_K` | int | `6` | Chunks handed to the generator |
| `USE_CROSS_ENCODER` | bool | `false` | Requires the `rerank` extra |
| `CROSS_ENCODER_MODEL` | str | `cross-encoder/ms-marco-MiniLM-L-6-v2` | |
| `COMPRESSION_ENABLED` | bool | `true` | Sentence-level context compression |
| `COMPRESSION_RATIO` | float | `0.6` | Keep sentences scoring ≥ this fraction of the top sentence |

## Ingestion (`NOWLENS_INGEST__…`)

| Variable | Type | Default | Notes |
|---|---|---|---|
| `USER_AGENT` | str | `NowLensBot/0.1 (+https://example.com/nowlens)` | Crawl UA |
| `REQUEST_TIMEOUT_S` | float | `30.0` | Crawl timeout |
| `MAX_CONCURRENCY` | int | `5` | Concurrent fetches |
| `CRAWL_DELAY_S` | float | `0.5` | Politeness delay |
| `RESPECT_ROBOTS` | bool | `true` | Honour `robots.txt` |
| `CHUNK_SIZE` | int | `1200` | Target chars/chunk |
| `CHUNK_OVERLAP` | int | `200` | Overlap between chunks |
| `MIN_CHUNK_CHARS` | int | `120` | Drop shorter chunks |
| `SIMHASH_MAX_DISTANCE` | int | `3` | Near-duplicate threshold |
| `RENDER_JAVASCRIPT` | bool | `false` | Requires the `render` extra + browser |
| `AI_CLEANING` | bool | `true` | LLM-assisted cleaning (degrades to rules) |

## Security (`NOWLENS_SECURITY__…`)

| Variable | Type | Default | Notes |
|---|---|---|---|
| `JWT_SECRET` | str | _placeholder_ | **Set a strong value in production** |
| `JWT_ALGORITHM` | str | `HS256` | |
| `ACCESS_TOKEN_TTL_MIN` | int | `30` | Access token lifetime (minutes) |
| `REFRESH_TOKEN_TTL_DAYS` | int | `14` | Refresh token lifetime (days) |
| `RATE_LIMIT_PER_MINUTE` | int | `60` | Per-identity request budget |
| `RATE_LIMIT_BURST` | int | `20` | One-off burst allowance |
| `MAX_INPUT_CHARS` | int | `8000` | Max free-text input size |

## Observability (`NOWLENS_OBS__…`)

| Variable | Type | Default | Notes |
|---|---|---|---|
| `LOG_LEVEL` | str | `INFO` | |
| `LOG_JSON` | bool | `true` | JSON logs (recommended in production) |
| `LANGFUSE_ENABLED` | bool | `false` | Requires the `langfuse` extra |
| `LANGFUSE_HOST` | str | `https://cloud.langfuse.com` | |
| `LANGFUSE_PUBLIC_KEY` | str? | — | |
| `LANGFUSE_SECRET_KEY` | str? | — | |

## Frontend

The Next.js app reads `NEXT_PUBLIC_API_BASE_URL` (default `http://localhost:8000`) to locate the API from the browser.

## Tips

- Override single nested values without restating the group, e.g. `NOWLENS_RAG__FINAL_TOP_K=8`.
- For 12-factor deployments, set everything via the environment; `.env` is mainly a local-dev convenience.
- The `/api/v1/config` endpoint (operator role) returns the effective, **secret-redacted** configuration — handy for verifying what a running instance actually loaded.
