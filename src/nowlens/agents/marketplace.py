"""Marketplace / Store-readiness assessment agent.

Assesses an application or customisation against ServiceNow Store / AppSec
submission expectations and returns a scored checklist plus a readable summary.
"""

from __future__ import annotations

from typing import Any

from nowlens.agents.base import AgentContext, complete, extract_json
from nowlens.agents.prompts import MARKETPLACE_SYSTEM
from nowlens.agents.state import AgentState

_STATUS_ICON = {"pass": "✓", "warn": "!", "fail": "✗"}


def _render(analysis: dict[str, Any]) -> str:
    readiness = analysis.get("readiness", "unknown")
    score = analysis.get("score")
    head = f"Store readiness: **{readiness}**"
    if isinstance(score, (int, float)):
        head += f" (score {int(score)}/100)"
    lines = [head]

    checklist = analysis.get("checklist") or []
    if isinstance(checklist, list) and checklist:
        lines.append("\n**Checklist**")
        for item in checklist:
            if not isinstance(item, dict):
                continue
            icon = _STATUS_ICON.get(str(item.get("status", "")), "-")
            note = f" — {item['note']}" if item.get("note") else ""
            lines.append(f"- {icon} {item.get('item', '')}{note}")

    for title, key in (
        ("Blocking issues", "blocking_issues"),
        ("Recommendations", "recommendations"),
    ):
        values = analysis.get(key) or []
        if isinstance(values, list) and values:
            lines.append(f"\n**{title}**")
            lines.extend(f"- {v}" for v in values)
    return "\n".join(lines).strip()


async def marketplace_assessment(state: AgentState, ctx: AgentContext) -> AgentState:
    context = state.get("context", "")
    user = (
        f"Numbered context passages:\n{context}\n\n"
        f"Application / submission description: {state['query']}\n\n"
        "Return the store-readiness JSON."
    )
    raw = await complete(ctx, system=MARKETPLACE_SYSTEM, user=user)
    parsed = extract_json(raw)

    if isinstance(parsed, dict):
        return AgentState(analysis=parsed, answer=_render(parsed) or raw, trace=["marketplace"])
    return AgentState(
        analysis={"summary": raw, "parse_error": True},
        answer=raw,
        trace=["marketplace:unstructured"],
        errors=["marketplace: model did not return valid JSON"],
    )
