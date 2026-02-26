"""Tests for message-level decision trace functionality.

These tests cover the new message_id field on Message model and the
message trace storage/retrieval methods on ThreadManager.
"""

import json
from unittest.mock import AsyncMock

import pytest

from redis_sre_agent.core.keys import RedisKeys
from redis_sre_agent.core.threads import Message, ThreadManager


class TestMessageModel:
    """Test Message model with message_id field."""

    def test_message_auto_generates_message_id(self):
        """Message should auto-generate a ULID message_id if not provided."""
        msg = Message(role="user", content="Hello")
        assert msg.message_id is not None
        assert len(msg.message_id) == 26  # ULID length

    def test_message_preserves_provided_message_id(self):
        """Message should use provided message_id if given."""
        custom_id = "01ARZ3NDEKTSV4RRFFQ69G5FAV"
        msg = Message(role="assistant", content="Hi there", message_id=custom_id)
        assert msg.message_id == custom_id

    def test_message_different_ids_for_different_messages(self):
        """Different messages should have different message_ids."""
        msg1 = Message(role="user", content="Hello")
        msg2 = Message(role="user", content="Hello")
        assert msg1.message_id != msg2.message_id

    def test_message_with_metadata(self):
        """Message should support metadata field."""
        msg = Message(
            role="assistant",
            content="Response",
            metadata={"task_id": "task-123", "message_id": "msg-456"},
        )
        assert msg.metadata["task_id"] == "task-123"
        assert msg.metadata["message_id"] == "msg-456"


class TestAppendMessagesPreservesMessageId:
    """Test that append_messages preserves message_id from input."""

    @pytest.fixture
    def mock_redis_client(self):
        """Mock Redis client for testing."""
        client = AsyncMock()
        client.rpush = AsyncMock(return_value=1)
        client.hset = AsyncMock(return_value=1)
        return client

    @pytest.fixture
    def thread_manager(self, mock_redis_client):
        """Create thread manager with mocked Redis."""
        manager = ThreadManager()
        manager._redis_client = mock_redis_client
        # Disable search doc update for this test
        manager._upsert_thread_search_doc = AsyncMock(return_value=True)
        return manager

    @pytest.mark.asyncio
    async def test_append_messages_preserves_message_id_from_metadata(
        self, thread_manager, mock_redis_client
    ):
        """append_messages should preserve message_id from metadata."""
        custom_id = "01CUSTOM1234567890ABCDEF"
        messages = [
            {
                "role": "assistant",
                "content": "Test response",
                "metadata": {"message_id": custom_id, "task_id": "task-123"},
            }
        ]

        await thread_manager.append_messages("thread-123", messages)

        # Verify rpush was called
        assert mock_redis_client.rpush.called
        call_args = mock_redis_client.rpush.call_args
        stored_json = call_args[0][1]
        stored_data = json.loads(stored_json)

        # The stored message should have the custom message_id, not an auto-generated one
        assert stored_data["message_id"] == custom_id

    @pytest.mark.asyncio
    async def test_append_messages_preserves_message_id_from_top_level(
        self, thread_manager, mock_redis_client
    ):
        """append_messages should preserve message_id from top-level field."""
        custom_id = "01TOPLEVEL234567890ABCDEF"
        messages = [
            {
                "role": "assistant",
                "content": "Test response",
                "message_id": custom_id,
            }
        ]

        await thread_manager.append_messages("thread-123", messages)

        call_args = mock_redis_client.rpush.call_args
        stored_json = call_args[0][1]
        stored_data = json.loads(stored_json)

        assert stored_data["message_id"] == custom_id

    @pytest.mark.asyncio
    async def test_append_messages_auto_generates_id_when_none_provided(
        self, thread_manager, mock_redis_client
    ):
        """append_messages should auto-generate message_id when not provided."""
        messages = [
            {
                "role": "user",
                "content": "User query",
            }
        ]

        await thread_manager.append_messages("thread-123", messages)

        call_args = mock_redis_client.rpush.call_args
        stored_json = call_args[0][1]
        stored_data = json.loads(stored_json)

        # Should have an auto-generated ULID (26 chars)
        assert stored_data["message_id"] is not None
        assert len(stored_data["message_id"]) == 26


class TestRedisKeysMessageTrace:
    """Test RedisKeys.message_decision_trace method."""

    def test_message_decision_trace_key_format(self):
        """Key should follow expected format."""
        key = RedisKeys.message_decision_trace("01ARZ3NDEKTSV4RRFFQ69G5FAV")
        assert key == "sre:message:01ARZ3NDEKTSV4RRFFQ69G5FAV:decision_trace"

    def test_message_decision_trace_key_unique_per_message(self):
        """Different message_ids should produce different keys."""
        key1 = RedisKeys.message_decision_trace("msg-111")
        key2 = RedisKeys.message_decision_trace("msg-222")
        assert key1 != key2


class TestThreadManagerMessageTrace:
    """Test ThreadManager message trace methods."""

    @pytest.fixture
    def mock_redis_client(self):
        """Mock Redis client for testing."""
        client = AsyncMock()
        client.setex.return_value = True
        client.get.return_value = None
        return client

    @pytest.fixture
    def thread_manager(self, mock_redis_client):
        """Create thread manager with mocked Redis."""
        manager = ThreadManager()
        manager._redis_client = mock_redis_client
        return manager

    @pytest.mark.asyncio
    async def test_set_message_trace_success(self, thread_manager, mock_redis_client):
        """Should store message trace successfully."""
        message_id = "01ARZ3NDEKTSV4RRFFQ69G5FAV"
        tool_envelopes = [
            {
                "tool_key": "knowledge_search",
                "name": "search",
                "args": {"query": "redis memory"},
                "status": "success",
                "data": {"results": []},
            }
        ]

        result = await thread_manager.set_message_trace(message_id, tool_envelopes)

        assert result is True
        mock_redis_client.setex.assert_called_once()
        call_args = mock_redis_client.setex.call_args
        assert call_args[0][0] == RedisKeys.message_decision_trace(message_id)
        assert call_args[0][1] == 7 * 24 * 60 * 60  # 7 days TTL

    @pytest.mark.asyncio
    async def test_set_message_trace_with_otel_trace_id(self, thread_manager, mock_redis_client):
        """Should include otel_trace_id in stored trace."""
        message_id = "msg-123"
        tool_envelopes = [{"tool_key": "test", "status": "success", "data": {}}]
        otel_trace_id = "abc123def456"

        await thread_manager.set_message_trace(
            message_id, tool_envelopes, otel_trace_id=otel_trace_id
        )

        call_args = mock_redis_client.setex.call_args
        stored_json = call_args[0][2]
        stored_data = json.loads(stored_json)
        assert stored_data["otel_trace_id"] == otel_trace_id

    @pytest.mark.asyncio
    async def test_get_message_trace_not_found(self, thread_manager, mock_redis_client):
        """Should return None when trace doesn't exist."""
        mock_redis_client.get.return_value = None

        result = await thread_manager.get_message_trace("nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_message_trace_success(self, thread_manager, mock_redis_client):
        """Should return trace data when it exists."""
        trace_data = {
            "message_id": "msg-123",
            "tool_envelopes": [{"tool_key": "test", "status": "success"}],
            "otel_trace_id": None,
            "created_at": "2024-01-01T00:00:00Z",
        }
        mock_redis_client.get.return_value = json.dumps(trace_data).encode()

        result = await thread_manager.get_message_trace("msg-123")

        assert result is not None
        assert result["message_id"] == "msg-123"
        assert len(result["tool_envelopes"]) == 1

    @pytest.mark.asyncio
    async def test_set_message_trace_error_handling(self, thread_manager, mock_redis_client):
        """Should return False on Redis error."""
        mock_redis_client.setex.side_effect = Exception("Redis connection failed")

        result = await thread_manager.set_message_trace("msg-123", [])

        assert result is False
