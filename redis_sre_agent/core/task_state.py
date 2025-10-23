"""Task (per-turn) state and manager.

A Task represents a single asynchronous agent turn associated with a Thread.
We persist per-task status, progress updates, and a final result.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field
from ulid import ULID

from redis_sre_agent.core.keys import RedisKeys
from redis_sre_agent.core.redis import get_redis_client
from redis_sre_agent.core.thread_state import ThreadStatus


class TaskMetadata(BaseModel):
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: Optional[str] = None
    user_id: Optional[str] = None
    subject: Optional[str] = None


class TaskUpdate(BaseModel):
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    message: str
    update_type: str = "progress"
    metadata: Optional[Dict[str, Any]] = None


class TaskState(BaseModel):
    task_id: str
    thread_id: str
    status: ThreadStatus = ThreadStatus.QUEUED
    updates: List[TaskUpdate] = Field(default_factory=list)
    result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    metadata: TaskMetadata = Field(default_factory=TaskMetadata)


class TaskManager:
    def __init__(self, redis_client=None):
        self._redis = redis_client or get_redis_client()

    async def create_task(
        self, *, thread_id: str, user_id: Optional[str] = None, subject: Optional[str] = None
    ) -> str:
        task_id = str(ULID())
        now_iso = datetime.now(timezone.utc).isoformat()
        await self._redis.set(RedisKeys.task_status(task_id), ThreadStatus.QUEUED.value)
        await self._redis.hset(
            RedisKeys.task_metadata(task_id),
            mapping={
                "created_at": now_iso,
                "user_id": user_id or "system",
                "thread_id": thread_id,
                "subject": subject or "",
            },
        )
        # Index task under thread with timestamp
        await self._redis.zadd(
            RedisKeys.thread_tasks_index(thread_id),
            {task_id: datetime.now(timezone.utc).timestamp()},
        )
        # Upsert search doc
        await self._upsert_task_search_doc(task_id)
        return task_id

    async def update_task_status(self, task_id: str, status: ThreadStatus) -> bool:
        ok = await self._redis.set(RedisKeys.task_status(task_id), status.value)
        await self._redis.hset(
            RedisKeys.task_metadata(task_id), "updated_at", datetime.now(timezone.utc).isoformat()
        )
        await self._upsert_task_search_doc(task_id)
        return bool(ok)

    async def add_task_update(
        self,
        task_id: str,
        message: str,
        update_type: str = "progress",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        update = TaskUpdate(message=message, update_type=update_type, metadata=metadata)
        # Using RPUSH of JSON strings would be ideal, but elsewhere updates are stored as JSON strings or hashes.
        # For simplicity, store as a JSON-serializable dict
        import json

        ok = await self._redis.rpush(
            RedisKeys.task_updates(task_id), json.dumps(update.model_dump())
        )
        await self._redis.hset(
            RedisKeys.task_metadata(task_id), "updated_at", datetime.now(timezone.utc).isoformat()
        )
        await self._upsert_task_search_doc(task_id)
        return bool(ok)

    async def set_task_result(self, task_id: str, result: Dict[str, Any]) -> bool:
        import json

        await self._redis.set(RedisKeys.task_result(task_id), json.dumps(result))
        await self._redis.hset(
            RedisKeys.task_metadata(task_id), "updated_at", datetime.now(timezone.utc).isoformat()
        )
        await self._upsert_task_search_doc(task_id)
        return True

    async def set_task_error(self, task_id: str, error_message: str) -> bool:
        await self._redis.set(RedisKeys.task_error(task_id), error_message)
        await self._redis.hset(
            RedisKeys.task_metadata(task_id), "updated_at", datetime.now(timezone.utc).isoformat()
        )
        await self.update_task_status(task_id, ThreadStatus.FAILED)
        await self._upsert_task_search_doc(task_id)
        return True

    async def _upsert_task_search_doc(self, task_id: str) -> bool:
        """Upsert a simplified task document into the tasks FT index (hash)."""
        try:
            from redis_sre_agent.core.redis import SRE_TASKS_INDEX, get_tasks_index

            # Ensure index exists (best-effort)
            try:
                index = await get_tasks_index()
                if not await index.exists():
                    await index.create()
            except Exception:
                pass

            status = await self._redis.get(RedisKeys.task_status(task_id))
            md_raw = await self._redis.hgetall(RedisKeys.task_metadata(task_id))

            def _decode(v):
                return v.decode() if isinstance(v, bytes) else v

            safe_md_raw = md_raw if isinstance(md_raw, dict) else {}
            md = {_decode(k): _decode(v) for k, v in safe_md_raw.items()}

            status_s = _decode(status) if status else ""
            subject = md.get("subject", "")
            user_id = md.get("user_id", "")
            thread_id = md.get("thread_id", "")
            created_at = md.get("created_at")
            updated_at = md.get("updated_at")

            from datetime import datetime, timezone

            def _to_ts(val: str | None) -> float:
                if not val:
                    return 0.0
                try:
                    dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
                    return dt.timestamp()
                except Exception:
                    try:
                        return float(val)
                    except Exception:
                        return 0.0

            created_ts = _to_ts(created_at)
            updated_ts = _to_ts(updated_at)
            if updated_ts <= 0:
                updated_ts = datetime.now(timezone.utc).timestamp()

            key = f"{SRE_TASKS_INDEX}:{task_id}"
            await self._redis.hset(
                key,
                mapping={
                    "status": status_s,
                    "subject": subject or "",
                    "user_id": user_id or "",
                    "thread_id": thread_id or "",
                    "created_at": created_ts,
                    "updated_at": updated_ts,
                },
            )
            await self._redis.expire(key, 86400)
            return True
        except Exception:
            return False

        await self.update_task_status(task_id, ThreadStatus.FAILED)
        return True

    async def get_task_state(self, task_id: str) -> Optional[TaskState]:
        status_val = await self._redis.get(RedisKeys.task_status(task_id))
        if not status_val:
            return None

        import json

        updates_raw = await self._redis.lrange(RedisKeys.task_updates(task_id), 0, -1)
        updates: List[TaskUpdate] = []
        for u in updates_raw:
            try:
                if isinstance(u, bytes):
                    u = u.decode("utf-8")
                updates.append(TaskUpdate(**json.loads(u)))
            except Exception:
                continue

        result_raw = await self._redis.get(RedisKeys.task_result(task_id))
        result = None
        if result_raw:
            if isinstance(result_raw, bytes):
                result_raw = result_raw.decode("utf-8")
            try:
                result = json.loads(result_raw)
            except Exception:
                result = None

        md = await self._redis.hgetall(RedisKeys.task_metadata(task_id))
        # thread_id stored in metadata for convenience
        thread_id = md.get("thread_id") if isinstance(md, dict) else None
        if isinstance(thread_id, bytes):
            thread_id = thread_id.decode("utf-8")

        return TaskState(
            task_id=task_id,
            thread_id=thread_id or "",
            status=ThreadStatus(
                status_val.decode("utf-8") if isinstance(status_val, bytes) else status_val
            ),
            updates=updates,
            result=result,
            error_message=(await self._redis.get(RedisKeys.task_error(task_id))) or None,
            metadata=TaskMetadata(
                created_at=(md.get("created_at") if isinstance(md, dict) else None)
                or datetime.now(timezone.utc).isoformat(),
                updated_at=(md.get("updated_at") if isinstance(md, dict) else None),
                user_id=(md.get("user_id") if isinstance(md, dict) else None),
                subject=(md.get("subject") if isinstance(md, dict) else None),
            ),
        )
