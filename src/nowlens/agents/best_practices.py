"""Best-practices agent.

The default specialist for "how should I…" questions. Produces grounded,
implementation-ready guidance citing the retrieved passages.
"""

from __future__ import annotations

from nowlens.agents.base import AgentContext, complete
from nowlens.agents.prompts import BEST_PRACTICE_SYSTEM
from nowlens.agents.state import AgentState


def _user_prompt(query: str, context: str, grounded: bool) -> str:
    if grounded:
        return (
            f"Numbered context passages:\n{context}\n\n"
            f"Question: {query}\n\n"
            "Answer with best-practice guidance, citing passages as [n]."
        )
    return (
        f"Question: {query}\n\n"
        "No retrieved documentation was available. Answer from general "
        "ServiceNow expertise, and begin by noting that this answer is not "
        "grounded in indexed documentation."
    )


async def best_practices(state: AgentState, ctx: AgentContext) -> AgentState:
    answer = await complete(
        ctx,
        system=BEST_PRACTICE_SYSTEM,
        user=_user_prompt(state["query"], state.get("context", ""), state.get("grounded", False)),
    )
    return AgentState(answer=answer, trace=["best_practices"])
