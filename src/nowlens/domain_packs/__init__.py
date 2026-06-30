"""Pluggable Domain Pack framework.

Public surface for platform plugins and the core's discovery of them. See
:mod:`nowlens.domain_packs.base` for the contract a pack implements and
:mod:`nowlens.domain_packs.registry` for discovery.
"""

from __future__ import annotations

from nowlens.domain_packs.base import Domain, DomainPack, PlatformSignal
from nowlens.domain_packs.registry import (
    ENTRY_POINT_GROUP,
    DomainPackRegistry,
    get_registry,
)

__all__ = [
    "ENTRY_POINT_GROUP",
    "Domain",
    "DomainPack",
    "DomainPackRegistry",
    "PlatformSignal",
    "get_registry",
]
