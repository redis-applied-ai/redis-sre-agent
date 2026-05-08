"""Read-only API for surfacing Agent Memory Server memories tied to a thread.

Powers the Memory side panel in the SRE Agent UI. Reuses the same AMS client
the agent uses internally; never exposes credentials or working-memory
message streams.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from redis_sre_agent.core.agent_memory import AgentMemoryService
from redis_sre_agent.core.config import settings
from redis_sre_agent.core.redis import get_redis_client
from redis_sre_agent.core.threads import ThreadManager

logger = logging.getLogger(__name__)

router = APIRouter()

try:
    from agent_memory_client import MemoryAPIClient, MemoryClientConfig
    from agent_memory_client.exceptions import MemoryNotFoundError
    from agent_memory_client.filters import Entities, Namespace, UserId

    AMS_SDK_AVAILABLE = True
except ImportError:  # pragma: no cover
    MemoryAPIClient = None  # type: ignore[assignment]
    MemoryClientConfig = None  # type: ignore[assignment]
    MemoryNotFoundError = Exception  # type: ignore[misc,assignment]
    Entities = None  # type: ignore[assignment]
    Namespace = None  # type: ignore[assignment]
    UserId = None  # type: ignore[assignment]
    AMS_SDK_AVAILABLE = False


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


def _empty_section() -> Dict[str, Any]:
    return {
        "long_term": {"items": [], "total": 0, "next_offset": None},
        "working_memory_context": None,
    }


def _ams_client_config() -> Any:
    return MemoryClientConfig(
        base_url=settings.agent_memory_base_url or "",
        timeout=settings.agent_memory_timeout,
        default_namespace=settings.agent_memory_namespace,
        default_model_name=settings.agent_memory_model_name,
    )


async def _fetch_long_term(
    client: Any,
    *,
    namespace: str,
    user_id: Optional[str],
    entities: Optional[List[str]],
    limit: int,
    offset: int,
) -> Dict[str, Any]:
    """List filter-matching memories. Uses a broad text query to satisfy AMS
    semantic search; relies on user_id/entities filters for correctness.
    """

    base_kwargs: Dict[str, Any] = {
        "namespace": Namespace(eq=namespace),
        "limit": limit,
        "offset": offset,
        "distance_threshold": 1.5,
    }
    if user_id:
        base_kwargs["user_id"] = UserId(eq=user_id)
    if entities:
        base_kwargs["entities"] = Entities(any=entities)

    last_exc: Optional[Exception] = None
    for query_text in (
        "redis sre operational context",
        "redis",
        "memory",
    ):
        try:
            result = await client.search_long_term_memory(text=query_text, **base_kwargs)
            memories = list(getattr(result, "memories", []) or [])
            if not memories and query_text != "memory":
                continue
            total = getattr(result, "total", None)
            if total is None:
                total = len(memories)
            next_offset = offset + len(memories) if len(memories) >= limit else None
            return {
                "items": [_serialize_memory(m) for m in memories],
                "total": total,
                "next_offset": next_offset,
            }
        except Exception as exc:  # pragma: no cover - defensive across AMS versions
            last_exc = exc
            continue

    if last_exc is not None:
        raise last_exc
    return {"items": [], "total": 0, "next_offset": None}


async def _fetch_working_context(
    client: Any,
    *,
    session_id: Optional[str],
    namespace: str,
    user_id: Optional[str] = None,
) -> Optional[str]:
    """Return the AMS-managed working-memory context summary, never the messages."""
    if not session_id:
        return None
    try:
        kwargs: Dict[str, Any] = {
            "session_id": session_id,
            "namespace": namespace,
        }
        if user_id:
            kwargs["user_id"] = user_id
        memory = await client.get_working_memory(**kwargs)
        return getattr(memory, "context", None)
    except MemoryNotFoundError:
        return None
    except Exception as exc:
        logger.debug("get_working_memory failed for %s/%s: %s", namespace, session_id, exc)
        return None


@router.get("/memory/thread/{thread_id}")
async def get_thread_memory(
    thread_id: str,
    user_limit: int = Query(default=50, ge=1, le=200),
    user_offset: int = Query(default=0, ge=0),
    asset_limit: int = Query(default=50, ge=1, le=200),
    asset_offset: int = Query(default=0, ge=0),
) -> Dict[str, Any]:
    """List all in-scope user and asset memories for a given thread."""

    if not (settings.agent_memory_enabled and settings.agent_memory_base_url):
        return _disabled_response("disabled")
    if not AMS_SDK_AVAILABLE or MemoryAPIClient is None:
        return _disabled_response("unavailable")

    rc = get_redis_client()
    tm = ThreadManager(redis_client=rc)
    state = await tm.get_thread(thread_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    try:
        metadata = state.metadata.model_dump()
    except Exception:
        try:
            metadata = dict(state.metadata)  # type: ignore[arg-type]
        except Exception:
            metadata = {}

    context: Dict[str, Any] = dict(state.context or {})
    user_id_raw = (metadata or {}).get("user_id") or context.get("user_id")
    user_id = (str(user_id_raw).strip() or None) if user_id_raw else None
    if not AgentMemoryService._valid_user_id(user_id):
        user_id = None

    instance_id = str(context.get("instance_id") or "").strip() or None
    cluster_id = str(context.get("cluster_id") or "").strip() or None
    entities = AgentMemoryService._target_entities(
        instance_id=instance_id, cluster_id=cluster_id
    )

    scope = {
        "user_id": user_id,
        "instance_id": instance_id,
        "cluster_id": cluster_id,
    }

    if not user_id and not entities:
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
        async with MemoryAPIClient(_ams_client_config()) as client:
            if user_id:
                user_long_term = await _fetch_long_term(
                    client,
                    namespace=settings.agent_memory_namespace,
                    user_id=user_id,
                    entities=None,
                    limit=user_limit,
                    offset=user_offset,
                )
                user_working = await _fetch_working_context(
                    client,
                    session_id=thread_id,
                    namespace=settings.agent_memory_namespace,
                    user_id=user_id,
                )
                user_section = {
                    "long_term": user_long_term,
                    "working_memory_context": user_working,
                }

            if entities:
                asset_long_term_raw = await _fetch_long_term(
                    client,
                    namespace=settings.agent_memory_asset_namespace,
                    user_id=None,
                    entities=entities,
                    limit=asset_limit,
                    offset=asset_offset,
                )
                filtered_items = [
                    item
                    for item in asset_long_term_raw["items"]
                    if not AgentMemoryService._is_operator_preference_memory(item.get("text"))
                ]
                removed = len(asset_long_term_raw["items"]) - len(filtered_items)
                asset_long_term = {
                    "items": filtered_items,
                    "total": max(0, asset_long_term_raw["total"] - removed),
                    "next_offset": asset_long_term_raw["next_offset"],
                }
                asset_session_id = AgentMemoryService._asset_session_id(
                    instance_id=instance_id, cluster_id=cluster_id
                )
                asset_working = await _fetch_working_context(
                    client,
                    session_id=asset_session_id,
                    namespace=settings.agent_memory_asset_namespace,
                )
                asset_section = {
                    "long_term": asset_long_term,
                    "working_memory_context": asset_working,
                }
    except Exception as exc:
        logger.warning("AMS memory listing failed for thread %s: %s", thread_id, exc)
        return {
            "enabled": True,
            "status": "error",
            "error": str(exc),
            "scope": scope,
            "user_scope": user_section or _empty_section(),
            "asset_scope": asset_section or _empty_section(),
        }

    return {
        "enabled": True,
        "status": "loaded",
        "error": None,
        "scope": scope,
        "user_scope": user_section,
        "asset_scope": asset_section,
    }
