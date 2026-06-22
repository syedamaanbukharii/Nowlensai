"""Shared state for the agent graph.

LangGraph passes a single mutable state object between nodes; each node returns
a partial update that is merged in. We use a ``TypedDict`` with explicit
reducers for the fields that *accumulate* across nodes (trace of executed
agents, per-agent metrics, non-fatal errors) so concurrent/branching nodes
compose cleanly.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


def _merge_dicts(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    """Reducer that shallow-merges metric/diagnostic dictionaries."""

    merged = dict(left)
    merged.update(right)
    return merged


class AgentState(TypedDict, total=False):
    """State threaded through the orchestration graph.

    ``total=False`` because most fields are populated incrementally by nodes.
    """

    # -- inputs ------------------------------------------------------------
    query: str
    history: list[dict[str, str]]
    requested_domains: list[str]
    final_top_k: int | None

    # -- routing -----------------------------------------------------------
    intent: str
    domains: list[str]

    # -- retrieval ---------------------------------------------------------
    context: str
    citations: list[dict[str, Any]]
    retrieval_metrics: dict[str, Any]
    grounded: bool

    # -- generation --------------------------------------------------------
    answer: str
    analysis: dict[str, Any]

    # -- quality assurance -------------------------------------------------
    qa: dict[str, Any]

    # -- accumulating diagnostics -----------------------------------------
    trace: Annotated[list[str], operator.add]
    metrics: Annotated[dict[str, Any], _merge_dicts]
    errors: Annotated[list[str], operator.add]


def initial_state(
    query: str,
    *,
    history: list[dict[str, str]] | None = None,
    requested_domains: list[str] | None = None,
    final_top_k: int | None = None,
) -> AgentState:
    """Build a fresh state for a single graph invocation."""

    return AgentState(
        query=query,
        history=history or [],
        requested_domains=requested_domains or [],
        final_top_k=final_top_k,
        citations=[],
        trace=[],
        metrics={},
        errors=[],
    )
