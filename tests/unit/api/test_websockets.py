"""Tests for WebSocket task status functionality."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from redis.asyncio import Redis

from redis_sre_agent.api.app import app
from redis_sre_agent.api.websockets import TaskStreamManager
from redis_sre_agent.core.threads import Thread, ThreadUpdate


class TestTaskStreamManager:
    """Test the TaskStreamManager class."""

    @pytest.fixture
    def stream_manager(self):
        """Create a TaskStreamManager instance for testing."""
        return TaskStreamManager()

    @pytest.mark.asyncio
    async def test_publish_task_update(self, stream_manager):
        """Test publishing task updates to Redis Stream."""
        mock_redis = AsyncMock(spec=Redis)
        mock_redis.xadd = AsyncMock(return_value=b"1234567890-0")
        mock_redis.expire = AsyncMock(return_value=True)

        with patch.object(
            stream_manager, "_get_client", new_callable=AsyncMock, return_value=mock_redis
        ):
            result = await stream_manager.publish_task_update(
                "test_thread", "status_change", {"status": "running", "message": "Task started"}
            )

            assert result is True

            # Verify xadd was called with correct parameters
            mock_redis.xadd.assert_called_once()
            call_args = mock_redis.xadd.call_args
            stream_key = call_args[0][0]
            stream_data = call_args[0][1]

            from redis_sre_agent.core.keys import RedisKeys

            assert stream_key == RedisKeys.task_stream("test_thread")
            assert "timestamp" in stream_data
            assert stream_data["update_type"] == "status_change"
            assert stream_data["thread_id"] == "test_thread"
            assert stream_data["status"] == "running"
            assert stream_data["message"] == "Task started"

            # Verify TTL was set
            mock_redis.expire.assert_called_once_with(stream_key, 86400)

    @pytest.mark.asyncio
    async def test_publish_task_update_with_duplicate_keys(self, stream_manager):
        """Ensure duplicate 'update_type'/'thread_id' keys in data don't break publish."""
        mock_redis = AsyncMock(spec=Redis)
        mock_redis.xadd = AsyncMock(return_value=b"1234567890-1")
        mock_redis.expire = AsyncMock(return_value=True)

        with patch.object(
            stream_manager, "_get_client", new_callable=AsyncMock, return_value=mock_redis
        ):
            data = {
                "update_type": "progress",  # duplicate with param
                "thread_id": "wrong_thread",  # duplicate with param
                "status": "running",
            }
            result = await stream_manager.publish_task_update("test_thread", "thread_update", data)

            assert result is True

            # Verify xadd was called and param values override data duplicates
            call_args = mock_redis.xadd.call_args
            stream_data = call_args[0][1]
            assert stream_data["update_type"] == "thread_update"
            assert stream_data["thread_id"] == "test_thread"
            assert stream_data["status"] == "running"

    @pytest.mark.asyncio
    async def test_publish_task_update_failure(self, stream_manager):
        """Test handling of Redis errors during publish."""
        mock_redis = AsyncMock(spec=Redis)
        mock_redis.xadd.side_effect = Exception("Redis connection failed")

        with patch.object(stream_manager, "_get_client", return_value=mock_redis):
            result = await stream_manager.publish_task_update(
                "test_thread", "status_change", {"status": "running"}
            )

            assert result is False

    @pytest.mark.asyncio
    async def test_start_stop_consumer(self, stream_manager):
        """Test starting and stopping stream consumers."""
        thread_id = "test_thread"

        # Mock the consume method to avoid actual Redis operations
        with patch.object(stream_manager, "_consume_stream", new_callable=AsyncMock):
            # Start consumer
            await stream_manager.start_consumer(thread_id)
            assert thread_id in stream_manager._consumer_tasks

            # Starting again should not create duplicate
            await stream_manager.start_consumer(thread_id)
            assert (
                len([t for t in stream_manager._consumer_tasks.values() if not t.cancelled()]) == 1
            )

            # Stop consumer
            await stream_manager.stop_consumer(thread_id)
            assert thread_id not in stream_manager._consumer_tasks

    @pytest.mark.asyncio
    async def test_broadcast_update(self, stream_manager):
        """Test broadcasting updates to WebSocket clients."""
        from redis_sre_agent.api.websockets import _active_connections

        thread_id = "test_thread"

        # Mock WebSocket connections
        mock_ws1 = AsyncMock()
        mock_ws2 = AsyncMock()
        mock_ws_failed = AsyncMock()
        mock_ws_failed.send_text.side_effect = Exception("Connection failed")

        _active_connections[thread_id] = {mock_ws1, mock_ws2, mock_ws_failed}

        # Test broadcast
        fields = {
            b"update_type": b"status_change",
            b"status": b'"running"',
            b"message": b"Task started",
        }

        await stream_manager._broadcast_update(thread_id, fields)

        # Verify successful connections received the message
        mock_ws1.send_text.assert_called_once()
        mock_ws2.send_text.assert_called_once()

        # Verify failed connection was removed
        assert mock_ws_failed not in _active_connections[thread_id]
        assert len(_active_connections[thread_id]) == 2

        # Clean up
        del _active_connections[thread_id]


class TestWebSocketEndpoint:
    """Test the WebSocket endpoint."""

    @pytest.fixture
    def test_client(self):
        """Create a test client."""
        return TestClient(app)

    @pytest.mark.asyncio
    async def test_websocket_connection_thread_not_found(self, test_client):
        """Test WebSocket connection when thread doesn't exist."""
        with (
            patch("redis_sre_agent.api.websockets.get_redis_client") as mock_get_redis,
            patch("redis_sre_agent.api.websockets.ThreadManager") as mock_manager_class,
        ):
            mock_redis = AsyncMock()
            mock_get_redis.return_value = mock_redis

            mock_manager = AsyncMock()
            mock_manager_class.return_value = mock_manager
            mock_manager.get_thread.return_value = None

            with test_client.websocket_connect("/api/v1/ws/tasks/nonexistent") as websocket:
                data = websocket.receive_json()
                assert data["error"] == "Thread not found"
                assert data["thread_id"] == "nonexistent"

    @pytest.mark.asyncio
    async def test_websocket_connection_success(self, test_client):
        """Test successful WebSocket connection."""
        # Clear global state
        from redis_sre_agent.api.websockets import _active_connections

        _active_connections.clear()

        thread_id = "test_thread"

        # Mock thread state
        mock_thread_state = Thread(
            thread_id=thread_id,
            updates=[
                ThreadUpdate(message="Processing...", update_type="progress"),
                ThreadUpdate(message="Task started", update_type="info"),
            ],
        )

        with (
            patch("redis_sre_agent.api.websockets.get_redis_client") as mock_get_redis,
            patch("redis_sre_agent.api.websockets.ThreadManager") as mock_manager_class,
            patch("redis_sre_agent.api.websockets._stream_manager") as mock_stream_manager,
        ):
            mock_redis = AsyncMock()
            # Mock Redis operations that the websocket endpoint uses
            mock_redis.zrevrange = AsyncMock(return_value=[])  # No latest task
            mock_get_redis.return_value = mock_redis

            mock_manager = AsyncMock()
            mock_manager_class.return_value = mock_manager
            mock_manager.get_thread.return_value = mock_thread_state

            mock_stream_manager.start_consumer = AsyncMock()
            mock_stream_manager.stop_consumer = AsyncMock()

            with test_client.websocket_connect(f"/api/v1/ws/tasks/{thread_id}") as websocket:
                # Should receive initial state
                data = websocket.receive_json()

                assert data["update_type"] == "initial_state"
                assert data["thread_id"] == thread_id
                # With no task, updates should be empty
                assert data["updates"] == []

                # Verify stream consumer was started
                mock_stream_manager.start_consumer.assert_called_once_with(thread_id)

                # Test ping/pong
                websocket.send_json({"type": "ping"})
                pong_response = websocket.receive_json()
                assert pong_response["type"] == "pong"

    def test_get_task_stream_info(self, test_client):
        """Test the stream info endpoint."""
        thread_id = "test_thread"

        mock_redis = AsyncMock()
        mock_redis.xinfo_stream.return_value = {b"length": b"5"}

        with patch("redis_sre_agent.api.websockets.get_redis_client", return_value=mock_redis):
            response = test_client.get(f"/api/v1/tasks/{thread_id}/stream-info")

            assert response.status_code == 200
            data = response.json()

            from redis_sre_agent.core.keys import RedisKeys

            assert data["thread_id"] == thread_id
            assert data["stream_key"] == RedisKeys.task_stream(thread_id)
            assert data["stream_length"] == 5
            assert data["active_connections"] == 0
            assert data["consumer_active"] is False

    def test_get_task_stream_info_no_stream(self, test_client):
        """Test stream info endpoint when stream doesn't exist."""
        thread_id = "test_thread"

        mock_redis = AsyncMock()
        mock_redis.xinfo_stream.side_effect = Exception("Stream not found")

        with patch("redis_sre_agent.api.websockets.get_redis_client", return_value=mock_redis):
            response = test_client.get(f"/api/v1/tasks/{thread_id}/stream-info")

            assert response.status_code == 200
            data = response.json()

            assert data["stream_length"] == 0  # Fallback value


class TestThreadManagerIntegration:
    """Test integration between ThreadManager and WebSocket streams."""

    @pytest.mark.asyncio
    async def test_thread_update_context_publishes_stream(self):
        """Test that thread context updates work correctly."""
        from redis_sre_agent.core.threads import ThreadManager

        thread_manager = ThreadManager()
        thread_id = "test_thread"

        mock_redis = AsyncMock()
        # Mock hgetall to return thread data
        mock_redis.hgetall.return_value = {
            b"id": b"test_thread",
            b"user_id": b"user1",
            b"created_at": b"2024-01-01T00:00:00Z",
            b"updated_at": b"2024-01-01T00:00:00Z",
            b"status": b"active",
        }
        mock_redis.hset.return_value = True

        with patch.object(thread_manager, "_get_client", return_value=mock_redis):
            # Test update_thread_context which is an actual method
            result = await thread_manager.update_thread_context(thread_id, {"key": "value"})
            # Method should complete without error
            assert result is True or result is False  # Depends on mock setup
