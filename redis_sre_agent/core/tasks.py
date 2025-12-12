"""Task (per-turn) state and manager.

A Task represents a single asynchronous agent turn associated with a Thread.
We persist per-task status, progress updates, and a final result.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field
from redisvl.query import FilterQuery
from redisvl.query.filter import Tag
from ulid import ULID

from redis_sre_agent.core.keys import RedisKeys
from redis_sre_agent.core.redis import get_redis_client, get_tasks_index
from redis_sre_agent.core.threads import ThreadManager


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


class TaskStatus(str, Enum):
    """Task execution status.

    NOTE: Threads no longer track status. This enum remains for task status only.
    """

    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskState(BaseModel):
    task_id: str
    thread_id: str
    status: TaskStatus = TaskStatus.QUEUED
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
        await self._redis.set(RedisKeys.task_status(task_id), TaskStatus.QUEUED.value)
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

    async def update_task_status(self, task_id: str, status: TaskStatus) -> bool:
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
        await self.update_task_status(task_id, TaskStatus.FAILED)
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

        await self.update_task_status(task_id, TaskStatus.FAILED)
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

        md_raw = await self._redis.hgetall(RedisKeys.task_metadata(task_id))
        # Decode byte keys/values from hgetall when decode_responses=False
        md: Dict[str, Any] = {}
        if isinstance(md_raw, dict):
            for k, v in md_raw.items():
                key = k.decode("utf-8") if isinstance(k, bytes) else k
                val = v.decode("utf-8") if isinstance(v, bytes) else v
                md[key] = val

        # thread_id stored in metadata for convenience
        thread_id = md.get("thread_id")

        # Handle error_message - decode if bytes
        error_raw = await self._redis.get(RedisKeys.task_error(task_id))
        error_message = None
        if error_raw:
            error_message = error_raw.decode("utf-8") if isinstance(error_raw, bytes) else error_raw

        return TaskState(
            task_id=task_id,
            thread_id=thread_id or "",
            status=TaskStatus(
                status_val.decode("utf-8") if isinstance(status_val, bytes) else status_val
            ),
            updates=updates,
            result=result,
            error_message=error_message,
            metadata=TaskMetadata(
                created_at=md.get("created_at") or datetime.now(timezone.utc).isoformat(),
                updated_at=md.get("updated_at"),
                user_id=md.get("user_id"),
                subject=md.get("subject"),
            ),
        )


# TODO: Why do we need create_task() here and also in TaskManager?
async def create_task(
    *,
    message: str,
    thread_id: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
    redis_client=None,
) -> Dict[str, Any]:
    """Create a Task and queue processing. If no thread_id, create a new thread."""
    if redis_client is None:
        redis_client = get_redis_client()

    thread_manager = ThreadManager(redis_client=redis_client)

    created_new_thread = False
    if not thread_id:
        # Ensure initial context includes the original query for UI transcript
        base_ctx = dict(context or {})
        base_ctx.setdefault("messages", [])
        base_ctx.setdefault("original_query", message)
        thread_id = await thread_manager.create_thread(initial_context=base_ctx)
        created_new_thread = True
        await thread_manager.update_thread_subject(thread_id, message)

    task_manager = TaskManager(redis_client=redis_client)
    state = await thread_manager.get_thread(thread_id)
    task_id = await task_manager.create_task(
        thread_id=thread_id,
        user_id=(state.metadata.user_id if state else None),
        subject=message,
    )

    await task_manager.update_task_status(task_id, TaskStatus.QUEUED)

    return {
        "task_id": task_id,
        "thread_id": thread_id,
        "status": TaskStatus.QUEUED,
        "message": "Task created and queued for processing"
        if not created_new_thread
        else "Thread created; task queued",
    }


async def get_task_by_id(*, task_id: str, redis_client=None) -> Dict[str, Any]:
    """Return a dict representing a single task by task_id."""
    if redis_client is None:
        redis_client = get_redis_client()

    task_manager = TaskManager(redis_client=redis_client)
    task = await task_manager.get_task_state(task_id)

    if not task:
        raise ValueError(f"Task {task_id} not found")

    updates = [
        {
            "timestamp": u.timestamp,
            "message": u.message,
            "type": u.update_type,
            "metadata": u.metadata or {},
        }
        for u in (task.updates or [])
    ]

    metadata = {
        "created_at": task.metadata.created_at,
        "updated_at": task.metadata.updated_at,
        "user_id": task.metadata.user_id,
        "subject": task.metadata.subject,
    }

    return {
        "task_id": task.task_id,
        "thread_id": task.thread_id,
        "status": task.status,
        "updates": updates,
        "result": task.result,
        "error_message": task.error_message,
        "metadata": metadata,
        "context": {},
    }


async def list_tasks(
    *,
    user_id: Optional[str] = None,
    status_filter: Optional[TaskStatus] = None,  # type: ignore[name-defined]
    show_all: bool = False,
    limit: int = 50,
    redis_client=None,
) -> List[Dict[str, Any]]:
    """List recent tasks with optional filters. Returns TaskStatus-like dicts."""
    if redis_client is None:
        redis_client = get_redis_client()

    thread_manager = ThreadManager(redis_client=redis_client)

    _instance_name_map: Dict[str, str] = {}
    try:
        from redis_sre_agent.core.instances import get_instances

        instances = await get_instances()
        _instance_name_map = {inst.id: inst.name for inst in instances}
    except Exception:
        pass

    try:
        index = await get_tasks_index()

        if show_all:
            expr = Tag("user_id") == user_id if user_id else None
        else:
            if status_filter:
                expr = Tag("status") == status_filter.value
            else:
                expr = (Tag("status") == TaskStatus.IN_PROGRESS.value) | (
                    Tag("status") == TaskStatus.QUEUED.value
                )
            if user_id:
                expr = expr & (Tag("user_id") == user_id)

        fq = FilterQuery(
            return_fields=[
                "id",
                "status",
                "subject",
                "user_id",
                "thread_id",
                "created_at",
                "updated_at",
            ],
            filter_expression=expr,
            num_results=limit,
        ).sort_by("updated_at", asc=False)

        results = await index.query(fq)

        def _iso(ts) -> str | None:
            try:
                tsf = float(ts)
                if tsf > 0:
                    return datetime.fromtimestamp(tsf, tz=timezone.utc).isoformat()
            except Exception:
                return None
            return None

        tasks: List[Dict[str, Any]] = []
        for res in results:
            if isinstance(res, dict):
                row = res
            else:
                row = {}
                for k in [
                    "id",
                    "status",
                    "subject",
                    "user_id",
                    "thread_id",
                    "created_at",
                    "updated_at",
                ]:
                    row[k] = res.__dict__.get(k)
            redis_key = row.get("id", "")
            task_id = (
                redis_key[len("sre_tasks:") :]
                if isinstance(redis_key, str) and redis_key.startswith("sre_tasks:")
                else redis_key
            )

            created_iso = _iso(row.get("created_at"))
            updated_iso = _iso(row.get("updated_at"))

            metadata = {
                "created_at": created_iso,
                "updated_at": updated_iso,
                "user_id": row.get("user_id"),
                "session_id": None,
                "priority": 0,
                "tags": [],
                "subject": row.get("subject") or "Untitled",
            }

            tasks.append(
                {
                    "task_id": task_id,
                    "thread_id": row.get("thread_id"),
                    "status": TaskStatus(row.get("status", TaskStatus.QUEUED.value)),
                    "updates": [],
                    "result": None,
                    "error_message": None,
                    "metadata": metadata,
                    "context": {},
                }
            )

        try:
            from redis_sre_agent.core.keys import RedisKeys

            for t in tasks:
                thid = t.get("thread_id")
                if not thid:
                    continue
                subj = await redis_client.hget(RedisKeys.thread_metadata(thid), "subject")
                if isinstance(subj, bytes):
                    subj = subj.decode()
                if subj:
                    t["metadata"]["thread_subject"] = subj
        except Exception:
            pass

        return tasks
    except Exception:
        statuses: Optional[List[TaskStatus]]
        if show_all:
            statuses = None
        elif status_filter:
            statuses = [status_filter]
        else:
            statuses = [TaskStatus.IN_PROGRESS, TaskStatus.QUEUED]

        fetch_size = max(limit * 10, 200)
        raw_summaries = await thread_manager.list_threads(
            user_id=user_id, status_filter=None, limit=fetch_size, offset=0
        )
        if statuses is None:
            thread_summaries = raw_summaries[:limit]
        else:
            allowed = {s.value for s in statuses}
            thread_summaries = [s for s in raw_summaries if s.get("status") in allowed][:limit]

        tasks: List[Dict[str, Any]] = []
        for summary in thread_summaries:
            metadata = {
                "created_at": summary.get("created_at"),
                "updated_at": summary.get("updated_at"),
                "user_id": summary.get("user_id"),
                "session_id": None,
                "priority": summary.get("priority", 0),
                "tags": summary.get("tags", []),
                "subject": summary.get("subject", "Untitled"),
                "thread_subject": summary.get("subject", "Untitled"),
            }
            tasks.append(
                {
                    "task_id": None,
                    "thread_id": summary["thread_id"],
                    "status": TaskStatus(summary["status"]),
                    "updates": [],
                    "result": None,
                    "error_message": None,
                    "metadata": metadata,
                    "context": {},
                }
            )

        return tasks


async def delete_task(*, task_id: str, redis_client=None) -> dict[str, Any]:
    """Permanently delete a single task and its related keys.

    Removes:
    - KV: status, updates, result, error, metadata
    - ZSET membership in sre:thread:{thread_id}:tasks
    - FT hash at sre_tasks:{task_id}
    """
    if redis_client is None:
        from redis_sre_agent.core.redis import get_redis_client as _get

        redis_client = _get()

    from redis_sre_agent.core.redis import SRE_TASKS_INDEX

    # Resolve thread_id from metadata
    md = await redis_client.hgetall(RedisKeys.task_metadata(task_id))
    thread_id = None
    if isinstance(md, dict):
        for k, v in md.items():
            k2 = k.decode() if isinstance(k, bytes) else k
            if k2 == "thread_id":
                thread_id = (v.decode() if isinstance(v, bytes) else v) or None
                break

    # Delete per-task keys
    await redis_client.delete(RedisKeys.task_status(task_id))
    await redis_client.delete(RedisKeys.task_updates(task_id))
    await redis_client.delete(RedisKeys.task_result(task_id))
    await redis_client.delete(RedisKeys.task_error(task_id))
    await redis_client.delete(RedisKeys.task_metadata(task_id))

    # Remove from thread’s task index
    if thread_id:
        await redis_client.zrem(RedisKeys.thread_tasks_index(thread_id), task_id)

    # Delete FT hash
    await redis_client.delete(f"{SRE_TASKS_INDEX}:{task_id}")

    return {"deleted": True}
