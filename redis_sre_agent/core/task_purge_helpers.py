"""Shared helpers for bulk task purge MCP tools."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from redis_sre_agent.core.helper_utils import (
    decode_text as _decode,
)
from redis_sre_agent.core.helper_utils import (
    parse_duration as _parse_duration,
)
from redis_sre_agent.core.redis import SRE_TASKS_INDEX, get_redis_client
from redis_sre_agent.core.tasks import delete_task as delete_task_core


async def purge_tasks_helper(
    *,
    status: Optional[str] = None,
    older_than: Optional[str] = None,
    purge_all: bool = False,
    dry_run: bool = False,
    confirm: bool = False,
    redis_client=None,
) -> Dict[str, Any]:
    """Delete tasks in bulk with safeguards and optional dry-run mode."""
    if not purge_all and not older_than and not status:
        return {
            "error": "Refusing to purge without a scope. Provide older_than/status or purge_all.",
            "status": "failed",
        }

    if not dry_run and not confirm:
        return {
            "error": "Confirmation required",
            "status": "cancelled",
            "dry_run": False,
        }

    client = redis_client or get_redis_client()
    cutoff_ts = None
    if older_than:
        cutoff_ts = (datetime.now(timezone.utc) - _parse_duration(older_than)).timestamp()

    cursor = 0
    scanned = 0
    deleted = 0
    matched: list[str] = []

    while True:
        cursor, keys = await client.scan(cursor=cursor, match=f"{SRE_TASKS_INDEX}:*", count=1000)
        if not keys and cursor == 0:
            break

        for key in keys or []:
            redis_key = _decode(key)
            task_id = redis_key[len(f"{SRE_TASKS_INDEX}:") :]

            try:
                st_raw, upd_raw, _ = await client.hmget(
                    redis_key, "status", "updated_at", "created_at"
                )
                task_status = _decode(st_raw).lower()
                updated_at = float(_decode(upd_raw) or 0)
            except Exception:
                task_status = ""
                updated_at = 0.0

            eligible = True
            if status:
                eligible = eligible and (task_status == status.lower())
            if cutoff_ts is not None:
                eligible = eligible and (updated_at > 0 and updated_at < cutoff_ts)

            if not purge_all and not eligible:
                scanned += 1
                continue

            matched.append(task_id)
            if not dry_run:
                try:
                    await delete_task_core(task_id=task_id, redis_client=client)
                    deleted += 1
                except Exception:
                    pass
            scanned += 1

        if cursor == 0:
            break

    return {
        "status": "dry_run" if dry_run else "purged",
        "scanned": scanned,
        "deleted": deleted,
        "matched": matched,
        "dry_run": dry_run,
    }
