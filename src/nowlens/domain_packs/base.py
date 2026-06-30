"""Domain Pack framework — the contract a platform plugin implements.

A *Domain Pack* makes the platform support pluggable: ServiceNow, Salesforce,
Jira, and future ecosystems are added by shipping a pack, never by editing the
core. The core discovers packs via the ``nowlens.domain_packs`` entry-point
group (see :mod:`nowlens.domain_packs.registry`) and depends only on this
abstract contract — it never imports a concrete pack by name.

A pack bundles, at minimum, the platform's **domains** (modules / capability
areas) and a **detector** that scores how strongly a query belongs to the
platform. Later phases extend the contract with prompt sets, metadata
extractors, validators, and agent extensions; those are optional hooks here so
the surface can grow without breaking existing packs.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

__all__ = ["Domain", "DomainPack", "PlatformSignal"]


@dataclass(frozen=True)
class Domain:
    """A module / capability area within a platform.

    Canonical home for the type so packs depend on the framework rather than on
    ``core`` internals; ``nowlens.core.domains`` re-exports it for compatibility.
    The ``related`` graph encodes commonly-confused or overlapping capabilities.
    """

    key: str
    name: str
    category: str
    description: str
    aliases: tuple[str, ...] = ()
    related: tuple[str, ...] = ()


@dataclass(frozen=True)
class PlatformSignal:
    """The outcome of platform detection for one pack.

    ``confidence`` is in ``[0, 1]``; ``matched`` lists the evidence terms that
    fired, for explainability and debugging.
    """

    platform: str
    confidence: float
    matched: list[str] = field(default_factory=list)

    @property
    def detected(self) -> bool:
        return bool(self.platform) and self.confidence > 0.0


class DomainPack(ABC):
    """Abstract base for a platform plugin.

    Subclasses set ``key``/``name`` (and optionally ``signals``) and implement
    :meth:`domains`. The default :meth:`detect` is a deterministic, dependency
    free heuristic over the pack's identifying ``signals`` plus its domain
    names/aliases; packs may override it for higher precision.
    """

    #: Stable identifier, e.g. ``"servicenow"``. Matches the entry-point name.
    key: str = ""
    #: Human-readable platform name, e.g. ``"ServiceNow"``.
    name: str = ""
    #: Strong platform-identifying terms (e.g. ``("servicenow", "glide")``).
    signals: tuple[str, ...] = ()

    @abstractmethod
    def domains(self) -> Mapping[str, Domain]:
        """Return the platform's modules / capability areas, keyed by slug."""

    def prompt_for(self, intent: str) -> str | None:
        """Optional per-intent prompt override for this platform (default: none)."""

        return None

    def detect(self, query: str, history: Sequence[Mapping[str, str]] = ()) -> PlatformSignal:
        """Score how strongly ``query`` (plus history) belongs to this platform.

        Strong ``signals`` contribute fully; domain name/alias hits contribute
        weakly. Two strong hits saturate confidence. Deterministic and offline.
        """

        haystack = " ".join([query, *(str(turn.get("content", "")) for turn in history)]).lower()
        matched: list[str] = []
        score = 0.0

        for signal in self.signals:
            term = signal.lower()
            if term and term in haystack:
                matched.append(signal)
                score += 1.0

        for domain in self.domains().values():
            for alias in (domain.name.lower(), *(a.lower() for a in domain.aliases)):
                if alias and alias in haystack:
                    matched.append(alias)
                    score += 0.25
                    break  # one weak hit per domain

        confidence = min(1.0, score / 2.0)
        return PlatformSignal(self.key, round(confidence, 3), matched)
