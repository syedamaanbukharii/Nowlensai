"""NowLens AI — multi-agent ServiceNow guidance platform.

The package is organised into cohesive layers:

* ``nowlens.core``         configuration, logging, tracing, errors, domains
* ``nowlens.llm``          provider-agnostic LLM + embedding abstraction
* ``nowlens.rag``          hybrid retrieval, fusion, reranking, compression
* ``nowlens.ingestion``    crawl → … → index pipeline
* ``nowlens.agents``       LangGraph orchestration + agent nodes
* ``nowlens.db``           SQLAlchemy models, session management, migrations
* ``nowlens.security``     auth, RBAC, rate limiting, sanitisation, auditing
* ``nowlens.api``          FastAPI application, routers, schemas
* ``nowlens.workers``      background task execution
* ``nowlens.observability`` structured logging, metrics, tracing hooks
"""

__version__ = "0.1.0"
