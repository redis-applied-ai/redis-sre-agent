"""CLI device-code login/logout + token-cache tests (US-003)."""

from unittest.mock import AsyncMock

import pytest
from click.testing import CliRunner
from starlette.requests import Request

from redis_sre_agent.api.auth import require_auth
from redis_sre_agent.cli import auth as cli_auth
from redis_sre_agent.core import auth as core_auth
from redis_sre_agent.core.config import settings

_META = {
    "device_authorization_endpoint": "https://issuer.example.com/devicecode",
    "token_endpoint": "https://issuer.example.com/token",
    "issuer": "https://issuer.example.com/v2.0",
    "jwks_uri": "https://issuer.example.com/jwks",
}


@pytest.fixture
def cache_path(tmp_path, monkeypatch):
    path = tmp_path / "token.json"
    monkeypatch.setattr(cli_auth, "_token_cache_path", lambda: path)
    return path


@pytest.fixture
def cli_surface(monkeypatch):
    monkeypatch.setattr(settings, "auth_cli_client_id", "cli-client")
    monkeypatch.setattr(settings, "auth_scopes", ["openid", "profile", "email"])
    monkeypatch.setattr(cli_auth, "_metadata", lambda: _META)


def _fake_post(device_resp, token_resp):
    def _post(url, data):
        return device_resp if "devicecode" in url else token_resp

    return _post


def test_login_writes_cache_0600(cache_path, cli_surface, monkeypatch):
    device = {
        "device_code": "dc",
        "user_code": "WXYZ-1234",
        "verification_uri": "https://verify.example.com",
        "interval": 1,
        "expires_in": 300,
    }
    token = {"access_token": "at-1", "refresh_token": "rt-1", "expires_in": 3600}
    monkeypatch.setattr(cli_auth, "_post_form", _fake_post(device, token))

    result = CliRunner().invoke(cli_auth.login)
    assert result.exit_code == 0, result.output
    assert "WXYZ-1234" in result.output
    assert cache_path.exists()
    assert oct(cache_path.stat().st_mode & 0o777) == "0o600"
    assert cli_auth._read_cache()["access_token"] == "at-1"


def test_login_disabled_when_cli_surface_absent(cache_path, monkeypatch):
    monkeypatch.setattr(settings, "auth_cli_client_id", None)
    result = CliRunner().invoke(cli_auth.login)
    assert result.exit_code != 0
    assert "CLI login is not configured" in result.output


def test_login_reports_device_error(cache_path, cli_surface, monkeypatch):
    monkeypatch.setattr(cli_auth, "_post_form", _fake_post({"error": "invalid_client"}, {}))
    result = CliRunner().invoke(cli_auth.login)
    assert result.exit_code != 0
    assert "device authorization failed" in result.output


def test_load_cached_token_valid(cache_path, cli_surface):
    cli_auth._save_token({"access_token": "at-9", "refresh_token": "rt", "expires_in": 3600})
    assert cli_auth.load_cached_token() == "at-9"


def test_load_cached_token_missing(cache_path):
    assert cli_auth.load_cached_token() is None


def test_load_cached_token_refreshes_when_expired(cache_path, cli_surface, monkeypatch):
    cli_auth._save_token({"access_token": "old", "refresh_token": "rt-2", "expires_in": -10})
    monkeypatch.setattr(
        cli_auth,
        "_post_form",
        lambda url, data: {"access_token": "fresh", "expires_in": 3600},
    )
    assert cli_auth.load_cached_token() == "fresh"
    assert cli_auth._read_cache()["access_token"] == "fresh"


def test_logout_removes_cache(cache_path, cli_surface):
    cli_auth._save_token({"access_token": "at", "expires_in": 3600})
    assert cache_path.exists()
    result = CliRunner().invoke(cli_auth.logout)
    assert result.exit_code == 0
    assert not cache_path.exists()


# ---------- AC-6: cached token attaches and is validated by the SAME validator ----------
def _req(headers):
    raw = [(k.lower().encode(), v.encode()) for k, v in headers.items()]
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/tasks",
        "headers": raw,
        "query_string": b"",
        "client": ("cli", 1),
    }
    return Request(scope)


async def test_cli_token_accepted_by_shared_validator(cache_path, cli_surface, monkeypatch):
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "auth_issuer_url", _META["issuer"])
    monkeypatch.setattr(settings, "auth_audience", "api://x")
    monkeypatch.setattr(core_auth, "validate_token", AsyncMock(return_value={"sub": "cli-user"}))

    cli_auth._save_token({"access_token": "at-cli", "expires_in": 3600})
    claims = await require_auth(_req(cli_auth.bearer_headers()))
    assert claims == {"sub": "cli-user"}
    core_auth.validate_token.assert_awaited_once_with("at-cli")


async def test_no_login_is_401_via_shared_validator(cache_path, monkeypatch):
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "auth_issuer_url", _META["issuer"])
    monkeypatch.setattr(settings, "auth_audience", "api://x")
    # no cache -> bearer_headers() is empty -> require_auth 401
    with pytest.raises(Exception) as ei:
        await require_auth(_req(cli_auth.bearer_headers()))
    assert ei.value.status_code == 401
