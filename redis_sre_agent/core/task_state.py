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

    async def create_task(self, *, thread_id: str, user_id: Optional[str] = None) -> str:
        task_id = str(ULID())
        await self._redis.set(RedisKeys.task_status(task_id), ThreadStatus.QUEUED.value)
        await self._redis.hset(
            RedisKeys.task_metadata(task_id),
            mapping={
                "created_at": datetime.now(timezone.utc).isoformat(),
                "user_id": user_id or "system",
                "thread_id": thread_id,
            },
        )
        # Index task under thread with timestamp
        await self._redis.zadd(
            RedisKeys.thread_tasks_index(thread_id),
            {task_id: datetime.now(timezone.utc).timestamp()},
        )
        return task_id

    async def update_task_status(self, task_id: str, status: ThreadStatus) -> bool:
        return bool(await self._redis.set(RedisKeys.task_status(task_id), status.value))

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

        return bool(
            await self._redis.rpush(
                RedisKeys.task_updates(task_id), json.dumps(update.model_dump())
            )
        )

    async def set_task_result(self, task_id: str, result: Dict[str, Any]) -> bool:
        import json

        await self._redis.set(RedisKeys.task_result(task_id), json.dumps(result))
        await self._redis.hset(
            RedisKeys.task_metadata(task_id), "updated_at", datetime.now(timezone.utc).isoformat()
        )
        return True

    async def set_task_error(self, task_id: str, error_message: str) -> bool:
        await self._redis.set(RedisKeys.task_error(task_id), error_message)
        await self._redis.hset(
            RedisKeys.task_metadata(task_id), "updated_at", datetime.now(timezone.utc).isoformat()
        )
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
