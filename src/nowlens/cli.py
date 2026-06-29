"""Command-line interface.

``nowlens <command>`` — a thin operator front-end over the same composition root
the API uses, so behaviour is identical between the two. Machine-readable output
(ingestion reports, answers) is written to **stdout as JSON**; all diagnostics go
to **stderr** (see :func:`nowlens.core.logging.configure_logging`), so the CLI
composes cleanly in pipelines::

    nowlens ingest --file seed_urls.txt | jq '.[] | {url, chunks_indexed}'
    nowlens ask "How should I model a CI relationship in the CMDB?" | jq -r .answer

Commands:

* ``serve``      run the API with uvicorn
* ``bootstrap``  create the Qdrant collection
* ``init-db``    create database tables (dev convenience; prod uses Alembic)
* ``ingest``     ingest one or more URLs (positional or ``--file``)
* ``ask``        ask the agent graph a question
* ``version``    print the version
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from nowlens import __version__
from nowlens.core.logging import configure_logging, get_logger

log = get_logger("nowlens.cli")


def _print_json(payload: Any) -> None:
    """Emit a JSON document to stdout (the machine-readable channel)."""

    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2, default=str)
    sys.stdout.write("\n")


# --------------------------------------------------------------------------
# serve
# --------------------------------------------------------------------------
def _cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    uvicorn.run(
        "nowlens.api.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        workers=args.workers if not args.reload else None,
        log_config=None,  # use our structlog config, not uvicorn's
    )
    return 0


# --------------------------------------------------------------------------
# bootstrap (Qdrant collection)
# --------------------------------------------------------------------------
async def _bootstrap() -> dict[str, Any]:
    from nowlens.core.config import get_settings
    from nowlens.services import get_vector_store

    settings = get_settings()
    store = get_vector_store()
    await store.ensure_collection()
    count = await store.count()
    await store.aclose()
    return {"collection": settings.rag.collection, "vector_count": count, "ready": True}


def _cmd_bootstrap(_: argparse.Namespace) -> int:
    _print_json(asyncio.run(_bootstrap()))
    return 0


# --------------------------------------------------------------------------
# init-db (dev convenience)
# --------------------------------------------------------------------------
async def _init_db() -> dict[str, Any]:
    from nowlens.db.base import Base
    from nowlens.db.repositories import TenantRepository
    from nowlens.db.session import dispose_engine, get_engine, session_scope

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    tables = sorted(Base.metadata.tables)
    # Seed the default tenant so registrations have a valid tenant FK target.
    async with session_scope() as session:
        await TenantRepository(session).ensure_default()
    await dispose_engine()
    return {"created": True, "tables": tables}


def _cmd_init_db(_: argparse.Namespace) -> int:
    _print_json(asyncio.run(_init_db()))
    return 0


# --------------------------------------------------------------------------
# ingest
# --------------------------------------------------------------------------
def _collect_urls(args: argparse.Namespace) -> list[str]:
    urls: list[str] = list(args.urls or [])
    if args.file:
        path = Path(args.file)
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                urls.append(stripped)
    # De-duplicate, preserve order.
    return list(dict.fromkeys(urls))


async def _ingest(urls: list[str]) -> list[dict[str, Any]]:
    from nowlens.db.models import DEFAULT_TENANT_ID
    from nowlens.db.session import session_scope
    from nowlens.services import build_ingestion_pipeline

    reports: list[dict[str, Any]] = []
    async with session_scope() as session:
        pipeline = build_ingestion_pipeline(session, DEFAULT_TENANT_ID)
        try:
            for url in urls:
                report = await pipeline.ingest_url(url)
                reports.append(
                    {
                        "url": report.url,
                        "document_id": report.document_id or None,
                        "success": report.success,
                        "skipped": report.skipped,
                        "chunks_indexed": report.chunks_indexed,
                        "duplicates_removed": report.duplicates_removed,
                        "error": report.error,
                        "stages": [
                            {"name": s.name, "ok": s.ok, "detail": s.detail, "items": s.items}
                            for s in report.stages
                        ],
                    }
                )
        finally:
            await pipeline.aclose()
    return reports


def _cmd_ingest(args: argparse.Namespace) -> int:
    urls = _collect_urls(args)
    if not urls:
        print("No URLs provided (pass URLs or --file).", file=sys.stderr)
        return 2
    reports = asyncio.run(_ingest(urls))
    _print_json(reports)
    failures = sum(1 for r in reports if not r["success"] and not r["skipped"])
    return 1 if failures else 0


# --------------------------------------------------------------------------
# ask
# --------------------------------------------------------------------------
async def _ask(query: str, *, domains: list[str], top_k: int | None) -> dict[str, Any]:
    from nowlens.agents.graph import run_answer
    from nowlens.db.models import DEFAULT_TENANT_ID
    from nowlens.db.session import session_scope
    from nowlens.services import build_agent_context

    async with session_scope() as session:
        ctx = build_agent_context(session, DEFAULT_TENANT_ID)
        return await run_answer(ctx, query, requested_domains=domains or None, final_top_k=top_k)


def _cmd_ask(args: argparse.Namespace) -> int:
    result = asyncio.run(_ask(args.query, domains=args.domains or [], top_k=args.top_k))
    if args.json:
        _print_json(result)
    else:
        sys.stdout.write(result.get("answer", "") + "\n")
        citations = result.get("citations", [])
        if citations:
            sys.stdout.write("\nSources:\n")
            for c in citations:
                sys.stdout.write(f"  [{c.get('index')}] {c.get('title')} — {c.get('source_url')}\n")
    return 0


# --------------------------------------------------------------------------
# parser
# --------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nowlens", description="NowLens AI — ServiceNow expert platform CLI."
    )
    parser.add_argument("--version", action="version", version=f"nowlens {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_serve = sub.add_parser("serve", help="Run the API server (uvicorn).")
    p_serve.add_argument("--host", default="0.0.0.0")
    p_serve.add_argument("--port", type=int, default=8000)
    p_serve.add_argument("--reload", action="store_true", help="Auto-reload (dev).")
    p_serve.add_argument("--workers", type=int, default=1)
    p_serve.set_defaults(func=_cmd_serve)

    p_boot = sub.add_parser("bootstrap", help="Create the Qdrant collection.")
    p_boot.set_defaults(func=_cmd_bootstrap)

    p_init = sub.add_parser("init-db", help="Create DB tables (dev; prod uses Alembic).")
    p_init.set_defaults(func=_cmd_init_db)

    p_ingest = sub.add_parser("ingest", help="Ingest documentation URLs.")
    p_ingest.add_argument("urls", nargs="*", help="URLs to ingest.")
    p_ingest.add_argument("--file", help="Path to a file with one URL per line.")
    p_ingest.set_defaults(func=_cmd_ingest)

    p_ask = sub.add_parser("ask", help="Ask the agent graph a question.")
    p_ask.add_argument("query", help="The question to ask.")
    p_ask.add_argument(
        "--domains", nargs="*", help="Restrict to these domain keys (e.g. itsm cmdb)."
    )
    p_ask.add_argument("--top-k", type=int, default=None, help="Override final_top_k.")
    p_ask.add_argument("--json", action="store_true", help="Emit the full result as JSON.")
    p_ask.set_defaults(func=_cmd_ask)

    p_version = sub.add_parser("version", help="Print the version.")
    p_version.set_defaults(func=lambda _a: (print(__version__) or 0))

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    configure_logging()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except KeyboardInterrupt:  # pragma: no cover
        print("Interrupted.", file=sys.stderr)
        return 130
    except Exception as exc:  # noqa: BLE001 - top-level CLI guard
        log.error("cli.command_failed", command=args.command, error=str(exc))
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
