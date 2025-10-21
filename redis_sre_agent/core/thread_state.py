"""Thread state management for SRE Agent conversations."""

import json
import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from openai import AsyncOpenAI
from pydantic import BaseModel, Field
from redis.asyncio import Redis
from ulid import ULID

from redis_sre_agent.core.config import settings
from redis_sre_agent.core.keys import RedisKeys
from redis_sre_agent.core.redis import get_redis_client

logger = logging.getLogger(__name__)


class ThreadStatus(str, Enum):
    """Thread execution status."""

    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ThreadUpdate(BaseModel):
    """Individual progress update within a thread."""

    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    message: str
    update_type: str = "progress"  # progress, tool_call, error, etc.
    metadata: Optional[Dict[str, Any]] = None


class ThreadMetadata(BaseModel):
    """Thread metadata and configuration."""

    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    priority: int = 0
    tags: List[str] = Field(default_factory=list)
    subject: Optional[str] = None  # Generated subject for the thread


class ThreadActionItem(BaseModel):
    """Individual action item or recommendation."""

    id: str = Field(default_factory=lambda: str(ULID()))
    title: str
    description: str
    priority: str = "medium"  # low, medium, high, critical
    category: str = "general"  # maintenance, investigation, escalation, etc.
    completed: bool = False
    due_date: Optional[str] = None


class ThreadState(BaseModel):
    """Complete thread state representation."""

    thread_id: str
    status: ThreadStatus = ThreadStatus.QUEUED
    updates: List[ThreadUpdate] = Field(default_factory=list)
    context: Dict[str, Any] = Field(default_factory=dict)
    action_items: List[ThreadActionItem] = Field(default_factory=list)
    metadata: ThreadMetadata = Field(default_factory=ThreadMetadata)
    result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None


class ThreadManager:
    """Manages thread state in Redis."""

    def __init__(self, redis_url: Optional[str] = None, redis_client: Optional[Redis] = None):
        self._redis_url = redis_url
        self._redis_client = redis_client

    async def _get_client(self) -> Redis:
        """Get Redis client (lazy initialization)."""
        if self._redis_client is None:
            self._redis_client = get_redis_client(self._redis_url)
        return self._redis_client

    def _get_thread_keys(self, thread_id: str) -> Dict[str, str]:
        """Get all Redis keys for a thread."""
        return RedisKeys.all_thread_keys(thread_id)

    async def _generate_thread_subject(self, original_message: str) -> str:
        """Generate a concise subject for the thread based on the original message."""
        try:
            # Use a small, fast model for subject generation
            client = AsyncOpenAI(api_key=settings.openai_api_key)

            prompt = f"""Generate a concise, descriptive subject line (max 50 characters) for this SRE support request:

"{original_message[:200]}..."

The subject should:
- Be specific and actionable
- Include key technical terms
- Be suitable for a support ticket list
- Start with the main system/service if mentioned

Examples:
- "Redis memory usage at 95%"
- "Connection pool exhausted"
- "Slow query performance issue"
- "Cluster failover investigation"

Subject:"""

            response = await client.chat.completions.create(
                model="gpt-4o-mini",  # Fast, cost-effective model
                messages=[{"role": "user", "content": prompt}],
                max_tokens=20,
            )

            subject = response.choices[0].message.content.strip()
            # Remove quotes if present and truncate to 50 chars
            subject = subject.strip('"').strip("'")[:50]

            logger.debug(f"Generated subject: {subject}")
            return subject

        except Exception as e:
            logger.warning(f"Failed to generate thread subject: {e}")
            # Fallback to truncated original message
            return original_message[:50].strip() + ("..." if len(original_message) > 50 else "")

    async def create_thread(
        self,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        initial_context: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
    ) -> str:
        """Create a new thread and return thread_id."""
        thread_id = str(ULID())

        # Initialize thread state
        metadata = ThreadMetadata(user_id=user_id, session_id=session_id, tags=tags or [])

        thread_state = ThreadState(
            thread_id=thread_id, context=initial_context or {}, metadata=metadata
        )

        await self._save_thread_state(thread_state)

        # Add to thread index for listing
        await self._add_to_thread_index(thread_id, user_id)
        # Best-effort: upsert search doc for ordering/filtering
        await self._upsert_thread_search_doc(thread_id)

        logger.info(f"Created thread {thread_id} for user {user_id}")
        return thread_id

    async def update_thread_subject(self, thread_id: str, original_message: str) -> bool:
        """Generate and update the thread subject based on the original message."""
        try:
            # Generate subject
            subject = await self._generate_thread_subject(original_message)

            # Update metadata
            client = await self._get_client()
            keys = self._get_thread_keys(thread_id)

            await client.hset(keys["metadata"], "subject", subject)
            await client.hset(
                keys["metadata"], "updated_at", datetime.now(timezone.utc).isoformat()
            )

            # Update search index
            await self._upsert_thread_search_doc(thread_id)

            logger.info(f"Updated thread {thread_id} subject: {subject}")
            return True

        except Exception as e:
            logger.error(f"Failed to update thread {thread_id} subject: {e}")
            return False

    async def _add_to_thread_index(self, thread_id: str, user_id: Optional[str] = None) -> bool:
        """Add thread to index for listing purposes."""
        try:
            client = await self._get_client()
            timestamp = datetime.now(timezone.utc).timestamp()

            # Add to global thread index (sorted by creation time)
            await client.zadd(RedisKeys.threads_index(), {thread_id: timestamp})

            # Add to user-specific index if user_id provided
            if user_id:
                await client.zadd(RedisKeys.threads_user_index(user_id), {thread_id: timestamp})

            # Set TTL for indices (30 days)
            await client.expire(RedisKeys.threads_index(), 2592000)
            if user_id:
                await client.expire(RedisKeys.threads_user_index(user_id), 2592000)

            return True
        except Exception as e:
            logger.error(f"Failed to add thread {thread_id} to index: {e}")
            return False

    async def _upsert_thread_search_doc(self, thread_id: str) -> bool:
        """Upsert a simplified thread document into the RedisVL threads index (hash).

        Best-effort; failures are logged and ignored.
        """
        try:
            from redis_sre_agent.core.redis import SRE_THREADS_INDEX, get_threads_index

            client = await self._get_client()
            # Ensure index exists
            try:
                index = await get_threads_index()
                if not await index.exists():
                    await index.create()
            except Exception:
                # Index creation is best-effort; proceed to write hash anyway
                pass

            keys = self._get_thread_keys(thread_id)

            status_b = await client.get(keys["status"]) or b""
            status = status_b.decode() if isinstance(status_b, bytes) else str(status_b)

            metadata_h = await client.hgetall(keys["metadata"]) or {}
            context_h = await client.hgetall(keys["context"]) or {}

            def _decode(dct):
                out = {}
                for k, v in dct.items():
                    k2 = k.decode() if isinstance(k, bytes) else k
                    v2 = v.decode() if isinstance(v, bytes) else v
                    out[k2] = v2
                return out

            metadata = _decode(metadata_h)
            context = _decode(context_h)

            subject = metadata.get("subject", "")
            user_id = metadata.get("user_id", "")
            instance_id = context.get("instance_id", "")
            try:
                priority = int(metadata.get("priority", 0))
            except Exception:
                priority = 0

            from datetime import datetime, timezone

            def _to_ts(val: str | None) -> float:
                if not val:
                    return 0.0
                try:
                    # ISO8601 string
                    dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
                    return dt.timestamp()
                except Exception:
                    try:
                        return float(val)
                    except Exception:
                        return 0.0

            created_ts = _to_ts(metadata.get("created_at"))
            updated_ts = _to_ts(metadata.get("updated_at"))
            if updated_ts <= 0:
                updated_ts = datetime.now(timezone.utc).timestamp()

            # Write to hash backing the index
            key = f"{SRE_THREADS_INDEX}:{thread_id}"
            mapping = {
                "status": status or "",
                "subject": subject or "",
                "user_id": user_id or "",
                "instance_id": instance_id or "",
                "priority": priority,
                "created_at": created_ts,
                "updated_at": updated_ts,
            }
            await client.hset(key, mapping=mapping)
            # TTL aligns with thread data TTL (24h)
            await client.expire(key, 86400)
            return True
        except Exception as e:
            logger.debug(f"Thread index upsert failed for {thread_id}: {e}")
            return False

    async def _remove_from_thread_index(
        self, thread_id: str, user_id: Optional[str] = None
    ) -> bool:
        """Remove thread from index."""
        try:
            client = await self._get_client()

            # Remove from global index
            await client.zrem(RedisKeys.threads_index(), thread_id)

            # Remove from user index if user_id provided
            if user_id:
                await client.zrem(RedisKeys.threads_user_index(user_id), thread_id)

            return True

        except Exception as e:
            logger.error(f"Failed to remove thread {thread_id} from index: {e}")
            return False

    async def list_threads(
        self,
        user_id: Optional[str] = None,
        status_filter: Optional[ThreadStatus] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """List threads with optional filtering."""
        try:
            # Prefer RedisVL FT.SEARCH via threads index; fallback to ZSET scan
            from datetime import datetime, timezone

            from redisvl.query import FilterQuery
            from redisvl.query.filter import Tag

            from redis_sre_agent.core.redis import get_threads_index

            index = await get_threads_index()

            # Build filter: default to in_progress OR queued if no explicit status and not show_all
            expr = None
            if status_filter:
                expr = Tag("status") == status_filter.value
            else:
                expr = (Tag("status") == ThreadStatus.IN_PROGRESS.value) | (
                    Tag("status") == ThreadStatus.QUEUED.value
                )
            if user_id:
                expr = (
                    expr & (Tag("user_id") == user_id)
                    if expr is not None
                    else (Tag("user_id") == user_id)
                )

            # Use offset if supported; otherwise overfetch and slice
            try:
                fq = FilterQuery(
                    return_fields=[
                        "id",
                        "status",
                        "subject",
                        "user_id",
                        "instance_id",
                        "priority",
                        "created_at",
                        "updated_at",
                    ],
                    filter_expression=expr,
                    num_results=limit,
                    offset=offset,
                ).sort_by("updated_at", asc=False)
            except TypeError:
                # Older RedisVL without offset param
                fq = FilterQuery(
                    return_fields=[
                        "id",
                        "status",
                        "subject",
                        "user_id",
                        "instance_id",
                        "priority",
                        "created_at",
                        "updated_at",
                    ],
                    filter_expression=expr,
                    num_results=limit + offset,
                ).sort_by("updated_at", asc=False)

            results = await index.query(fq)
            if offset and len(results) > offset:
                results = results[offset:]

            def _iso(ts) -> str | None:
                try:
                    tsf = float(ts)
                    if tsf > 0:
                        return datetime.fromtimestamp(tsf, tz=timezone.utc).isoformat()
                except Exception:
                    return None
                return None

            threads: List[Dict[str, Any]] = []
            for res in results:
                row = (
                    res
                    if isinstance(res, dict)
                    else {
                        k: getattr(res, k, None)
                        for k in [
                            "id",
                            "status",
                            "subject",
                            "user_id",
                            "instance_id",
                            "priority",
                            "created_at",
                            "updated_at",
                        ]
                    }
                )
                redis_key = row.get("id", "")
                thread_id = (
                    redis_key[len("sre_threads:") :]
                    if isinstance(redis_key, str) and redis_key.startswith("sre_threads:")
                    else redis_key
                )

                created_iso = _iso(row.get("created_at"))
                updated_iso = _iso(row.get("updated_at"))

                # Build summary
                summary = {
                    "thread_id": thread_id,
                    "status": row.get("status") or ThreadStatus.QUEUED.value,
                    "subject": row.get("subject") or "Untitled",
                    "created_at": created_iso,
                    "updated_at": updated_iso,
                    "user_id": row.get("user_id") or None,
                    "latest_message": "No updates",
                    "tags": [],
                    "priority": int(row.get("priority") or 0),
                    "instance_id": row.get("instance_id") or None,
                }
                threads.append(summary)

            return threads

        except Exception:
            # Fallback: ZSET-based listing (existing logic)
            try:
                client = await self._get_client()
                index_key = (
                    RedisKeys.threads_user_index(user_id) if user_id else RedisKeys.threads_index()
                )
                threads: list[dict] = []
                page = max(50, limit * 5)
                start = offset
                while len(threads) < limit:
                    thread_ids = await client.zrevrange(
                        index_key, start, start + page - 1, withscores=False
                    )
                    if not thread_ids:
                        break
                    for raw_id in thread_ids:
                        if len(threads) >= limit:
                            break
                        thread_id = raw_id.decode() if isinstance(raw_id, bytes) else raw_id
                        try:
                            keys = self._get_thread_keys(thread_id)
                            status_data = await client.get(keys["status"])
                            if not status_data:
                                continue
                            status = status_data.decode()
                            if status_filter and status != status_filter.value:
                                continue
                            metadata_data = await client.hgetall(keys["metadata"])
                            context_data = await client.hgetall(keys["context"])
                            latest_update = await client.lrange(keys["updates"], 0, 0)
                            metadata = {}
                            if metadata_data:
                                metadata = {
                                    k.decode(): v.decode() for k, v in metadata_data.items()
                                }
                                if "tags" in metadata:
                                    try:
                                        metadata["tags"] = json.loads(metadata["tags"])
                                    except json.JSONDecodeError:
                                        metadata["tags"] = []
                            context = {}
                            if context_data:
                                context = {k.decode(): v.decode() for k, v in context_data.items()}
                            latest_message = "No updates"
                            if latest_update:
                                try:
                                    update_data = json.loads(latest_update[0])
                                    latest_message = update_data.get("message", "No updates")
                                except json.JSONDecodeError:
                                    pass
                            thread_summary = {
                                "thread_id": thread_id,
                                "status": status,
                                "subject": metadata.get("subject", "Untitled"),
                                "created_at": metadata.get("created_at"),
                                "updated_at": metadata.get("updated_at"),
                                "user_id": metadata.get("user_id"),
                                "latest_message": latest_message[:100],
                                "tags": metadata.get("tags", []),
                                "priority": int(metadata.get("priority", 0)),
                                "instance_id": context.get("instance_id"),
                            }
                            threads.append(thread_summary)
                        except Exception as e:
                            logger.warning(f"Failed to get summary for thread {thread_id}: {e}")
                            continue
                    start += page
                return threads
            except Exception as e:
                logger.error(f"Failed to list threads (fallback): {e}")
                return []

    async def get_thread_state(self, thread_id: str) -> Optional[ThreadState]:
        """Retrieve complete thread state."""
        try:
            client = await self._get_client()
            keys = self._get_thread_keys(thread_id)

            # Check if thread exists
            if not await client.exists(keys["status"]):
                return None

            # Load all thread data
            status = await client.get(keys["status"])
            updates_data = await client.lrange(keys["updates"], 0, -1)
            context_data = await client.hgetall(keys["context"])
            action_items_data = await client.get(keys["action_items"])
            metadata_data = await client.hgetall(keys["metadata"])
            result_data = await client.get(keys["result"])
            error_data = await client.get(keys["error"])

            # Parse updates
            updates = []
            for update_json in updates_data:
                try:
                    update_dict = json.loads(update_json)
                    updates.append(ThreadUpdate(**update_dict))
                except (json.JSONDecodeError, Exception) as e:
                    logger.warning(f"Failed to parse update: {e}")

            # Parse action items
            action_items = []
            if action_items_data:
                try:
                    action_items_list = json.loads(action_items_data)
                    action_items = [ThreadActionItem(**item) for item in action_items_list]
                except (json.JSONDecodeError, Exception) as e:
                    logger.warning(f"Failed to parse action items: {e}")

            # Parse metadata
            metadata = ThreadMetadata()
            if metadata_data:
                try:
                    # Convert Redis hash to metadata
                    metadata_dict = {k.decode(): v.decode() for k, v in metadata_data.items()}
                    if "tags" in metadata_dict:
                        metadata_dict["tags"] = json.loads(metadata_dict["tags"])
                    metadata = ThreadMetadata(**metadata_dict)
                except Exception as e:
                    logger.warning(f"Failed to parse metadata: {e}")

            # Parse context
            context = {}
            if context_data:
                try:
                    # Convert Redis hash to context dict and attempt to parse JSON values
                    for k, v in context_data.items():
                        key = k.decode() if isinstance(k, bytes) else k
                        value = v.decode() if isinstance(v, bytes) else v

                        # Try to parse as JSON first (for complex objects like lists)
                        try:
                            context[key] = json.loads(value)
                        except (json.JSONDecodeError, ValueError):
                            # If not JSON, keep as string
                            context[key] = value
                except Exception as e:
                    logger.warning(f"Failed to parse context: {e}")
                    # Fallback: just decode bytes to strings
                    context = {k.decode(): v.decode() for k, v in context_data.items()}

            # Parse result and error
            result = None
            if result_data:
                try:
                    result = json.loads(result_data)
                except json.JSONDecodeError:
                    result = {"raw": result_data.decode()}

            error_message = error_data.decode() if error_data else None

            return ThreadState(
                thread_id=thread_id,
                status=ThreadStatus(status.decode()),
                updates=updates,
                context=context,
                action_items=action_items,
                metadata=metadata,
                result=result,
                error_message=error_message,
            )

        except Exception as e:
            logger.error(f"Failed to get thread state {thread_id}: {e}")
            return None

    async def update_thread_status(self, thread_id: str, status: ThreadStatus) -> bool:
        """Update thread status."""
        try:
            client = await self._get_client()
            keys = self._get_thread_keys(thread_id)

            await client.set(keys["status"], status.value)

            # Update metadata timestamp
            await client.hset(
                keys["metadata"], "updated_at", datetime.now(timezone.utc).isoformat()
            )

            # Publish status update to stream
            await self._publish_stream_update(
                thread_id,
                "status_change",
                {"status": status.value, "message": f"Status changed to {status.value}"},
            )

            # Update search index
            await self._upsert_thread_search_doc(thread_id)

            logger.info(f"Updated thread {thread_id} status to {status.value}")
            return True

        except Exception as e:
            logger.error(f"Failed to update thread {thread_id} status: {e}")
            return False

    async def add_thread_update(
        self,
        thread_id: str,
        message: str,
        update_type: str = "progress",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Add a progress update to the thread."""
        try:
            client = await self._get_client()
            keys = self._get_thread_keys(thread_id)

            update = ThreadUpdate(message=message, update_type=update_type, metadata=metadata)

            # Add to updates list
            update_json = update.model_dump_json()
            await client.lpush(keys["updates"], update_json)

            # Keep only last 100 updates
            await client.ltrim(keys["updates"], 0, 99)

            # Update metadata timestamp
            await client.hset(
                keys["metadata"], "updated_at", datetime.now(timezone.utc).isoformat()
            )

            # Publish update to stream
            await self._publish_stream_update(
                thread_id,
                "thread_update",
                {
                    "message": message,
                    "update_type": update_type,
                    "metadata": metadata or {},
                    "timestamp": update.timestamp,
                },
            )

            # Update search index
            await self._upsert_thread_search_doc(thread_id)

            logger.debug(f"Added update to thread {thread_id}: {message}")
            return True

        except Exception as e:
            logger.error(f"Failed to add update to thread {thread_id}: {e}")
            return False

    async def set_thread_result(self, thread_id: str, result: Dict[str, Any]) -> bool:
        """Set the final result for a thread."""
        try:
            client = await self._get_client()
            keys = self._get_thread_keys(thread_id)

            result_json = json.dumps(result)
            await client.set(keys["result"], result_json)

            # Update metadata timestamp
            await client.hset(
                keys["metadata"], "updated_at", datetime.now(timezone.utc).isoformat()
            )

            # Publish result to stream
            await self._publish_stream_update(
                thread_id, "result_set", {"result": result, "message": "Task result available"}
            )

            # Update search index
            await self._upsert_thread_search_doc(thread_id)

            logger.info(f"Set result for thread {thread_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to set result for thread {thread_id}: {e}")
            return False

    async def _publish_stream_update(
        self, thread_id: str, update_type: str, data: Dict[str, Any]
    ) -> bool:
        """Publish an update to the Redis Stream for real-time WebSocket updates."""
        try:
            # Import here to avoid circular imports
            from redis_sre_agent.api.websockets import get_stream_manager

            stream_manager = await get_stream_manager()
            return await stream_manager.publish_task_update(thread_id, update_type, data)

        except Exception as e:
            logger.error(f"Failed to publish stream update for {thread_id}: {e}")
            return False

    async def add_action_items(self, thread_id: str, action_items: List[ThreadActionItem]) -> bool:
        """Add action items to the thread."""
        try:
            client = await self._get_client()
            keys = self._get_thread_keys(thread_id)

            # Get existing action items
            existing_data = await client.get(keys["action_items"])
            existing_items = []
            if existing_data:
                try:
                    existing_list = json.loads(existing_data)
                    existing_items = [ThreadActionItem(**item) for item in existing_list]
                except Exception:
                    pass

            # Combine with new items
            all_items = existing_items + action_items
            items_json = json.dumps([item.model_dump() for item in all_items])

            await client.set(keys["action_items"], items_json)

            # Update metadata timestamp
            await client.hset(
                keys["metadata"], "updated_at", datetime.now(timezone.utc).isoformat()
            )

            # Update search index
            await self._upsert_thread_search_doc(thread_id)

            logger.info(f"Added {len(action_items)} action items to thread {thread_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to add action items to thread {thread_id}: {e}")
            return False

    async def set_thread_error(self, thread_id: str, error_message: str) -> bool:
        """Set error message and mark thread as failed."""
        try:
            client = await self._get_client()
            keys = self._get_thread_keys(thread_id)

            await client.set(keys["error"], error_message)
            await self.update_thread_status(thread_id, ThreadStatus.FAILED)

            logger.error(f"Set error for thread {thread_id}: {error_message}")
            return True

        except Exception as e:
            logger.error(f"Failed to set error for thread {thread_id}: {e}")
            return False

    async def update_thread_context(
        self, thread_id: str, context_updates: Dict[str, Any], merge: bool = True
    ) -> bool:
        """Update thread context with new values.

        Args:
            thread_id: Thread identifier
            context_updates: Dictionary of context key-value pairs to update
            merge: If True, merge with existing context. If False, replace entirely.

        Returns:
            True if successful, False otherwise
        """
        try:
            client = await self._get_client()
            keys = self._get_thread_keys(thread_id)

            if merge:
                # Get existing context and merge
                existing_context = await client.hgetall(keys["context"])
                merged_context = {}

                # Decode existing context
                for k, v in existing_context.items():
                    key = k.decode() if isinstance(k, bytes) else k
                    value = v.decode() if isinstance(v, bytes) else v
                    merged_context[key] = value

                # Apply updates
                for k, v in context_updates.items():
                    if v is None:
                        merged_context[k] = ""
                    elif isinstance(v, (dict, list)):
                        merged_context[k] = json.dumps(v)
                    else:
                        merged_context[k] = str(v)

                context_to_save = merged_context
            else:
                # Replace entirely
                context_to_save = {}
                for k, v in context_updates.items():
                    if v is None:
                        context_to_save[k] = ""
                    elif isinstance(v, (dict, list)):
                        context_to_save[k] = json.dumps(v)
                    else:
                        context_to_save[k] = str(v)

            # Save updated context
            if context_to_save:
                # Clear existing context if not merging
                if not merge:
                    await client.delete(keys["context"])
                await client.hset(keys["context"], mapping=context_to_save)

            # Update metadata timestamp
            await client.hset(
                keys["metadata"], "updated_at", datetime.now(timezone.utc).isoformat()
            )

            logger.info(f"Updated context for thread {thread_id}: {list(context_updates.keys())}")
            return True

        except Exception as e:
            logger.error(f"Failed to update context for thread {thread_id}: {e}")
            return False

    async def append_messages(self, thread_id: str, messages: List[Dict[str, Any]]) -> bool:
        """Append messages to a thread's message list in context.

        This treats context["messages"] as a JSON-serializable list of {role, content, ...} dicts.
        """
        try:
            # Load existing messages from thread state
            state = await self.get_thread_state(thread_id)
            existing = []
            if state and isinstance(state.context.get("messages"), list):
                existing = state.context.get("messages")

            # Append new messages, minimal validation
            for m in messages or []:
                if not isinstance(m, dict):
                    continue
                role = m.get("role")
                content = m.get("content")
                if not content:
                    continue
                if role not in ("user", "assistant", "system", None):
                    role = "user"
                existing.append(
                    {k: v for k, v in m.items() if k in ("role", "content", "metadata") or True}
                )

            # Save back to context
            return await self.update_thread_context(thread_id, {"messages": existing}, merge=True)
        except Exception as e:
            logger.error(f"Failed to append messages for thread {thread_id}: {e}")
            return False

    async def _save_thread_state(self, thread_state: ThreadState) -> bool:
        """Save complete thread state to Redis."""
        try:
            client = await self._get_client()
            keys = self._get_thread_keys(thread_state.thread_id)

            async with client.pipeline(transaction=True) as pipe:
                # Set basic fields
                pipe.set(keys["status"], thread_state.status.value)

                # Set context as hash
                if thread_state.context:
                    # Filter out None values and serialize complex objects as JSON
                    clean_context = {}
                    for k, v in thread_state.context.items():
                        if v is None:
                            clean_context[k] = ""
                        elif isinstance(v, (dict, list)):
                            # Serialize complex objects as JSON
                            clean_context[k] = json.dumps(v)
                        else:
                            # Keep simple types as strings
                            clean_context[k] = str(v)

                    if clean_context:
                        pipe.hset(keys["context"], mapping=clean_context)

                # Set metadata as hash
                metadata_dict = thread_state.metadata.model_dump()
                metadata_dict["tags"] = json.dumps(metadata_dict["tags"])
                # Ensure all metadata values are strings and not None
                clean_metadata = {
                    k: str(v) if v is not None else "" for k, v in metadata_dict.items()
                }
                pipe.hset(keys["metadata"], mapping=clean_metadata)

                # Set action items as JSON
                if thread_state.action_items:
                    items_json = json.dumps(
                        [item.model_dump() for item in thread_state.action_items]
                    )
                    pipe.set(keys["action_items"], items_json)

                # Set result if exists
                if thread_state.result:
                    pipe.set(keys["result"], json.dumps(thread_state.result))

                # Set error if exists
                if thread_state.error_message:
                    pipe.set(keys["error"], thread_state.error_message)

                # Add updates
                for update in thread_state.updates:
                    pipe.lpush(keys["updates"], update.model_dump_json())

                # Set TTL (24 hours for thread data)
                for key in keys.values():
                    pipe.expire(key, 86400)

                # Execute pipeline
                await pipe.execute()

            logger.info(f"Saved thread state for {thread_state.thread_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to save thread state {thread_state.thread_id}: {e}")
            return False

    async def delete_thread(self, thread_id: str) -> bool:
        """Delete all thread data."""
        try:
            client = await self._get_client()
            keys = self._get_thread_keys(thread_id)

            # Get user_id before deletion for index cleanup
            metadata_data = await client.hgetall(keys["metadata"])
            user_id = None
            if metadata_data:
                metadata = {k.decode(): v.decode() for k, v in metadata_data.items()}
                user_id = metadata.get("user_id")

            # Delete thread data
            await client.delete(*keys.values())

            # Remove from indices
            await self._remove_from_thread_index(thread_id, user_id)

            logger.info(f"Deleted thread {thread_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete thread {thread_id}: {e}")
            return False
