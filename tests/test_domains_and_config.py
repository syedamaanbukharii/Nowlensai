"""Domain registry, overlap analysis, and configuration (env parsing) tests."""

from __future__ import annotations

import pytest

from nowlens.core.config import Settings, get_settings
from nowlens.core.domains import (
    DOMAINS,
    all_domain_keys,
    analyze_overlap,
    detect_domains,
    get_domain,
)

# --------------------------------------------------------------------------- #
# domains
# --------------------------------------------------------------------------- #


def test_registry_non_trivial() -> None:
    assert len(all_domain_keys()) >= 20
    assert "itsm" in DOMAINS


def test_get_domain_case_insensitive() -> None:
    assert get_domain("ITSM") is not None
    assert get_domain("does-not-exist") is None


def test_detect_domains_matches_aliases() -> None:
    detected = detect_domains("We need help with incident management and change management")
    assert "itsm" in detected


def test_detect_domains_limit() -> None:
    text = "itsm csm hrsd cmdb itom flow designer integrationhub portals"
    assert len(detect_domains(text, limit=3)) <= 3


def test_analyze_overlap_related() -> None:
    result = analyze_overlap("itsm", "csm")
    assert result.related is True
    assert result.domain_a == "itsm"


def test_analyze_overlap_shared_neighbours() -> None:
    # itam and sam both relate to cmdb.
    result = analyze_overlap("itam", "sam")
    assert "cmdb" in result.shared_neighbours


def test_analyze_overlap_unknown_raises() -> None:
    with pytest.raises(KeyError):
        analyze_overlap("itsm", "nonsense")


# --------------------------------------------------------------------------- #
# config
# --------------------------------------------------------------------------- #


def test_default_settings_load() -> None:
    settings = Settings()
    assert settings.llm.provider in {"ollama", "groq"}
    assert settings.rag.final_top_k >= 1
    assert settings.security.access_token_ttl_min > 0


def test_get_settings_cached() -> None:
    assert get_settings() is get_settings()


def test_cors_origins_comma_split(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOWLENS_CORS_ORIGINS", "https://a.com,https://b.com")
    settings = Settings()
    assert "https://a.com" in settings.cors_origins
    assert "https://b.com" in settings.cors_origins


def test_nested_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOWLENS_RAG__FINAL_TOP_K", "9")
    monkeypatch.setenv("NOWLENS_LLM__PROVIDER", "groq")
    settings = Settings()
    assert settings.rag.final_top_k == 9
    assert settings.llm.provider == "groq"


def test_is_production_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOWLENS_ENVIRONMENT", "production")
    # Production refuses to boot without a strong JWT secret (see the security
    # guard in Settings); supply one so this exercises only the flag.
    monkeypatch.setenv("NOWLENS_SECURITY__JWT_SECRET", "s" * 40)
    assert Settings().is_production is True


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
