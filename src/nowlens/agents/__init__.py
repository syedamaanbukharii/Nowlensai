"""Multi-agent orchestration layer.

LangGraph-based orchestration of ServiceNow specialist agents. The public entry
points are :func:`build_answer_graph` (compiled graph) and :func:`run_answer`
(single-call convenience). Ingestion-time agents are exposed for reuse by the
pipeline and admin tooling.
"""

from nowlens.agents.base import (
    ALL_INTENTS,
    INTENT_BEST_PRACTICE,
    INTENT_BUSINESS_ANALYSIS,
    INTENT_FEATURE_OVERLAP,
    INTENT_MARKETPLACE,
    INTENT_RESEARCH,
    AgentContext,
    route_intent,
)
from nowlens.agents.graph import build_answer_graph, run_answer
from nowlens.agents.ingestion import (
    ContentCleaningAgent,
    DeduplicationAgent,
    MetadataEnrichmentAgent,
)
from nowlens.agents.state import AgentState, initial_state

__all__ = [
    "ALL_INTENTS",
    "INTENT_BEST_PRACTICE",
    "INTENT_BUSINESS_ANALYSIS",
    "INTENT_FEATURE_OVERLAP",
    "INTENT_MARKETPLACE",
    "INTENT_RESEARCH",
    "AgentContext",
    "AgentState",
    "ContentCleaningAgent",
    "DeduplicationAgent",
    "MetadataEnrichmentAgent",
    "build_answer_graph",
    "initial_state",
    "route_intent",
    "run_answer",
]
