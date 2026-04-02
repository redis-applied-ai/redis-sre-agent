"""Helpers for thread maintenance MCP tools."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from redis_sre_agent.core.helper_utils import (
    decode_text as _decode,
)
from redis_sre_agent.core.helper_utils import (
    parse_duration as _parse_duration,
)
from redis_sre_agent.core.helper_utils import (
    parse_timestamp as _parse_timestamp,
)
from redis_sre_agent.core.keys import RedisKeys
from redis_sre_agent.core.redis import (
    SRE_THREADS_INDEX,
    get_redis_client,
    get_threads_index,
)
from redis_sre_agent.core.tasks import delete_task as delete_task_core
from redis_sre_agent.core.threads import ThreadManager


def _derive_subject(state: Any) -> Optional[str]:
    context = getattr(state, "context", {}) or {}
    original_query = context.get("original_query")
    if isinstance(original_query, str) and original_query.strip():
        return original_query.strip()

    for message in getattr(state, "messages", []) or []:
        if getattr(message, "role", None) == "user":
            content = getattr(message, "content", "")
            if isinstance(content, str) and content.strip():
                return content.strip()

    legacy_messages = context.get("messages") if isinstance(context, dict) else None
    if isinstance(legacy_messages, list):
        for message in legacy_messages:
            if isinstance(message, dict) and message.get("role") == "user":
                content = message.get("content")
                if isinstance(content, str) and content.strip():
                    return content.strip()

    return None


async def _backfill_threads_from_zset(
    thread_manager: ThreadManager, client, limit: int, start: int
) -> int:
    processed = 0
    offset = start
    page = 500

    while True:
        ids = await client.zrevrange(RedisKeys.threads_index(), offset, offset + page - 1)
        if not ids:
            break

        for raw in ids:
            if limit and processed >= limit:
                return processed
            thread_id = _decode(raw)
            await thread_manager._upsert_thread_search_doc(thread_id)
            processed += 1

        offset += page

    return processed


async def reindex_threads_helper(
    *,
    drop: bool = False,
    limit: int = 0,
    start: int = 0,
    redis_client=None,
) -> dict[str, Any]:
    client = redis_client or get_redis_client()
    thread_manager = ThreadManager(redis_client=client)
    index = await get_threads_index()

    try:
        exists = await index.exists()
    except Exception:
        exists = False

    dropped = False
    if exists and drop:
        try:
            await index.drop()  # type: ignore[attr-defined]
            dropped = True
        except Exception:
            try:
                await client.execute_command("FT.DROPINDEX", SRE_THREADS_INDEX)
                dropped = True
            except Exception:
                pass

    if not await index.exists():
        await index.create()

    processed = await _backfill_threads_from_zset(thread_manager, client, limit=limit, start=start)
    return {
        "status": "completed",
        "processed": processed,
        "dropped": dropped,
        "index": SRE_THREADS_INDEX,
    }


async def backfill_threads_helper(
    *,
    limit: int = 0,
    start: int = 0,
    redis_client=None,
) -> dict[str, Any]:
    client = redis_client or get_redis_client()
    thread_manager = ThreadManager(redis_client=client)
    processed = await _backfill_threads_from_zset(thread_manager, client, limit=limit, start=start)
    return {"status": "completed", "processed": processed, "index": SRE_THREADS_INDEX}


async def backfill_scheduled_thread_subjects_helper(
    *,
    limit: int = 0,
    start: int = 0,
    dry_run: bool = False,
    redis_client=None,
) -> dict[str, Any]:
    client = redis_client or get_redis_client()
    thread_manager = ThreadManager(redis_client=client)
    scanned = 0
    subject_updates = 0
    tag_updates = 0
    offset = start
    page = 500

    while True:
        ids = await client.zrevrange(RedisKeys.threads_index(), offset, offset + page - 1)
        if not ids:
            break

        for raw in ids:
            if limit and scanned >= limit:
                return {
                    "status": "dry_run" if dry_run else "completed",
                    "scanned": scanned,
                    "subjects_updated": subject_updates,
                    "tags_updated": tag_updates,
                    "dry_run": dry_run,
                }

            thread_id = _decode(raw)
            state = await thread_manager.get_thread(thread_id)
            if not state:
                scanned += 1
                continue

            metadata = state.metadata
            context = state.context or {}
            schedule_name = context.get("schedule_name") or None
            is_scheduled = (
                (metadata.user_id or "") == "scheduler"
                or ("scheduled" in (metadata.tags or []))
                or (bool(context.get("automated")) and bool(schedule_name))
            )

            subject = (metadata.subject or "").strip()
            if (
                is_scheduled
                and schedule_name
                and (not subject or subject.lower() in {"untitled", "unknown"})
            ):
                if not dry_run:
                    await thread_manager.set_thread_subject(thread_id, schedule_name)
                subject_updates += 1

            if is_scheduled and "scheduled" not in (metadata.tags or []):
                if not dry_run:
                    metadata.tags = list(sorted(set((metadata.tags or []) + ["scheduled"])))
                    await thread_manager._save_thread_state(state)
                tag_updates += 1

            scanned += 1

        offset += page

    return {
        "status": "dry_run" if dry_run else "completed",
        "scanned": scanned,
        "subjects_updated": subject_updates,
        "tags_updated": tag_updates,
        "dry_run": dry_run,
    }


async def backfill_empty_thread_subjects_helper(
    *,
    limit: int = 0,
    start: int = 0,
    dry_run: bool = False,
    redis_client=None,
) -> dict[str, Any]:
    client = redis_client or get_redis_client()
    thread_manager = ThreadManager(redis_client=client)
    scanned = 0
    skipped = 0
    updated = 0
    cursor = 0

    while True:
        cursor, keys = await client.scan(cursor=cursor, match=f"{SRE_THREADS_INDEX}:*", count=1000)
        if not keys and cursor == 0:
            break

        for key in keys or []:
            if skipped < start:
                skipped += 1
                continue

            if limit and scanned >= limit:
                return {
                    "status": "dry_run" if dry_run else "completed",
                    "scanned": scanned,
                    "subjects_updated": updated,
                    "dry_run": dry_run,
                }

            redis_key = _decode(key)
            thread_id = redis_key[len(f"{SRE_THREADS_INDEX}:") :]
            state = await thread_manager.get_thread(thread_id)
            if not state:
                scanned += 1
                continue

            subject = (state.metadata.subject or "").strip()
            if subject and subject.lower() not in {"untitled", "unknown"}:
                scanned += 1
                continue

            candidate = _derive_subject(state)
            if not candidate:
                scanned += 1
                continue

            line = candidate.splitlines()[0].strip()
            if len(line) > 80:
                line = line[:77].rstrip() + "..."

            if not dry_run:
                await thread_manager.set_thread_subject(thread_id, line)
            updated += 1
            scanned += 1

        if cursor == 0:
            break

    return {
        "status": "dry_run" if dry_run else "completed",
        "scanned": scanned,
        "subjects_updated": updated,
        "dry_run": dry_run,
    }


async def purge_threads_helper(
    *,
    older_than: Optional[str] = None,
    purge_all: bool = False,
    include_tasks: bool = True,
    dry_run: bool = False,
    confirm: bool = False,
    redis_client=None,
) -> dict[str, Any]:
    if not purge_all and not older_than:
        return {
            "error": "Refusing to purge without a scope. Provide older_than or purge_all.",
            "status": "failed",
        }

    if not dry_run and not confirm:
        return {"error": "Confirmation required", "status": "cancelled", "dry_run": False}

    client = redis_client or get_redis_client()
    thread_manager = ThreadManager(redis_client=client)
    cutoff_ts = None
    if older_than:
        cutoff_ts = (datetime.now(timezone.utc) - _parse_duration(older_than)).timestamp()

    cursor = 0
    scanned = 0
    deleted = 0
    deleted_tasks = 0
    matched: list[str] = []

    while True:
        cursor, keys = await client.scan(cursor=cursor, match=f"{SRE_THREADS_INDEX}:*", count=1000)
        if not keys and cursor == 0:
            break

        for key in keys or []:
            redis_key = _decode(key)
            thread_id = redis_key[len(f"{SRE_THREADS_INDEX}:") :]

            eligible = True
            if cutoff_ts is not None:
                try:
                    created_at = await client.hget(redis_key, "created_at")
                    created_ts = _parse_timestamp(created_at)
                    eligible = created_ts > 0 and created_ts < cutoff_ts
                except Exception:
                    eligible = False

            if not eligible:
                scanned += 1
                continue

            matched.append(thread_id)
            if not dry_run:
                if include_tasks:
                    task_ids = await client.zrevrange(
                        RedisKeys.thread_tasks_index(thread_id), 0, -1
                    )
                    for raw in task_ids or []:
                        try:
                            await delete_task_core(task_id=_decode(raw), redis_client=client)
                            deleted_tasks += 1
                        except Exception:
                            pass

                if await thread_manager.delete_thread(thread_id):
                    try:
                        await client.delete(f"{SRE_THREADS_INDEX}:{thread_id}")
                    except Exception:
                        pass
                    deleted += 1

            scanned += 1

        if cursor == 0:
            break

    return {
        "status": "dry_run" if dry_run else "purged",
        "scanned": scanned,
        "deleted": deleted,
        "deleted_tasks": deleted_tasks,
        "matched": matched,
        "dry_run": dry_run,
        "include_tasks": include_tasks,
    }
