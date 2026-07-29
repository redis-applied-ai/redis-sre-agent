"""Enforcement at the base target loaders (US-001).

The security invariant: no caller can obtain a RedisCluster/RedisInstance it may not
access, because the base loaders (get_cluster_by_id / get_instance_by_id) route through
the authorization hook and return None (the existing not-found path) on deny.

Redis is mocked, so this runs without containers.
"""

import json

import pytest

from redis_sre_agent.core import authorization as authz
from redis_sre_agent.core import clusters as clusters_mod
from redis_sre_agent.core import instances as instances_mod
from redis_sre_agent.core.authorization import TargetRef
from redis_sre_agent.core.clusters import get_cluster_by_id
from redis_sre_agent.core.config import settings
from redis_sre_agent.core.instances import RedisInstanceType, get_instance_by_id

_CLUSTER_DATA = {
    "id": "c1",
    "name": "prod-cache",
    "environment": "production",
    "description": "prod cluster",
}
_INSTANCE_DATA = {
    "id": "i1",
    "name": "billing",
    "connection_url": "redis://billing:6379",
    "environment": "production",
    "usage": "cache",
    "description": "billing instance",
    "instance_type": list(RedisInstanceType)[0].value,
}


class _FakeRedis:
    def __init__(self, payload):
        self._payload = payload

    async def hget(self, key, field):
        return self._payload


@pytest.fixture
def fake_redis(monkeypatch):
    monkeypatch.setattr(clusters_mod, "get_redis_client", lambda: _FakeRedis(json.dumps(_CLUSTER_DATA)))
    monkeypatch.setattr(instances_mod, "get_redis_client", lambda: _FakeRedis(json.dumps(_INSTANCE_DATA)))


@pytest.fixture
def authz_on(monkeypatch):
    monkeypatch.setattr(settings, "infrastructure_authorization_enabled", True)
    authz.reset_hook_cache()
    yield
    authz.reset_hook_cache()


def _use_hook(monkeypatch, fn):
    monkeypatch.setattr(authz, "_load_hook", lambda: fn)


# --- passthrough when authz off: loaders behave exactly as before ---


async def test_loaders_passthrough_when_authz_off(fake_redis, monkeypatch):
    monkeypatch.setattr(settings, "infrastructure_authorization_enabled", False)
    cluster = await get_cluster_by_id("c1")
    instance = await get_instance_by_id("i1")
    assert cluster is not None and cluster.id == "c1"
    assert instance is not None and instance.id == "i1"


# --- authz on: allowed principal resolves the target ---


async def test_loaders_resolve_when_allowed(fake_redis, authz_on, monkeypatch):
    def allow_all(claims, targets):
        return list(targets)

    _use_hook(monkeypatch, allow_all)
    tok = authz.set_principal({"sub": "u1"})
    try:
        assert (await get_cluster_by_id("c1")).id == "c1"
        assert (await get_instance_by_id("i1")).id == "i1"
    finally:
        authz.reset_principal(tok)


# --- authz on: disallowed principal gets None (deny == not-found) ---


async def test_loaders_deny_when_not_allowed(fake_redis, authz_on, monkeypatch):
    def deny_all(claims, targets):
        return []

    _use_hook(monkeypatch, deny_all)
    tok = authz.set_principal({"sub": "u1"})
    try:
        assert await get_cluster_by_id("c1") is None
        assert await get_instance_by_id("i1") is None
    finally:
        authz.reset_principal(tok)


# --- authz on, no principal -> fail closed (None) even though the record exists ---


async def test_loaders_fail_closed_without_principal(fake_redis, authz_on):
    assert await get_cluster_by_id("c1") is None
    assert await get_instance_by_id("i1") is None


# --- selective: a hook that allows only the cluster denies the instance ---


async def test_loaders_selective(fake_redis, authz_on, monkeypatch):
    def clusters_only(claims, targets):
        return [t for t in targets if t.kind == "cluster"]

    _use_hook(monkeypatch, clusters_only)
    tok = authz.set_principal({"sub": "u1"})
    try:
        assert (await get_cluster_by_id("c1")).id == "c1"
        assert await get_instance_by_id("i1") is None
    finally:
        authz.reset_principal(tok)


# --- adapters map model -> TargetRef correctly ---


async def test_targetref_adapters(fake_redis, monkeypatch):
    monkeypatch.setattr(settings, "infrastructure_authorization_enabled", False)
    cluster = await get_cluster_by_id("c1")
    instance = await get_instance_by_id("i1")
    cref = TargetRef.from_cluster(cluster)
    iref = TargetRef.from_instance(instance)
    assert cref.kind == "cluster" and cref.resource_id == "c1" and cref.name == "prod-cache"
    assert iref.kind == "instance" and iref.resource_id == "i1" and iref.name == "billing"


# --- structural guard: the base loaders MUST retain the enforcement call ---


def test_chokepoint_guards_present():
    """Regression guard: removing the hook call from a base loader fails this test.

    ponytail: this checks the enforcement call is present in the known chokepoints — it
    does not (yet) prove no NEW unguarded construction path exists elsewhere. The stronger
    no-unguarded-construction AST scan is tracked for the hardening pass (US-008).
    """
    import inspect

    assert "assert_target_allowed" in inspect.getsource(get_cluster_by_id)
    assert "assert_target_allowed" in inspect.getsource(get_instance_by_id)


# --- scope_candidates: drop denied bindings before materialization (US-001b) ---

from types import SimpleNamespace  # noqa: E402

from redis_sre_agent.core.authorization import scope_candidates  # noqa: E402


def _cand(kind, rid):
    return SimpleNamespace(target_kind=kind, resource_id=rid)


async def test_scope_candidates_passthrough_when_off(monkeypatch):
    monkeypatch.setattr(settings, "infrastructure_authorization_enabled", False)
    cands = [_cand("cluster", "c1"), _cand("instance", "i1")]
    assert await scope_candidates(cands) == cands


async def test_scope_candidates_filters_when_on(authz_on, monkeypatch):
    def clusters_only(claims, targets):
        return [t for t in targets if t.kind == "cluster"]

    _use_hook(monkeypatch, clusters_only)
    tok = authz.set_principal({"sub": "u1"})
    try:
        out = await scope_candidates([_cand("cluster", "c1"), _cand("instance", "i1")])
        assert [c.resource_id for c in out] == ["c1"]
    finally:
        authz.reset_principal(tok)


async def test_scope_candidates_fail_closed_no_principal(authz_on):
    assert await scope_candidates([_cand("cluster", "c1")]) == []


async def test_scope_candidates_drops_candidate_without_resource_id(authz_on, monkeypatch):
    def allow_all(claims, targets):
        return list(targets)

    _use_hook(monkeypatch, allow_all)
    tok = authz.set_principal({"sub": "u1"})
    try:
        out = await scope_candidates([_cand("instance", None), _cand("instance", "i1")])
        assert [c.resource_id for c in out] == ["i1"]  # unidentifiable candidate dropped
    finally:
        authz.reset_principal(tok)


# --- listing: scope-before-count/paginate (US-003, no hidden-count leak) ---

from redis_sre_agent.core.authorization import scope_and_paginate, scope_models  # noqa: E402


def _model(cid):
    return SimpleNamespace(id=cid, name=f"n-{cid}", environment="production")


async def test_scope_models_passthrough_off(monkeypatch):
    monkeypatch.setattr(settings, "infrastructure_authorization_enabled", False)
    models = [_model("c1"), _model("c2")]
    assert await scope_models(models, TargetRef.from_cluster) == models


async def test_scope_and_paginate_total_and_page_reflect_allowed(authz_on, monkeypatch):
    # 5 clusters exist; hook allows only c1/c3/c5 -> total must be 3 (not 5), page bounded.
    allowed = {"c1", "c3", "c5"}

    def hook(claims, targets):
        return [t for t in targets if t.resource_id in allowed]

    _use_hook(monkeypatch, hook)
    models = [_model(f"c{i}") for i in range(1, 6)]
    tok = authz.set_principal({"sub": "u1"})
    try:
        page, total = await scope_and_paginate(models, TargetRef.from_cluster, offset=0, limit=2)
        assert total == 3  # hidden count (5) never leaks
        assert [m.id for m in page] == ["c1", "c3"]
        page2, total2 = await scope_and_paginate(models, TargetRef.from_cluster, offset=2, limit=2)
        assert total2 == 3
        assert [m.id for m in page2] == ["c5"]  # full page across the allowed set, not short
    finally:
        authz.reset_principal(tok)


async def test_scope_and_paginate_fail_closed_no_principal(authz_on):
    models = [_model("c1"), _model("c2")]
    page, total = await scope_and_paginate(models, TargetRef.from_cluster, offset=0, limit=10)
    assert page == [] and total == 0
