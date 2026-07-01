"""Salesforce Domain Pack tests.

Also the proof that the Domain Pack framework works: a second platform is added
with **no change to the core** — detection now distinguishes Salesforce from
ServiceNow purely from the installed packs.
"""

from __future__ import annotations

import pytest

from nowlens.agents.detect import detect_module, detect_platform
from nowlens.domain_packs import get_registry
from nowlens.domain_packs.salesforce import SalesforcePack


def test_salesforce_pack_lists_domains_and_detects() -> None:
    pack = SalesforcePack()
    assert pack.key == "salesforce"
    assert "apex" in pack.domains()
    signal = pack.detect("write an Apex trigger with a SOQL query in Salesforce")
    assert signal.platform == "salesforce"
    assert signal.confidence > 0


def test_salesforce_pack_discovered_via_entry_point() -> None:
    assert get_registry().get("salesforce") is not None


def test_detection_distinguishes_salesforce_from_servicenow() -> None:
    # ServiceNow-flavoured query resolves to ServiceNow...
    sn = detect_platform("How do I write a GlideRecord query on the Now Platform?")
    assert sn.platform == "servicenow"
    # ...and a Salesforce-flavoured query resolves to Salesforce, with no core
    # change — only the installed packs differ.
    sf = detect_platform("How do I write an Apex trigger and SOQL in Salesforce?")
    assert sf.platform == "salesforce"


def test_module_detection_scoped_to_salesforce() -> None:
    modules = detect_module(
        "I need to build a Lightning Web Component and an Apex class", "salesforce"
    )
    assert "lwc" in modules
    assert "apex" in modules
    # ServiceNow modules must not leak into a Salesforce query.
    assert "itsm" not in modules


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
