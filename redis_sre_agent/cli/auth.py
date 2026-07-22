"""CLI authentication: OIDC device-code login/logout (humans only).

`login` runs the RFC 8628 device-code flow against the provider's discovered
device_authorization_endpoint, caches the token to disk (0600), and refreshes it
silently. `load_cached_token` / `bearer_headers` let other CLI commands attach
the cached bearer when they call the API — that token is validated by the SAME shared
validator the API/WS use. In-process CLI commands are not gated this phase (OQ-1).
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Optional

import click
import httpx

from redis_sre_agent.core import auth as core_auth
from redis_sre_agent.core.config import settings

DEVICE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"
_REFRESH_BUFFER_SECONDS = 30


def _token_cache_path() -> Path:
    override = os.environ.get("SRE_AGENT_TOKEN_CACHE")
    if override:
        return Path(override)
    return Path.home() / ".config" / "redis-sre-agent" / "token.json"


def _metadata() -> dict:
    """Fetch OIDC discovery via the shared (async) validator, from sync CLI code."""
    return asyncio.run(core_auth.get_oidc_metadata())


def _post_form(url: str, data: dict) -> dict:
    """POST form-encoded and return JSON. OAuth endpoints return JSON even on errors."""
    resp = httpx.post(url, data=data, timeout=15.0)
    try:
        return resp.json()
    except ValueError:
        resp.raise_for_status()
        raise


def _save_token(token: dict) -> None:
    path = _token_cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "access_token": token["access_token"],
        "refresh_token": token.get("refresh_token"),
        "expires_at": time.time() + int(token.get("expires_in", 3600)),
    }
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        json.dump(payload, fh)


def _read_cache() -> Optional[dict]:
    path = _token_cache_path()
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (ValueError, OSError):
        return None


def _refresh(refresh_token: str) -> Optional[dict]:
    meta = _metadata()
    token = _post_form(
        meta["token_endpoint"],
        {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": settings.auth_cli_client_id,
            "scope": " ".join(settings.auth_scopes),
        },
    )
    if "access_token" not in token:
        return None
    token.setdefault("refresh_token", refresh_token)  # keep RT if provider didn't rotate it
    _save_token(token)
    return token


def load_cached_token() -> Optional[str]:
    """Return a usable access token from cache, refreshing silently if near expiry."""
    cache = _read_cache()
    if not cache:
        return None
    if cache.get("expires_at", 0) - time.time() > _REFRESH_BUFFER_SECONDS:
        return cache["access_token"]
    refresh_token = cache.get("refresh_token")
    if refresh_token:
        refreshed = _refresh(refresh_token)
        if refreshed:
            return refreshed["access_token"]
    return None


def bearer_headers() -> dict:
    """Authorization header for authenticated API calls, or {} when not logged in.

    The thin reusable helper other CLI commands use to attach the cached bearer:
    `httpx.get(url, headers=bearer_headers())`.
    """
    token = load_cached_token()
    return {"Authorization": f"Bearer {token}"} if token else {}


@click.command()
def login():
    """Authenticate via OIDC device-code flow and cache a token (humans only)."""
    if not core_auth.surface_enabled("cli"):
        raise click.ClickException(core_auth.surface_disabled_message("cli"))
    meta = _metadata()
    device_ep = meta.get("device_authorization_endpoint")
    if not device_ep:
        raise click.ClickException("provider exposes no device_authorization_endpoint")

    init = _post_form(
        device_ep,
        {"client_id": settings.auth_cli_client_id, "scope": " ".join(settings.auth_scopes)},
    )
    if "device_code" not in init:
        raise click.ClickException(f"device authorization failed: {init.get('error', init)}")

    click.echo(f"To sign in, open: {init.get('verification_uri')}")
    click.echo(f"and enter code: {init['user_code']}")
    if init.get("verification_uri_complete"):
        click.echo(f"(or open directly: {init['verification_uri_complete']})")

    interval = int(init.get("interval", 5))
    deadline = time.time() + int(init.get("expires_in", 300))
    token_ep = meta["token_endpoint"]
    while time.time() < deadline:
        token = _post_form(
            token_ep,
            {
                "grant_type": DEVICE_GRANT,
                "device_code": init["device_code"],
                "client_id": settings.auth_cli_client_id,
            },
        )
        if "access_token" in token:
            _save_token(token)
            click.echo("Login successful. Token cached.")
            return
        error = token.get("error")
        if error == "authorization_pending":
            time.sleep(interval)
        elif error == "slow_down":
            interval += 5
            time.sleep(interval)
        else:
            raise click.ClickException(f"device-code login failed: {error or token}")
    raise click.ClickException("device-code login timed out")


@click.command()
def logout():
    """Delete the cached CLI token."""
    path = _token_cache_path()
    if path.exists():
        path.unlink()
        click.echo("Logged out (cached token removed).")
    else:
        click.echo("No cached token.")
