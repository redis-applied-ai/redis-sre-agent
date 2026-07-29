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
    monkeypatch.setattr(
        clusters_mod, "get_redis_client", lambda: _FakeRedis(json.dumps(_CLUSTER_DATA))
    )
    monkeypatch.setattr(
        instances_mod, "get_redis_client", lambda: _FakeRedis(json.dumps(_INSTANCE_DATA))
    )


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
    def allow_all(token, targets):
        return list(targets)

    _use_hook(monkeypatch, allow_all)
    tok = authz.set_auth_token("tok-u1")
    try:
        assert (await get_cluster_by_id("c1")).id == "c1"
        assert (await get_instance_by_id("i1")).id == "i1"
    finally:
        authz.reset_auth_token(tok)


# --- authz on: disallowed principal gets None (deny == not-found) ---


async def test_loaders_deny_when_not_allowed(fake_redis, authz_on, monkeypatch):
    def deny_all(token, targets):
        return []

    _use_hook(monkeypatch, deny_all)
    tok = authz.set_auth_token("tok-u1")
    try:
        assert await get_cluster_by_id("c1") is None
        assert await get_instance_by_id("i1") is None
    finally:
        authz.reset_auth_token(tok)


# --- authz on, no principal -> fail closed (None) even though the record exists ---


async def test_loaders_fail_closed_without_principal(fake_redis, authz_on):
    assert await get_cluster_by_id("c1") is None
    assert await get_instance_by_id("i1") is None


# --- selective: a hook that allows only the cluster denies the instance ---


async def test_loaders_selective(fake_redis, authz_on, monkeypatch):
    def clusters_only(token, targets):
        return [t for t in targets if t.kind == "cluster"]

    _use_hook(monkeypatch, clusters_only)
    tok = authz.set_auth_token("tok-u1")
    try:
        assert (await get_cluster_by_id("c1")).id == "c1"
        assert await get_instance_by_id("i1") is None
    finally:
        authz.reset_auth_token(tok)


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


def test_agent_does_not_call_unscoped_bulk_loaders():
    """Regression for the fail-open the architect caught (US-008): the agent must NOT call the
    unscoped bulk loaders get_instances()/get_clusters() directly — only via the authz-scoped
    _scoped_instances() helper or the guarded get_*_by_id loaders. A new unguarded bulk call in
    the agent bumps the count and fails here.
    """
    import inspect

    from redis_sre_agent.agent import langgraph_agent

    src = inspect.getsource(langgraph_agent)
    # Unscoped get_instances() is allowed in EXACTLY two places: (1) inside the _scoped_instances
    # helper, and (2) the instance-type persist path, which feeds save_instances() (REPLACE
    # semantics) and MUST see the full registry or it deletes instances the principal can't access
    # (Bugbot). A NEW unguarded bulk call for an authz-relevant read bumps this and fails here.
    assert src.count("await get_instances()") == 2, "unexpected unscoped get_instances() call count"
    assert "await get_clusters()" not in src, "unscoped get_clusters() call in agent module"


def test_named_target_authz_deny_runs_on_every_triage_turn():
    """Regression (multi-turn deny): a target NAMED in a follow-up message must be authorized on
    EVERY triage turn, not only the first (zero-scope) one. Otherwise a thread already bound to an
    allowed target shadows a newly-named denied target and silently reuses the old target instead
    of denying (e.g. "triage inst-1" then "triage inst-3"). Guard: the named-target deny block must
    appear BEFORE (i.e. not be nested inside) the zero_scope gate in docket_tasks.
    """
    import inspect

    from redis_sre_agent.core import docket_tasks

    src = inspect.getsource(docket_tasks)
    deny_marker = "_resolve_named_targets"
    zero_scope_gate = 'current_scope.scope_kind == "zero_scope"'
    assert deny_marker in src, "named-target authz deny block missing"
    assert zero_scope_gate in src, "zero_scope gate missing (test anchor stale)"
    assert src.index(deny_marker) < src.index(zero_scope_gate), (
        "named-target authz deny is gated behind zero_scope — follow-up denied targets would be "
        "shadowed by an existing binding (multi-turn regression)"
    )


# --- the agent's scoped bulk-instance loader (US-008 fix) ---

from redis_sre_agent.agent import langgraph_agent as _lg  # noqa: E402


async def test_agent_scoped_instances_filters(authz_on, monkeypatch):
    fakes = [_model("i1"), _model("i2"), _model("i3")]

    async def fake_get_instances():
        return fakes

    monkeypatch.setattr(_lg, "get_instances", fake_get_instances)
    _use_hook(monkeypatch, lambda token, targets: [t for t in targets if t.resource_id == "i2"])
    tok = authz.set_auth_token("tok-u1")
    try:
        out = await _lg._scoped_instances()
        assert [i.id for i in out] == ["i2"]
    finally:
        authz.reset_auth_token(tok)


async def test_agent_scoped_instances_fail_closed_no_principal(authz_on, monkeypatch):
    async def fake_get_instances():
        return [_model("i1")]

    monkeypatch.setattr(_lg, "get_instances", fake_get_instances)
    assert await _lg._scoped_instances() == []  # no principal -> deny all


async def test_agent_scoped_instances_passthrough_off(monkeypatch):
    monkeypatch.setattr(settings, "infrastructure_authorization_enabled", False)
    fakes = [_model("i1"), _model("i2")]

    async def fake_get_instances():
        return fakes

    monkeypatch.setattr(_lg, "get_instances", fake_get_instances)
    assert await _lg._scoped_instances() == fakes


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
    def clusters_only(token, targets):
        return [t for t in targets if t.kind == "cluster"]

    _use_hook(monkeypatch, clusters_only)
    tok = authz.set_auth_token("tok-u1")
    try:
        out = await scope_candidates([_cand("cluster", "c1"), _cand("instance", "i1")])
        assert [c.resource_id for c in out] == ["c1"]
    finally:
        authz.reset_auth_token(tok)


async def test_scope_candidates_fail_closed_no_principal(authz_on):
    assert await scope_candidates([_cand("cluster", "c1")]) == []


async def test_scope_candidates_drops_candidate_without_resource_id(authz_on, monkeypatch):
    def allow_all(token, targets):
        return list(targets)

    _use_hook(monkeypatch, allow_all)
    tok = authz.set_auth_token("tok-u1")
    try:
        out = await scope_candidates([_cand("instance", None), _cand("instance", "i1")])
        assert [c.resource_id for c in out] == ["i1"]  # unidentifiable candidate dropped
    finally:
        authz.reset_auth_token(tok)


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

    def hook(token, targets):
        return [t for t in targets if t.resource_id in allowed]

    _use_hook(monkeypatch, hook)
    models = [_model(f"c{i}") for i in range(1, 6)]
    tok = authz.set_auth_token("tok-u1")
    try:
        page, total = await scope_and_paginate(models, TargetRef.from_cluster, offset=0, limit=2)
        assert total == 3  # hidden count (5) never leaks
        assert [m.id for m in page] == ["c1", "c3"]
        page2, total2 = await scope_and_paginate(models, TargetRef.from_cluster, offset=2, limit=2)
        assert total2 == 3
        assert [m.id for m in page2] == ["c5"]  # full page across the allowed set, not short
    finally:
        authz.reset_auth_token(tok)


async def test_scope_and_paginate_fail_closed_no_principal(authz_on):
    models = [_model("c1"), _model("c2")]
    page, total = await scope_and_paginate(models, TargetRef.from_cluster, offset=0, limit=10)
    assert page == [] and total == 0
