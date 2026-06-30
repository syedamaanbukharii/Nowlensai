"""Domain Pack framework tests: the contract, detection, and entry-point discovery.

Fully offline — fake packs stand in for real platform plugins, and entry-point
discovery is exercised by monkeypatching ``importlib.metadata.entry_points``.
"""

from __future__ import annotations

import pytest

from nowlens.core.config import PacksSettings
from nowlens.domain_packs import Domain, DomainPack, DomainPackRegistry
from nowlens.domain_packs import registry as registry_mod


class _ServiceNowish(DomainPack):
    key = "servicenow"
    name = "ServiceNow"
    signals = ("servicenow", "now platform", "glide")

    def domains(self):  # type: ignore[no-untyped-def]
        return {
            "itsm": Domain(
                "itsm", "IT Service Management", "product", "", aliases=("incident management",)
            )
        }


class _Salesforceish(DomainPack):
    key = "salesforce"
    name = "Salesforce"
    signals = ("salesforce", "apex", "lightning")

    def domains(self):  # type: ignore[no-untyped-def]
        return {"apex": Domain("apex", "Apex", "product", "", aliases=("apex class",))}


class _FakeEntryPoint:
    def __init__(self, name: str, obj: object) -> None:
        self.name = name
        self._obj = obj

    def load(self) -> object:
        return self._obj


# --------------------------------------------------------------------------- #
# registry basics
# --------------------------------------------------------------------------- #


def test_register_and_lookup() -> None:
    reg = DomainPackRegistry()
    reg.register(_ServiceNowish())
    reg.register(_Salesforceish())
    assert {p.key for p in reg.all()} == {"servicenow", "salesforce"}
    assert reg.get("servicenow").name == "ServiceNow"
    assert reg.get("missing") is None


def test_register_rejects_empty_key() -> None:
    class _Bad(DomainPack):
        key = ""

        def domains(self):  # type: ignore[no-untyped-def]
            return {}

    with pytest.raises(ValueError):
        DomainPackRegistry().register(_Bad())


# --------------------------------------------------------------------------- #
# detection
# --------------------------------------------------------------------------- #


def test_default_detector_scores_signals_and_aliases() -> None:
    signal = _ServiceNowish().detect("How do I configure incident management in ServiceNow?")
    assert signal.platform == "servicenow"
    assert signal.confidence > 0
    assert "servicenow" in signal.matched


def test_registry_detect_picks_highest_confidence() -> None:
    reg = DomainPackRegistry()
    reg.register(_ServiceNowish())
    reg.register(_Salesforceish())
    best = reg.detect("write an Apex class for a Salesforce Lightning component")
    assert best.platform == "salesforce"
    assert best.detected


def test_registry_detect_no_match_is_empty() -> None:
    reg = DomainPackRegistry()
    reg.register(_ServiceNowish())
    best = reg.detect("what's the weather like today")
    assert best.platform == ""
    assert best.confidence == 0.0
    assert not best.detected


# --------------------------------------------------------------------------- #
# entry-point discovery
# --------------------------------------------------------------------------- #


def test_discover_loads_entrypoint_packs(monkeypatch) -> None:
    eps = [
        _FakeEntryPoint("servicenow", _ServiceNowish),
        _FakeEntryPoint("salesforce", _Salesforceish),
    ]
    monkeypatch.setattr(registry_mod, "entry_points", lambda group: eps)
    reg = DomainPackRegistry()
    reg.discover()
    assert set(reg.keys()) == {"servicenow", "salesforce"}


def test_discover_respects_allow_list(monkeypatch) -> None:
    eps = [
        _FakeEntryPoint("servicenow", _ServiceNowish),
        _FakeEntryPoint("salesforce", _Salesforceish),
    ]
    monkeypatch.setattr(registry_mod, "entry_points", lambda group: eps)
    reg = DomainPackRegistry()
    reg.discover(enabled=["salesforce"])
    assert reg.keys() == ["salesforce"]


def test_discover_skips_a_broken_pack(monkeypatch) -> None:
    def _boom() -> DomainPack:
        raise RuntimeError("bad pack")

    eps = [_FakeEntryPoint("broken", _boom), _FakeEntryPoint("servicenow", _ServiceNowish)]
    monkeypatch.setattr(registry_mod, "entry_points", lambda group: eps)
    reg = DomainPackRegistry()
    reg.discover()  # must not raise
    assert reg.keys() == ["servicenow"]


# --------------------------------------------------------------------------- #
# config
# --------------------------------------------------------------------------- #


def test_packs_settings_parses_csv_enabled() -> None:
    settings = PacksSettings(enabled="servicenow, salesforce")  # type: ignore[arg-type]
    assert settings.enabled == ["servicenow", "salesforce"]
    assert settings.default == "servicenow"


# --------------------------------------------------------------------------- #
# bundled ServiceNow pack
# --------------------------------------------------------------------------- #


def test_servicenow_pack_lists_domains_and_detects() -> None:
    from nowlens.domain_packs.servicenow import ServiceNowPack

    pack = ServiceNowPack()
    assert pack.key == "servicenow"
    assert "itsm" in pack.domains()
    signal = pack.detect("how do I write a GlideRecord query in ServiceNow?")
    assert signal.platform == "servicenow"
    assert signal.confidence > 0


def test_servicenow_pack_discovered_via_entry_point() -> None:
    # Registered in pyproject under the nowlens.domain_packs group, so a normal
    # install (incl. CI's fresh install) discovers it.
    from nowlens.domain_packs import get_registry

    assert get_registry().get("servicenow") is not None


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
