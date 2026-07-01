"""Jira Domain Pack.

The third first-party pack. Like the others, it is discovered via the
``nowlens.domain_packs`` entry-point; the core never imports it by name.
"""

from __future__ import annotations

from collections.abc import Mapping

from nowlens.domain_packs.base import Domain, DomainPack
from nowlens.domain_packs.jira.domains import JIRA_DOMAINS


class JiraPack(DomainPack):
    key = "jira"
    name = "Jira"
    # Strong Jira/Atlassian identifiers; avoids generic agile vocabulary
    # (sprint, backlog, epic) that could belong to other tools.
    signals = (
        "jira",
        "jql",
        "atlassian",
        "jira service management",
        "jira software",
        "confluence",
        "automation for jira",
        "jira automation",
        "jira cloud",
        "jira admin",
    )

    def domains(self) -> Mapping[str, Domain]:
        return JIRA_DOMAINS
