"""Worker-side identity resolution (US-002, token contract): _set_worker_auth_token.

A deferred worker turn resolves its auth token from the persisted bearer, RE-VALIDATES it
(authn), and sets the validated token; anything else fails closed. No system principal.
"""

import pytest

from redis_sre_agent.core import auth as core_auth
from redis_sre_agent.core import authorization as authz
from redis_sre_agent.core.config import settings
from redis_sre_agent.core.docket_tasks import _set_worker_auth_token


@pytest.fixture
def authz_on(monkeypatch):
    monkeypatch.setattr(settings, "infrastructure_authorization_enabled", True)
    yield


async def test_off_is_noop(monkeypatch):
    monkeypatch.setattr(settings, "infrastructure_authorization_enabled", False)
    tok = await _set_worker_auth_token({"_authz_bearer": "x"})
    assert tok is None
    assert authz.current_auth_token() is None


async def test_valid_bearer_sets_token(authz_on, monkeypatch):
    async def fake_validate(token):
        assert token == "good-jwt"
        return {"sub": "u1"}  # claims returned by validate_token; we set the TOKEN, not these

    monkeypatch.setattr(core_auth, "validate_token", fake_validate)
    tok = await _set_worker_auth_token({"_authz_bearer": "good-jwt"})
    try:
        assert authz.current_auth_token() == "good-jwt"
    finally:
        authz.reset_auth_token(tok)


async def test_invalid_bearer_fail_closed(authz_on, monkeypatch):
    async def boom(token):
        raise core_auth.AuthError("expired")

    monkeypatch.setattr(core_auth, "validate_token", boom)
    tok = await _set_worker_auth_token({"_authz_bearer": "bad"})
    try:
        assert authz.current_auth_token() is None
    finally:
        authz.reset_auth_token(tok)


async def test_no_bearer_fail_closed(authz_on):
    tok = await _set_worker_auth_token({})
    try:
        assert authz.current_auth_token() is None
    finally:
        authz.reset_auth_token(tok)


async def test_reset_restores_none(authz_on, monkeypatch):
    async def fake_validate(token):
        return {"sub": "u1"}

    monkeypatch.setattr(core_auth, "validate_token", fake_validate)
    assert authz.current_auth_token() is None
    tok = await _set_worker_auth_token({"_authz_bearer": "good-jwt"})
    assert authz.current_auth_token() == "good-jwt"
    authz.reset_auth_token(tok)
    assert authz.current_auth_token() is None
