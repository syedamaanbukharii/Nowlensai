"""Business analysis agent.

Turns a request into a structured business analysis (stakeholders, outcomes,
processes, risks, metrics) and also renders a readable summary so the chat
surface always has prose to show alongside the structured ``analysis`` object.
"""

from __future__ import annotations

from typing import Any

from nowlens.agents.base import AgentContext, complete, extract_json
from nowlens.agents.prompts import BUSINESS_ANALYSIS_SYSTEM
from nowlens.agents.state import AgentState


def _render(analysis: dict[str, Any]) -> str:
    lines: list[str] = []
    summary = analysis.get("summary")
    if summary:
        lines.append(str(summary))

    def section(title: str, key: str) -> None:
        values = analysis.get(key) or []
        if isinstance(values, list) and values:
            lines.append(f"\n**{title}**")
            lines.extend(f"- {v}" for v in values)

    section("Primary domains", "primary_domains")
    section("Stakeholders", "stakeholders")
    section("Business outcomes", "business_outcomes")
    section("Key processes", "key_processes")
    section("Recommended capabilities", "recommended_capabilities")
    section("Risks", "risks")
    section("Success metrics", "success_metrics")
    return "\n".join(lines).strip()


async def business_analysis(state: AgentState, ctx: AgentContext) -> AgentState:
    context = state.get("context", "")
    detected = ", ".join(state.get("domains", [])) or "none detected"
    user = (
        f"Numbered context passages:\n{context}\n\n"
        f"Detected domains: {detected}\n"
        f"Request: {state['query']}\n\n"
        "Return the business analysis JSON."
    )
    raw = await complete(ctx, system=BUSINESS_ANALYSIS_SYSTEM, user=user)
    parsed = extract_json(raw)

    if isinstance(parsed, dict):
        return AgentState(
            analysis=parsed,
            answer=_render(parsed) or raw,
            trace=["business_analysis"],
        )
    # Parsing failed — keep the raw text as the answer rather than discarding work.
    return AgentState(
        analysis={"summary": raw, "parse_error": True},
        answer=raw,
        trace=["business_analysis:unstructured"],
        errors=["business_analysis: model did not return valid JSON"],
    )
