"""Unit tests for the shared OIDC/JWT validator (redis_sre_agent.core.auth).

No network: discovery is primed into the module cache and the JWKS client is replaced
with a fake that returns a locally generated RSA public key. Tokens are signed with the
matching private key so signature verification is real.
"""

import time
from types import SimpleNamespace

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.exceptions import PyJWKClientError

from redis_sre_agent.core import auth as auth_mod
from redis_sre_agent.core.auth import (
    AuthConfigError,
    AuthError,
    surface_disabled_message,
    surface_enabled,
    validate_token,
)
from redis_sre_agent.core.config import settings

ISS = "https://issuer.example.com/v2.0"
AUD = "api://sre-agent"


@pytest.fixture
def rsa_keys():
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return priv, priv.public_key()


@pytest.fixture(autouse=True)
def _auth_env(monkeypatch, rsa_keys):
    """Enable auth, prime discovery, and stub the JWKS client with our public key."""
    _priv, pub = rsa_keys
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "auth_issuer_url", ISS)
    monkeypatch.setattr(settings, "auth_audience", AUD)
    monkeypatch.setattr(settings, "auth_clock_skew_leeway_seconds", 60)

    auth_mod.reset_oidc_cache()
    auth_mod._metadata_cache = {"issuer": ISS, "jwks_uri": "https://issuer.example.com/jwks"}
    auth_mod._metadata_expires_at = time.monotonic() + 3600

    fake_client = SimpleNamespace(get_signing_key_from_jwt=lambda token: SimpleNamespace(key=pub))
    monkeypatch.setattr(auth_mod, "_get_jwks_client", lambda jwks_uri: fake_client)
    yield
    auth_mod.reset_oidc_cache()


def _token(priv, *, kid="k1", **overrides):
    now = int(time.time())
    payload = {"iss": ISS, "aud": AUD, "sub": "user-1", "iat": now, "exp": now + 3600}
    payload.update(overrides)
    return pyjwt.encode(payload, priv, algorithm="RS256", headers={"kid": kid})


# --- T-U1: happy path ---
async def test_valid_token_returns_claims(rsa_keys):
    priv, _ = rsa_keys
    claims = await validate_token(_token(priv))
    assert claims["sub"] == "user-1"
    assert claims["aud"] == AUD
    assert claims["iss"] == ISS


# --- T-U2: deny-by-default rejection cases (validator level) ---
async def test_expired_rejected(rsa_keys):
    priv, _ = rsa_keys
    now = int(time.time())
    with pytest.raises(AuthError) as ei:
        await validate_token(_token(priv, iat=now - 7200, exp=now - 3600))
    assert ei.value.reason == "expired"


async def test_wrong_audience_rejected(rsa_keys):
    priv, _ = rsa_keys
    with pytest.raises(AuthError) as ei:
        await validate_token(_token(priv, aud="api://someone-else"))
    assert ei.value.reason == "bad_audience"


async def test_wrong_issuer_rejected(rsa_keys):
    priv, _ = rsa_keys
    with pytest.raises(AuthError) as ei:
        await validate_token(_token(priv, iss="https://evil.example.com/v2.0"))
    assert ei.value.reason == "bad_issuer"


async def test_bad_signature_rejected(rsa_keys):
    # Sign with a DIFFERENT key than the public key the validator holds.
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with pytest.raises(AuthError) as ei:
        await validate_token(_token(other))
    assert ei.value.reason == "bad_signature"


async def test_malformed_rejected():
    with pytest.raises(AuthError) as ei:
        await validate_token("not-a-jwt")
    assert ei.value.reason in {"malformed", "invalid"}


async def test_missing_token_rejected():
    with pytest.raises(AuthError) as ei:
        await validate_token("")
    assert ei.value.reason == "missing"


# --- T-U2b: fail-closed when resource config absent ---
async def test_get_oidc_metadata_fails_closed_without_config(monkeypatch, rsa_keys):
    priv, _ = rsa_keys
    monkeypatch.setattr(settings, "auth_issuer_url", None)
    monkeypatch.setattr(settings, "auth_audience", None)
    auth_mod.reset_oidc_cache()  # force re-evaluation (no primed cache)
    with pytest.raises(AuthConfigError):
        await validate_token(_token(priv))


class _BoomClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url):
        import httpx

        raise httpx.ConnectError("discovery down")


async def test_discovery_serves_stale_cache_on_refresh_failure(monkeypatch):
    # Cache present but expired -> refresh attempted; the fetch fails, so the prior
    # good copy is served (stale-while-revalidate) instead of failing closed.
    import httpx

    auth_mod._metadata_cache = {"issuer": ISS, "jwks_uri": "https://issuer.example.com/jwks"}
    auth_mod._metadata_expires_at = time.monotonic() - 1
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: _BoomClient())
    meta = await auth_mod.get_oidc_metadata()
    assert meta["issuer"] == ISS  # served stale, did not raise


async def test_discovery_raises_when_no_cache(monkeypatch):
    import httpx

    from redis_sre_agent.core.auth import DiscoveryError

    auth_mod.reset_oidc_cache()  # nothing cached
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: _BoomClient())
    with pytest.raises(DiscoveryError):
        await auth_mod.get_oidc_metadata()


# --- T-U4: JWKS rotation / unknown kid → typed error, not a crash ---
async def test_unknown_kid_maps_to_invalid_key(monkeypatch, rsa_keys):
    priv, pub = rsa_keys

    def _raiser(token):
        raise PyJWKClientError("Unable to find a signing key that matches kid")

    monkeypatch.setattr(
        auth_mod, "_get_jwks_client", lambda uri: SimpleNamespace(get_signing_key_from_jwt=_raiser)
    )
    with pytest.raises(AuthError) as ei:
        await validate_token(_token(priv, kid="rotated-away"))
    assert ei.value.reason == "invalid_key"

    # After "rotation" resolves, the same validator accepts a good token (no restart).
    monkeypatch.setattr(
        auth_mod,
        "_get_jwks_client",
        lambda uri: SimpleNamespace(get_signing_key_from_jwt=lambda t: SimpleNamespace(key=pub)),
    )
    claims = await validate_token(_token(priv, kid="k-new"))
    assert claims["sub"] == "user-1"


# --- T-U5: clock-skew leeway ---
async def test_clock_skew_within_leeway_accepted(rsa_keys):
    priv, _ = rsa_keys
    now = int(time.time())
    claims = await validate_token(_token(priv, iat=now - 120, exp=now - 30))  # 30s past, leeway 60
    assert claims["sub"] == "user-1"


async def test_clock_skew_beyond_leeway_rejected(rsa_keys):
    priv, _ = rsa_keys
    now = int(time.time())
    with pytest.raises(AuthError) as ei:
        await validate_token(_token(priv, iat=now - 200, exp=now - 90))  # 90s past, leeway 60
    assert ei.value.reason == "expired"


# --- T-U3: partial registration (surface helpers) ---
def test_surface_enabled_partial(monkeypatch):
    monkeypatch.setattr(settings, "auth_ui_client_id", "ui-client")
    monkeypatch.setattr(settings, "auth_cli_client_id", None)
    monkeypatch.setattr(settings, "auth_api_client_id", None)
    assert surface_enabled("ui") is True
    assert surface_enabled("cli") is False
    assert "CLI login is not configured" in surface_disabled_message("cli")
