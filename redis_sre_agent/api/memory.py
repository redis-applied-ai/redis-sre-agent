"""Read-only API for surfacing Agent Memory Server memories tied to a thread.

Powers the Memory side panel in the SRE Agent UI. Composes the same
MemorySession primitives the agent uses internally so retrieval logic,
namespace selection, and asset/user scope filtering stay in one place.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from redis_sre_agent.core.agent_memory import (
    AgentMemoryService,
    LongTermSearchResult,
    MemorySession,
    WorkingMemoryResult,
)
from redis_sre_agent.core.config import settings
from redis_sre_agent.core.redis import get_redis_client
from redis_sre_agent.core.threads import ThreadManager

logger = logging.getLogger(__name__)

router = APIRouter()

# Broad-text fallbacks tried in order. AMS search requires a text query;
# entity / user_id filters narrow results, but text drives semantic ranking.
# Each phrase is generic enough that any in-scope memory should match at
# least one of them.
_LIST_QUERY_FALLBACKS = (
    "redis sre operational context",
    "redis",
    "memory",
)


def _serialize_memory(memory: Any) -> Dict[str, Any]:
    """Best-effort serialization of an AMS MemoryRecord-like object."""
    return {
        "id": getattr(memory, "id", None),
        "text": getattr(memory, "text", None),
        "memory_type": getattr(memory, "memory_type", None),
        "created_at": _iso(getattr(memory, "created_at", None)),
        "last_accessed": _iso(getattr(memory, "last_accessed", None)),
        "topics": list(getattr(memory, "topics", None) or []),
        "entities": list(getattr(memory, "entities", None) or []),
    }


def _iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            return None
    if isinstance(value, str):
        return value
    return None


def _disabled_response(reason: str = "disabled") -> Dict[str, Any]:
    return {
        "enabled": False,
        "status": reason,
        "error": None,
        "scope": {"user_id": None, "instance_id": None, "cluster_id": None},
        "user_scope": None,
        "asset_scopes": [],
    }


def _serialize_section(
    *,
    long_term: LongTermSearchResult,
    working: WorkingMemoryResult,
) -> Dict[str, Any]:
    return {
        "long_term": {
            "items": [_serialize_memory(m) for m in long_term.memories],
            "total": long_term.total,
            "next_offset": long_term.next_offset,
        },
        "working_memory_context": getattr(working.memory, "context", None),
    }


async def _list_user_long_term(
    session: MemorySession,
    *,
    user_id: str,
    limit: int,
    offset: int,
) -> LongTermSearchResult:
    """Try broad-text fallbacks until one returns results (or all exhaust).

    When paginating (offset > 0), only use the first canonical query so
    subsequent pages stay anchored to the same result set instead of
    falling through to a different fallback.
    """
    queries = _LIST_QUERY_FALLBACKS[:1] if offset > 0 else _LIST_QUERY_FALLBACKS
    last: Optional[LongTermSearchResult] = None
    for query in queries:
        result = await session.search_user_long_term(
            query=query, user_id=user_id, limit=limit, offset=offset
        )
        if result.memories:
            return result
        last = result
    return last or LongTermSearchResult()


async def _list_asset_long_term(
    session: MemorySession,
    *,
    instance_id: Optional[str],
    cluster_id: Optional[str],
    limit: int,
    offset: int,
) -> LongTermSearchResult:
    """Try broad-text fallbacks until one returns results (or all exhaust).

    When paginating (offset > 0), only use the first canonical query so
    subsequent pages stay anchored to the same result set instead of
    falling through to a different fallback.
    """
    queries = _LIST_QUERY_FALLBACKS[:1] if offset > 0 else _LIST_QUERY_FALLBACKS
    last: Optional[LongTermSearchResult] = None
    for query in queries:
        result = await session.search_asset_long_term(
            query=query,
            instance_id=instance_id,
            cluster_id=cluster_id,
            limit=limit,
            offset=offset,
            filter_preferences=True,
        )
        if result.memories:
            return result
        last = result
    return last or LongTermSearchResult()


async def _load_asset_scope_entry(
    session: MemorySession,
    *,
    label: str,
    instance_id: Optional[str],
    cluster_id: Optional[str],
    thread_id: str,
    limit: int,
    offset: int,
) -> Dict[str, Any]:
    """Fetch long-term and working memory for one asset and return a labelled section."""
    long_term = await _list_asset_long_term(
        session,
        instance_id=instance_id,
        cluster_id=cluster_id,
        limit=limit,
        offset=offset,
    )
    working = await session.get_asset_working_memory(
        instance_id=instance_id,
        cluster_id=cluster_id,
        create_if_missing=False,
    )
    section = _serialize_section(long_term=long_term, working=working)
    return {
        "label": label,
        "instance_id": instance_id,
        "cluster_id": cluster_id,
        **section,
    }


def _resolve_scope(state: Any) -> Dict[str, Any]:
    """Extract user_id, instance_id, cluster_id, and referenced_assets from thread state."""
    try:
        metadata = state.metadata.model_dump()
    except Exception:
        try:
            metadata = dict(state.metadata)  # type: ignore[arg-type]
        except Exception:
            metadata = {}
    context: Dict[str, Any] = dict(state.context or {})

    raw_user = (metadata or {}).get("user_id") or context.get("user_id")
    user_id = (str(raw_user).strip() or None) if raw_user else None
    if not AgentMemoryService._valid_user_id(user_id):
        user_id = None

    instance_id = str(context.get("instance_id") or "").strip() or None
    cluster_id = str(context.get("cluster_id") or "").strip() or None

    raw_refs = context.get("referenced_assets")
    referenced_assets: List[Dict[str, Any]] = []
    if isinstance(raw_refs, list):
        for entry in raw_refs:
            if isinstance(entry, dict) and (
                entry.get("instance_id") or entry.get("cluster_id") or entry.get("target_handle")
            ):
                referenced_assets.append(entry)

    return {
        "user_id": user_id,
        "instance_id": instance_id,
        "cluster_id": cluster_id,
        "referenced_assets": referenced_assets,
    }


async def _resolve_handle_to_ids(target_handle: str) -> tuple[Optional[str], Optional[str]]:
    """Look up instance_id/cluster_id for a target_handle via the handle store."""
    try:
        from redis_sre_agent.core.targets import get_target_handle_store

        store = get_target_handle_store()
        record = await store.get_record(target_handle)
        if record is None:
            return None, None
        subject = record.binding_subject or ""
        kind = (record.private_binding_ref or {}).get("target_kind", "")
        if kind == "instance":
            return subject or None, None
        if kind == "cluster":
            return None, subject or None
        return None, None
    except Exception:
        logger.debug("Could not resolve target_handle %s to IDs", target_handle)
        return None, None


@router.get("/memory/thread/{thread_id}")
async def get_thread_memory(
    thread_id: str,
    user_limit: int = Query(default=50, ge=1, le=200),
    user_offset: int = Query(default=0, ge=0),
    asset_limit: int = Query(default=50, ge=1, le=200),
    asset_offset: int = Query(default=0, ge=0),
    asset_instance_id: Optional[str] = Query(default=None),
    asset_cluster_id: Optional[str] = Query(default=None),
) -> Dict[str, Any]:
    """List in-scope user and asset memories for a given thread.

    When `asset_instance_id` or `asset_cluster_id` is supplied, only that
    one resolved asset scope is paginated and returned (so per-scope "load
    more" works correctly when multiple asset scopes exist). The
    `asset_offset` then applies to that specific scope. Without those
    params, all in-scope assets are returned at `asset_offset=0`.
    """

    service = AgentMemoryService()
    if not service.enabled:
        return _disabled_response("unavailable" if settings.agent_memory_enabled else "disabled")

    rc = get_redis_client()
    tm = ThreadManager(redis_client=rc)
    state = await tm.get_thread(thread_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    scope = _resolve_scope(state)
    user_id = scope["user_id"]
    instance_id = scope["instance_id"]
    cluster_id = scope["cluster_id"]
    referenced_assets: List[Dict[str, Any]] = scope["referenced_assets"]

    has_declared_asset = bool(instance_id or cluster_id)
    has_referenced_assets = bool(referenced_assets)

    if not user_id and not has_declared_asset and not has_referenced_assets:
        return {
            "enabled": True,
            "status": "missing_scope",
            "error": None,
            "scope": {k: v for k, v in scope.items() if k != "referenced_assets"},
            "user_scope": None,
            "asset_scopes": [],
        }

    target_asset_key: Optional[tuple[Optional[str], Optional[str]]] = None
    if asset_instance_id or asset_cluster_id:
        target_asset_key = (asset_instance_id or None, asset_cluster_id or None)

    user_section: Optional[Dict[str, Any]] = None
    asset_scopes: List[Dict[str, Any]] = []

    try:
        async with service.open_session() as ams_session:
            # When the caller is paginating a single asset scope, skip
            # re-fetching the user scope to keep the request lean and
            # avoid double-counting working memory.
            if user_id and target_asset_key is None:
                user_long_term = await _list_user_long_term(
                    ams_session,
                    user_id=user_id,
                    limit=user_limit,
                    offset=user_offset,
                )
                user_working = await ams_session.get_user_working_memory(
                    session_id=thread_id,
                    user_id=user_id,
                    create_if_missing=False,
                )
                user_section = _serialize_section(long_term=user_long_term, working=user_working)

            if has_declared_asset:
                declared_key = (instance_id, cluster_id)
                if target_asset_key is None or target_asset_key == declared_key:
                    label = instance_id or cluster_id or "asset"
                    entry = await _load_asset_scope_entry(
                        ams_session,
                        label=label,
                        instance_id=instance_id,
                        cluster_id=cluster_id,
                        thread_id=thread_id,
                        limit=asset_limit,
                        offset=asset_offset if target_asset_key is not None else 0,
                    )
                    asset_scopes.append(entry)

            # Deduplicate referenced assets against the declared scope.
            declared_key = (instance_id, cluster_id)
            seen_keys = {declared_key} if has_declared_asset else set()

            for ref in referenced_assets:
                ref_instance = ref.get("instance_id") or None
                ref_cluster = ref.get("cluster_id") or None
                handle = ref.get("target_handle")

                if not ref_instance and not ref_cluster and handle:
                    ref_instance, ref_cluster = await _resolve_handle_to_ids(handle)

                if not ref_instance and not ref_cluster:
                    continue

                key = (ref_instance, ref_cluster)
                if key in seen_keys:
                    continue
                seen_keys.add(key)

                if target_asset_key is not None and target_asset_key != key:
                    continue

                label = ref.get("label") or ref_instance or ref_cluster or "asset"
                entry = await _load_asset_scope_entry(
                    ams_session,
                    label=label,
                    instance_id=ref_instance,
                    cluster_id=ref_cluster,
                    thread_id=thread_id,
                    limit=asset_limit,
                    offset=asset_offset if target_asset_key is not None else 0,
                )
                asset_scopes.append(entry)

    except Exception as exc:
        logger.warning("AMS memory listing failed for thread %s: %s", thread_id, exc)
        return {
            "enabled": True,
            "status": "error",
            "error": "Failed to load memory context",
            "scope": {k: v for k, v in scope.items() if k != "referenced_assets"},
            "user_scope": user_section,
            "asset_scopes": asset_scopes,
        }

    return {
        "enabled": True,
        "status": "loaded",
        "error": None,
        "scope": {k: v for k, v in scope.items() if k != "referenced_assets"},
        "user_scope": user_section,
        "asset_scopes": asset_scopes,
    }
