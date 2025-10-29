"""WebSocket endpoints for real-time task status updates."""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Set

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from redis.asyncio import Redis

from redis_sre_agent.core.keys import RedisKeys
from redis_sre_agent.core.redis import get_redis_client
from redis_sre_agent.core.task_events import InitialStateEvent, TaskStreamEvent
from redis_sre_agent.core.threads import ThreadManager

logger = logging.getLogger(__name__)

router = APIRouter()

# Active WebSocket connections per task
_active_connections: Dict[str, Set[WebSocket]] = {}


class TaskStreamManager:
    """Manages Redis Streams for task status updates."""

    def __init__(self):
        self.redis_client: Redis = None
        self._consumer_tasks: Dict[str, asyncio.Task] = {}

    async def _get_client(self) -> Redis:
        """Get Redis client (lazy initialization)."""
        if self.redis_client is None:
            self.redis_client = get_redis_client()
        return self.redis_client

    def _get_stream_key(self, thread_id: str) -> str:
        """Get Redis stream key for a thread."""
        return RedisKeys.task_stream(thread_id)

    async def publish_task_update(self, thread_id: str, update_type: str, data: Dict) -> bool:
        """Publish a task update to Redis Stream."""
        try:
            client = await self._get_client()
            stream_key = self._get_stream_key(thread_id)

            # Build typed event with extra fields preserved at top-level
            # Avoid duplicate keyword errors if callers pass 'update_type' or 'thread_id' in data
            safe_data = {
                k: v for k, v in (data or {}).items() if k not in {"update_type", "thread_id"}
            }
            event = TaskStreamEvent(thread_id=thread_id, update_type=update_type, **safe_data)
            stream_data = event.model_dump()

            # Convert all values to strings for Redis Stream
            stream_data_str = {
                k: json.dumps(v) if not isinstance(v, str) else v for k, v in stream_data.items()
            }

            # Add to stream with automatic ID generation
            await client.xadd(stream_key, stream_data_str)

            # Set TTL on the stream (24 hours)
            await client.expire(stream_key, 86400)

            logger.debug(f"Published update to stream {stream_key}: {update_type}")
            return True

        except Exception as e:
            logger.error(f"Failed to publish task update for {thread_id}: {e}")
            return False

    async def start_consumer(self, thread_id: str) -> None:
        """Start consuming updates for a specific thread."""
        if thread_id in self._consumer_tasks:
            return  # Already consuming

        task = asyncio.create_task(self._consume_stream(thread_id))
        self._consumer_tasks[thread_id] = task
        logger.info(f"Started stream consumer for thread {thread_id}")

    async def stop_consumer(self, thread_id: str) -> None:
        """Stop consuming updates for a specific thread."""
        if thread_id in self._consumer_tasks:
            task = self._consumer_tasks.pop(thread_id)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            logger.info(f"Stopped stream consumer for thread {thread_id}")

    async def _consume_stream(self, thread_id: str) -> None:
        """Consume updates from Redis Stream and broadcast to WebSocket clients."""
        try:
            client = await self._get_client()
            stream_key = self._get_stream_key(thread_id)

            # Start reading from the latest messages
            last_id = "$"

            while thread_id in _active_connections and _active_connections[thread_id]:
                try:
                    # Read new messages from the stream
                    messages = await client.xread({stream_key: last_id}, count=10, block=1000)

                    if not messages:
                        continue

                    # Process messages
                    for stream, stream_messages in messages:
                        for message_id, fields in stream_messages:
                            await self._broadcast_update(thread_id, fields)
                            last_id = (
                                message_id.decode() if isinstance(message_id, bytes) else message_id
                            )

                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Error consuming stream for {thread_id}: {e}")
                    await asyncio.sleep(1)  # Brief pause before retrying

        except Exception as e:
            logger.error(f"Stream consumer failed for {thread_id}: {e}")
        finally:
            logger.info(f"Stream consumer stopped for {thread_id}")

    async def _broadcast_update(self, thread_id: str, fields: Dict) -> None:
        """Broadcast update to all WebSocket clients for this thread."""
        if thread_id not in _active_connections:
            return

        # Parse the stream fields back to proper types
        try:
            update_data = {}
            for key, value in fields.items():
                key_str = key.decode() if isinstance(key, bytes) else key
                value_str = value.decode() if isinstance(value, bytes) else value

                # Try to parse JSON values, fallback to string
                try:
                    update_data[key_str] = json.loads(value_str)
                except (json.JSONDecodeError, TypeError):
                    update_data[key_str] = value_str

            # Validate and serialize via typed event (preserve top-level extras)
            try:
                event = TaskStreamEvent(**update_data)
                message = event.model_dump_json()
            except Exception:
                message = json.dumps(update_data)

            # Broadcast to all connected clients for this thread
            disconnected_clients = set()
            for websocket in _active_connections[thread_id].copy():
                try:
                    await websocket.send_text(message)
                except Exception as e:
                    logger.warning(f"Failed to send message to WebSocket client: {e}")
                    disconnected_clients.add(websocket)

            # Remove disconnected clients
            for websocket in disconnected_clients:
                _active_connections[thread_id].discard(websocket)

            # Stop consumer if no more clients
            if not _active_connections[thread_id]:
                await self.stop_consumer(thread_id)
                del _active_connections[thread_id]

        except Exception as e:
            logger.error(f"Failed to broadcast update for {thread_id}: {e}")


# Global stream manager instance
_stream_manager = TaskStreamManager()


async def get_stream_manager() -> TaskStreamManager:
    """Get the global stream manager instance."""
    return _stream_manager


@router.websocket("/ws/tasks/{thread_id}")
async def websocket_task_status(websocket: WebSocket, thread_id: str):
    """
    WebSocket endpoint for real-time task status updates.

    Clients can connect to this endpoint to receive real-time updates
    about a specific task's progress without polling.
    """
    await websocket.accept()
    logger.info(f"WebSocket client connected for thread {thread_id}")

    try:
        # Verify thread exists
        redis_client = get_redis_client()
        thread_manager = ThreadManager(redis_client=redis_client)
        thread_state = await thread_manager.get_thread(thread_id)
        if not thread_state:
            await websocket.send_text(
                json.dumps({"error": "Thread not found", "thread_id": thread_id})
            )
            await websocket.close(code=4004)
            return

        # Add client to active connections
        if thread_id not in _active_connections:
            _active_connections[thread_id] = set()
        _active_connections[thread_id].add(websocket)

        # Start stream consumer if this is the first client
        if len(_active_connections[thread_id]) == 1:
            await _stream_manager.start_consumer(thread_id)

        # Send current thread state immediately (no thread status)
        initial_event = InitialStateEvent(
            update_type="initial_state",
            thread_id=thread_id,
            updates=thread_state.updates[-10:],  # Last 10 updates
            result=thread_state.result,
            error_message=thread_state.error_message,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        await websocket.send_text(initial_event.model_dump_json())

        # Keep connection alive and handle client messages
        while True:
            try:
                # Wait for client messages (ping/pong, etc.)
                message = await websocket.receive_text()

                # Handle client commands
                try:
                    data = json.loads(message)
                    if data.get("type") == "ping":
                        await websocket.send_text(json.dumps({"type": "pong"}))
                except json.JSONDecodeError:
                    # Ignore invalid JSON
                    pass

            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error(f"WebSocket error for thread {thread_id}: {e}")
                break

    except Exception as e:
        logger.error(f"WebSocket connection error for thread {thread_id}: {e}")

    finally:
        # Clean up connection
        if thread_id in _active_connections:
            _active_connections[thread_id].discard(websocket)

            # Stop consumer if no more clients
            if not _active_connections[thread_id]:
                await _stream_manager.stop_consumer(thread_id)
                del _active_connections[thread_id]

        logger.info(f"WebSocket client disconnected for thread {thread_id}")


@router.get("/tasks/{thread_id}/stream-info")
async def get_task_stream_info(thread_id: str):
    """Get information about the task's stream status."""
    try:
        client = get_redis_client()
        stream_key = RedisKeys.task_stream(thread_id)

        # Get stream info
        try:
            stream_info = await client.xinfo_stream(stream_key)
            stream_length = stream_info.get(b"length", 0)
            if isinstance(stream_length, bytes):
                stream_length = int(stream_length.decode())
        except Exception:
            stream_length = 0

        # Get active connections count
        active_connections = len(_active_connections.get(thread_id, set()))

        return {
            "thread_id": thread_id,
            "stream_key": stream_key,
            "stream_length": stream_length,
            "active_connections": active_connections,
            "consumer_active": thread_id in _stream_manager._consumer_tasks,
        }

    except Exception as e:
        logger.error(f"Failed to get stream info for {thread_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get stream info: {str(e)}")
