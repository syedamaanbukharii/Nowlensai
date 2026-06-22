"""Research agent.

Synthesises the retrieved context into a structured briefing. Distinct from the
best-practices agent in intent: it organises and summarises available material
(findings → detail → gaps) rather than prescribing a single recommendation.
"""

from __future__ import annotations

from nowlens.agents.base import AgentContext, complete
from nowlens.agents.prompts import RESEARCH_SYSTEM
from nowlens.agents.state import AgentState


async def research(state: AgentState, ctx: AgentContext) -> AgentState:
    context = state.get("context", "")
    user = (
        f"Numbered context passages:\n{context}\n\n"
        f"Research question: {state['query']}\n\n"
        "Produce the briefing, citing passages as [n]."
        if context
        else (
            f"Research question: {state['query']}\n\n"
            "No indexed material was available; summarise from general knowledge "
            "and state clearly that the briefing is not grounded in sources."
        )
    )
    answer = await complete(ctx, system=RESEARCH_SYSTEM, user=user)
    return AgentState(answer=answer, trace=["research"])
