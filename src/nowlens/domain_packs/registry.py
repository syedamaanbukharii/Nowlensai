"""Domain Pack registry + discovery.

Packs are discovered via the ``nowlens.domain_packs`` entry-point group, so the
core never imports a concrete pack by name and a new platform is added simply by
installing a distribution that advertises the entry-point. An optional
``NOWLENS_PACKS__ENABLED`` allow-list restricts which discovered packs load.

The registry also supports explicit :meth:`register` (used by tests and for
programmatic wiring) independent of entry-point discovery.
"""

from __future__ import annotations

from functools import lru_cache
from importlib.metadata import entry_points

from nowlens.core.config import get_settings
from nowlens.core.logging import get_logger
from nowlens.domain_packs.base import DomainPack, PlatformSignal

log = get_logger(__name__)

ENTRY_POINT_GROUP = "nowlens.domain_packs"


class DomainPackRegistry:
    """An in-memory collection of loaded :class:`DomainPack` instances."""

    def __init__(self) -> None:
        self._packs: dict[str, DomainPack] = {}

    def register(self, pack: DomainPack) -> None:
        if not pack.key:
            raise ValueError("DomainPack.key must be a non-empty identifier")
        self._packs[pack.key] = pack

    def get(self, key: str) -> DomainPack | None:
        return self._packs.get(key)

    def all(self) -> list[DomainPack]:
        return list(self._packs.values())

    def keys(self) -> list[str]:
        return list(self._packs)

    def detect(self, query: str, history: list[dict[str, str]] | None = None) -> PlatformSignal:
        """Run every pack's detector and return the highest-confidence signal.

        Returns an empty (``confidence == 0``) signal when nothing matches, so
        callers can fall back to a configured default platform.
        """

        hist = history or []
        best = PlatformSignal("", 0.0, [])
        for pack in self._packs.values():
            signal = pack.detect(query, hist)
            if signal.confidence > best.confidence:
                best = signal
        return best

    def discover(self, *, enabled: list[str] | None = None) -> None:
        """Load packs advertised on the entry-point group.

        ``enabled`` (when provided and non-empty) restricts which entry-point
        names are loaded. Failures to load a single pack are logged and skipped
        rather than breaking startup.
        """

        allow = set(enabled) if enabled else None
        for ep in entry_points(group=ENTRY_POINT_GROUP):
            if allow is not None and ep.name not in allow:
                continue
            try:
                obj = ep.load()
                pack = obj() if isinstance(obj, type) else obj
                self.register(pack)
                log.info("domain_pack.loaded", pack=pack.key, source=ep.name)
            except Exception as exc:  # noqa: BLE001 - one bad pack must not crash boot
                log.warning("domain_pack.load_failed", entry_point=ep.name, error=str(exc))


@lru_cache
def get_registry() -> DomainPackRegistry:
    """Process-cached registry with entry-point packs discovered + filtered."""

    settings = get_settings()
    registry = DomainPackRegistry()
    registry.discover(enabled=settings.packs.enabled or None)
    return registry
