"""API authentication: the bearer dependency + the browser-login endpoints (/auth/*).

`require_auth` is the HTTP enforcement point; every protected router depends on it. It
and the /auth endpoints route all token validation and discovery through the ONE shared
validator in `core.auth` (only token *acquisition* differs per surface).

The /auth/login + /auth/callback + /auth/logout endpoints are the API's own browser-login
convenience (a human hitting the API directly in a browser). The SPA UI does its own PKCE
round-trip client-side and does not use these. PKCE verifier + state are held in short-lived
httponly cookies, so no server-side session store is required.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import secrets
from urllib.parse import urlencode

from authlib.integrations.httpx_client import AsyncOAuth2Client
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

from redis_sre_agent.core import auth as core_auth
from redis_sre_agent.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Auth"])

_PKCE_COOKIE = "sre_auth_pkce"
_STATE_COOKIE = "sre_auth_state"
_COOKIE_MAX_AGE = 600  # 10 min: only spans the login->callback round-trip


async def require_auth(request: Request) -> dict:
    """FastAPI dependency enforcing a valid bearer token on protected routes.

    - auth disabled           -> {} (open mode, backward compatible)
    - enabled, no resource cfg -> 503 (fail-closed; never silently open)
    - enabled, discovery down  -> 503 (transient; auto-recovers, no restart)
    - enabled, bad/missing tok -> 401

    On success it also sets the infrastructure-authorization token (the validated bearer) in a
    ContextVar so synchronous surfaces (cluster/instance list endpoints) enforce via the same
    token. No explicit reset needed here: Starlette handles each request in its own asyncio
    task, and ContextVars are per-task, so there is no cross-request bleed. (The worker/docket
    paths, which may reuse a context, DO reset in finally — see the @sre_task tops.)
    """
    if not settings.auth_enabled:
        return {}
    if not core_auth.auth_resource_configured():
        raise HTTPException(status_code=503, detail="auth misconfigured (fail-closed)")

    header = request.headers.get("authorization")
    if not header or not header.lower().startswith("bearer "):
        logger.info("auth reject reason=missing path=%s", request.url.path)
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = header.split(" ", 1)[1].strip()

    try:
        claims = await core_auth.validate_token(token)
    except core_auth.DiscoveryError as exc:
        raise HTTPException(status_code=503, detail="auth provider discovery unavailable") from exc
    except core_auth.AuthConfigError as exc:
        raise HTTPException(status_code=503, detail="auth misconfigured (fail-closed)") from exc
    except core_auth.AuthError as exc:
        logger.info("auth reject reason=%s path=%s", exc.reason, request.url.path)
        raise HTTPException(status_code=401, detail=exc.reason) from exc

    request.state.auth_claims = claims

    from redis_sre_agent.core.authorization import set_auth_token

    set_auth_token(token)
    return claims


def _require_api_login_surface() -> None:
    """Guard the /auth browser endpoints: partial-registration + fail-closed on base URL."""
    if not core_auth.surface_enabled("api"):
        raise HTTPException(status_code=404, detail=core_auth.surface_disabled_message("api"))
    if not settings.auth_api_public_base_url:
        raise HTTPException(
            status_code=503,
            detail="auth_api_public_base_url is required when the API login surface is enabled (fail-closed)",
        )


async def _login_metadata() -> dict:
    """Fetch OIDC discovery for the browser endpoints, mapping failures to fail-closed
    503s (same contract as require_auth) instead of leaking a 500."""
    try:
        return await core_auth.get_oidc_metadata()
    except core_auth.DiscoveryError as exc:
        raise HTTPException(status_code=503, detail="auth provider discovery unavailable") from exc
    except core_auth.AuthConfigError as exc:
        raise HTTPException(status_code=503, detail="auth misconfigured (fail-closed)") from exc


def _redirect_uri() -> str:
    return settings.auth_api_public_base_url.rstrip("/") + "/auth/callback"


@router.get("/login")
async def login():
    """302 -> the provider's discovered authorization_endpoint (auth-code + PKCE)."""
    _require_api_login_surface()
    meta = await _login_metadata()

    verifier = secrets.token_urlsafe(64)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    )
    state = secrets.token_urlsafe(32)
    params = {
        "response_type": "code",
        "client_id": settings.auth_api_client_id,
        "redirect_uri": _redirect_uri(),
        "scope": " ".join(settings.auth_scopes),
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    url = meta["authorization_endpoint"] + "?" + urlencode(params)
    resp = RedirectResponse(url, status_code=302)
    resp.set_cookie(_PKCE_COOKIE, verifier, httponly=True, max_age=_COOKIE_MAX_AGE, samesite="lax")
    resp.set_cookie(_STATE_COOKIE, state, httponly=True, max_age=_COOKIE_MAX_AGE, samesite="lax")
    return resp


@router.get("/callback")
async def callback(request: Request, code: str = "", state: str = ""):
    """Exchange the authorization code at the discovered token_endpoint; return the token."""
    _require_api_login_surface()
    expected_state = request.cookies.get(_STATE_COOKIE)
    verifier = request.cookies.get(_PKCE_COOKIE)
    if not code or not state or state != expected_state or not verifier:
        raise HTTPException(status_code=400, detail="invalid auth callback (state/code mismatch)")

    meta = await _login_metadata()
    secret = (
        settings.auth_api_client_secret.get_secret_value()
        if settings.auth_api_client_secret
        else None
    )
    async with AsyncOAuth2Client(
        client_id=settings.auth_api_client_id,
        client_secret=secret,
        token_endpoint_auth_method="client_secret_post",
    ) as client:
        token = await client.fetch_token(
            meta["token_endpoint"],
            grant_type="authorization_code",
            code=code,
            redirect_uri=_redirect_uri(),
            code_verifier=verifier,
        )

    resp = JSONResponse(dict(token))
    resp.delete_cookie(_PKCE_COOKIE)
    resp.delete_cookie(_STATE_COOKIE)
    return resp


@router.get("/logout")
async def logout():
    """302 -> the provider's discovered end_session_endpoint (ends the SSO session).

    Stateless: no server session to invalidate. An already-issued JWT stays valid until
    its TTL — revocation before expiry would require a denylist (out of scope this phase).
    """
    _require_api_login_surface()
    meta = await _login_metadata()
    end_session = meta.get("end_session_endpoint")
    if not end_session:
        raise HTTPException(status_code=501, detail="provider exposes no end_session_endpoint")
    post_logout = settings.auth_api_public_base_url.rstrip("/") + "/"
    url = end_session + "?" + urlencode({"post_logout_redirect_uri": post_logout})
    return RedirectResponse(url, status_code=302)
