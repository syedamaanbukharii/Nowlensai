"""Chunking stage.

A recursive, separator-aware splitter tuned for technical documentation: it
prefers to break on structural boundaries (headings, paragraphs, fenced code
blocks) before falling back to sentence/word boundaries, keeps fenced code
blocks intact, and applies a character overlap so context isn't severed at
chunk edges. Pure and deterministic — fully unit-tested.
"""

from __future__ import annotations

import re
import uuid

from nowlens.ingestion.models import Chunk, ExtractedDocument

# Ordered from coarsest to finest. Code fences are handled specially first.
_SEPARATORS = ["\n## ", "\n### ", "\n\n", "\n", ". ", " "]
_CODE_FENCE_RE = re.compile(r"(```.*?```)", re.DOTALL)


def _split_keeping_code(text: str) -> list[tuple[str, bool]]:
    """Split text into (segment, is_code) parts, preserving fenced code blocks."""

    parts: list[tuple[str, bool]] = []
    for piece in _CODE_FENCE_RE.split(text):
        if not piece:
            continue
        parts.append((piece, piece.startswith("```")))
    return parts


def _recursive_split(text: str, max_chars: int, separators: list[str]) -> list[str]:
    if len(text) <= max_chars:
        return [text] if text.strip() else []
    if not separators:
        # Hard split as a last resort.
        return [text[i : i + max_chars] for i in range(0, len(text), max_chars)]

    sep, *rest = separators
    segments = text.split(sep)
    chunks: list[str] = []
    buffer = ""
    for seg in segments:
        candidate = seg if not buffer else f"{buffer}{sep}{seg}"
        if len(candidate) <= max_chars:
            buffer = candidate
        else:
            if buffer:
                chunks.append(buffer)
            if len(seg) > max_chars:
                chunks.extend(_recursive_split(seg, max_chars, rest))
                buffer = ""
            else:
                buffer = seg
    if buffer:
        chunks.append(buffer)
    return chunks


def _apply_overlap(pieces: list[str], overlap: int) -> list[str]:
    if overlap <= 0 or len(pieces) <= 1:
        return pieces
    out: list[str] = []
    for i, piece in enumerate(pieces):
        if i == 0:
            out.append(piece)
            continue
        tail = pieces[i - 1][-overlap:]
        out.append(f"{tail} {piece}".strip())
    return out


def chunk_text(text: str, *, chunk_size: int, overlap: int) -> list[str]:
    raw: list[str] = []
    for segment, is_code in _split_keeping_code(text):
        if is_code and len(segment) <= chunk_size * 2:
            # Keep small/medium code blocks whole even if slightly oversized.
            raw.append(segment)
        else:
            raw.extend(_recursive_split(segment, chunk_size, list(_SEPARATORS)))
    raw = [r.strip() for r in raw if r.strip()]
    return _apply_overlap(raw, overlap)


def chunk_document(
    doc: ExtractedDocument,
    document_id: str,
    *,
    chunk_size: int,
    overlap: int,
    min_chunk_chars: int,
) -> list[Chunk]:
    pieces = chunk_text(doc.text, chunk_size=chunk_size, overlap=overlap)
    chunks: list[Chunk] = []
    index = 0
    for piece in pieces:
        if len(piece) < min_chunk_chars:
            continue
        chunks.append(
            Chunk(
                chunk_id=str(uuid.uuid4()),
                document_id=document_id,
                text=piece,
                index=index,
                metadata={
                    "title": doc.title,
                    "source_url": doc.url,
                    "language": doc.language,
                    **doc.metadata,
                },
            )
        )
        index += 1
    return chunks
