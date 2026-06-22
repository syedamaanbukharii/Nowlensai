"""Ingestion-time agents.

These three agents operate during document ingestion rather than during chat.
They wrap the corresponding pipeline stages behind a small agent interface so
they can be invoked independently (e.g. from an admin "re-clean" action or a
test harness) and so the agent roster is complete and consistent.

* :class:`ContentCleaningAgent` — rule-based + LLM-assisted noise removal that
  preserves technical examples.
* :class:`MetadataEnrichmentAgent` — domain tagging, heading/keyword extraction.
* :class:`DeduplicationAgent` — exact + near-duplicate (SimHash) removal.
"""

from __future__ import annotations

from nowlens.ingestion.models import Chunk
from nowlens.ingestion.stages.clean import AICleaner, rule_clean
from nowlens.ingestion.stages.dedup import deduplicate
from nowlens.ingestion.stages.enrich import enrich_chunks
from nowlens.llm.base import LLMProvider


class ContentCleaningAgent:
    """Removes navigation noise and repeated boilerplate, repairs formatting.

    Always applies deterministic rule cleaning; if an LLM provider is supplied,
    an AI pass further repairs formatting while preserving code/examples. The AI
    pass degrades to the rule-cleaned text on any failure (see
    :class:`~nowlens.ingestion.stages.clean.AICleaner`).
    """

    def __init__(self, provider: LLMProvider | None = None, *, max_chars: int = 6000) -> None:
        self._ai = AICleaner(provider, max_chars=max_chars) if provider is not None else None

    async def clean(self, text: str) -> str:
        cleaned = rule_clean(text)
        if self._ai is not None:
            cleaned = await self._ai.clean(cleaned)
        return cleaned


class MetadataEnrichmentAgent:
    """Attaches retrieval metadata (domains, headings, keywords, code flags)."""

    def enrich(self, chunks: list[Chunk]) -> list[Chunk]:
        return enrich_chunks(chunks)


class DeduplicationAgent:
    """Drops exact and near-duplicate chunks via SimHash Hamming distance."""

    def __init__(self, *, max_distance: int = 3) -> None:
        self._max_distance = max_distance

    def deduplicate(self, chunks: list[Chunk]) -> tuple[list[Chunk], int]:
        return deduplicate(chunks, max_distance=self._max_distance)
