"""The eval harness injects infrastructure authorization for authz behavioral scenarios.

Deterministic (no LLM): asserts _apply_eval_authz turns authz on, installs a stub hook scoped
to `allowed_handles`, sets a validated token, and that teardown restores prior state.
"""

from types import SimpleNamespace

from redis_sre_agent.core import authorization as authz
from redis_sre_agent.core.authorization import TargetRef, scope_targets
from redis_sre_agent.core.config import settings
from redis_sre_agent.evaluation.runtime import _apply_eval_authz


def _scn(enabled, allowed_handles, catalog):
    return SimpleNamespace(
        scope=SimpleNamespace(
            authz=SimpleNamespace(
                enabled=enabled, allowed_handles=allowed_handles, token="eval-tok"
            ),
            target_catalog=catalog,
        )
    )


def _entry(handle, rid):
    return SimpleNamespace(handle=handle, resource_id=rid)


async def test_eval_authz_disabled_is_noop(monkeypatch):
    monkeypatch.setattr(settings, "infrastructure_authorization_enabled", False)
    td = _apply_eval_authz(_scn(False, None, []))
    assert settings.infrastructure_authorization_enabled is False
    assert authz.current_auth_token() is None
    td()


async def test_eval_authz_scopes_to_allowed_handles(monkeypatch):
    monkeypatch.setattr(settings, "infrastructure_authorization_enabled", False)
    catalog = [_entry("h_a", "res-a"), _entry("h_b", "res-b")]
    td = _apply_eval_authz(_scn(True, ["h_a"], catalog))
    try:
        assert settings.infrastructure_authorization_enabled is True
        assert authz.current_auth_token() == "eval-tok"
        out = await scope_targets([TargetRef("instance", "res-a"), TargetRef("instance", "res-b")])
        assert [t.resource_id for t in out] == ["res-a"]  # only the allowed handle's resource
    finally:
        td()
    # teardown restores prior state
    assert settings.infrastructure_authorization_enabled is False
    assert authz.current_auth_token() is None


async def test_eval_authz_allow_all_when_handles_none(monkeypatch):
    monkeypatch.setattr(settings, "infrastructure_authorization_enabled", False)
    td = _apply_eval_authz(_scn(True, None, [_entry("h_a", "res-a")]))
    try:
        out = await scope_targets([TargetRef("instance", "res-a"), TargetRef("cluster", "res-z")])
        assert {t.resource_id for t in out} == {"res-a", "res-z"}
    finally:
        td()
