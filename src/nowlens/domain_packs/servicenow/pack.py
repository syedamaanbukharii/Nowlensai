"""ServiceNow Domain Pack.

The first-party pack, registered via the ``nowlens.domain_packs`` entry-point in
``pyproject.toml``. Bundled with the core distribution but discovered through the
same mechanism as any third-party pack, so the core never references it by name.
"""

from __future__ import annotations

from collections.abc import Mapping

from nowlens.domain_packs.base import Domain, DomainPack
from nowlens.domain_packs.servicenow.domains import SERVICENOW_DOMAINS


class ServiceNowPack(DomainPack):
    key = "servicenow"
    name = "ServiceNow"
    # Strong platform-identifying terms; deliberately ServiceNow-specific to
    # avoid false positives against generic ITSM vocabulary.
    signals = (
        "servicenow",
        "service-now",
        "now platform",
        "glide",
        "gliderecord",
        "update set",
        "scoped application",
        "flow designer",
    )

    def domains(self) -> Mapping[str, Domain]:
        return SERVICENOW_DOMAINS
