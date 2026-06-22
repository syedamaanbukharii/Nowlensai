"""Feature overlap detection agent.

Combines the structural ``related`` graph from :mod:`nowlens.core.domains`
(deterministic) with LLM reasoning over retrieved context to explain where two
or more ServiceNow capability areas overlap and how to choose between them.
"""

from __future__ import annotations

from itertools import combinations
from typing import Any

from nowlens.agents.base import AgentContext, complete, extract_json
from nowlens.agents.prompts import FEATURE_OVERLAP_SYSTEM
from nowlens.agents.state import AgentState
from nowlens.core.domains import analyze_overlap, get_domain


def _structural_hint(domains: list[str]) -> str:
    """Deterministic relatedness facts to anchor the model."""

    facts: list[str] = []
    for a, b in combinations(domains, 2):
        da, db = get_domain(a), get_domain(b)
        if da is None or db is None:
            continue
        try:
            overlap = analyze_overlap(a, b)
        except KeyError:
            continue
        rel = "related" if overlap.related else "not directly related"
        shared = (
            f"; shared neighbours: {', '.join(overlap.shared_neighbours)}"
            if overlap.shared_neighbours
            else ""
        )
        facts.append(f"{da.name} vs {db.name}: {rel}{shared}.")
    return "\n".join(facts)


def _render(analysis: dict[str, Any]) -> str:
    lines: list[str] = []
    domains = analysis.get("domains") or []
    if domains:
        lines.append("Comparing: " + ", ".join(str(d) for d in domains))

    def section(title: str, key: str) -> None:
        values = analysis.get(key) or []
        if isinstance(values, list) and values:
            lines.append(f"\n**{title}**")
            lines.extend(f"- {v}" for v in values)

    section("Overlap", "overlap")
    section("Differences", "differences")
    guidance = analysis.get("decision_guidance")
    if guidance:
        lines.append(f"\n**Decision guidance**\n{guidance}")
    section("Anti-patterns", "anti_patterns")
    return "\n".join(lines).strip()


async def feature_overlap(state: AgentState, ctx: AgentContext) -> AgentState:
    domains = state.get("domains", [])
    hint = _structural_hint(domains)
    context = state.get("context", "")
    user = (
        f"Numbered context passages:\n{context}\n\n"
        f"Structural relatedness hint:\n{hint or 'none available'}\n\n"
        f"Question: {state['query']}\n\n"
        "Return the feature-overlap JSON."
    )
    raw = await complete(ctx, system=FEATURE_OVERLAP_SYSTEM, user=user)
    parsed = extract_json(raw)

    if isinstance(parsed, dict):
        parsed.setdefault("domains", domains)
        return AgentState(analysis=parsed, answer=_render(parsed) or raw, trace=["feature_overlap"])
    return AgentState(
        analysis={"summary": raw, "domains": domains, "parse_error": True},
        answer=raw,
        trace=["feature_overlap:unstructured"],
        errors=["feature_overlap: model did not return valid JSON"],
    )
