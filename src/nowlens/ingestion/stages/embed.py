"""Embed stage.

Generates embedding vectors for chunks via the provider-agnostic embedding
interface. Batched to keep request counts bounded, with the embedded text being
the chunk body prefixed by its heading breadcrumb (improves retrieval for short
chunks that lack self-contained context).
"""

from __future__ import annotations

from nowlens.core.exceptions import IngestionError
from nowlens.ingestion.models import Chunk, EmbeddedChunk
from nowlens.llm.base import EmbeddingProvider


def _embedding_text(chunk: Chunk) -> str:
    headings = chunk.metadata.get("headings") or []
    breadcrumb = " > ".join(headings[-2:]) if headings else chunk.metadata.get("title", "")
    return f"{breadcrumb}\n{chunk.text}".strip() if breadcrumb else chunk.text


async def embed_chunks(
    chunks: list[Chunk], embedder: EmbeddingProvider, *, batch_size: int = 32
) -> list[EmbeddedChunk]:
    embedded: list[EmbeddedChunk] = []
    for start in range(0, len(chunks), batch_size):
        batch = chunks[start : start + batch_size]
        texts = [_embedding_text(c) for c in batch]
        vectors = await embedder.embed(texts)
        if len(vectors) != len(batch):
            raise IngestionError(
                f"Embedding count mismatch: expected {len(batch)}, got {len(vectors)}"
            )
        for chunk, vector in zip(batch, vectors, strict=True):
            embedded.append(EmbeddedChunk(chunk=chunk, embedding=vector))
    return embedded
