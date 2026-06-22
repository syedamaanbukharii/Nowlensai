# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres
to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-06-22

Initial release.

### Added

- **Hybrid RAG retrieval** — Qdrant vector search fused with lexical search
  (in-memory BM25 / PostgreSQL full-text) via Reciprocal Rank Fusion, followed
  by reranking (lexical-overlap by default, optional sentence-transformers
  cross-encoder), sentence-level context compression, and document-level
  citations.
- **Multi-agent graph (LangGraph)** — deterministic intent router, knowledge
  retrieval, five specialists (best practices, business analysis, feature
  overlap, marketplace assessment, research), and a quality-assurance node that
  checks grounding and citation validity. Streaming and non-streaming chat.
- **Ingestion pipeline** — crawl → render (optional) → extract → clean →
  normalize → chunk → enrich → deduplicate (SimHash) → embed → validate → index,
  with retries, incremental re-crawl skips, and per-stage reporting.
- **Provider-agnostic LLM layer** — Ollama and Groq backends behind common
  chat/embedding interfaces, selected by configuration.
- **FastAPI surface** — auth (JWT register/login/refresh), chat, streaming chat
  (SSE), hybrid search, session management, ingestion + document admin, the
  ServiceNow domain catalogue with overlap analysis, a redacted config snapshot,
  health/readiness probes, and Prometheus metrics.
- **Security** — bcrypt passwords, RBAC (viewer/user/operator/admin), a
  sliding-window rate limiter (Redis-backed or in-process), HTML/text
  sanitisation, prompt-injection scanning (direct and indirect), and audit
  logging.
- **Persistence** — SQLAlchemy 2.0 async models, repositories, and Alembic
  migrations (PostgreSQL; Qdrant for vectors).
- **Observability** — structured logging with per-request trace ids, Prometheus
  metrics, and an optional Langfuse tracing hook.
- **CLI** — `serve`, `bootstrap`, `init-db`, `ingest`, `ask`, `version`.
- **Frontend** — Next.js (App Router) UI for chat, search, and admin.
- **Tooling & infra** — Docker image, Compose stack (API, Postgres, Qdrant,
  Redis, Prometheus, Grafana, Ollama, frontend), Makefile, pre-commit config,
  GitHub Actions CI, and a fully offline test suite.

[Unreleased]: https://example.com/nowlens-ai/compare/v0.1.0...HEAD
[0.1.0]: https://example.com/nowlens-ai/releases/tag/v0.1.0
