"""Thread state management for SRE Agent conversations."""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from openai import AsyncOpenAI
from pydantic import BaseModel, Field
from redis.asyncio import Redis
from redisvl.query import FilterQuery
from redisvl.query.filter import Tag
from ulid import ULID

from redis_sre_agent.core.config import settings
from redis_sre_agent.core.keys import RedisKeys
from redis_sre_agent.core.redis import SRE_THREADS_INDEX, get_redis_client, get_threads_index

logger = logging.getLogger(__name__)


class ThreadUpdate(BaseModel):
    """Individual progress update within a thread.

    DEPRECATED: Progress updates should be stored on TaskState, not Thread.
    This class is kept for backward compatibility when reading old data.
    """

    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    message: str
    update_type: str = "progress"  # progress, tool_call, error, etc.
    metadata: Optional[Dict[str, Any]] = None


class Message(BaseModel):
    """A single message in a thread conversation."""

    role: str = Field(default="user", description="Message role: user|assistant|system")
    content: str
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


class Thread(BaseModel):
    """Complete thread state representation.

    A Thread represents a conversation. It contains:
    - messages: The conversation history (user, assistant, system messages)
    - context: Additional context data (instance_id, original_query, etc.)
    - metadata: Thread metadata (created_at, user_id, tags, etc.)

    Note: result, error_message, and progress updates belong on TaskState,
    not Thread. Tasks represent individual agent turns within a thread.
    """

    thread_id: str = Field(default_factory=lambda: str(ULID()))
    messages: List[Message] = Field(default_factory=list)
    context: Dict[str, Any] = Field(default_factory=dict)
    metadata: ThreadMetadata = Field(default_factory=ThreadMetadata)


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
        # Initialize thread state
        metadata = ThreadMetadata(user_id=user_id, session_id=session_id, tags=tags or [])

        thread = Thread(context=initial_context or {}, metadata=metadata)

        await self._save_thread_state(thread)

        # Best-effort: upsert search doc for ordering/filtering
        await self._upsert_thread_search_doc(thread.thread_id)

        logger.info(f"Created thread {thread.thread_id} for user {user_id}")
        return thread.thread_id

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

    async def set_thread_subject(self, thread_id: str, subject: str) -> bool:
        """Set the thread subject explicitly and update the search index."""
        try:
            client = await self._get_client()
            keys = self._get_thread_keys(thread_id)

            await client.hset(keys["metadata"], "subject", subject or "")
            await client.hset(
                keys["metadata"], "updated_at", datetime.now(timezone.utc).isoformat()
            )

            # Update search index
            await self._upsert_thread_search_doc(thread_id)
            logger.info(f"Set thread {thread_id} subject: {subject}")
            return True
        except Exception as e:
            logger.error(f"Failed to set thread {thread_id} subject: {e}")
            return False

    async def _upsert_thread_search_doc(self, thread_id: str) -> bool:
        """Upsert a simplified thread document into the RedisVL threads index (hash).

        Best-effort; failures are logged and ignored.
        """
        try:
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

            metadata_h = await client.hgetall(keys["metadata"]) or {}
            context_h = await client.hgetall(keys["context"]) or {}

            def _decode(dct):
                out = {}
                if not isinstance(dct, dict):
                    return out
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
            # Parse tags from metadata JSON (stored as string)
            raw_tags = metadata.get("tags", "[]")
            try:
                tags_list = json.loads(raw_tags) if isinstance(raw_tags, str) else (raw_tags or [])
                if not isinstance(tags_list, list):
                    tags_list = []
            except Exception:
                # Accept simple comma-delimited strings
                tags_list = [t for t in str(raw_tags).split(",") if t]
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
                "subject": subject or "",
                "user_id": user_id or "",
                "instance_id": instance_id or "",
                "priority": priority,
                "created_at": created_ts,
                "updated_at": updated_ts,
                # Store tags as comma-delimited for TAG field
                "tags": ",".join([str(t) for t in (tags_list or [])]),
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
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """List threads with optional filtering."""
        index = await get_threads_index()
        expr = None

        if user_id:
            expr = (
                expr & (Tag("user_id") == user_id)
                if expr is not None
                else (Tag("user_id") == user_id)
            )

        fq = FilterQuery(
            return_fields=[
                "id",
                "subject",
                "user_id",
                "instance_id",
                "priority",
                "created_at",
                "updated_at",
                "tags",
            ],
        ).sort_by("updated_at", asc=False)
        if expr:
            fq.set_filter(expr)
        fq.paging(offset, limit)

        results = await index.query(fq)

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
            if isinstance(res, dict):
                row = res
            else:
                row = {}
                for k in [
                    "id",
                    "subject",
                    "user_id",
                    "instance_id",
                    "priority",
                    "created_at",
                    "updated_at",
                ]:
                    row[k] = res.__dict__.get(k)
            redis_key = row.get("id", "")
            thread_id = (
                redis_key[len("sre_threads:") :]
                if isinstance(redis_key, str) and redis_key.startswith("sre_threads:")
                else redis_key
            )

            created_iso = _iso(row.get("created_at"))
            updated_iso = _iso(row.get("updated_at"))

            # Build summary
            # Parse tags back into a list
            raw_tags = row.get("tags") or ""
            tags_list = [t for t in str(raw_tags).split(",") if t]

            summary = {
                "thread_id": thread_id,
                "subject": row.get("subject") or "Untitled",
                "created_at": created_iso,
                "updated_at": updated_iso,
                "user_id": row.get("user_id") or None,
                "latest_message": "No updates",
                "tags": tags_list,
                "priority": int(row.get("priority") or 0),
                "instance_id": row.get("instance_id") or None,
            }
            threads.append(summary)

        return threads

    async def get_thread(self, thread_id: str) -> Optional[Thread]:
        """Retrieve complete thread state."""
        try:
            client = await self._get_client()
            keys = self._get_thread_keys(thread_id)

            # Check if thread exists (use metadata as source of truth)
            if not await client.exists(keys["metadata"]):
                return None

            # Load thread data
            messages_data = await client.lrange(keys["messages"], 0, -1)
            context_data = await client.hgetall(keys["context"])
            metadata_data = await client.hgetall(keys["metadata"])

            # Parse messages from dedicated list (FIFO order via RPUSH)
            messages: List[Message] = []
            for msg_json in messages_data:
                try:
                    msg_dict = json.loads(msg_json)
                    messages.append(Message(**msg_dict))
                except (json.JSONDecodeError, Exception) as e:
                    logger.warning(f"Failed to parse message: {e}")

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

            # BACKWARD COMPATIBILITY: If no messages in dedicated list, check context["messages"]
            if not messages and isinstance(context.get("messages"), list):
                for m in context["messages"]:
                    if isinstance(m, dict) and m.get("content"):
                        messages.append(
                            Message(
                                role=m.get("role", "user"),
                                content=m.get("content", ""),
                                metadata=m.get("metadata"),
                            )
                        )
                # Remove messages from context since they're now in the messages field
                context.pop("messages", None)

            return Thread(
                thread_id=thread_id,
                messages=messages,
                context=context,
                metadata=metadata,
            )

        except Exception as e:
            logger.error(f"Failed to get thread state {thread_id}: {e}")
            return None

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
        """Append messages to thread's message list.

        Messages are stored in a dedicated Redis list (RPUSH for FIFO order).
        Each message should have {role, content, metadata?}.
        """
        try:
            client = await self._get_client()
            keys = self._get_thread_keys(thread_id)

            # Append each message to the list (RPUSH for chronological order)
            for m in messages or []:
                if not isinstance(m, dict):
                    continue
                content = m.get("content")
                if not content:
                    continue

                role = m.get("role", "user")
                if role not in ("user", "assistant", "system"):
                    role = "user"

                msg = Message(
                    role=role,
                    content=content,
                    metadata=m.get("metadata"),
                )
                await client.rpush(keys["messages"], msg.model_dump_json())

            # Update metadata timestamp
            await client.hset(
                keys["metadata"], "updated_at", datetime.now(timezone.utc).isoformat()
            )

            # Update search index
            await self._upsert_thread_search_doc(thread_id)

            logger.debug(f"Appended {len(messages)} messages to thread {thread_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to append messages for thread {thread_id}: {e}")
            return False

    async def _save_thread_state(self, thread_state: Thread) -> bool:
        """Save complete thread state to Redis."""
        try:
            client = await self._get_client()
            keys = self._get_thread_keys(thread_state.thread_id)

            async with client.pipeline(transaction=True) as pipe:
                # Save messages to dedicated list (clear and rebuild for atomicity)
                if thread_state.messages:
                    pipe.delete(keys["messages"])
                    for msg in thread_state.messages:
                        pipe.rpush(keys["messages"], msg.model_dump_json())

                # Set context as hash (excluding messages which are now separate)
                if thread_state.context:
                    # Filter out None values and serialize complex objects as JSON
                    clean_context = {}
                    for k, v in thread_state.context.items():
                        # Skip 'messages' key - messages are stored separately
                        if k == "messages":
                            continue
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

            # Remove the hash document used by the threads search index
            search_doc_key = f"{SRE_THREADS_INDEX}:{thread_id}"
            await client.delete(search_doc_key)

            logger.info(f"Deleted thread {thread_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete thread {thread_id}: {e}")
            return False


# ---- Domain-level helpers moved from redis_sre_agent.models.threads ----


async def _build_initial_context(
    query: str,
    priority: int = 0,
    base_context: Optional[Dict[str, Any]] = None,
    instance_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Create the initial context dict used when starting a thread.

    Optionally enrich with instance name when instance_id is provided.
    """
    initial_context: Dict[str, Any] = {
        "original_query": query,
        "priority": priority,
        "messages": [],
    }
    if base_context:
        initial_context.update(base_context)

    if instance_id:
        initial_context["instance_id"] = instance_id
        try:
            from redis_sre_agent.core.instances import get_instances

            instances = await get_instances()
            for inst in instances:
                if inst.id == instance_id:
                    initial_context["instance_name"] = inst.name
                    break
        except Exception as e:
            logger.debug(f"Could not enrich context with instance name: {e}")

    return initial_context


async def create_thread(
    *,
    query: str,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
    priority: int = 0,
    tags: Optional[list[str]] = None,
    instance_id: Optional[str] = None,
    redis_client=None,
) -> Dict[str, Any]:
    """Create a thread and queue the agent to process the initial query."""
    if redis_client is None:
        from redis_sre_agent.core.redis import get_redis_client as _get

        redis_client = _get()

    # Local imports to avoid import cycles
    from docket import Docket  # type: ignore

    from redis_sre_agent.core.docket_tasks import get_redis_url, process_agent_turn

    thread_manager = ThreadManager(redis_client=redis_client)

    initial_context = await _build_initial_context(
        query=query, priority=priority, base_context=context, instance_id=instance_id
    )

    thread_id = await thread_manager.create_thread(
        user_id=user_id,
        session_id=session_id,
        initial_context=initial_context,
        tags=tags or [],
    )

    await thread_manager.update_thread_subject(thread_id, query)

    async with Docket(url=await get_redis_url(), name="sre_docket") as docket:
        task_func = docket.add(process_agent_turn)
        await task_func(thread_id=thread_id, message=query, context=initial_context)

    return {
        "thread_id": thread_id,
        "message": "Thread created and queued for analysis",
        "estimated_completion": "2-5 minutes",
        "context": initial_context,
    }


async def continue_thread(
    *, thread_id: str, query: str, context: Optional[Dict[str, Any]] = None, redis_client=None
) -> Dict[str, Any]:
    """Queue another agent processing turn for an existing thread."""
    if redis_client is None:
        from redis_sre_agent.core.redis import get_redis_client as _get

        redis_client = _get()

    from docket import Docket  # type: ignore

    from redis_sre_agent.core.docket_tasks import get_redis_url, process_agent_turn

    thread_manager = ThreadManager(redis_client=redis_client)

    thread_state = await thread_manager.get_thread(thread_id)
    if not thread_state:
        raise ValueError(f"Thread {thread_id} not found")

    async with Docket(url=await get_redis_url(), name="sre_docket") as docket:
        task_func = docket.add(process_agent_turn)
        await task_func(thread_id=thread_id, message=query, context=context)

    return {
        "thread_id": thread_id,
        "message": "Continuation queued for processing",
        "estimated_completion": "2-5 minutes",
    }


async def cancel_thread(*, thread_id: str, redis_client=None) -> Dict[str, Any]:
    """Mark a thread as cancelled and add a cancellation update."""
    if redis_client is None:
        from redis_sre_agent.core.redis import get_redis_client as _get

        redis_client = _get()

    from redis_sre_agent.core.keys import RedisKeys
    from redis_sre_agent.core.tasks import TaskManager

    thread_manager = ThreadManager(redis_client=redis_client)
    thread_state = await thread_manager.get_thread(thread_id)
    if not thread_state:
        raise ValueError(f"Thread {thread_id} not found")

    # Get the latest task for this thread to add cancellation update
    latest_task_ids = await redis_client.zrevrange(RedisKeys.thread_tasks_index(thread_id), 0, 0)
    if latest_task_ids:
        task_id = latest_task_ids[0]
        if isinstance(task_id, bytes):
            task_id = task_id.decode()
        task_manager = TaskManager(redis_client=redis_client)
        await task_manager.add_task_update(
            task_id, "Task cancelled by user request", "cancellation"
        )

    return {"cancelled": True}


async def delete_thread(*, thread_id: str, redis_client=None) -> Dict[str, Any]:
    """Permanently delete a thread.

    This operation is idempotent: it will succeed even if the thread has
    already been deleted or never existed, as long as Redis is reachable.
    """
    if redis_client is None:
        from redis_sre_agent.core.redis import get_redis_client as _get

        redis_client = _get()

    thread_manager = ThreadManager(redis_client=redis_client)
    success = await thread_manager.delete_thread(thread_id)
    if not success:
        raise RuntimeError(f"Failed to delete thread {thread_id}")

    return {"deleted": True}
