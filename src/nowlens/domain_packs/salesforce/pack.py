"""Salesforce Domain Pack.

Demonstrates the framework's core promise: a new platform is added by shipping a
pack that advertises the ``nowlens.domain_packs`` entry-point — no change to the
core, the agents, or any other pack.
"""

from __future__ import annotations

from collections.abc import Mapping

from nowlens.domain_packs.base import Domain, DomainPack
from nowlens.domain_packs.salesforce.domains import SALESFORCE_DOMAINS


class SalesforcePack(DomainPack):
    key = "salesforce"
    name = "Salesforce"
    # Strong, Salesforce-specific identifiers; avoids generic CRM vocabulary that
    # could collide with other platforms.
    signals = (
        "salesforce",
        "sfdc",
        "force.com",
        "apex",
        "soql",
        "sosl",
        "visualforce",
        "lightning web component",
        "lwc",
        "trailhead",
        "validation rule",
        "permission set",
        "sandbox org",
    )

    def domains(self) -> Mapping[str, Domain]:
        return SALESFORCE_DOMAINS
