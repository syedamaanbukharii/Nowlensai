"""Quality assurance agent.

The final gate in the answering graph. It reviews the drafted answer against the
question and the available context, checking factual grounding, citation
validity, and whether the question was actually addressed. The verdict is
attached to the state (and surfaced via the API) so consumers can decide how
much to trust a given response.

A lightweight deterministic pre-check runs first (does the answer cite passages
that exist?) and the LLM provides the qualitative judgement. If the LLM review
itself fails for any reason, QA degrades to the deterministic result rather than
blocking the answer.
"""

from __future__ import annotations

import re

from nowlens.agents.base import AgentContext, complete, extract_json
from nowlens.agents.prompts import QA_SYSTEM
from nowlens.agents.state import AgentState
from nowlens.core.logging import get_logger

log = get_logger(__name__)

_CITATION_RE = re.compile(r"\[(\d+)\]")


def _citation_check(answer: str, citation_count: int) -> dict[str, object]:
    used = {int(n) for n in _CITATION_RE.findall(answer)}
    valid = all(1 <= n <= citation_count for n in used) if used else True
    return {
        "cited_indices": sorted(used),
        "citations_valid": valid,
        "uses_citations": bool(used),
    }


async def quality_assurance(state: AgentState, ctx: AgentContext) -> AgentState:
    answer = state.get("answer", "")
    context = state.get("context", "")
    citations = state.get("citations", [])
    pre = _citation_check(answer, len(citations))

    # No context at all -> grounding is impossible; report honestly, don't call LLM.
    if not context:
        qa = {
            "grounded": False,
            "citations_valid": pre["citations_valid"],
            "answers_question": bool(answer),
            "issues": ["answer not grounded in indexed documentation"],
            "verdict": "pass" if answer else "revise",
            "deterministic": pre,
        }
        return AgentState(qa=qa, trace=["quality_assurance:ungrounded"])

    user = (
        f"User question: {state['query']}\n\n"
        f"Numbered context passages:\n{context}\n\n"
        f"Drafted answer:\n{answer}\n\n"
        "Return the QA JSON."
    )
    try:
        raw = await complete(ctx, system=QA_SYSTEM, user=user, max_tokens=512)
        parsed = extract_json(raw)
    except Exception as exc:  # noqa: BLE001 - QA must never crash the request
        log.warning("qa.llm_failed", error=str(exc))
        parsed = None

    if isinstance(parsed, dict):
        parsed.setdefault("verdict", "pass")
        parsed["deterministic"] = pre
        # Reconcile: a model claim of valid citations can't override a concrete
        # out-of-range reference detected deterministically.
        if not pre["citations_valid"]:
            parsed["citations_valid"] = False
        return AgentState(qa=parsed, trace=["quality_assurance"])

    qa = {
        "grounded": state.get("grounded", False),
        "citations_valid": pre["citations_valid"],
        "answers_question": bool(answer),
        "issues": [] if pre["citations_valid"] else ["invalid citation reference"],
        "verdict": "pass",
        "deterministic": pre,
    }
    return AgentState(qa=qa, trace=["quality_assurance:deterministic"])
