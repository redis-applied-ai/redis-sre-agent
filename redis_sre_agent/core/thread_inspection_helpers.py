"""Shared helpers for MCP thread inspection tools."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from redis_sre_agent.core.keys import RedisKeys
from redis_sre_agent.core.redis import get_redis_client
from redis_sre_agent.core.tasks import TaskManager
from redis_sre_agent.core.threads import ThreadManager


def _decode_task_id(task_id: Any) -> str:
    if isinstance(task_id, bytes):
        return task_id.decode()
    return str(task_id)


def _extract_source_fragments(updates: Any, task_id: str) -> List[Dict[str, Any]]:
    fragments: List[Dict[str, Any]] = []
    for update in updates or []:
        try:
            if (getattr(update, "update_type", "") or "") != "knowledge_sources":
                continue
            metadata = getattr(update, "metadata", None) or {}
            for fragment in metadata.get("fragments") or []:
                fragments.append(
                    {
                        "timestamp": getattr(update, "timestamp", None),
                        "task_id": task_id,
                        "id": fragment.get("id"),
                        "document_hash": fragment.get("document_hash"),
                        "chunk_index": fragment.get("chunk_index"),
                        "title": fragment.get("title"),
                        "source": fragment.get("source"),
                    }
                )
        except Exception:
            continue
    return fragments


def _build_tool_call(envelope: Dict[str, Any], include_tool_data: bool) -> Dict[str, Any]:
    data = envelope.get("data") or {}
    summary = envelope.get("summary")
    if summary:
        result_preview = summary
    else:
        result_preview = json.dumps(data, default=str)

    tool_call = {
        "name": envelope.get("name") or envelope.get("tool_key", "unknown"),
        "tool_key": envelope.get("tool_key"),
        "args": envelope.get("args") or {},
        "status": envelope.get("status", "unknown"),
        "summary": summary,
        "result_preview": result_preview,
    }
    if include_tool_data:
        tool_call["data"] = data
    return tool_call


def _derive_citations(tool_envelopes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    citations: List[Dict[str, Any]] = []
    for envelope in tool_envelopes:
        tool_key = str(envelope.get("tool_key", ""))
        tool_name = str(envelope.get("name", ""))
        if "knowledge" not in tool_key.lower() or "search" not in tool_name.lower():
            continue

        data = envelope.get("data") or {}
        for result in data.get("results") or []:
            citations.append(
                {
                    "title": result.get("title"),
                    "source": result.get("source"),
                    "score": result.get("score"),
                    "document_id": result.get("id"),
                }
            )
    return citations


async def get_thread_sources_helper(
    thread_id: str, task_id: Optional[str] = None
) -> Dict[str, Any]:
    """Collect knowledge-source fragments for a thread or a single task turn."""
    client = get_redis_client()
    thread_manager = ThreadManager(redis_client=client)
    task_manager = TaskManager(redis_client=client)

    thread = await thread_manager.get_thread(thread_id)
    if not thread:
        return {
            "error": f"Thread {thread_id} not found",
            "thread_id": thread_id,
            "task_id": task_id,
            "fragments": [],
            "count": 0,
        }

    fragments: List[Dict[str, Any]] = []
    task_ids = await client.zrange(RedisKeys.thread_tasks_index(thread_id), 0, -1)
    for raw_task_id in task_ids:
        normalized_task_id = _decode_task_id(raw_task_id)
        if task_id and normalized_task_id != task_id:
            continue

        task_state = await task_manager.get_task_state(normalized_task_id)
        if not task_state:
            continue

        fragments.extend(_extract_source_fragments(task_state.updates, normalized_task_id))

    return {
        "thread_id": thread_id,
        "task_id": task_id,
        "fragments": fragments,
        "count": len(fragments),
    }


async def get_thread_trace_helper(
    message_id: str, include_tool_data: bool = False
) -> Dict[str, Any]:
    """Retrieve and summarize a message decision trace."""
    client = get_redis_client()
    thread_manager = ThreadManager(redis_client=client)
    trace = await thread_manager.get_message_trace(message_id)

    if not trace:
        return {
            "error": f"No decision trace found for message {message_id}",
            "message_id": message_id,
            "tool_calls": [],
            "tool_call_count": 0,
            "citations": [],
            "citation_count": 0,
        }

    tool_envelopes = trace.get("tool_envelopes") or []
    tool_calls = [_build_tool_call(envelope, include_tool_data) for envelope in tool_envelopes]
    citations = _derive_citations(tool_envelopes)

    return {
        "message_id": trace.get("message_id", message_id),
        "otel_trace_id": trace.get("otel_trace_id"),
        "created_at": trace.get("created_at"),
        "tool_calls": tool_calls,
        "tool_call_count": len(tool_calls),
        "citations": citations,
        "citation_count": len(citations),
    }
