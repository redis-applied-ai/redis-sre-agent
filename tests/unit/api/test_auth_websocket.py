"""WebSocket auth (pre-accept) tests for US-002."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from starlette.websockets import WebSocketDisconnect

from redis_sre_agent.api import websockets as ws_mod
from redis_sre_agent.api.websockets import authenticate_ws
from redis_sre_agent.core import auth as core_auth
from redis_sre_agent.core.auth import AuthError
from redis_sre_agent.core.config import settings

WS_PATH = "/api/v1/ws/tasks/thread-1"


def _fake_ws(subprotocols=None, query=None):
    return SimpleNamespace(
        scope={"subprotocols": subprotocols or []},
        query_params=query or {},
    )


# ---------- authenticate_ws unit: token extraction ----------
async def test_authenticate_ws_reads_bearer_subprotocol(monkeypatch):
    monkeypatch.setattr(core_auth, "validate_token", AsyncMock(return_value={"sub": "u"}))
    claims = await authenticate_ws(_fake_ws(subprotocols=["bearer", "tok-123"]))
    assert claims == {"sub": "u"}
    core_auth.validate_token.assert_awaited_once_with("tok-123")


async def test_authenticate_ws_query_param_fallback(monkeypatch):
    monkeypatch.setattr(core_auth, "validate_token", AsyncMock(return_value={"sub": "u"}))
    claims = await authenticate_ws(_fake_ws(query={"token": "qtok"}))
    assert claims == {"sub": "u"}
    core_auth.validate_token.assert_awaited_once_with("qtok")


async def test_authenticate_ws_no_token_returns_none():
    assert await authenticate_ws(_fake_ws()) is None


async def test_authenticate_ws_invalid_token_returns_none(monkeypatch):
    monkeypatch.setattr(core_auth, "validate_token", AsyncMock(side_effect=AuthError("expired")))
    assert await authenticate_ws(_fake_ws(subprotocols=["bearer", "bad"])) is None


# ---------- end-to-end via TestClient ----------
def test_ws_rejected_without_token(test_client, monkeypatch):
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "auth_issuer_url", "https://i/v2.0")
    monkeypatch.setattr(settings, "auth_audience", "api://x")
    with pytest.raises(WebSocketDisconnect) as ei:
        with test_client.websocket_connect(WS_PATH):
            pass
    assert ei.value.code == ws_mod.WS_AUTH_FAILED_CODE  # 4401


def test_ws_accepts_with_valid_token(test_client, monkeypatch):
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "auth_issuer_url", "https://i/v2.0")
    monkeypatch.setattr(settings, "auth_audience", "api://x")
    monkeypatch.setattr(core_auth, "validate_token", AsyncMock(return_value={"sub": "u"}))
    # Connecting succeeds => the server called accept() (post-auth path).
    with test_client.websocket_connect(WS_PATH, subprotocols=["bearer", "tok"]) as ws:
        assert ws is not None


def test_ws_accepts_with_query_token_no_subprotocol(test_client, monkeypatch):
    # Non-browser client: token via ?token= query param, no subprotocol offered.
    # The server must accept WITHOUT echoing a "bearer" subprotocol (which the client
    # never offered) or the handshake breaks.
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "auth_issuer_url", "https://i/v2.0")
    monkeypatch.setattr(settings, "auth_audience", "api://x")
    monkeypatch.setattr(core_auth, "validate_token", AsyncMock(return_value={"sub": "u"}))
    with test_client.websocket_connect(WS_PATH + "?token=qtok") as ws:
        assert ws is not None


def test_ws_open_mode_accepts_without_token(test_client, monkeypatch):
    monkeypatch.setattr(settings, "auth_enabled", False)
    with test_client.websocket_connect(WS_PATH) as ws:
        assert ws is not None
