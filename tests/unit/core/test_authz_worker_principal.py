"""Worker-side identity resolution (token contract): _set_worker_auth_token.

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


def test_all_agent_tasks_set_and_reset_worker_token():
    """Regression: every @sre_task that runs the agent / hits guarded loaders must set
    the worker auth token at the top and reset it in a finally, or a reused worker context can
    leak a prior task's principal. process_chat_turn was missing this.
    """
    import inspect

    from redis_sre_agent.core import docket_tasks

    for name in ("process_agent_turn", "resume_task_after_approval", "process_chat_turn"):
        src = inspect.getsource(getattr(docket_tasks, name))
        assert "_set_worker_auth_token" in src, f"{name} does not set the worker auth token"
        assert "reset_auth_token" in src, f"{name} does not reset the worker auth token"
        assert "finally" in src, f"{name} does not reset the worker token in a finally"


async def test_reset_restores_none(authz_on, monkeypatch):
    async def fake_validate(token):
        return {"sub": "u1"}

    monkeypatch.setattr(core_auth, "validate_token", fake_validate)
    assert authz.current_auth_token() is None
    tok = await _set_worker_auth_token({"_authz_bearer": "good-jwt"})
    assert authz.current_auth_token() == "good-jwt"
    authz.reset_auth_token(tok)
    assert authz.current_auth_token() is None
