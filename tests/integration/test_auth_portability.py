"""T-P1: OIDC portability acceptance test.

Proves the agent's auth is provider-neutral: pointing auth_issuer_url
at dex (a non-Entra OIDC provider) authenticates end-to-end using the SAME validator
and login/discovery code, with only CONFIG changed and NO code change. If Docker or the
dex image is unavailable, the test skips (it never silently passes).
"""

import time
from pathlib import Path

import httpx
import pytest

from redis_sre_agent.core import auth as core_auth
from redis_sre_agent.core.auth import get_oidc_metadata, reset_oidc_cache, validate_token
from redis_sre_agent.core.config import settings

pytestmark = pytest.mark.integration

DEX_ISSUER = "http://127.0.0.1:5556/dex"
DEX_CONFIG = Path(__file__).parent / "dex" / "dex-test-config.yaml"
CLIENT_ID = "sre-client"
CLIENT_SECRET = "sre-secret"


@pytest.fixture(scope="module")
def dex_server():
    try:
        from testcontainers.core.container import DockerContainer
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"testcontainers unavailable: {exc}")

    container = (
        DockerContainer("ghcr.io/dexidp/dex:v2.41.1")
        .with_command("dex serve /etc/dex/config.yaml")
        .with_bind_ports(5556, 5556)
        .with_volume_mapping(str(DEX_CONFIG), "/etc/dex/config.yaml", "ro")
    )
    try:
        container.start()
    except Exception as exc:  # docker missing / image unavailable
        pytest.skip(f"could not start dex container: {exc}")

    discovery = f"{DEX_ISSUER}/.well-known/openid-configuration"
    try:
        deadline = time.time() + 30
        while time.time() < deadline:
            try:
                if httpx.get(discovery, timeout=2.0).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(1)
        else:
            pytest.skip("dex did not become ready within 30s")
        yield
    finally:
        container.stop()


@pytest.fixture
def dex_config(monkeypatch, dex_server):
    # ONLY config changes — no code path is provider-specific.
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "auth_issuer_url", DEX_ISSUER)
    monkeypatch.setattr(settings, "auth_audience", CLIENT_ID)
    monkeypatch.setattr(settings, "auth_scopes", ["openid", "profile", "email"])
    reset_oidc_cache()
    yield
    reset_oidc_cache()


async def test_discovery_is_provider_neutral(dex_config):
    meta = await get_oidc_metadata()
    assert meta["issuer"] == DEX_ISSUER
    assert meta["jwks_uri"].startswith(DEX_ISSUER)
    assert "token_endpoint" in meta  # resolved from dex discovery, not hardcoded


async def test_dex_token_validates_with_no_code_change(dex_config):
    meta = await get_oidc_metadata()
    # Acquire a real dex-signed JWT via the password grant (test-only convenience).
    resp = httpx.post(
        meta["token_endpoint"],
        data={
            "grant_type": "password",
            "username": "admin@example.com",
            "password": "password",
            "scope": "openid profile email",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
        },
        timeout=10.0,
    )
    assert resp.status_code == 200, resp.text
    id_token = resp.json()["id_token"]

    # The SAME validator used for Entra now accepts a dex-issued token — config only.
    claims = await validate_token(id_token)
    assert claims["iss"] == DEX_ISSUER
    assert claims["aud"] == CLIENT_ID
    assert claims["email"] == "admin@example.com"


async def test_wrong_audience_rejected_against_dex(dex_config, monkeypatch):
    meta = await get_oidc_metadata()
    resp = httpx.post(
        meta["token_endpoint"],
        data={
            "grant_type": "password",
            "username": "admin@example.com",
            "password": "password",
            "scope": "openid profile email",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
        },
        timeout=10.0,
    )
    id_token = resp.json()["id_token"]
    # A deployment expecting a different audience must reject this real token.
    monkeypatch.setattr(settings, "auth_audience", "api://someone-else")
    reset_oidc_cache()
    with pytest.raises(core_auth.AuthError) as ei:
        await validate_token(id_token)
    assert ei.value.reason == "bad_audience"
