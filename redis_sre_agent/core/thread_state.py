"""Thread state management for SRE Agent conversations."""

import json
import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field
from ulid import ULID

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

    def __init__(self):
        self.redis_client = None

    async def _get_client(self):
        """Get Redis client (lazy initialization)."""
        if self.redis_client is None:
            self.redis_client = get_redis_client()
        return self.redis_client

    def _get_thread_keys(self, thread_id: str) -> Dict[str, str]:
        """Get all Redis keys for a thread."""
        return {
            "status": f"sre:thread:{thread_id}:status",
            "updates": f"sre:thread:{thread_id}:updates",
            "context": f"sre:thread:{thread_id}:context",
            "action_items": f"sre:thread:{thread_id}:action_items",
            "metadata": f"sre:thread:{thread_id}:metadata",
            "result": f"sre:thread:{thread_id}:result",
            "error": f"sre:thread:{thread_id}:error",
        }

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

        logger.info(f"Created thread {thread_id} for user {user_id}")
        return thread_id

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
                context=context_data,
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

            logger.info(f"Set result for thread {thread_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to set result for thread {thread_id}: {e}")
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
                # Filter out None values and ensure all values are strings
                clean_context = {
                    k: str(v) if v is not None else "" for k, v in thread_state.context.items()
                }
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

            await client.delete(*keys.values())

            logger.info(f"Deleted thread {thread_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete thread {thread_id}: {e}")
            return False


# Singleton instance
_thread_manager = None


def get_thread_manager() -> ThreadManager:
    """Get the global thread manager instance."""
    global _thread_manager
    if _thread_manager is None:
        _thread_manager = ThreadManager()
    return _thread_manager
