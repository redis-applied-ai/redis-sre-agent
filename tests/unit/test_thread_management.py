"""Tests for thread management and async task execution."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from redis_sre_agent.core.tasks import extract_action_items_from_response, process_agent_turn
from redis_sre_agent.core.thread_state import (
    ThreadActionItem,
    ThreadManager,
    ThreadMetadata,
    ThreadState,
    ThreadStatus,
    ThreadUpdate,
    get_thread_manager,
)


class TestThreadManager:
    """Test thread management functionality."""

    @pytest.fixture
    def mock_redis_client(self):
        """Mock Redis client for testing."""
        client = AsyncMock()
        client.exists.return_value = True
        client.set.return_value = True
        client.get.return_value = b"queued"
        client.hset.return_value = True
        client.hgetall.return_value = {}
        client.lrange.return_value = []
        client.lpush.return_value = True
        client.ltrim.return_value = True
        client.expire.return_value = True
        client.delete.return_value = True

        # Mock pipeline properly
        mock_pipeline = AsyncMock()
        mock_pipeline.set.return_value = None
        mock_pipeline.hset.return_value = None
        mock_pipeline.lpush.return_value = None
        mock_pipeline.expire.return_value = None
        mock_pipeline.execute.return_value = [True] * 10

        client.pipeline.return_value = mock_pipeline
        return client

    @pytest.fixture
    def thread_manager(self, mock_redis_client):
        """Create thread manager with mocked Redis."""
        manager = ThreadManager()
        manager.redis_client = mock_redis_client
        return manager

    @pytest.mark.asyncio
    async def test_create_thread(self, thread_manager):
        """Test thread creation."""
        with patch.object(thread_manager, "_save_thread_state", return_value=True) as mock_save:
            thread_id = await thread_manager.create_thread(
                user_id="test_user",
                session_id="test_session",
                initial_context={"query": "test query"},
                tags=["test", "redis"],
            )

            assert thread_id is not None
            assert len(thread_id) > 0
            # Check that save was called
            mock_save.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_thread_state_not_found(self, thread_manager):
        """Test getting non-existent thread state."""
        thread_manager.redis_client.exists.return_value = False

        state = await thread_manager.get_thread_state("nonexistent")
        assert state is None

    @pytest.mark.asyncio
    async def test_get_thread_state_success(self, thread_manager):
        """Test successful thread state retrieval."""
        # Mock Redis data
        thread_manager.redis_client.exists.return_value = True
        thread_manager.redis_client.get.side_effect = [
            b"in_progress",  # status
            None,  # action_items
            None,  # result
            None,  # error
        ]
        thread_manager.redis_client.lrange.return_value = [
            json.dumps(
                {
                    "timestamp": "2023-01-01T00:00:00Z",
                    "message": "Test update",
                    "update_type": "progress",
                    "metadata": None,
                }
            )
        ]
        thread_manager.redis_client.hgetall.side_effect = [
            {b"test_key": b"test_value"},  # context
            {  # metadata
                b"created_at": b"2023-01-01T00:00:00Z",
                b"updated_at": b"2023-01-01T00:00:00Z",
                b"user_id": b"test_user",
                b"session_id": b"test_session",
                b"priority": b"0",
                b"tags": b"[]",
            },
        ]

        state = await thread_manager.get_thread_state("test_thread")

        assert state is not None
        assert state.status == ThreadStatus.IN_PROGRESS
        assert len(state.updates) == 1
        assert state.updates[0].message == "Test update"
        assert state.metadata.user_id == "test_user"

    @pytest.mark.asyncio
    async def test_update_thread_status(self, thread_manager):
        """Test updating thread status."""
        result = await thread_manager.update_thread_status("test_thread", ThreadStatus.DONE)

        assert result is True
        thread_manager.redis_client.set.assert_called()
        thread_manager.redis_client.hset.assert_called()

    @pytest.mark.asyncio
    async def test_add_thread_update(self, thread_manager):
        """Test adding thread updates."""
        result = await thread_manager.add_thread_update(
            "test_thread", "Test progress message", "progress", {"tool": "test_tool"}
        )

        assert result is True
        thread_manager.redis_client.lpush.assert_called()
        thread_manager.redis_client.ltrim.assert_called()

    @pytest.mark.asyncio
    async def test_set_thread_result(self, thread_manager):
        """Test setting thread result."""
        result_data = {"response": "Test response", "metadata": {}}

        result = await thread_manager.set_thread_result("test_thread", result_data)

        assert result is True
        thread_manager.redis_client.set.assert_called()

    @pytest.mark.asyncio
    async def test_add_action_items(self, thread_manager):
        """Test adding action items."""
        action_items = [
            ThreadActionItem(
                title="Test Action",
                description="Test description",
                priority="high",
                category="investigation",
            )
        ]

        # Mock existing action items
        thread_manager.redis_client.get.return_value = None

        result = await thread_manager.add_action_items("test_thread", action_items)

        assert result is True
        thread_manager.redis_client.set.assert_called()

    @pytest.mark.asyncio
    async def test_set_thread_error(self, thread_manager):
        """Test setting thread error."""
        with patch.object(thread_manager, "update_thread_status") as mock_update:
            mock_update.return_value = True

            result = await thread_manager.set_thread_error("test_thread", "Test error")

            assert result is True
            thread_manager.redis_client.set.assert_called()
            mock_update.assert_called_with("test_thread", ThreadStatus.FAILED)

    @pytest.mark.asyncio
    async def test_delete_thread(self, thread_manager):
        """Test thread deletion."""
        result = await thread_manager.delete_thread("test_thread")

        assert result is True
        thread_manager.redis_client.delete.assert_called()


class TestProcessAgentTurn:
    """Test the main agent turn processing task."""

    @pytest.mark.asyncio
    async def test_process_agent_turn_success(self):
        """Test successful agent turn processing."""
        with (
            patch("redis_sre_agent.core.tasks.get_thread_manager") as mock_get_manager,
            patch("redis_sre_agent.agent.get_sre_agent") as mock_get_agent,
            patch("redis_sre_agent.core.tasks.run_agent_with_progress") as mock_run_agent,
        ):
            # Mock thread manager
            mock_manager = AsyncMock()
            mock_manager.get_thread_state.return_value = ThreadState(
                thread_id="test_thread",
                status=ThreadStatus.QUEUED,
                context={"messages": []},
                metadata=ThreadMetadata(),
            )
            mock_manager.update_thread_status.return_value = True
            mock_manager.add_thread_update.return_value = True
            mock_manager.set_thread_result.return_value = True
            mock_manager.add_action_items.return_value = True
            mock_get_manager.return_value = mock_manager

            # Mock agent
            mock_agent = AsyncMock()
            mock_get_agent.return_value = mock_agent

            # Mock agent response
            mock_run_agent.return_value = {
                "response": "Test response from agent",
                "metadata": {"iterations": 2},
                "action_items": [{"title": "Test action", "description": "Test description"}],
            }

            # Execute the task
            result = await process_agent_turn(
                thread_id="test_thread", message="Test message", context={"test": "context"}
            )

            # Verify result
            assert result["response"] == "Test response from agent"
            assert result["metadata"]["iterations"] == 2
            assert len(result["action_items"]) == 1

            # Verify manager calls
            mock_manager.update_thread_status.assert_called()
            mock_manager.add_thread_update.assert_called()
            mock_manager.set_thread_result.assert_called()

    @pytest.mark.asyncio
    async def test_process_agent_turn_thread_not_found(self):
        """Test agent turn processing with non-existent thread."""
        with patch("redis_sre_agent.core.tasks.get_thread_manager") as mock_get_manager:
            mock_manager = AsyncMock()
            mock_manager.get_thread_state.return_value = None
            mock_manager.update_thread_status.return_value = True
            mock_manager.add_thread_update.return_value = True
            mock_manager.set_thread_error.return_value = True
            mock_get_manager.return_value = mock_manager

            with pytest.raises(ValueError, match="Thread test_thread not found"):
                await process_agent_turn(thread_id="test_thread", message="Test message")

    @pytest.mark.asyncio
    async def test_process_agent_turn_agent_error(self):
        """Test agent turn processing with agent error."""
        with (
            patch("redis_sre_agent.core.tasks.get_thread_manager") as mock_get_manager,
            patch("redis_sre_agent.agent.get_sre_agent") as mock_get_agent,
            patch("redis_sre_agent.core.tasks.run_agent_with_progress") as mock_run_agent,
        ):
            # Mock thread manager
            mock_manager = AsyncMock()
            mock_manager.get_thread_state.return_value = ThreadState(
                thread_id="test_thread",
                status=ThreadStatus.QUEUED,
                context={"messages": []},
                metadata=ThreadMetadata(),
            )
            mock_manager.update_thread_status.return_value = True
            mock_manager.add_thread_update.return_value = True
            mock_manager.set_thread_error.return_value = True
            mock_get_manager.return_value = mock_manager

            # Mock agent
            mock_agent = AsyncMock()
            mock_get_agent.return_value = mock_agent

            # Mock agent error
            mock_run_agent.side_effect = Exception("Agent processing failed")

            # Execute the task and expect it to raise
            with pytest.raises(Exception, match="Agent processing failed"):
                await process_agent_turn(thread_id="test_thread", message="Test message")

            # Verify error handling
            mock_manager.set_thread_error.assert_called()


class TestActionItemExtraction:
    """Test action item extraction from agent responses."""

    def test_extract_action_items_basic(self):
        """Test basic action item extraction."""
        response = """
        Based on the analysis, here are the action items:
        1. Check Redis memory usage
        2. Review slow query log
        3. Optimize key expiration settings
        """

        items = extract_action_items_from_response(response)

        assert len(items) >= 2  # Should find at least 2 items
        assert any("memory usage" in item["title"].lower() for item in items)
        assert any("slow query" in item["title"].lower() for item in items)

    def test_extract_action_items_recommendations(self):
        """Test action item extraction with recommendations section."""
        response = """
        Analysis complete.

        Recommendations:
        - Increase Redis max memory setting
        - Enable memory eviction policy
        - Monitor key patterns for optimization

        Additional context...
        """

        items = extract_action_items_from_response(response)

        assert len(items) >= 2
        assert any("memory setting" in item["title"].lower() for item in items)
        assert any("eviction policy" in item["title"].lower() for item in items)

    def test_extract_action_items_no_items(self):
        """Test action item extraction with no action items."""
        response = "This is just a regular response with no action items or recommendations."

        items = extract_action_items_from_response(response)

        assert len(items) == 0

    def test_extract_action_items_mixed_case(self):
        """Test action item extraction with mixed case."""
        response = """
        Next Steps:
        * Check the configuration file
        * Restart the Redis service
        TODO:
        + Verify backup procedures
        """

        items = extract_action_items_from_response(response)

        assert len(items) >= 2
        assert any("configuration" in item["title"].lower() for item in items)
        assert any("restart" in item["title"].lower() for item in items)


class TestThreadStateModels:
    """Test thread state model functionality."""

    def test_thread_update_creation(self):
        """Test ThreadUpdate model creation."""
        update = ThreadUpdate(
            message="Test update", update_type="progress", metadata={"tool": "test_tool"}
        )

        assert update.message == "Test update"
        assert update.update_type == "progress"
        assert update.metadata["tool"] == "test_tool"
        assert update.timestamp is not None

    def test_thread_action_item_creation(self):
        """Test ThreadActionItem model creation."""
        item = ThreadActionItem(
            title="Test Action",
            description="Test description",
            priority="high",
            category="investigation",
        )

        assert item.title == "Test Action"
        assert item.description == "Test description"
        assert item.priority == "high"
        assert item.category == "investigation"
        assert item.completed is False
        assert item.id is not None

    def test_thread_state_creation(self):
        """Test ThreadState model creation."""
        state = ThreadState(
            thread_id="test_thread",
            status=ThreadStatus.IN_PROGRESS,
            context={"query": "test"},
            updates=[ThreadUpdate(message="Test update")],
            action_items=[ThreadActionItem(title="Test", description="Test")],
        )

        assert state.thread_id == "test_thread"
        assert state.status == ThreadStatus.IN_PROGRESS
        assert state.context["query"] == "test"
        assert len(state.updates) == 1
        assert len(state.action_items) == 1
        assert state.result is None
        assert state.error_message is None

    def test_thread_metadata_defaults(self):
        """Test ThreadMetadata default values."""
        metadata = ThreadMetadata()

        assert metadata.created_at is not None
        assert metadata.updated_at is not None
        assert metadata.user_id is None
        assert metadata.session_id is None
        assert metadata.priority == 0
        assert metadata.tags == []


class TestThreadManagerSingleton:
    """Test thread manager singleton functionality."""

    def test_get_thread_manager_singleton(self):
        """Test that get_thread_manager returns the same instance."""
        manager1 = get_thread_manager()
        manager2 = get_thread_manager()

        assert manager1 is manager2
        assert isinstance(manager1, ThreadManager)
