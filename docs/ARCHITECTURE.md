# Architecture

NowLens is a retrieval-augmented, multi-agent system behind a typed FastAPI. This document explains the components, how a request flows through them, and the design decisions behind the structure.

## Goals and principles

- **Provider-agnostic.** Business logic depends only on the `LLMProvider` / `EmbeddingProvider` interfaces (`nowlens.llm.base`). Chat (Ollama, Groq) and embeddings (Ollama, OpenAI-compatible) are selected independently by configuration — so a hosted chat model can pair with local or hosted embeddings; adding a backend is a factory change, never an application change.
- **Grounded answers.** Generation is always paired with retrieval and citations, and a quality-assurance step checks grounding before an answer is returned. A degraded "no knowledge base" mode is explicit rather than silently hallucinated.
- **Each stage independently testable.** Retrieval, ingestion, and the agent graph are wired from small, pure-where-possible units. The whole system runs offline against in-memory fakes (see the test suite).
- **One place per concern.** Configuration lives in `core.config`; SQL lives in `db.repositories`; provider construction lives in `llm.factory` and the `services` composition root. Nothing reads `os.environ` directly.

## Component map

```
core/          Settings, typed exceptions, structured logging, trace ids,
               and the ServiceNow domain registry (≈two dozen capability areas).
llm/           Provider-agnostic chat + embedding ABCs; Ollama and Groq clients;
               an lru-cached factory.
rag/           QdrantVectorStore, lexical retrievers (BM25 / Postgres FTS),
               Reciprocal Rank Fusion, rerankers, context compression,
               citations, and the HybridRetriever that wires them.
ingestion/     The pipeline orchestrator and its stages (crawl, render, extract,
               clean, normalize, chunk, enrich, dedup, embed, validate, index).
agents/        LangGraph nodes (router, knowledge retrieval, five specialists,
               quality assurance), prompts, shared state, and graph wiring.
db/            SQLAlchemy 2.0 async models, repositories (the only SQL),
               session management, and Alembic migrations.
security/      JWT issuance/verification, bcrypt passwords, RBAC, a sliding-window
               rate limiter, HTML/text sanitisation, prompt-injection scanning,
               and audit logging.
observability/ Prometheus metrics and an optional Langfuse tracing hook.
api/           The FastAPI app factory, dependency providers, ASGI middleware,
               routers, and Pydantic schemas.
workers/       The background ingestion task and an optional arq worker.
services.py    Composition root: builds retrievers, agent contexts, and the
               ingestion pipeline from settings + a DB session.
```

## Request flow — chat

```
POST /api/v1/chat
  → auth (decode JWT, load active user)         [api.deps.current_user]
  → rate limit (per identity)                   [api.deps.rate_limit]
  → guard_user_input (length + injection)       [security.prompt_injection]
  → resolve/create ChatSession, persist user msg [db.repositories]
  → run_answer(ctx, message, …)                 [agents.graph]
        START
          → route                 classify intent + resolve domains (deterministic)
          → knowledge_retrieval   HybridRetriever → context + citations
          → <specialist>          best_practices | business_analysis |
                                  feature_overlap | marketplace | research
          → quality_assurance     grounding + citation validity check
        END
  → persist assistant msg (+ intent/citations/qa), audit event
  → ChatResponse {answer, intent, domains, citations, qa, grounded, metrics}
```

`POST /chat/stream` runs a lower-latency single pass (retrieve → best-practice generation) and emits Server-Sent Events: `session` → `citations` → many `token` → `done` (or a terminal `error`). Validation, injection guarding, and session resolution all happen *before* streaming begins, so failures are ordinary HTTP errors rather than mid-stream surprises.

## Request flow — retrieval

`HybridRetriever.retrieve` is the public RAG entry point:

```
query
  ├─ embed query ─────────────▶ Qdrant vector search ┐
  └─ raw query ───────────────▶ lexical search        ├─▶ RRF fusion
                                                       ┘
     ▶ rerank ▶ context compression ▶ citations ▶ RetrievalResult
```

1. **Vector search** — the query is embedded and searched in Qdrant (cosine), optionally filtered by domain.
2. **Lexical search** — BM25 over an in-memory corpus, or PostgreSQL `ts_rank` full-text in production.
3. **Fusion** — Reciprocal Rank Fusion (`score = Σ 1/(k+rank)`) merges the two rankings by chunk id. RRF relies only on ranks, so it never has to reconcile incomparable raw scores (cosine vs BM25).
4. **Rerank** — a dependency-free lexical-overlap reranker by default; a sentence-transformers cross-encoder when the `rerank` extra is enabled.
5. **Compression** — each chunk is reduced to its query-relevant sentences (code blocks preserved verbatim) to cut prompt tokens and noise.
6. **Citations + context** — chunks are turned into a numbered context block and a parallel list of `Citation` objects; chunks from the same document collapse to one citation number.

`adaptive_top_k` tunes how many chunks reach the generator based on query complexity.

## The agent graph

LangGraph's `StateGraph` is the orchestration core. The graph is a single forward pass (no loops), which keeps execution bounded and deterministic:

- **route** (pure) resolves the working domain set and classifies intent with a deterministic, unit-testable heuristic. Specialist agents still do the heavy lifting with the LLM; routing only decides *which* specialist runs.
- **knowledge_retrieval** runs the hybrid retriever and writes context + citations into the state. With no retriever wired in, it returns a `grounded: false` state so downstream nodes flag the lack of grounding rather than pretending.
- **specialists** each assemble a prompt and call the provider-agnostic LLM. Structured specialists (business analysis, feature overlap, marketplace) return JSON that is parsed defensively and also rendered to prose, so the chat surface always has readable text.
- **quality_assurance** runs a deterministic citation check (do cited `[n]` markers exist?) and an LLM qualitative review, reconciling the two (a concrete out-of-range citation overrides any model claim of validity). QA degrades to the deterministic result if the LLM review fails.

Nodes receive an `AgentContext` (chat provider + optional retriever) bound at graph-build time, so the graph contains no global or provider coupling.

## Data model

PostgreSQL is the system of record for **metadata**: users, chat sessions and messages, ingestion jobs, document/chunk metadata, and the audit log. Vector embeddings live in **Qdrant**. The `document_chunks` table mirrors chunk metadata and adds a generated `tsvector` column (with a GIN index) that powers the lexical retriever; a second GIN index on `domains` backs metadata filtering. Repositories in `db.repositories` are the only place that talks SQL, so the ingestion `ChunkSink` protocol, the chat history endpoints, and the admin views all share one data-access layer.

## Cross-cutting concerns

- **Configuration** — a single typed `Settings` aggregates per-area settings groups, read from environment variables and an optional `.env`. `get_settings()` is process-cached.
- **Errors** — typed exceptions carry an HTTP status and a stable machine-readable `code`. One exception layer turns every `NowLensError` (plus validation and unexpected errors) into the uniform `{code, message, trace_id}` envelope.
- **Observability** — a pure-ASGI middleware establishes a trace id (propagated via `X-Trace-Id`), emits structured access logs, and records Prometheus counters/histograms keyed by the *route template* so label cardinality stays bounded. Logs go to stderr so CLI stdout stays clean.
- **Lifespan** — startup best-effort-ensures the Qdrant collection exists (a missing Qdrant must not stop the API booting; readiness reports it honestly); shutdown releases provider HTTP clients, cached singletons, and the database engine.

## Extension points

- **New LLM/embedding backend** — implement the `llm.base` interfaces and register in `llm.factory`.
- **New retriever** — implement the `LexicalRetriever` / `Reranker` protocols and wire via `services`.
- **New specialist agent** — add a node function and register it in `agents.graph._SPECIALISTS` plus the router vocabulary.
- **New domain** — extend the hand-maintained registry in `core.domains`.

See [INGESTION.md](INGESTION.md), [SECURITY.md](SECURITY.md), [CONFIGURATION.md](CONFIGURATION.md), and [DEPLOYMENT.md](DEPLOYMENT.md) for deeper dives.
