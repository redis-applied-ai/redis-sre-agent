"""Worker-side identity resolution (US-002 Part C): _set_worker_authz_principal.

A deferred worker turn resolves its principal from the persisted bearer (re-validated live),
falls back to a system principal for explicit machine paths, and fails closed otherwise.
"""

import pytest

from redis_sre_agent.core import auth as core_auth
from redis_sre_agent.core import authorization as authz
from redis_sre_agent.core.config import settings
from redis_sre_agent.core.docket_tasks import _set_worker_authz_principal


@pytest.fixture
def authz_on(monkeypatch):
    monkeypatch.setattr(settings, "infrastructure_authorization_enabled", True)
    yield


async def test_off_is_noop(monkeypatch):
    monkeypatch.setattr(settings, "infrastructure_authorization_enabled", False)
    tok = await _set_worker_authz_principal({"_authz_bearer": "x"})
    assert tok is None
    assert authz.current_principal() is None


async def test_valid_bearer_sets_claims(authz_on, monkeypatch):
    async def fake_validate(token):
        assert token == "good"
        return {"sub": "u1", "groups": ["g"]}

    monkeypatch.setattr(core_auth, "validate_token", fake_validate)
    tok = await _set_worker_authz_principal({"_authz_bearer": "good"})
    try:
        assert authz.current_principal() == {"sub": "u1", "groups": ["g"]}
    finally:
        authz.reset_principal(tok)


async def test_invalid_bearer_fail_closed(authz_on, monkeypatch):
    async def boom(token):
        raise core_auth.AuthError("expired")

    monkeypatch.setattr(core_auth, "validate_token", boom)
    tok = await _set_worker_authz_principal({"_authz_bearer": "bad"})
    try:
        assert authz.current_principal() is None
    finally:
        authz.reset_principal(tok)


async def test_system_marker_gets_system_principal(authz_on):
    tok = await _set_worker_authz_principal({"_authz_system": True})
    try:
        assert authz.current_principal()["sub"] == "system"
    finally:
        authz.reset_principal(tok)


async def test_no_identity_fail_closed(authz_on):
    tok = await _set_worker_authz_principal({})
    try:
        assert authz.current_principal() is None
    finally:
        authz.reset_principal(tok)


async def test_reset_restores_none(authz_on, monkeypatch):
    async def fake_validate(token):
        return {"sub": "u1"}

    monkeypatch.setattr(core_auth, "validate_token", fake_validate)
    assert authz.current_principal() is None
    tok = await _set_worker_authz_principal({"_authz_bearer": "good"})
    assert authz.current_principal() == {"sub": "u1"}
    authz.reset_principal(tok)
    assert authz.current_principal() is None
