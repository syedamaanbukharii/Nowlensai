"""Citations and prompt-context formatting.

Turns ranked chunks into (a) a numbered context block the generator is told to
cite with ``[n]`` markers, and (b) a parallel list of :class:`Citation` objects
the UI renders as source references. Multiple chunks from the same document are
de-duplicated to one citation number so answers cite *documents*, not fragments.
"""

from __future__ import annotations

from collections.abc import Sequence

from nowlens.rag.types import Citation, RetrievedChunk

_SNIPPET_CHARS = 240


def _snippet(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= _SNIPPET_CHARS else text[: _SNIPPET_CHARS - 1].rstrip() + "…"


def build_citations(chunks: Sequence[RetrievedChunk]) -> tuple[list[Citation], dict[str, int]]:
    """Return citations and a map from chunk_id -> citation index.

    Chunks sharing a ``document_id`` (or, lacking one, a ``source_url``) collapse
    to a single citation number.
    """

    citations: list[Citation] = []
    by_key: dict[str, int] = {}
    chunk_to_index: dict[str, int] = {}

    for chunk in chunks:
        key = chunk.document_id or chunk.source_url or chunk.chunk_id
        if key not in by_key:
            index = len(citations) + 1
            by_key[key] = index
            citations.append(
                Citation(
                    index=index,
                    chunk_id=chunk.chunk_id,
                    document_id=chunk.document_id,
                    title=chunk.title or chunk.source_url or "Untitled source",
                    source_url=chunk.source_url,
                    snippet=_snippet(chunk.text),
                )
            )
        chunk_to_index[chunk.chunk_id] = by_key[key]

    return citations, chunk_to_index


def format_context(chunks: Sequence[RetrievedChunk], chunk_to_index: dict[str, int]) -> str:
    """Build the numbered context block injected into the generator prompt."""

    blocks: list[str] = []
    for chunk in chunks:
        index = chunk_to_index.get(chunk.chunk_id, 0)
        header = f"[{index}] {chunk.title or chunk.source_url or 'source'}".strip()
        blocks.append(f"{header}\n{chunk.text.strip()}")
    return "\n\n---\n\n".join(blocks)
