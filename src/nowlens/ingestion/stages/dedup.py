"""Deduplication stage.

Two layers:

* **Exact** — identical chunk text (via SHA-256) is collapsed immediately.
* **Near-duplicate** — 64-bit SimHash fingerprints + Hamming distance catch
  boilerplate that survives extraction (repeated headers, "related articles",
  near-identical release-note blurbs). Chunks within ``max_distance`` of an
  already-kept fingerprint are dropped.

SimHash is fully deterministic and unit-tested; no external services involved.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable

from nowlens.ingestion.models import Chunk

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_HASH_BITS = 64


def _shingles(text: str, n: int = 3) -> list[str]:
    tokens = _TOKEN_RE.findall(text.lower())
    if len(tokens) < n:
        return tokens
    return [" ".join(tokens[i : i + n]) for i in range(len(tokens) - n + 1)]


def _hash_feature(feature: str) -> int:
    digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big")


def simhash(text: str) -> int:
    """Compute a 64-bit SimHash of ``text``."""

    vector = [0] * _HASH_BITS
    features = _shingles(text)
    if not features:
        return 0
    for feature in features:
        h = _hash_feature(feature)
        for bit in range(_HASH_BITS):
            if (h >> bit) & 1:
                vector[bit] += 1
            else:
                vector[bit] -= 1
    fingerprint = 0
    for bit in range(_HASH_BITS):
        if vector[bit] > 0:
            fingerprint |= 1 << bit
    return fingerprint


def hamming_distance(a: int, b: int) -> int:
    return (a ^ b).bit_count()


def deduplicate(chunks: Iterable[Chunk], *, max_distance: int = 3) -> tuple[list[Chunk], int]:
    """Return (unique_chunks, removed_count)."""

    kept: list[Chunk] = []
    kept_fingerprints: list[int] = []
    seen_exact: set[str] = set()
    removed = 0

    for chunk in chunks:
        exact = hashlib.sha256(chunk.text.encode("utf-8")).hexdigest()
        if exact in seen_exact:
            removed += 1
            continue

        fingerprint = simhash(chunk.text)
        is_near_dupe = any(
            hamming_distance(fingerprint, existing) <= max_distance
            for existing in kept_fingerprints
        )
        if is_near_dupe:
            removed += 1
            continue

        seen_exact.add(exact)
        kept_fingerprints.append(fingerprint)
        chunk.metadata["simhash"] = format(fingerprint, "016x")
        kept.append(chunk)

    return kept, removed
