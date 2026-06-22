"""Knowledge retrieval agent.

The first specialist in the graph. It resolves the working domain set, runs the
hybrid retriever with adaptive depth, and writes the retrieved context +
citations into the state for downstream agents to reason over.
"""

from __future__ import annotations

from nowlens.agents.base import AgentContext, citations_payload, domains_for
from nowlens.agents.state import AgentState
from nowlens.core.logging import get_logger
from nowlens.rag.retriever import adaptive_top_k

log = get_logger(__name__)


async def knowledge_retrieval(state: AgentState, ctx: AgentContext) -> AgentState:
    query = state["query"]
    # Prefer domains already resolved by the router; otherwise resolve here so
    # the node also works when invoked standalone (tests, ad-hoc retrieval).
    domains = state.get("domains") or domains_for(query, state.get("requested_domains", []))

    if ctx.retriever is None:
        # Degraded mode: no knowledge base wired in. Be explicit so the QA node
        # and the answer can flag the lack of grounding instead of pretending.
        return AgentState(
            domains=domains,
            context="",
            citations=[],
            grounded=False,
            trace=["knowledge_retrieval:skipped(no_retriever)"],
            metrics={"retrieval": {"skipped": True}},
        )

    base = state.get("final_top_k")
    top_k = base if base is not None else adaptive_top_k(query, base=ctx_top_k(ctx))
    result = await ctx.retriever.retrieve(query, domains=domains or None, final_top_k=top_k)

    return AgentState(
        domains=domains,
        context=result.context,
        citations=citations_payload(result.citations),
        retrieval_metrics=result.metrics,
        grounded=bool(result.chunks),
        trace=[f"knowledge_retrieval:{len(result.chunks)} chunks"],
        metrics={"retrieval": result.metrics},
    )


def ctx_top_k(ctx: AgentContext) -> int:
    """Resolve the retriever's configured final_top_k as the adaptive base."""

    retriever = ctx.retriever
    cfg = getattr(retriever, "_cfg", None)
    return int(getattr(cfg, "final_top_k", 6)) if cfg is not None else 6
