"""Infrastructure authorization: pluggable per-principal target scoping (authz only).

Delegates "which clusters/instances may this principal access" to a deployment-supplied
hook. This repo owns no principal->target mapping. Fail-closed when enabled: no principal,
hook error/timeout, or an unresolvable identity -> empty allowed set.

The hook receives the VALIDATED JWT (a bearer token string) plus the candidate targets and
returns the allowed subset. Passing the raw validated token (not pre-parsed claims) lets the
hook decode it OR forward it to an external authz service. The token is authn-validated
(signature/iss/aud/exp, via the single `validate_token` path) BEFORE the hook runs — the hook
never sees an unverified token.

Identity flows via a trust-boundary ContextVar (`set_auth_token`), set once where trust is
established (the `require_auth` API dependency, and the top of each agent-running worker
task). Enforcement then lives inside the base target loaders (`get_cluster_by_id`,
`get_instance_by_id`, `materialize_bound_target_scope`) and the listing paths, which read the
token via `current_auth_token()` — so it is never threaded through every signature, and a
target object cannot be produced without passing a guarded loader.

Passthrough when `infrastructure_authorization_enabled` is False (zero behavior change).
"""

from __future__ import annotations

import asyncio
import contextvars
import importlib
import inspect
import logging
from dataclasses import dataclass
from typing import Awaitable, Callable, List, Optional, Union

from redis_sre_agent.core.config import settings

logger = logging.getLogger(__name__)

# Hard ceiling on a single hook call so a slow/hung external authz service cannot stall
# every target resolution. Applies to awaitable hooks; a blocking sync hook is the
# deployment's responsibility. ponytail: fixed timeout, make configurable if it bites.
_HOOK_TIMEOUT_SECONDS = 5.0


@dataclass(frozen=True)
class TargetRef:
    """The single identity shape the authorization hook receives.

    Each surface (RedisCluster/RedisInstance records, TargetCatalogDoc) adapts its native
    object to/from this so ONE hook serves clusters and instances.
    """

    kind: str  # "cluster" | "instance"
    resource_id: str
    name: str = ""
    environment: Optional[str] = None

    @property
    def key(self) -> tuple[str, str]:
        return (self.kind, self.resource_id)

    # Duck-typed adapters (no import of the model classes -> no import cycle, since
    # clusters.py / instances.py import THIS module for enforcement).
    @classmethod
    def from_cluster(cls, cluster) -> "TargetRef":
        return cls(
            "cluster",
            str(cluster.id),
            getattr(cluster, "name", "") or "",
            getattr(cluster, "environment", None),
        )

    @classmethod
    def from_instance(cls, instance) -> "TargetRef":
        return cls(
            "instance",
            str(instance.id),
            getattr(instance, "name", "") or "",
            getattr(instance, "environment", None),
        )


# hook(auth_token, candidate_targets) -> {"allowed_targets": [{"type","id",...}], ...}  (sync or
# async). `auth_token` is the VALIDATED JWT bearer string; the hook may decode it or forward it to
# an external service. `candidate_targets` are plain {type,id,name,environment} dicts and the
# return is a plain dict, so no internal class crosses the boundary (external services speak JSON).
ScopeHook = Callable[[str, List[dict]], Union[dict, Awaitable[dict]]]


# --- trust-boundary auth token (validated JWT bearer; None => no authenticated identity) ---
_auth_token: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "infra_authz_token", default=None
)


def set_auth_token(token: Optional[str]) -> "contextvars.Token[Optional[str]]":
    """Set the current validated auth token for this async context. Returns a reset token."""
    return _auth_token.set(token)


def reset_auth_token(token: "contextvars.Token[Optional[str]]") -> None:
    """Reset the auth token (call in a finally at each worker task top, so a reused context
    cannot inherit a prior task's token — the None default must hold)."""
    _auth_token.reset(token)


def current_auth_token() -> Optional[str]:
    return _auth_token.get()


# --- pluggable hook resolution (import path "module:callable", cached) ---
_hook_cache: Optional[ScopeHook] = None


def _load_hook() -> ScopeHook:
    global _hook_cache
    if _hook_cache is not None:
        return _hook_cache
    path = settings.infrastructure_authorization_hook
    if not path:
        raise RuntimeError("infrastructure_authorization_hook is not configured")
    module_path, sep, attr = path.partition(":")
    if not module_path or not sep or not attr:
        raise RuntimeError(
            f"invalid infrastructure_authorization_hook {path!r}; expected 'module:callable'"
        )
    module = importlib.import_module(module_path)
    hook = getattr(module, attr)
    _hook_cache = hook
    return hook


def reset_hook_cache() -> None:
    """Drop the cached hook. For tests and config reloads."""
    global _hook_cache
    _hook_cache = None


def _to_wire(t: TargetRef) -> dict:
    """The plain-data shape a target takes when handed to the hook, so no internal class crosses
    the boundary (an external authz service consumes/returns JSON directly)."""
    return {"type": t.kind, "id": t.resource_id, "name": t.name, "environment": t.environment}


def _allowed_keys_from_hook_result(result) -> set:
    """Parse the hook's dict return into a set of (type, id) keys. Fail-closed by construction:
    a non-dict return or a missing/non-list `allowed_targets` raises (-> deny all); a record
    missing `type`/`id` is skipped (-> that target denied). Extra fields (name, access_level, ...)
    are ignored this phase."""
    if not isinstance(result, dict):
        raise ValueError("authorization hook must return a dict")
    allowed = result.get("allowed_targets")
    if not isinstance(allowed, list):
        raise ValueError("authorization hook result missing an 'allowed_targets' list")
    keys = set()
    for rec in allowed:
        if not isinstance(rec, dict):
            continue
        typ, rid = rec.get("type"), rec.get("id")
        if not typ or not rid:
            continue  # a target must be identified unambiguously by type + id
        keys.add((str(typ), str(rid)))
    return keys


async def scope_targets(targets: List[TargetRef]) -> List[TargetRef]:
    """Return the subset of `targets` the current principal may access.

    - authz disabled -> passthrough (zero behavior change).
    - no validated token / hook error / timeout / invalid return shape -> [] (fail closed).
    - the hook receives plain `{type,id,name,environment}` dicts and returns
      `{"allowed_targets": [{"type","id",...}], ...}`; we intersect the returned (type,id) keys
      with the input by identity and return the ORIGINAL input objects. A buggy or hostile hook
      can only ever REMOVE access, never add or mutate.
    """
    if not settings.infrastructure_authorization_enabled:
        return list(targets)
    token = current_auth_token()
    if not token:
        return []  # fail closed: no verified token in scope
    if not targets:
        return []
    try:
        hook = _load_hook()
        result = hook(token, [_to_wire(t) for t in targets])
        if inspect.isawaitable(result):
            result = await asyncio.wait_for(result, timeout=_HOOK_TIMEOUT_SECONDS)
        allowed_keys = _allowed_keys_from_hook_result(result)
    except Exception:
        logger.exception(
            "infrastructure authorization hook failed or returned an invalid shape; denying (fail-closed)"
        )
        return []
    # Intersect: keep only inputs the hook allowed; never trust the hook to add targets.
    return [t for t in targets if t.key in allowed_keys]


async def assert_target_allowed(target: TargetRef) -> bool:
    """True iff the current principal may access `target` (a single-target scope check)."""
    allowed = await scope_targets([target])
    return bool(allowed)


async def scope_models(models: list, ref_adapter) -> list:
    """Scope a list of native models (RedisCluster/RedisInstance) to the allowed subset.

    `ref_adapter` maps a model -> TargetRef (e.g. TargetRef.from_cluster). Returns the
    ORIGINAL model objects the current principal may access. Passthrough when authz off.
    """
    if not settings.infrastructure_authorization_enabled:
        return list(models)
    refs = [ref_adapter(m) for m in models]
    allowed_keys = {r.key for r in await scope_targets(refs)}
    # Reuse `refs` (zip) instead of calling ref_adapter again per model — one pass on listing
    # paths that can carry up to 1000 models.
    return [m for m, r in zip(models, refs) if r.key in allowed_keys]


async def scope_and_paginate(models: list, ref_adapter, offset: int, limit: int):
    """Scope THEN count THEN paginate (in that order) for listing surfaces.

    Scoping before count/paginate is what keeps `total` and page contents from leaking the
    existence or number of inaccessible targets (a user never sees them, and can't infer the
    hidden count). Returns (page, total_over_allowed).
    """
    scoped = await scope_models(models, ref_adapter)
    total = len(scoped)
    start = max(0, offset)
    return scoped[start : start + max(1, limit)], total


async def scope_candidates(candidates: list) -> list:
    """Filter discovery candidates (duck-typed `.target_kind` / `.resource_id`) to the subset
    the current principal may access. Used to drop denied bindings before materialization so
    the deep-triage fan-out cannot operate on a target the principal can't access.

    authz off -> passthrough. authz on -> a candidate with no resource_id (unidentifiable) or
    not in the allowed set is dropped (fail-closed).
    """
    if not settings.infrastructure_authorization_enabled:
        return list(candidates)
    refs = []
    for c in candidates:
        rid = getattr(c, "resource_id", None)
        if not rid:
            continue
        refs.append(TargetRef(str(getattr(c, "target_kind", "") or ""), str(rid)))
    allowed_keys = {r.key for r in await scope_targets(refs)}
    return [
        c
        for c in candidates
        if getattr(c, "resource_id", None)
        and (str(getattr(c, "target_kind", "") or ""), str(c.resource_id)) in allowed_keys
    ]
