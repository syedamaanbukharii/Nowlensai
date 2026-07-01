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


# Minimum confidence required to switch *away* from the default platform. A
# strong platform-specific signal (e.g. "salesforce", "jql", "glide") scores
# >= 0.5, whereas a single shared domain alias (e.g. "service desk", which many
# platforms use) scores lower. Requiring a strong signal prevents ambiguous
# vocabulary from mis-routing to the wrong platform as more packs are installed.
MIN_PLATFORM_CONFIDENCE = 0.5


def detect_platform(query: str, history: History = ()) -> PlatformSignal:
    """Resolve the platform via the pack registry; fall back to the default.

    Only a sufficiently strong signal switches platform; weak/ambiguous evidence
    falls back to the configured default so shared vocabulary can't mis-route.
    """

    signal = get_registry().detect(query, [dict(turn) for turn in history])
    if signal.confidence >= MIN_PLATFORM_CONFIDENCE:
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
