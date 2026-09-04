"""US-005: startup/health auth self-check (advisory only, never gates)."""

from unittest.mock import AsyncMock

from starlette.requests import Request

from redis_sre_agent.api.auth import require_auth
from redis_sre_agent.core import auth as core_auth
from redis_sre_agent.core.auth import DiscoveryError, auth_startup_selfcheck, auth_status
from redis_sre_agent.core.config import settings


def _req(headers):
    raw = [(k.lower().encode(), v.encode()) for k, v in headers.items()]
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/tasks",
            "headers": raw,
            "query_string": b"",
            "client": ("t", 1),
        }
    )


def test_auth_status_default_disabled(monkeypatch):
    monkeypatch.setattr(settings, "auth_enabled", False)
    s = auth_status()
    assert s["enabled"] is False
    assert set(s["surfaces"]) == {"ui", "cli", "api"}
    assert s["fail_closed"] is False


def test_auth_status_fail_closed_when_enabled_unconfigured(monkeypatch):
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "auth_issuer_url", None)
    monkeypatch.setattr(settings, "auth_audience", None)
    assert auth_status()["fail_closed"] is True


async def test_selfcheck_disabled_advisory(monkeypatch):
    monkeypatch.setattr(settings, "auth_enabled", False)
    status = await auth_startup_selfcheck()  # must not raise
    assert status["enabled"] is False


async def test_selfcheck_discovery_down_is_advisory(monkeypatch):
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "auth_issuer_url", "https://i/v2.0")
    monkeypatch.setattr(settings, "auth_audience", "api://x")
    monkeypatch.setattr(
        core_auth, "get_oidc_metadata", AsyncMock(side_effect=DiscoveryError("down"))
    )
    status = await auth_startup_selfcheck()  # must not raise
    assert status["discovery"] == "unreachable"


async def test_selfcheck_does_not_gate_requests(monkeypatch):
    # Even if the startup self-check saw discovery down, per-request auth is unaffected:
    # there is no shared blocking flag.
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "auth_issuer_url", "https://i/v2.0")
    monkeypatch.setattr(settings, "auth_audience", "api://x")
    monkeypatch.setattr(
        core_auth, "get_oidc_metadata", AsyncMock(side_effect=DiscoveryError("down"))
    )
    await auth_startup_selfcheck()
    # discovery now healthy for the actual request:
    monkeypatch.setattr(core_auth, "validate_token", AsyncMock(return_value={"sub": "u"}))
    claims = await require_auth(_req({"authorization": "Bearer x"}))
    assert claims == {"sub": "u"}


def test_health_endpoint_includes_auth(test_client):
    resp = test_client.get("/api/v1/health")
    assert resp.status_code in (200, 503)
    body = resp.json()
    assert "auth" in body
    assert "enabled" in body["auth"]
    assert set(body["auth"]["surfaces"]) == {"ui", "cli", "api"}
