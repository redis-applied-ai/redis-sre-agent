"""Integration tests for API auth: require_auth truth table, route enforcement,
/auth/login|callback|logout, CORS preflight, and fail-closed discovery recovery.

Auth defaults OFF, so the rest of the suite is unaffected; these tests toggle it ON.
"""

from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.routing import APIRoute
from starlette.requests import Request

from redis_sre_agent.api import auth as api_auth
from redis_sre_agent.api.auth import require_auth
from redis_sre_agent.core import auth as core_auth
from redis_sre_agent.core.auth import AuthError, DiscoveryError
from redis_sre_agent.core.config import settings

ISS = "https://issuer.example.com/v2.0"
AUD = "api://sre-agent"
_META = {
    "issuer": ISS,
    "jwks_uri": "https://issuer.example.com/jwks",
    "authorization_endpoint": "https://issuer.example.com/authorize",
    "token_endpoint": "https://issuer.example.com/token",
    "end_session_endpoint": "https://issuer.example.com/logout",
    "device_authorization_endpoint": "https://issuer.example.com/devicecode",
}

_EXEMPT = {
    "/",
    "/api/v1/",
    "/api/v1/health",
    "/api/v1/metrics",
    "/api/v1/metrics/health",
    "/docs",
    "/openapi.json",
    "/redoc",
}


def _is_exempt(path: str) -> bool:
    return path in _EXEMPT or path.startswith("/auth")


def _req(headers=None, path="/api/v1/tasks"):
    raw = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "headers": raw,
        "query_string": b"",
        "client": ("test", 1),
    }
    return Request(scope)


@pytest.fixture
def auth_on(monkeypatch):
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "auth_issuer_url", ISS)
    monkeypatch.setattr(settings, "auth_audience", AUD)
    monkeypatch.setattr(settings, "auth_scopes", ["openid", "profile", "email"])
    yield monkeypatch


# ---------- require_auth truth table (T-U2 / T-I1 unit level) ----------
async def test_require_auth_open_mode_returns_empty(monkeypatch):
    monkeypatch.setattr(settings, "auth_enabled", False)
    assert await require_auth(_req()) == {}


async def test_require_auth_enabled_missing_config_503(monkeypatch):
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "auth_issuer_url", None)
    monkeypatch.setattr(settings, "auth_audience", None)
    with pytest.raises(Exception) as ei:
        await require_auth(_req())
    assert getattr(ei.value, "status_code", None) == 503


async def test_require_auth_missing_bearer_401(auth_on):
    with pytest.raises(Exception) as ei:
        await require_auth(_req(headers={}))
    assert ei.value.status_code == 401


async def test_require_auth_invalid_token_401(auth_on):
    auth_on.setattr(core_auth, "validate_token", AsyncMock(side_effect=AuthError("expired")))
    with pytest.raises(Exception) as ei:
        await require_auth(_req(headers={"authorization": "Bearer x"}))
    assert ei.value.status_code == 401
    assert ei.value.detail == "expired"


async def test_require_auth_valid_token_returns_claims(auth_on):
    auth_on.setattr(core_auth, "validate_token", AsyncMock(return_value={"sub": "u-1"}))
    claims = await require_auth(_req(headers={"authorization": "Bearer good"}))
    assert claims == {"sub": "u-1"}


# ---------- T-I5: transient discovery failure -> 503, then auto-recover ----------
async def test_require_auth_discovery_down_503_then_recovers(auth_on):
    vt = AsyncMock(side_effect=DiscoveryError("down"))
    auth_on.setattr(core_auth, "validate_token", vt)
    with pytest.raises(Exception) as ei:
        await require_auth(_req(headers={"authorization": "Bearer x"}))
    assert ei.value.status_code == 503
    # discovery recovers — no restart, same dependency now succeeds
    vt.side_effect = None
    vt.return_value = {"sub": "u-1"}
    assert await require_auth(_req(headers={"authorization": "Bearer x"})) == {"sub": "u-1"}


# ---------- T-I1: every protected GET route rejects anonymous with 401 ----------
def test_all_protected_get_routes_401_when_anonymous(test_client, auth_on):
    app = test_client.app
    protected = [
        r
        for r in app.routes
        if isinstance(r, APIRoute)
        and "GET" in r.methods
        and "{" not in r.path
        and not _is_exempt(r.path)
    ]
    assert protected, "expected at least one protected parameterless GET route"
    for r in protected:
        resp = test_client.get(r.path)
        assert resp.status_code == 401, f"{r.path} -> {resp.status_code} (expected 401)"


def test_exempt_routes_not_401_when_enabled(test_client, auth_on):
    assert test_client.get("/").status_code == 200
    for path in ("/api/v1/health", "/api/v1/metrics"):
        assert test_client.get(path).status_code != 401, path


def test_open_mode_allows_anonymous(test_client, monkeypatch):
    monkeypatch.setattr(settings, "auth_enabled", False)
    # A protected route no longer 401s when auth is disabled (backward compatible).
    assert test_client.get("/api/v1/metrics").status_code != 401


# ---------- T-I2: /auth/login + /auth/callback ----------
@pytest.fixture
def api_surface(auth_on):
    auth_on.setattr(settings, "auth_api_client_id", "api-client")
    auth_on.setattr(settings, "auth_api_public_base_url", "https://api.example.com")
    auth_on.setattr(core_auth, "get_oidc_metadata", AsyncMock(return_value=_META))
    yield auth_on


def test_login_redirects_to_authorization_endpoint(test_client, api_surface):
    resp = test_client.get("/auth/login", follow_redirects=False)
    assert resp.status_code == 302
    loc = resp.headers["location"]
    assert loc.startswith(_META["authorization_endpoint"])
    q = parse_qs(urlparse(loc).query)
    assert q["client_id"] == ["api-client"]
    assert q["redirect_uri"] == ["https://api.example.com/auth/callback"]
    assert q["code_challenge_method"] == ["S256"]
    assert "code_challenge" in q
    assert api_auth._PKCE_COOKIE in resp.cookies
    assert api_auth._STATE_COOKIE in resp.cookies


def test_callback_exchanges_code_for_token(test_client, api_surface):
    class _FakeOAuth:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def fetch_token(self, *a, **k):
            return {"access_token": "tok-123", "token_type": "Bearer"}

    api_surface.setattr(api_auth, "AsyncOAuth2Client", _FakeOAuth)
    # login first to obtain matching state + verifier cookies
    login = test_client.get("/auth/login", follow_redirects=False)
    state = login.cookies[api_auth._STATE_COOKIE]
    resp = test_client.get(f"/auth/callback?code=abc&state={state}", follow_redirects=False)
    assert resp.status_code == 200, resp.text
    assert resp.json()["access_token"] == "tok-123"


def test_callback_rejects_state_mismatch(test_client, api_surface):
    test_client.get("/auth/login", follow_redirects=False)
    resp = test_client.get("/auth/callback?code=abc&state=wrong", follow_redirects=False)
    assert resp.status_code == 400


def test_login_disabled_when_api_surface_absent(test_client, auth_on):
    auth_on.setattr(settings, "auth_api_client_id", None)
    resp = test_client.get("/auth/login", follow_redirects=False)
    assert resp.status_code == 404


def test_login_fail_closed_without_base_url(test_client, auth_on):
    auth_on.setattr(settings, "auth_api_client_id", "api-client")
    auth_on.setattr(settings, "auth_api_public_base_url", None)
    resp = test_client.get("/auth/login", follow_redirects=False)
    assert resp.status_code == 503


# ---------- logout ----------
def test_logout_redirects_to_end_session(test_client, api_surface):
    resp = test_client.get("/auth/logout", follow_redirects=False)
    assert resp.status_code == 302
    loc = resp.headers["location"]
    assert loc.startswith(_META["end_session_endpoint"])
    q = parse_qs(urlparse(loc).query)
    assert q["post_logout_redirect_uri"] == ["https://api.example.com/"]


# ---------- T-I4: CORS preflight allows Authorization ----------
def test_cors_preflight_allows_authorization(test_client):
    resp = test_client.options(
        "/api/v1/tasks",
        headers={
            "Origin": "http://localhost:3002",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    assert resp.status_code in (200, 204)
    allow = resp.headers.get("access-control-allow-headers", "").lower()
    assert "authorization" in allow
