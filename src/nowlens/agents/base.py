"""Agent building blocks shared across nodes.

Nodes are deliberately thin: they assemble a prompt, call the *provider-agnostic*
LLM, and write structured results back into :class:`~nowlens.agents.state.AgentState`.
None of them import a concrete provider — they receive an :class:`AgentContext`
created from the factory, which keeps the whole graph testable and vendor-neutral.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass

from nowlens.core.domains import detect_domains
from nowlens.core.logging import get_logger
from nowlens.llm.base import ChatMessage, LLMProvider
from nowlens.rag.retriever import HybridRetriever

log = get_logger(__name__)

# Intent labels the router can emit. Kept as plain constants so both the
# heuristic router and the graph edges reference the same vocabulary.
INTENT_BEST_PRACTICE = "best_practice"
INTENT_BUSINESS_ANALYSIS = "business_analysis"
INTENT_FEATURE_OVERLAP = "feature_overlap"
INTENT_MARKETPLACE = "marketplace"
INTENT_RESEARCH = "research"

ALL_INTENTS = (
    INTENT_BEST_PRACTICE,
    INTENT_BUSINESS_ANALYSIS,
    INTENT_FEATURE_OVERLAP,
    INTENT_MARKETPLACE,
    INTENT_RESEARCH,
)


@dataclass(slots=True)
class AgentContext:
    """Dependencies handed to every node.

    ``retriever`` is optional so the graph can run in a degraded "no knowledge
    base" mode (e.g. before any ingestion has happened) — nodes detect this and
    answer from parametric knowledge while flagging the lack of grounding.
    """

    chat: LLMProvider
    retriever: HybridRetriever | None = None
    max_answer_tokens: int = 1024


async def complete(
    ctx: AgentContext,
    *,
    system: str,
    user: str,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> str:
    """Run a single system+user completion and return the text content."""

    messages = [ChatMessage(role="system", content=system), ChatMessage(role="user", content=user)]
    result = await ctx.chat.chat(
        messages, temperature=temperature, max_tokens=max_tokens or ctx.max_answer_tokens
    )
    return result.content.strip()


_JSON_BLOCK = re.compile(r"\{.*\}|\[.*\]", re.DOTALL)


def extract_json(text: str) -> object | None:
    """Best-effort parse of a JSON object/array from an LLM response.

    Models occasionally wrap JSON in prose or code fences; we strip fences and
    fall back to the first balanced ``{...}``/``[...]`` span. Returns ``None``
    if nothing parses, so callers can degrade gracefully rather than crash.
    """

    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    match = _JSON_BLOCK.search(cleaned)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return None


_OVERLAP_HINTS = (" vs ", " versus ", "difference between", "overlap", "compare", "or use")
_MARKETPLACE_HINTS = (
    "store",
    "marketplace",
    "publish",
    "certification",
    "appsec",
    "scoped app submission",
    "store readiness",
    "listing",
)
_BUSINESS_HINTS = (
    "should we",
    "business case",
    "roi",
    "justify",
    "stakeholder",
    "adopt",
    "rollout",
    "implement",
    "migrate",
    "process design",
)
_RESEARCH_HINTS = ("research", "what's new", "whats new", "latest", "deep dive", "investigate")


def route_intent(query: str, domains: Sequence[str]) -> str:
    """Heuristic, deterministic intent router.

    Cheap and dependency-free so routing is reproducible and unit-testable. The
    individual agents still use the LLM for the heavy lifting; this only decides
    *which* specialist handles the request. Order matters — more specific
    intents are checked first.
    """

    q = f" {query.lower()} "
    if any(h in q for h in _OVERLAP_HINTS) or len(domains) >= 2:
        return INTENT_FEATURE_OVERLAP
    if any(h in q for h in _MARKETPLACE_HINTS):
        return INTENT_MARKETPLACE
    if any(h in q for h in _RESEARCH_HINTS):
        return INTENT_RESEARCH
    if any(h in q for h in _BUSINESS_HINTS):
        return INTENT_BUSINESS_ANALYSIS
    return INTENT_BEST_PRACTICE


def domains_for(query: str, requested: Sequence[str]) -> list[str]:
    """Resolve the working domain set: explicit request wins, else detect."""

    if requested:
        return list(requested)
    return detect_domains(query, limit=4)


def citations_payload(citations: Sequence[object]) -> list[dict[str, object]]:
    """Serialise Citation dataclasses to JSON-friendly dicts for the state."""

    payload: list[dict[str, object]] = []
    for c in citations:
        payload.append(
            {
                "index": getattr(c, "index", 0),
                "chunk_id": getattr(c, "chunk_id", ""),
                "title": getattr(c, "title", ""),
                "source_url": getattr(c, "source_url", ""),
                "document_id": getattr(c, "document_id", ""),
                "snippet": getattr(c, "snippet", ""),
            }
        )
    return payload
