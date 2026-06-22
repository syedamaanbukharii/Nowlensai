"""Validate stage.

Post-embedding integrity checks run before indexing so corrupt data never
reaches the stores: every chunk must have non-empty text, a stable id, an
embedding of the expected dimensionality, and finite numeric components.
Returns the subset of valid chunks plus a list of human-readable problems.
"""

from __future__ import annotations

import math

from nowlens.ingestion.models import EmbeddedChunk


def validate_embedded(
    embedded: list[EmbeddedChunk], *, expected_dim: int
) -> tuple[list[EmbeddedChunk], list[str]]:
    valid: list[EmbeddedChunk] = []
    problems: list[str] = []

    for item in embedded:
        chunk = item.chunk
        if not chunk.text.strip():
            problems.append(f"chunk {chunk.chunk_id}: empty text")
            continue
        if not chunk.chunk_id:
            problems.append("chunk with missing id")
            continue
        if len(item.embedding) != expected_dim:
            problems.append(
                f"chunk {chunk.chunk_id}: embedding dim {len(item.embedding)} != {expected_dim}"
            )
            continue
        if any(not math.isfinite(v) for v in item.embedding):
            problems.append(f"chunk {chunk.chunk_id}: non-finite embedding value")
            continue
        valid.append(item)

    return valid, problems
