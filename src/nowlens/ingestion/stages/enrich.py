"""Enrich-metadata stage.

Augments every chunk with retrieval- and filter-relevant metadata:

* ``domains``     detected ServiceNow domains (lexical, from the registry)
* ``headings``    nearest Markdown headings for breadcrumb context
* ``has_code``    whether the chunk contains a fenced code block
* ``keywords``    top distinctive tokens (cheap TF heuristic)
* ``char_count`` / ``token_estimate``

All deterministic and dependency-free. An optional LLM enrichment (summaries,
richer tags) can layer on top, but the baseline never requires a model.
"""

from __future__ import annotations

import re
from collections import Counter

from nowlens.core.domains import detect_domains
from nowlens.ingestion.models import Chunk

_HEADING_RE = re.compile(r"^#{1,4}\s+(.*)$", re.MULTILINE)
_CODE_FENCE_RE = re.compile(r"```")
_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]{2,}")

_STOPWORDS = frozenset(
    [
        "the",
        "and",
        "for",
        "are",
        "with",
        "this",
        "that",
        "you",
        "your",
        "can",
        "will",
        "from",
        "has",
        "have",
        "not",
        "but",
        "when",
        "how",
        "what",
        "which",
        "who",
        "use",
        "using",
        "used",
        "into",
        "onto",
        "over",
        "under",
        "more",
        "most",
        "then",
        "than",
        "they",
        "them",
        "their",
        "there",
        "here",
        "also",
        "may",
        "can't",
        "cannot",
        "should",
        "would",
        "could",
        "been",
        "being",
        "does",
        "done",
        "each",
    ]
)


def _keywords(text: str, *, limit: int = 8) -> list[str]:
    tokens = [t.lower() for t in _TOKEN_RE.findall(text) if t.lower() not in _STOPWORDS]
    counts = Counter(tokens)
    return [word for word, _ in counts.most_common(limit)]


def enrich_chunk(chunk: Chunk) -> Chunk:
    text = chunk.text
    headings = _HEADING_RE.findall(text)
    domains = detect_domains(f"{chunk.metadata.get('title', '')} {text}")
    chunk.metadata.update(
        {
            "domains": domains,
            "headings": headings[:5],
            "has_code": bool(_CODE_FENCE_RE.search(text)),
            "keywords": _keywords(text),
            "char_count": len(text),
            "token_estimate": max(1, len(text) // 4),
        }
    )
    return chunk


def enrich_chunks(chunks: list[Chunk]) -> list[Chunk]:
    return [enrich_chunk(chunk) for chunk in chunks]
