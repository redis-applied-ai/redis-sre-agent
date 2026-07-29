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


# --- config validator (AC-2, AC-3) ---


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


# --- passthrough when disabled (AC-1) ---


async def test_passthrough_when_disabled(monkeypatch):
    monkeypatch.setattr(settings, "infrastructure_authorization_enabled", False)
    assert await scope_targets([C1, I1]) == [C1, I1]


# --- fail closed (AC-11) ---


async def test_fail_closed_no_principal(authz_on):
    # No set_principal() -> current_principal() is None -> deny all.
    assert await scope_targets([C1, I1]) == []


async def test_fail_closed_hook_exception(authz_on, monkeypatch):
    def boom(claims, targets):
        raise RuntimeError("authz service down")

    _use_hook(monkeypatch, boom)
    tok = authz.set_principal({"sub": "u1"})
    try:
        assert await scope_targets([C1, I1]) == []
    finally:
        authz.reset_principal(tok)


async def test_fail_closed_hook_timeout(authz_on, monkeypatch):
    async def slow(claims, targets):
        await asyncio.sleep(10)
        return targets

    _use_hook(monkeypatch, slow)
    monkeypatch.setattr(authz, "_HOOK_TIMEOUT_SECONDS", 0.05)
    tok = authz.set_principal({"sub": "u1"})
    try:
        assert await scope_targets([C1]) == []
    finally:
        authz.reset_principal(tok)


# --- allowed subset, sync + async (AC-5/AC-10 core) ---


async def test_sync_hook_returns_subset(authz_on, monkeypatch):
    def only_i1(claims, targets):
        return [t for t in targets if t.resource_id == "i1"]

    _use_hook(monkeypatch, only_i1)
    tok = authz.set_principal({"sub": "u1"})
    try:
        assert await scope_targets([C1, I1, I2]) == [I1]
    finally:
        authz.reset_principal(tok)


async def test_async_hook_returns_subset(authz_on, monkeypatch):
    async def only_clusters(claims, targets):
        return [t for t in targets if t.kind == "cluster"]

    _use_hook(monkeypatch, only_clusters)
    tok = authz.set_principal({"sub": "u1"})
    try:
        assert await scope_targets([C1, I1]) == [C1]
    finally:
        authz.reset_principal(tok)


# --- the hook can only REMOVE access, never add (intersect invariant) ---


async def test_hook_superset_is_intersected(authz_on, monkeypatch):
    rogue = TargetRef("instance", "i999", "secret-prod", "prod")

    def add_rogue(claims, targets):
        return list(targets) + [rogue]  # buggy/hostile hook tries to grant extra

    _use_hook(monkeypatch, add_rogue)
    tok = authz.set_principal({"sub": "u1"})
    try:
        out = await scope_targets([I1])
        assert out == [I1]  # rogue was not in the input set -> dropped
        assert rogue not in out
    finally:
        authz.reset_principal(tok)


async def test_scope_targets_returns_original_objects(authz_on, monkeypatch):
    # Hook returns a mutated copy; we must return the ORIGINAL input object, not the hook's.
    def mutated(claims, targets):
        return [TargetRef(t.kind, t.resource_id, "HOOK-RENAMED", "evil") for t in targets]

    _use_hook(monkeypatch, mutated)
    tok = authz.set_principal({"sub": "u1"})
    try:
        out = await scope_targets([I1])
        assert out == [I1]
        assert out[0].name == "billing"  # original, not the hook's "HOOK-RENAMED"
    finally:
        authz.reset_principal(tok)


async def test_assert_target_allowed(authz_on, monkeypatch):
    def only_i1(claims, targets):
        return [t for t in targets if t.resource_id == "i1"]

    _use_hook(monkeypatch, only_i1)
    tok = authz.set_principal({"sub": "u1"})
    try:
        assert await assert_target_allowed(I1) is True
        assert await assert_target_allowed(I2) is False
    finally:
        authz.reset_principal(tok)


# --- ContextVar isolation (M-2): a task that sets no principal sees None, not a bleed ---


def test_principal_reset_isolation():
    assert authz.current_principal() is None
    tok = authz.set_principal({"sub": "x"})
    assert authz.current_principal() == {"sub": "x"}
    authz.reset_principal(tok)
    assert authz.current_principal() is None


def test_system_principal_shape():
    assert authz.system_principal()["sub"] == "system"


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
