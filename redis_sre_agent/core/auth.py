"""Shared OIDC/JWT authentication (authn only).

THE single JWKS validator for the whole agent. Every surface (REST API, WebSockets,
CLI-via-API) validates its bearer token through `validate_token` here — only token
*acquisition* differs per surface. Provider-neutral: everything (issuer, jwks_uri,
authorize/token/device/end-session endpoints) is read from the provider's OIDC
discovery document, so swapping Entra for another OIDC provider is a config change.

Structural invariant (AC-8): `jwt.decode`, `PyJWKClient`, and JWKS/discovery fetching
appear ONLY in this module. Do not validate tokens anywhere else.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, Optional

import httpx
import jwt
from jwt import PyJWKClient
from jwt.exceptions import PyJWKClientError

from redis_sre_agent.core.config import settings

logger = logging.getLogger(__name__)

# Surfaces whose client is configured independently (partial registration).
_SURFACES = ("ui", "cli", "api")


class AuthError(Exception):
    """Token validation failed. `reason` is a stable, log-safe slug (never the token)."""

    def __init__(self, reason: str, detail: str = ""):
        self.reason = reason
        super().__init__(detail or reason)


class AuthConfigError(Exception):
    """Auth is enabled but resource config (issuer/audience) is missing — fail closed."""


class DiscoveryError(Exception):
    """OIDC discovery is currently unreachable — transient; caller should 503 and retry."""


# --- discovery + JWKS caches (module-level; reset via reset_oidc_cache for tests) ---
_metadata_cache: Optional[Dict[str, Any]] = None
_metadata_expires_at: float = 0.0
_jwks_client: Optional[PyJWKClient] = None
_jwks_client_uri: Optional[str] = None


def reset_oidc_cache() -> None:
    """Drop cached discovery + JWKS client. For tests and config reloads."""
    global _metadata_cache, _metadata_expires_at, _jwks_client, _jwks_client_uri
    _metadata_cache = None
    _metadata_expires_at = 0.0
    _jwks_client = None
    _jwks_client_uri = None


def auth_resource_configured() -> bool:
    """True when the resource config required to validate tokens is present."""
    return bool(settings.auth_issuer_url and settings.auth_audience)


def surface_enabled(kind: str) -> bool:
    """Whether a surface's login is configured (its client_id is set)."""
    return bool(getattr(settings, f"auth_{kind}_client_id", None))


def surface_disabled_message(kind: str) -> str:
    """Actionable message when an unconfigured surface's login is used."""
    return (
        f"{kind.upper()} login is not configured on this deployment. "
        f"Set auth_{kind}_client_id (and required companion settings) to enable it."
    )


async def get_oidc_metadata() -> Dict[str, Any]:
    """Return the cached OIDC discovery document, fetching/refreshing as needed.

    Cached for `auth_jwks_cache_ttl_seconds`. On a transient fetch failure this raises
    `DiscoveryError` and does NOT cache the failure (so the next request retries) — a
    transient IdP blip therefore recovers on its own without a restart.
    """
    global _metadata_cache, _metadata_expires_at

    if not auth_resource_configured():
        raise AuthConfigError("auth_enabled but auth_issuer_url/auth_audience are not set")

    now = time.monotonic()
    if _metadata_cache is not None and now < _metadata_expires_at:
        return _metadata_cache

    issuer = (settings.auth_issuer_url or "").rstrip("/")
    url = f"{issuer}/.well-known/openid-configuration"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            metadata = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        # Transient failure. If we have a previously-fetched document, keep serving it
        # (stale-while-revalidate): issuer/jwks_uri are stable and JWKS keys are fetched
        # separately by PyJWKClient, so validation stays correct and available through a
        # discovery blip. Only fail closed when we have nothing cached at all.
        if _metadata_cache is not None:
            logger.warning(
                "OIDC discovery refresh failed (%s); serving cached metadata: %s", url, exc
            )
            return _metadata_cache
        logger.warning("OIDC discovery fetch failed (%s): %s", url, exc)
        raise DiscoveryError(str(exc)) from exc

    if "issuer" not in metadata or "jwks_uri" not in metadata:
        raise DiscoveryError(f"discovery document missing issuer/jwks_uri: {url}")

    _metadata_cache = metadata
    _metadata_expires_at = now + max(1, settings.auth_jwks_cache_ttl_seconds)
    return metadata


def _get_jwks_client(jwks_uri: str) -> PyJWKClient:
    """Lazy singleton PyJWKClient. PyJWKClient caches keys and refetches on unknown kid."""
    global _jwks_client, _jwks_client_uri
    if _jwks_client is None or _jwks_client_uri != jwks_uri:
        _jwks_client = PyJWKClient(
            jwks_uri,
            cache_keys=True,
            lifespan=max(1, settings.auth_jwks_cache_ttl_seconds),
        )
        _jwks_client_uri = jwks_uri
    return _jwks_client


def auth_status() -> Dict[str, Any]:
    """Advisory summary of auth configuration for health/observability (never gates)."""
    return {
        "enabled": settings.auth_enabled,
        "resource_configured": auth_resource_configured(),
        "surfaces": {kind: surface_enabled(kind) for kind in _SURFACES},
        "fail_closed": settings.auth_enabled and not auth_resource_configured(),
        # Infrastructure authorization (authz) flag — surfaced so the UI can hide features
        # that are unavailable when authz is on (e.g. scheduling). Advisory only; never gates.
        "infrastructure_authorization_enabled": settings.infrastructure_authorization_enabled,
    }


async def auth_startup_selfcheck() -> Dict[str, Any]:
    """Log an advisory startup self-check and return the auth status.

    Observability ONLY — this NEVER gates requests and sets no flag that `require_auth`
    reads (per-request `get_oidc_metadata` is the sole enforcement source). A discovery
    blip here is logged, not fatal, so a transient IdP outage at boot cannot brick the API.
    """
    status = auth_status()
    if not settings.auth_enabled:
        logger.info("Auth self-check: DISABLED (open mode) - all surfaces unauthenticated.")
        return status
    if not auth_resource_configured():
        logger.warning(
            "Auth self-check: ENABLED but FAIL-CLOSED - auth_issuer_url/auth_audience "
            "missing; protected routes will 503 until configured."
        )
        return status
    try:
        await get_oidc_metadata()
        status["discovery"] = "ok"
        logger.info(
            "Auth self-check: ENABLED surfaces=%s discovery=ok",
            status["surfaces"],
        )
    except Exception as exc:  # advisory only - never blocks startup
        status["discovery"] = "unreachable"
        logger.warning(
            "Auth self-check: ENABLED but discovery unreachable at startup "
            "(advisory; retried per-request): %s",
            exc,
        )
    return status


async def validate_token(token: str) -> Dict[str, Any]:
    """Validate a bearer JWT and return its claims. THE one validation path.

    Checks signature (provider JWKS, RS256), issuer (discovered), audience
    (`auth_audience`), and expiry (with `auth_clock_skew_leeway_seconds` leeway).
    Raises `AuthError(reason)` on any validation failure and `DiscoveryError` when the
    provider metadata/JWKS cannot currently be reached.
    """
    if not token:
        raise AuthError("missing")

    metadata = await get_oidc_metadata()
    jwks_uri = metadata["jwks_uri"]
    issuer = metadata["issuer"]
    client = _get_jwks_client(jwks_uri)

    try:
        # PyJWKClient does blocking HTTP on a cache miss; keep it off the event loop.
        signing_key = await asyncio.to_thread(client.get_signing_key_from_jwt, token)
    except PyJWKClientError as exc:
        # Unknown/unresolvable kid — treat as an untrusted key.
        raise AuthError("invalid_key", str(exc)) from exc
    except jwt.DecodeError as exc:
        raise AuthError("malformed", str(exc)) from exc

    try:
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=settings.auth_audience,
            issuer=issuer,
            leeway=settings.auth_clock_skew_leeway_seconds,
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthError("expired", str(exc)) from exc
    except jwt.InvalidAudienceError as exc:
        raise AuthError("bad_audience", str(exc)) from exc
    except jwt.InvalidIssuerError as exc:
        raise AuthError("bad_issuer", str(exc)) from exc
    except jwt.InvalidSignatureError as exc:
        raise AuthError("bad_signature", str(exc)) from exc
    except jwt.InvalidTokenError as exc:  # base class — catch last
        raise AuthError("invalid", str(exc)) from exc

    return claims
