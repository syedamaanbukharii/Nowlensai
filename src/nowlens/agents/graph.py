"""Agent orchestration graph (LangGraph).

LangGraph is the orchestration core. The answering graph is::

        START
          │
        route                 (classify intent + resolve domains)
          │
    knowledge_retrieval        (hybrid RAG → context + citations)
          │
   ┌──────┴───────────────────────────────────────────┐
   │ conditional on intent                             │
 best_practices / business_analysis / feature_overlap /
 marketplace_assessment / research
   └──────┬───────────────────────────────────────────┘
          │
    quality_assurance          (grounding + citation check)
          │
         END

The graph is a single forward pass: QA annotates the result with a verdict
rather than looping, which keeps execution bounded and deterministic. Nodes are
bound to an :class:`~nowlens.agents.base.AgentContext` at build time so the
graph contains no global/provider coupling.

LangChain is used only for incidental utilities elsewhere; the architectural
core here is LangGraph's ``StateGraph``.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from langgraph.graph import END, START, StateGraph

from nowlens.agents.base import (
    INTENT_BEST_PRACTICE,
    INTENT_BUSINESS_ANALYSIS,
    INTENT_FEATURE_OVERLAP,
    INTENT_MARKETPLACE,
    INTENT_RESEARCH,
    AgentContext,
    domains_for,
    route_intent,
)
from nowlens.agents.best_practices import best_practices
from nowlens.agents.business_analysis import business_analysis
from nowlens.agents.feature_overlap import feature_overlap
from nowlens.agents.knowledge import knowledge_retrieval
from nowlens.agents.marketplace import marketplace_assessment
from nowlens.agents.quality_assurance import quality_assurance
from nowlens.agents.research import research
from nowlens.agents.state import AgentState, initial_state
from nowlens.core.logging import get_logger

log = get_logger(__name__)

NodeFn = Callable[[AgentState, AgentContext], Awaitable[AgentState]]

_SPECIALISTS: dict[str, NodeFn] = {
    INTENT_BEST_PRACTICE: best_practices,
    INTENT_BUSINESS_ANALYSIS: business_analysis,
    INTENT_FEATURE_OVERLAP: feature_overlap,
    INTENT_MARKETPLACE: marketplace_assessment,
    INTENT_RESEARCH: research,
}


async def _route(state: AgentState) -> AgentState:
    """Resolve domains then classify intent (pure, deterministic)."""

    domains = domains_for(state["query"], state.get("requested_domains", []))
    intent = route_intent(state["query"], domains)
    return AgentState(domains=domains, intent=intent, trace=[f"route:{intent}"])


def _select_specialist(state: AgentState) -> str:
    intent = state.get("intent", INTENT_BEST_PRACTICE)
    return intent if intent in _SPECIALISTS else INTENT_BEST_PRACTICE


def _bind(fn: NodeFn, ctx: AgentContext) -> Callable[[AgentState], Awaitable[AgentState]]:
    async def _run(state: AgentState) -> AgentState:
        return await fn(state, ctx)

    return _run


def build_answer_graph(ctx: AgentContext):  # type: ignore[no-untyped-def]
    """Compile the answering graph bound to ``ctx``.

    Returns a compiled LangGraph runnable exposing ``ainvoke``.
    """

    graph = StateGraph(AgentState)
    graph.add_node("route", _route)
    graph.add_node("knowledge_retrieval", _bind(knowledge_retrieval, ctx))  # type: ignore[arg-type]
    for intent, fn in _SPECIALISTS.items():
        graph.add_node(intent, _bind(fn, ctx))  # type: ignore[arg-type]
    graph.add_node("quality_assurance", _bind(quality_assurance, ctx))  # type: ignore[arg-type]

    graph.add_edge(START, "route")
    graph.add_edge("route", "knowledge_retrieval")
    graph.add_conditional_edges(
        "knowledge_retrieval",
        _select_specialist,
        {intent: intent for intent in _SPECIALISTS},
    )
    for intent in _SPECIALISTS:
        graph.add_edge(intent, "quality_assurance")
    graph.add_edge("quality_assurance", END)

    return graph.compile()


def _result(state: AgentState) -> dict[str, Any]:
    """Normalise the terminal state into a stable response payload."""

    return {
        "answer": state.get("answer", ""),
        "intent": state.get("intent", ""),
        "domains": state.get("domains", []),
        "citations": state.get("citations", []),
        "analysis": state.get("analysis"),
        "qa": state.get("qa", {}),
        "grounded": state.get("grounded", False),
        "metrics": state.get("metrics", {}),
        "trace": state.get("trace", []),
        "errors": state.get("errors", []),
    }


async def run_answer(
    ctx: AgentContext,
    query: str,
    *,
    history: Sequence[dict[str, str]] | None = None,
    requested_domains: Sequence[str] | None = None,
    final_top_k: int | None = None,
) -> dict[str, Any]:
    """Build + invoke the graph for one question, returning a result dict."""

    graph = build_answer_graph(ctx)
    state = initial_state(
        query,
        history=list(history or []),
        requested_domains=list(requested_domains or []),
        final_top_k=final_top_k,
    )
    final: AgentState = await graph.ainvoke(state)
    result = _result(final)
    log.info("agents.run", intent=result["intent"], grounded=result["grounded"])
    return result
