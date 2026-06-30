"""Platform / module / role detection.

The detection layer makes routing *automatic*: the user never selects a
platform. Given a query (and history) it resolves which **platform** (via the
Domain Pack registry), which **modules** within that platform, and the user's
likely **role**. All three are deterministic, dependency-free heuristics so they
are reproducible and unit-testable; an LLM classifier can refine them later.

These are the Platform/Module/Role Detection Agents of the multi-agent design,
composed by the orchestration graph's detection node.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from nowlens.core.config import get_settings
from nowlens.core.domains import detect_domains_in
from nowlens.domain_packs import PlatformSignal, get_registry

History = Sequence[Mapping[str, str]]

# Role inference: distinctive vocabulary per role. Platform-neutral on purpose.
_ROLE_HINTS: dict[str, tuple[str, ...]] = {
    "developer": (
        "code",
        "script",
        "api",
        "function",
        "class",
        "debug",
        "build",
        "deploy",
        "apex",
        "gliderecord",
        "rest",
        "sdk",
        "compile",
    ),
    "administrator": (
        "configure",
        "admin",
        "permission",
        "role",
        "user",
        "instance",
        "setup",
        "acl",
        "access control",
        "property",
        "update set",
        "manage",
    ),
    "business_analyst": (
        "requirement",
        "process",
        "stakeholder",
        "user story",
        "gap analysis",
        "workflow",
        "business need",
        "use case",
        "kpi",
    ),
    "architect": (
        "architecture",
        "design pattern",
        "scalab",
        "data model",
        "integration design",
        "blueprint",
        "topology",
        "trade-off",
        "non-functional",
    ),
    "project_manager": (
        "timeline",
        "milestone",
        "sprint",
        "backlog",
        "resource",
        "project plan",
        "deadline",
        "roadmap",
        "scope creep",
    ),
    "consultant": (
        "best practice",
        "recommend",
        "advisory",
        "approach",
        "should we",
        "pros and cons",
        "strategy",
    ),
    "support_engineer": (
        "error",
        "issue",
        "ticket",
        "troubleshoot",
        "not working",
        "broken",
        "fails",
        "outage",
        "root cause",
        "stack trace",
    ),
}


def detect_platform(query: str, history: History = ()) -> PlatformSignal:
    """Resolve the platform via the pack registry; fall back to the default.

    Returns the highest-confidence pack signal, or the configured default
    platform with zero confidence when nothing matches (keeps behaviour stable
    on a single-pack install).
    """

    signal = get_registry().detect(query, [dict(turn) for turn in history])
    if signal.detected:
        return signal
    return PlatformSignal(get_settings().packs.default, 0.0, [])


def detect_module(query: str, platform: str, *, limit: int = 4) -> list[str]:
    """Detect the most relevant modules within ``platform``'s catalogue."""

    pack = get_registry().get(platform)
    if pack is None:
        return []
    return detect_domains_in(query, pack.domains(), limit=limit)


def detect_role(query: str, history: History = ()) -> str:
    """Infer the user's role from query vocabulary (``""`` when inconclusive)."""

    text = " ".join([query, *(str(turn.get("content", "")) for turn in history)]).lower()
    best_role, best_score = "", 0
    for role, hints in _ROLE_HINTS.items():
        score = sum(1 for hint in hints if hint in text)
        if score > best_score:
            best_role, best_score = role, score
    return best_role
