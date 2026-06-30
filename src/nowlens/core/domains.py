"""Platform-neutral domain utilities.

The ``Domain`` type and the *generic* operations over a domain catalogue
(detection, overlap analysis) live here; the actual catalogue is supplied by the
active :class:`~nowlens.domain_packs.base.DomainPack` (ServiceNow, Salesforce,
Jira, …), resolved from the registry. The core therefore owns no platform data.

``Domain`` is re-exported from :mod:`nowlens.domain_packs.base` so existing
imports (``from nowlens.core.domains import Domain``) keep working.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from nowlens.domain_packs.base import Domain

__all__ = [
    "Domain",
    "OverlapResult",
    "all_domain_keys",
    "analyze_overlap",
    "detect_domains",
    "get_domain",
]


def _active_domains() -> dict[str, Domain]:
    """Domains of the configured default pack (empty if none is installed).

    Imports are local to avoid an import-time cycle (the registry imports
    ``core.config``) and so the catalogue is resolved lazily at call time.
    """

    from nowlens.core.config import get_settings
    from nowlens.domain_packs.registry import get_registry

    pack = get_registry().get(get_settings().packs.default)
    return dict(pack.domains()) if pack is not None else {}


def all_domain_keys() -> list[str]:
    return list(_active_domains())


def get_domain(key: str) -> Domain | None:
    return _active_domains().get(key.lower())


def detect_domains(text: str, *, limit: int = 5) -> list[str]:
    """Heuristically detect the most relevant domains for a piece of text.

    Pure lexical scoring over names + aliases of the active catalogue. Cheap,
    deterministic, and dependency-free; an LLM classifier can refine it.
    """

    lowered = f" {text.lower()} "
    scores: dict[str, int] = {}
    for key, domain in _active_domains().items():
        score = 0
        needles = (domain.name.lower(), key.replace("_", " "), *domain.aliases)
        for needle in needles:
            n = needle.lower()
            if not n:
                continue
            # Word-ish boundary match to avoid spurious substring hits.
            if f" {n} " in lowered or lowered.startswith(f"{n} ") or lowered.endswith(f" {n}"):
                score += 2
            elif n in lowered:
                score += 1
        if score:
            scores[key] = score
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    return [key for key, _ in ranked[:limit]]


@dataclass
class OverlapResult:
    domain_a: str
    domain_b: str
    related: bool
    shared_neighbours: list[str] = field(default_factory=list)


def analyze_overlap(domain_a: str, domain_b: str) -> OverlapResult:
    """Structural overlap between two domains via the ``related`` graph."""

    domains = _active_domains()
    a = domains.get(domain_a.lower())
    b = domains.get(domain_b.lower())
    if a is None or b is None:
        raise KeyError("unknown domain in overlap analysis")
    shared = sorted(set(a.related) & set(b.related))
    related = b.key in a.related or a.key in b.related or bool(shared)
    return OverlapResult(a.key, b.key, related, shared)
