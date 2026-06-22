# Ingestion pipeline

NowLens keeps its knowledge base fresh by crawling documentation and turning it into searchable, embedded chunks. The pipeline is a documented, per-stage sequence; every stage records a `StageOutcome`, so the admin API/UI can show exactly where a document succeeded or failed.

## Stage sequence

```
crawl → render → extract → clean → normalize → chunk → enrich
      → deduplicate → embed → validate → index   (with retry on transient crawl failures)
```

| Stage | Module | What it does |
|---|---|---|
| **crawl** | `stages/crawl.py` | Async HTTP fetch with a configurable user-agent, per-host `robots.txt` enforcement (cached), a concurrency semaphore, and a crawl delay. Network/HTTP errors are captured on the `CrawlResult`, not raised. |
| **render** | `stages/render.py` | *Optional.* When `RENDER_JAVASCRIPT=true` (and the `render` extra + a browser are present), loads the page in headless Chromium and returns post-render HTML. Otherwise a transparent pass-through. |
| **extract** | `stages/extract.py` | Parses HTML with selectolax: strips non-content nodes (script/style/nav/header/footer/aside/forms), prefers semantic `main`/`article` containers, converts headings to Markdown `#`, and turns `<pre>/<code>` into fenced code blocks. |
| **clean** | `stages/clean.py` | `rule_clean` always runs (drops nav/breadcrumb/legal boilerplate, collapses whitespace, dedupes repeated lines — code fences protected). An optional `AICleaner` LLM pass removes residual noise and repairs formatting, **preserving code verbatim**, and degrades to the rule-cleaned text on any error. |
| **normalize** | `stages/normalize.py` | NFKC normalisation, smart-quote/dash folding, zero-width removal, bullet unification, trailing-space trim — so dedup fingerprints and embeddings see canonical text. |
| **chunk** | `stages/chunk.py` | Recursive, separator-aware splitter tuned for technical docs: breaks on structural boundaries (headings, paragraphs) before sentence/word fallbacks, keeps fenced code blocks intact, and applies a character overlap. |
| **enrich** | `stages/enrich.py` | Adds metadata: detected domains, nearest headings (breadcrumb), `has_code`, top keywords, char/token estimates. |
| **deduplicate** | `stages/dedup.py` | Exact (SHA-256) and near-duplicate (64-bit SimHash + Hamming distance) removal of boilerplate that survives extraction. |
| **embed** | `stages/embed.py` | Batched embedding via the provider-agnostic interface; short chunks are prefixed with their heading breadcrumb to improve retrieval. |
| **validate** | `stages/validate.py` | Integrity gate before indexing: non-empty text, stable id, correct embedding dimensionality, finite components. Invalid chunks are reported, never silently dropped. |
| **index** | `stages/index.py` | Writes vectors + payload to Qdrant and (optionally) chunk rows to PostgreSQL via the injected `ChunkSink`. |

## Retry and incremental behaviour

- **Retry.** Transient crawl failures (network errors, 5xx, empty body) are retried with exponential backoff up to `max_attempts`. An explicit `robots.txt` disallow is non-retryable. Provider calls have their own retry inside the LLM/embedding clients.
- **Incremental.** An optional `unchanged(url, content_hash)` predicate lets the caller skip pages whose canonical content hash matches a prior run, so re-crawls are cheap. The default predicate (`DocumentRepository.is_unchanged`) compares against the stored hash.
- **Validation gate.** Only chunks passing `validate_embedded` are indexed.

## Running ingestion

Via the API (operator role):

```bash
# Inline (returns per-URL reports — good for small jobs / scripts):
curl -s localhost:8000/api/v1/ingest \
  -H "authorization: Bearer $TOKEN" -H 'content-type: application/json' \
  -d '{"urls":["https://docs.example.com/itsm"],"wait":true}'

# Queued (returns job ids; poll GET /api/v1/jobs):
curl -s localhost:8000/api/v1/ingest \
  -H "authorization: Bearer $TOKEN" -H 'content-type: application/json' \
  -d '{"urls":["https://docs.example.com/a","https://docs.example.com/b"]}'
```

Via the CLI:

```bash
nowlens ingest https://docs.example.com/itsm
nowlens ingest --file data/sample/seed_urls.txt
```

Background work runs as a FastAPI `BackgroundTask` by default. For a durable queue, install the `worker` extra and run the arq worker (see [DEPLOYMENT.md](DEPLOYMENT.md)).

## Tuning

| Setting | Default | Effect |
|---|---|---|
| `NOWLENS_INGEST__CHUNK_SIZE` | 1200 | Target characters per chunk |
| `NOWLENS_INGEST__CHUNK_OVERLAP` | 200 | Overlap between adjacent chunks |
| `NOWLENS_INGEST__MIN_CHUNK_CHARS` | 120 | Drop chunks shorter than this |
| `NOWLENS_INGEST__SIMHASH_MAX_DISTANCE` | 3 | Larger = more aggressive near-dup removal |
| `NOWLENS_INGEST__AI_CLEANING` | true | Enable the LLM cleaning pass |
| `NOWLENS_INGEST__RENDER_JAVASCRIPT` | false | Enable headless rendering (needs `render` extra) |
| `NOWLENS_INGEST__RESPECT_ROBOTS` | true | Honour `robots.txt` |
| `NOWLENS_INGEST__MAX_CONCURRENCY` | 5 | Concurrent fetches |
| `NOWLENS_INGEST__CRAWL_DELAY_S` | 0.5 | Politeness delay between fetches |

## Capability boundaries (honest scope)

Static crawling, extraction, cleaning, chunking, dedup, embedding, and indexing work without any optional extras. **JavaScript rendering** requires the `render` extra plus `playwright install chromium`; it is a documented capability boundary, not a stub. **AI cleaning** uses the configured LLM and degrades gracefully to rule-based cleaning if the provider is unavailable.
