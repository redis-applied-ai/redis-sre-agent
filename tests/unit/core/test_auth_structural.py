"""Structural + observability guarantees (AC-8, AC-9, T-O2)."""

import logging
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from starlette.requests import Request

import redis_sre_agent
from redis_sre_agent.api.auth import require_auth
from redis_sre_agent.core import auth as core_auth
from redis_sre_agent.core.auth import AuthError
from redis_sre_agent.core.config import settings

PKG = Path(redis_sre_agent.__file__).parent


def _py_files():
    return list(PKG.rglob("*.py"))


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


# ---------- AC-8: JWT validation primitives live ONLY in core/auth.py ----------
def test_jwt_primitives_only_in_core_auth():
    primitives = ["jwt.decode(", "PyJWKClient", "get_signing_key_from_jwt"]
    offenders = {}
    for path in _py_files():
        if path.name == "auth.py" and path.parent.name == "core":
            continue  # the one allowed home
        text = path.read_text(encoding="utf-8")
        hits = [tok for tok in primitives if tok in text]
        if hits:
            offenders[str(path.relative_to(PKG))] = hits
    assert not offenders, f"JWT primitives leaked outside core/auth.py: {offenders}"


# ---------- AC-9: no static/long-lived API-key auth path ----------
def test_no_settings_api_key_usage_in_request_path():
    offenders = [
        str(p.relative_to(PKG))
        for p in _py_files()
        if "settings.api_key" in p.read_text(encoding="utf-8")
    ]
    assert not offenders, f"settings.api_key must not be an auth path; used in: {offenders}"


# ---------- T-O2: 401 log records the reason, never the token ----------
async def test_401_log_excludes_token_value(monkeypatch, caplog):
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "auth_issuer_url", "https://i/v2.0")
    monkeypatch.setattr(settings, "auth_audience", "api://x")
    monkeypatch.setattr(core_auth, "validate_token", AsyncMock(side_effect=AuthError("expired")))

    secret = "super-secret-token-value-DO-NOT-LOG"
    with caplog.at_level(logging.INFO):
        with pytest.raises(Exception):
            await require_auth(_req({"authorization": f"Bearer {secret}"}))

    joined = " ".join(r.getMessage() for r in caplog.records)
    assert "expired" in joined
    assert secret not in joined
