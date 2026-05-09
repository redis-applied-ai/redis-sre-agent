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
        "asset_scope": None,
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
    """Try broad-text fallbacks until one returns results (or all exhaust)."""
    last: Optional[LongTermSearchResult] = None
    for query in _LIST_QUERY_FALLBACKS:
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
    """Try broad-text fallbacks until one returns results (or all exhaust)."""
    last: Optional[LongTermSearchResult] = None
    for query in _LIST_QUERY_FALLBACKS:
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


def _resolve_scope(state: Any) -> Dict[str, Optional[str]]:
    """Extract user_id, instance_id, cluster_id from a thread state."""
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
    return {"user_id": user_id, "instance_id": instance_id, "cluster_id": cluster_id}


@router.get("/memory/thread/{thread_id}")
async def get_thread_memory(
    thread_id: str,
    user_limit: int = Query(default=50, ge=1, le=200),
    user_offset: int = Query(default=0, ge=0),
    asset_limit: int = Query(default=50, ge=1, le=200),
    asset_offset: int = Query(default=0, ge=0),
) -> Dict[str, Any]:
    """List in-scope user and asset memories for a given thread."""

    service = AgentMemoryService()
    if not service.enabled:
        return _disabled_response("disabled" if settings.agent_memory_enabled else "disabled")

    rc = get_redis_client()
    tm = ThreadManager(redis_client=rc)
    state = await tm.get_thread(thread_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    scope = _resolve_scope(state)
    user_id = scope["user_id"]
    instance_id = scope["instance_id"]
    cluster_id = scope["cluster_id"]

    if not user_id and not (instance_id or cluster_id):
        return {
            "enabled": True,
            "status": "missing_scope",
            "error": None,
            "scope": scope,
            "user_scope": None,
            "asset_scope": None,
        }

    user_section: Optional[Dict[str, Any]] = None
    asset_section: Optional[Dict[str, Any]] = None

    try:
        async with service.open_session() as ams_session:
            if user_id:
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

            if instance_id or cluster_id:
                asset_long_term = await _list_asset_long_term(
                    ams_session,
                    instance_id=instance_id,
                    cluster_id=cluster_id,
                    limit=asset_limit,
                    offset=asset_offset,
                )
                asset_working = await ams_session.get_asset_working_memory(
                    instance_id=instance_id,
                    cluster_id=cluster_id,
                    create_if_missing=False,
                )
                asset_section = _serialize_section(long_term=asset_long_term, working=asset_working)
    except Exception as exc:
        logger.warning("AMS memory listing failed for thread %s: %s", thread_id, exc)
        return {
            "enabled": True,
            "status": "error",
            "error": "Failed to load memory context",
            "scope": scope,
            "user_scope": user_section,
            "asset_scope": asset_section,
        }

    return {
        "enabled": True,
        "status": "loaded",
        "error": None,
        "scope": scope,
        "user_scope": user_section,
        "asset_scope": asset_section,
    }
