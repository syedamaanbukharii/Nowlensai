"""Automatic platform / module / role detection tests.

Covers the pure detectors, their composition in the answering graph, and the
platform/role surfaced on the chat API response.
"""

from __future__ import annotations

import pytest

from nowlens.agents.detect import detect_module, detect_platform, detect_role

# --------------------------------------------------------------------------- #
# platform
# --------------------------------------------------------------------------- #


def test_detect_platform_resolves_servicenow() -> None:
    signal = detect_platform("Write a GlideRecord query on the Now Platform")
    assert signal.platform == "servicenow"
    assert signal.confidence > 0


def test_detect_platform_falls_back_to_default() -> None:
    signal = detect_platform("what is the weather like today")
    assert signal.platform == "servicenow"  # configured default
    assert signal.confidence == 0.0


# --------------------------------------------------------------------------- #
# module
# --------------------------------------------------------------------------- #


def test_detect_module_scoped_to_platform() -> None:
    modules = detect_module("incident management and change management", "servicenow")
    assert "itsm" in modules


def test_detect_module_unknown_platform_is_empty() -> None:
    # No Salesforce pack is installed yet, so its modules can't be detected.
    assert detect_module("write an apex class", "salesforce") == []


# --------------------------------------------------------------------------- #
# role
# --------------------------------------------------------------------------- #


def test_detect_role_developer() -> None:
    assert detect_role("I need to debug this script and deploy the REST api") == "developer"


def test_detect_role_administrator() -> None:
    assert detect_role("how do I configure permissions and roles for a user") == "administrator"


def test_detect_role_support_engineer() -> None:
    assert detect_role("the page throws an error and is not working, help me troubleshoot") == (
        "support_engineer"
    )


def test_detect_role_inconclusive_is_empty() -> None:
    assert detect_role("hello there") == ""


# --------------------------------------------------------------------------- #
# graph composition
# --------------------------------------------------------------------------- #


async def test_run_answer_surfaces_platform_and_role(fake_chat) -> None:
    from nowlens.agents.base import AgentContext
    from nowlens.agents.graph import run_answer

    ctx = AgentContext(chat=fake_chat, retriever=None)
    result = await run_answer(ctx, "How do I configure an ACL in ServiceNow?")
    assert result["platform"] == "servicenow"
    assert result["role"] == "administrator"
    assert any(t.startswith("platform:") for t in result["trace"])
    assert result["detection"]["platform"] == "servicenow"


# --------------------------------------------------------------------------- #
# API surfacing
# --------------------------------------------------------------------------- #


def test_chat_response_includes_detected_platform(db_client) -> None:
    token = db_client.post(
        "/api/v1/auth/register", json={"email": "detect@example.com", "password": "password123"}
    ).json()["access_token"]
    resp = db_client.post(
        "/api/v1/chat",
        headers={"authorization": f"Bearer {token}"},
        json={"message": "How do I configure an ACL in ServiceNow?", "stream": False},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["platform"] == "servicenow"
    assert "role" in body


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
