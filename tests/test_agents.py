"""Agent tests: deterministic routing, JSON extraction, the knowledge node's
degraded mode, the QA citation check, and an end-to-end graph run on fakes."""

from __future__ import annotations

import pytest

from nowlens.agents.base import (
    INTENT_BEST_PRACTICE,
    INTENT_BUSINESS_ANALYSIS,
    INTENT_FEATURE_OVERLAP,
    INTENT_MARKETPLACE,
    INTENT_RESEARCH,
    AgentContext,
    citations_payload,
    domains_for,
    extract_json,
    route_intent,
)
from nowlens.agents.graph import run_answer
from nowlens.agents.knowledge import knowledge_retrieval
from nowlens.agents.quality_assurance import quality_assurance
from nowlens.agents.state import initial_state
from nowlens.rag.types import Citation

# --------------------------------------------------------------------------- #
# routing
# --------------------------------------------------------------------------- #


def test_route_feature_overlap_on_vs() -> None:
    assert route_intent("itsm vs csm differences", []) == INTENT_FEATURE_OVERLAP


def test_route_feature_overlap_on_two_domains() -> None:
    assert route_intent("how do these compare", ["itsm", "csm"]) == INTENT_FEATURE_OVERLAP


def test_route_marketplace() -> None:
    assert (
        route_intent("how do I publish to the store with certification", []) == INTENT_MARKETPLACE
    )


def test_route_research() -> None:
    assert route_intent("what's new in the latest release", []) == INTENT_RESEARCH


def test_route_business_analysis() -> None:
    assert route_intent("should we adopt hrsd, business case", []) == INTENT_BUSINESS_ANALYSIS


def test_route_default_best_practice() -> None:
    assert route_intent("how do I configure assignment rules", []) == INTENT_BEST_PRACTICE


def test_domains_for_prefers_requested() -> None:
    assert domains_for("anything", ["csm"]) == ["csm"]
    assert "itsm" in domains_for("incident management questions", [])


# --------------------------------------------------------------------------- #
# extract_json
# --------------------------------------------------------------------------- #


def test_extract_json_plain() -> None:
    assert extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_fenced() -> None:
    assert extract_json('```json\n{"a": 2}\n```') == {"a": 2}


def test_extract_json_embedded_in_prose() -> None:
    assert extract_json('Here you go: {"a": 3} hope that helps') == {"a": 3}


def test_extract_json_invalid_returns_none() -> None:
    assert extract_json("not json at all") is None


def test_citations_payload_shape() -> None:
    citation = Citation(
        index=1, chunk_id="c1", document_id="d1", title="T", source_url="u", snippet="s"
    )
    payload = citations_payload([citation])
    assert payload[0]["chunk_id"] == "c1"
    assert payload[0]["index"] == 1


# --------------------------------------------------------------------------- #
# knowledge node (degraded) + QA
# --------------------------------------------------------------------------- #


async def test_knowledge_retrieval_degraded_without_retriever(fake_chat) -> None:
    ctx = AgentContext(chat=fake_chat, retriever=None)
    state = initial_state("how does itsm work")
    update = await knowledge_retrieval(state, ctx)
    assert update["grounded"] is False
    assert update["context"] == ""


async def test_knowledge_retrieval_with_retriever(fake_chat, seeded_retriever) -> None:
    ctx = AgentContext(chat=fake_chat, retriever=seeded_retriever)
    state = initial_state("incident management in itsm")
    update = await knowledge_retrieval(state, ctx)
    assert update["grounded"] is True
    assert update["citations"]


async def test_qa_ungrounded_when_no_context(fake_chat) -> None:
    ctx = AgentContext(chat=fake_chat, retriever=None)
    state = initial_state("q")
    state["answer"] = "Some answer."
    state["context"] = ""
    update = await quality_assurance(state, ctx)
    assert update["qa"]["grounded"] is False
    assert update["qa"]["verdict"] in {"pass", "revise"}


async def test_qa_detects_out_of_range_citation(fake_chat) -> None:
    ctx = AgentContext(chat=fake_chat, retriever=None)
    state = initial_state("q")
    state["answer"] = "Answer citing [5]."
    state["context"] = "[1] only one passage"
    state["citations"] = [{"index": 1}]
    update = await quality_assurance(state, ctx)
    # The model claims valid, but deterministic check overrides to invalid.
    assert update["qa"]["citations_valid"] is False


# --------------------------------------------------------------------------- #
# full graph run
# --------------------------------------------------------------------------- #


async def test_run_answer_best_practice_grounded(fake_chat, seeded_retriever) -> None:
    ctx = AgentContext(chat=fake_chat, retriever=seeded_retriever)
    result = await run_answer(ctx, "how do I configure assignment rules for the service desk")
    assert result["answer"]
    assert result["grounded"] is True
    assert result["intent"] == INTENT_BEST_PRACTICE
    assert "route:best_practice" in result["trace"]
    assert result["qa"]


async def test_run_answer_feature_overlap_specialist(fake_chat, seeded_retriever) -> None:
    ctx = AgentContext(chat=fake_chat, retriever=seeded_retriever)
    result = await run_answer(ctx, "itsm vs csm: where do they overlap?")
    assert result["intent"] == INTENT_FEATURE_OVERLAP
    assert result["analysis"] is not None


async def test_run_answer_degraded_without_retriever(fake_chat) -> None:
    ctx = AgentContext(chat=fake_chat, retriever=None)
    result = await run_answer(ctx, "how do I configure assignment rules")
    assert result["answer"]
    assert result["grounded"] is False


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
