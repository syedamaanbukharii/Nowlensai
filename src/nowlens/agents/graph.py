"""Agent orchestration graph (LangGraph).

LangGraph is the orchestration core. The answering graph is::

        START
          │
        detect                (auto platform / module / role detection)
          │
        route                 (classify intent from detected modules)
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
from contextvars import ContextVar
from functools import lru_cache
from typing import Any, cast

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from nowlens.agents.base import (
    INTENT_BEST_PRACTICE,
    INTENT_BUSINESS_ANALYSIS,
    INTENT_FEATURE_OVERLAP,
    INTENT_MARKETPLACE,
    INTENT_RESEARCH,
    AgentContext,
    route_intent,
)
from nowlens.agents.best_practices import best_practices
from nowlens.agents.business_analysis import business_analysis
from nowlens.agents.detect import detect_module, detect_platform, detect_role
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


async def _detect(state: AgentState) -> AgentState:
    """Automatic platform / module / role detection (pure, deterministic).

    Runs first: resolves the platform via the Domain Pack registry, the modules
    within that platform, and the user's role — so the rest of the graph routes
    without the user ever selecting a platform. An explicit ``requested_domains``
    overrides module detection.
    """

    query = state["query"]
    history = state.get("history", [])
    signal = detect_platform(query, history)
    requested = state.get("requested_domains", [])
    modules = list(requested) if requested else detect_module(query, signal.platform)
    role = detect_role(query, history)
    return AgentState(
        platform=signal.platform,
        domains=modules,
        role=role,
        detection={
            "platform": signal.platform,
            "platform_confidence": signal.confidence,
            "platform_matched": signal.matched,
            "role": role,
        },
        trace=[f"platform:{signal.platform or 'unknown'}", f"role:{role or 'unknown'}"],
    )


async def _route(state: AgentState) -> AgentState:
    """Classify intent from the detected modules (pure, deterministic)."""

    intent = route_intent(state["query"], state.get("domains", []))
    return AgentState(intent=intent, trace=[f"route:{intent}"])


def _select_specialist(state: AgentState) -> str:
    intent = state.get("intent", INTENT_BEST_PRACTICE)
    return intent if intent in _SPECIALISTS else INTENT_BEST_PRACTICE


def _bind(fn: NodeFn, ctx: AgentContext) -> Callable[[AgentState], Awaitable[AgentState]]:
    async def _run(state: AgentState) -> AgentState:
        return await fn(state, ctx)

    return _run


# Per-invocation context for the *cached* graph. The compiled graph is shared
# across requests, so nodes read the active context from here instead of having
# it baked in at compile time. ContextVars are copied into child tasks at
# creation, so concurrent requests stay isolated.
_active_ctx: ContextVar[AgentContext] = ContextVar("nowlens_agent_context")


def _bind_active(fn: NodeFn) -> Callable[[AgentState], Awaitable[AgentState]]:
    async def _run(state: AgentState) -> AgentState:
        return await fn(state, _active_ctx.get())

    return _run


def _assemble(
    knowledge: Callable[[AgentState], Awaitable[AgentState]],
    specialists: dict[str, Callable[[AgentState], Awaitable[AgentState]]],
    qa: Callable[[AgentState], Awaitable[AgentState]],
) -> CompiledStateGraph:
    """Wire + compile the answering graph from pre-bound node callables."""

    # LangGraph's node stubs don't model an ``async (State) -> State`` callable
    # cleanly, so these registrations need a targeted arg-type ignore; the
    # callables are valid nodes at runtime.
    graph = StateGraph(AgentState)
    graph.add_node("detect", _detect)
    graph.add_node("route", _route)
    graph.add_node("knowledge_retrieval", knowledge)  # type: ignore[arg-type]
    for intent, fn in specialists.items():
        graph.add_node(intent, fn)  # type: ignore[arg-type]
    graph.add_node("quality_assurance", qa)  # type: ignore[arg-type]

    graph.add_edge(START, "detect")
    graph.add_edge("detect", "route")
    graph.add_edge("route", "knowledge_retrieval")
    graph.add_conditional_edges(
        "knowledge_retrieval",
        _select_specialist,
        {intent: intent for intent in specialists},
    )
    for intent in specialists:
        graph.add_edge(intent, "quality_assurance")
    graph.add_edge("quality_assurance", END)

    return graph.compile()


def build_answer_graph(ctx: AgentContext) -> CompiledStateGraph:
    """Compile the answering graph bound to ``ctx``.

    Returns a compiled LangGraph runnable exposing ``ainvoke``. Each call builds
    and compiles a fresh graph; prefer :func:`run_answer`, which reuses a cached
    compiled graph, on the hot request path.
    """

    return _assemble(
        _bind(knowledge_retrieval, ctx),
        {intent: _bind(fn, ctx) for intent, fn in _SPECIALISTS.items()},
        _bind(quality_assurance, ctx),
    )


@lru_cache(maxsize=1)
def _cached_answer_graph() -> CompiledStateGraph:
    """Compile the answering graph once; nodes read ctx from :data:`_active_ctx`.

    The topology is identical on every request, so compilation (~8 ms) is wasted
    work per call. This compiles a single graph whose nodes resolve the active
    :class:`AgentContext` at run time.
    """

    return _assemble(
        _bind_active(knowledge_retrieval),
        {intent: _bind_active(fn) for intent, fn in _SPECIALISTS.items()},
        _bind_active(quality_assurance),
    )


def _result(state: AgentState) -> dict[str, Any]:
    """Normalise the terminal state into a stable response payload."""

    return {
        "answer": state.get("answer", ""),
        "platform": state.get("platform", ""),
        "role": state.get("role", ""),
        "detection": state.get("detection", {}),
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
    """Invoke the cached answering graph for one question, returning a result dict.

    The compiled graph is shared across calls; the per-request ``ctx`` is made
    available to its nodes through :data:`_active_ctx` for the duration of this
    invocation and reset afterwards.
    """

    graph = _cached_answer_graph()
    state = initial_state(
        query,
        history=list(history or []),
        requested_domains=list(requested_domains or []),
        final_top_k=final_top_k,
    )
    token = _active_ctx.set(ctx)
    try:
        # ainvoke returns the terminal state dict; cast to the TypedDict view.
        final = cast(AgentState, await graph.ainvoke(state))
    finally:
        _active_ctx.reset(token)
    result = _result(final)
    log.info("agents.run", intent=result["intent"], grounded=result["grounded"])
    return result
