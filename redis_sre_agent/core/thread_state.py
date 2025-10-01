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
            client = await self._get_client()

            # Choose index based on user_id
            index_key = (
                RedisKeys.threads_user_index(user_id) if user_id else RedisKeys.threads_index()
            )

            # Get thread IDs from index (most recent first)
            thread_ids = await client.zrevrange(
                index_key, offset, offset + limit - 1, withscores=False
            )

            if not thread_ids:
                return []

            # Get thread summaries
            threads = []
            for thread_id in thread_ids:
                thread_id = thread_id.decode() if isinstance(thread_id, bytes) else thread_id

                try:
                    # Get basic thread info
                    keys = self._get_thread_keys(thread_id)

                    # Get status, metadata, and latest update
                    status_data = await client.get(keys["status"])
                    metadata_data = await client.hgetall(keys["metadata"])
                    latest_update = await client.lrange(keys["updates"], 0, 0)

                    if not status_data:
                        continue  # Skip if thread doesn't exist

                    status = status_data.decode()

                    # Apply status filter
                    if status_filter and status != status_filter.value:
                        continue

                    # Parse metadata
                    metadata = {}
                    if metadata_data:
                        metadata = {k.decode(): v.decode() for k, v in metadata_data.items()}
                        if "tags" in metadata:
                            try:
                                metadata["tags"] = json.loads(metadata["tags"])
                            except json.JSONDecodeError:
                                metadata["tags"] = []

                    # Get latest update message
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
                        "latest_message": latest_message[:100],  # Truncate for summary
                        "tags": metadata.get("tags", []),
                        "priority": int(metadata.get("priority", 0)),
                    }

                    threads.append(thread_summary)

                except Exception as e:
                    logger.warning(f"Failed to get summary for thread {thread_id}: {e}")
                    continue

            return threads

        except Exception as e:
            logger.error(f"Failed to list threads: {e}")
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

    async def _save_thread_state(self, thread_state: ThreadState) -> bool:
        """Save complete thread state to Redis."""
        try:
            client = await self._get_client()
            keys = self._get_thread_keys(thread_state.thread_id)

            # Use pipeline for atomic operations
            pipe = client.pipeline()

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
            clean_metadata = {k: str(v) if v is not None else "" for k, v in metadata_dict.items()}
            pipe.hset(keys["metadata"], mapping=clean_metadata)

            # Set action items as JSON
            if thread_state.action_items:
                items_json = json.dumps([item.model_dump() for item in thread_state.action_items])
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
