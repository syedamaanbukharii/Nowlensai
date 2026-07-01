"""Jira Domain Pack tests + three-platform detection.

Confirms the third first-party pack is discoverable and that detection now
distinguishes ServiceNow / Salesforce / Jira purely from installed packs — still
with no change to the core.
"""

from __future__ import annotations

import pytest

from nowlens.agents.detect import detect_module, detect_platform
from nowlens.domain_packs import get_registry
from nowlens.domain_packs.jira import JiraPack


def test_jira_pack_lists_domains_and_detects() -> None:
    pack = JiraPack()
    assert pack.key == "jira"
    assert "jql" in pack.domains()
    signal = pack.detect("write a JQL filter and a Jira automation rule")
    assert signal.platform == "jira"
    assert signal.confidence > 0


def test_jira_pack_discovered_via_entry_point() -> None:
    assert get_registry().get("jira") is not None


def test_detection_across_three_platforms() -> None:
    assert detect_platform("GlideRecord on the ServiceNow Now Platform").platform == "servicenow"
    assert detect_platform("Apex trigger and SOQL in Salesforce").platform == "salesforce"
    assert detect_platform("build a JQL filter in Jira").platform == "jira"


def test_shared_alias_does_not_switch_platform() -> None:
    # "service desk" is a shared alias (ServiceNow ITSM + Jira JSM). Without a
    # strong platform signal, detection must stay on the default platform rather
    # than mis-route on ambiguous vocabulary.
    assert (
        detect_platform("configure assignment rules for the service desk").platform == "servicenow"
    )


def test_module_detection_scoped_to_jira() -> None:
    modules = detect_module("configure a scrum board and a JQL filter", "jira")
    assert "boards" in modules
    assert "jql" in modules
    # Other platforms' modules must not leak in.
    assert "itsm" not in modules
    assert "apex" not in modules


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
