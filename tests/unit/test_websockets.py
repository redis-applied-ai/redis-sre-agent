"""Tests for WebSocket task status functionality."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from redis.asyncio import Redis

from redis_sre_agent.api.app import app
from redis_sre_agent.api.websockets import TaskStreamManager
from redis_sre_agent.core.thread_state import ThreadState, ThreadStatus, ThreadUpdate


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

            assert stream_key == "sre:stream:task:test_thread"
            assert "timestamp" in stream_data
            assert stream_data["update_type"] == "status_change"
            assert stream_data["thread_id"] == "test_thread"
            assert stream_data["status"] == "running"
            assert stream_data["message"] == "Task started"

            # Verify TTL was set
            mock_redis.expire.assert_called_once_with(stream_key, 86400)

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
        with patch("redis_sre_agent.api.websockets.get_thread_manager") as mock_get_manager:
            mock_manager = AsyncMock()
            mock_manager.get_thread_state.return_value = None
            mock_get_manager.return_value = mock_manager

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
        mock_thread_state = ThreadState(
            thread_id=thread_id,
            status=ThreadStatus.IN_PROGRESS,
            updates=[
                ThreadUpdate(message="Processing...", update_type="progress"),
                ThreadUpdate(message="Task started", update_type="info"),
            ],
        )

        with (
            patch("redis_sre_agent.api.websockets.get_thread_manager") as mock_get_manager,
            patch("redis_sre_agent.api.websockets._stream_manager") as mock_stream_manager,
        ):
            mock_manager = AsyncMock()
            mock_manager.get_thread_state.return_value = mock_thread_state
            mock_get_manager.return_value = mock_manager

            mock_stream_manager.start_consumer = AsyncMock()
            mock_stream_manager.stop_consumer = AsyncMock()

            with test_client.websocket_connect(f"/api/v1/ws/tasks/{thread_id}") as websocket:
                # Should receive initial state
                data = websocket.receive_json()

                assert data["update_type"] == "initial_state"
                assert data["thread_id"] == thread_id
                assert data["status"] == "in_progress"
                assert len(data["updates"]) == 2
                assert data["updates"][0]["message"] == "Processing..."  # Most recent first

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

            assert data["thread_id"] == thread_id
            assert data["stream_key"] == f"sre:stream:task:{thread_id}"
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
    async def test_thread_status_update_publishes_stream(self):
        """Test that thread status updates are published to streams."""
        from redis_sre_agent.core.thread_state import ThreadManager

        thread_manager = ThreadManager()
        thread_id = "test_thread"

        mock_redis = AsyncMock()
        mock_stream_manager = AsyncMock()

        with (
            patch.object(thread_manager, "_get_client", return_value=mock_redis),
            patch(
                "redis_sre_agent.api.websockets.get_stream_manager",
                return_value=mock_stream_manager,
            ),
        ):
            await thread_manager.update_thread_status(thread_id, ThreadStatus.DONE)

            # Verify stream update was published
            mock_stream_manager.publish_task_update.assert_called_once_with(
                thread_id, "status_change", {"status": "done", "message": "Status changed to done"}
            )

    @pytest.mark.asyncio
    async def test_thread_update_publishes_stream(self):
        """Test that thread updates are published to streams."""
        from redis_sre_agent.core.thread_state import ThreadManager

        thread_manager = ThreadManager()
        thread_id = "test_thread"

        mock_redis = AsyncMock()
        mock_stream_manager = AsyncMock()

        with (
            patch.object(thread_manager, "_get_client", return_value=mock_redis),
            patch(
                "redis_sre_agent.api.websockets.get_stream_manager",
                return_value=mock_stream_manager,
            ),
        ):
            await thread_manager.add_thread_update(
                thread_id, "Processing data...", "progress", {"step": 1, "total": 5}
            )

            # Verify stream update was published
            mock_stream_manager.publish_task_update.assert_called_once()
            call_args = mock_stream_manager.publish_task_update.call_args

            assert call_args[0][0] == thread_id
            assert call_args[0][1] == "thread_update"
            assert call_args[0][2]["message"] == "Processing data..."
            assert call_args[0][2]["update_type"] == "progress"
            assert call_args[0][2]["metadata"] == {"step": 1, "total": 5}
