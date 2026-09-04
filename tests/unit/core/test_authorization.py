"""Unit contract for infrastructure authorization (authz-only target scoping).

Security boundary — the DENY paths are the spec, so they are the bulk of this file.
Enforcement wiring (base loaders, listing, resume, triage) is covered by integration
tests; here we pin the core `scope_targets` contract, the fail-closed behavior, the
hook-cannot-add-access invariant, ContextVar isolation, and the config validator.
"""

import asyncio

import pytest
from pydantic import ValidationError

from redis_sre_agent.core import authorization as authz
from redis_sre_agent.core.authorization import (
    TargetRef,
    assert_target_allowed,
    scope_targets,
)
from redis_sre_agent.core.config import Settings, settings

C1 = TargetRef("cluster", "c1", "prod-cache", "prod")
I1 = TargetRef("instance", "i1", "billing", "prod")
I2 = TargetRef("instance", "i2", "staging", "staging")


@pytest.fixture
def authz_on(monkeypatch):
    """Enable authz for the test; reset the hook cache around it."""
    monkeypatch.setattr(settings, "infrastructure_authorization_enabled", True)
    authz.reset_hook_cache()
    yield
    authz.reset_hook_cache()


def _use_hook(monkeypatch, fn):
    """Bypass import-path resolution; inject a stub hook directly."""
    monkeypatch.setattr(authz, "_load_hook", lambda: fn)


def _allow(records):
    """Wrap an allowed subset in the hook's dict return contract ({"allowed_targets": [...]})."""
    return {"allowed_targets": list(records)}


# --- config validator ---


def test_authz_requires_authn():
    with pytest.raises(ValidationError):
        Settings(
            infrastructure_authorization_enabled=True,
            auth_enabled=False,
            infrastructure_authorization_hook="pkg.mod:hook",
        )


def test_authz_requires_hook():
    with pytest.raises(ValidationError):
        Settings(
            infrastructure_authorization_enabled=True,
            auth_enabled=True,
            infrastructure_authorization_hook=None,
        )


def test_authz_config_ok_when_fully_configured():
    s = Settings(
        infrastructure_authorization_enabled=True,
        auth_enabled=True,
        infrastructure_authorization_hook="pkg.mod:hook",
    )
    assert s.infrastructure_authorization_enabled is True


def test_authz_off_by_default():
    assert Settings().infrastructure_authorization_enabled is False


# --- passthrough when disabled ---


async def test_passthrough_when_disabled(monkeypatch):
    monkeypatch.setattr(settings, "infrastructure_authorization_enabled", False)
    assert await scope_targets([C1, I1]) == [C1, I1]


# --- fail closed ---


async def test_fail_closed_no_principal(authz_on):
    # No set_auth_token() -> current_auth_token() is None -> deny all.
    assert await scope_targets([C1, I1]) == []


async def test_fail_closed_hook_exception(authz_on, monkeypatch):
    def boom(token, targets):
        raise RuntimeError("authz service down")

    _use_hook(monkeypatch, boom)
    tok = authz.set_auth_token("tok-u1")
    try:
        assert await scope_targets([C1, I1]) == []
    finally:
        authz.reset_auth_token(tok)


async def test_fail_closed_hook_timeout(authz_on, monkeypatch):
    async def slow(token, targets):
        await asyncio.sleep(10)
        return _allow(targets)

    _use_hook(monkeypatch, slow)
    monkeypatch.setattr(authz, "_HOOK_TIMEOUT_SECONDS", 0.05)
    tok = authz.set_auth_token("tok-u1")
    try:
        assert await scope_targets([C1]) == []
    finally:
        authz.reset_auth_token(tok)


# --- allowed subset, sync + async ---


async def test_sync_hook_returns_subset(authz_on, monkeypatch):
    def only_i1(token, targets):
        return _allow(t for t in targets if t["id"] == "i1")

    _use_hook(monkeypatch, only_i1)
    tok = authz.set_auth_token("tok-u1")
    try:
        assert await scope_targets([C1, I1, I2]) == [I1]
    finally:
        authz.reset_auth_token(tok)


async def test_async_hook_returns_subset(authz_on, monkeypatch):
    async def only_clusters(token, targets):
        return _allow(t for t in targets if t["type"] == "cluster")

    _use_hook(monkeypatch, only_clusters)
    tok = authz.set_auth_token("tok-u1")
    try:
        assert await scope_targets([C1, I1]) == [C1]
    finally:
        authz.reset_auth_token(tok)


# --- the hook can only REMOVE access, never add (intersect invariant) ---


async def test_hook_superset_is_intersected(authz_on, monkeypatch):
    rogue = TargetRef("instance", "i999", "secret-prod", "prod")

    def add_rogue(token, targets):
        # buggy/hostile hook tries to grant an extra target not in the candidate set
        return _allow(list(targets) + [{"type": rogue.kind, "id": rogue.resource_id}])

    _use_hook(monkeypatch, add_rogue)
    tok = authz.set_auth_token("tok-u1")
    try:
        out = await scope_targets([I1])
        assert out == [I1]  # rogue was not in the input set -> dropped
        assert rogue not in out
    finally:
        authz.reset_auth_token(tok)


async def test_scope_targets_returns_original_objects(authz_on, monkeypatch):
    # Hook returns a mutated copy; we must return the ORIGINAL input object, not the hook's.
    def mutated(token, targets):
        return _allow(
            {"type": t["type"], "id": t["id"], "name": "HOOK-RENAMED", "environment": "evil"}
            for t in targets
        )

    _use_hook(monkeypatch, mutated)
    tok = authz.set_auth_token("tok-u1")
    try:
        out = await scope_targets([I1])
        assert out == [I1]
        assert out[0].name == "billing"  # original, not the hook's "HOOK-RENAMED"
    finally:
        authz.reset_auth_token(tok)


async def test_assert_target_allowed(authz_on, monkeypatch):
    def only_i1(token, targets):
        return _allow(t for t in targets if t["id"] == "i1")

    _use_hook(monkeypatch, only_i1)
    tok = authz.set_auth_token("tok-u1")
    try:
        assert await assert_target_allowed(I1) is True
        assert await assert_target_allowed(I2) is False
    finally:
        authz.reset_auth_token(tok)


# --- ContextVar isolation (M-2): a task that sets no principal sees None, not a bleed ---


def test_auth_token_reset_isolation():
    assert authz.current_auth_token() is None
    tok = authz.set_auth_token("tok-x")
    assert authz.current_auth_token() == "tok-x"
    authz.reset_auth_token(tok)
    assert authz.current_auth_token() is None


# --- hook import-path resolution ---


def test_load_hook_resolves_import_path(monkeypatch):
    authz.reset_hook_cache()
    monkeypatch.setattr(
        settings,
        "infrastructure_authorization_hook",
        "redis_sre_agent.core.authorization:reset_hook_cache",
    )
    try:
        assert authz._load_hook() is authz.reset_hook_cache
    finally:
        authz.reset_hook_cache()


def test_load_hook_invalid_path(monkeypatch):
    authz.reset_hook_cache()
    monkeypatch.setattr(settings, "infrastructure_authorization_hook", "no-colon-path")
    try:
        with pytest.raises(RuntimeError):
            authz._load_hook()
    finally:
        authz.reset_hook_cache()


# --- dict-return contract (type+id disambiguation, fail-closed on bad shape) ---


async def test_dict_contract_fail_closed_on_wrong_shape(authz_on, monkeypatch):
    # A non-dict return (e.g. the old bare-list contract) or a dict missing allowed_targets
    # fails closed -> deny all.
    for bad in (lambda token, targets: list(targets), lambda token, targets: {"nope": []}):
        _use_hook(monkeypatch, bad)
        tok = authz.set_auth_token("tok-u1")
        try:
            assert await scope_targets([C1, I1]) == []
        finally:
            authz.reset_auth_token(tok)


async def test_dict_contract_type_disambiguates(authz_on, monkeypatch):
    # Same id, wrong type must NOT match: allowing instance "c1" does not grant cluster "c1".
    _use_hook(
        monkeypatch, lambda token, targets: {"allowed_targets": [{"type": "instance", "id": "c1"}]}
    )
    tok = authz.set_auth_token("tok-u1")
    try:
        assert await scope_targets([C1]) == []  # C1 is a CLUSTER -> (cluster,c1) != (instance,c1)
    finally:
        authz.reset_auth_token(tok)


async def test_dict_contract_record_missing_type_or_id_skipped(authz_on, monkeypatch):
    # A record lacking type or id can't be matched -> that target is denied (fail-closed).
    _use_hook(
        monkeypatch,
        lambda token, targets: {"allowed_targets": [{"id": "i1"}, {"type": "instance"}]},
    )
    tok = authz.set_auth_token("tok-u1")
    try:
        assert await scope_targets([I1]) == []
    finally:
        authz.reset_auth_token(tok)
