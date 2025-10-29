"""Tests for thread management and async task execution."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from redis_sre_agent.core.docket_tasks import process_agent_turn
from redis_sre_agent.core.threads import (
    Thread,
    ThreadManager,
    ThreadMetadata,
    ThreadUpdate,
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
        manager._redis_client = mock_redis_client
        return manager

    @pytest.mark.asyncio
    async def test_create_thread(self, thread_manager):
        """Test thread creation."""
        with (
            patch.object(thread_manager, "_save_thread_state", return_value=True) as mock_save,
            patch.object(
                thread_manager, "_upsert_thread_search_doc", new=AsyncMock(return_value=True)
            ),
        ):
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
        thread_manager._redis_client.exists.return_value = False

        state = await thread_manager.get_thread("nonexistent")
        assert state is None

    @pytest.mark.asyncio
    async def test_get_thread_state_success(self, thread_manager):
        """Test successful thread state retrieval."""
        # Mock Redis data
        thread_manager._redis_client.exists.return_value = True
        thread_manager._redis_client.get.side_effect = [
            None,  # result
            None,  # error
        ]
        thread_manager._redis_client.lrange.return_value = [
            json.dumps(
                {
                    "timestamp": "2023-01-01T00:00:00Z",
                    "message": "Test update",
                    "update_type": "progress",
                    "metadata": None,
                }
            )
        ]
        thread_manager._redis_client.hgetall.side_effect = [
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

        state = await thread_manager.get_thread("test_thread")

        assert state is not None
        assert len(state.updates) == 1
        assert state.updates[0].message == "Test update"
        assert state.metadata.user_id == "test_user"

    @pytest.mark.asyncio
    async def test_add_thread_update(self, thread_manager):
        """Test adding thread updates."""
        result = await thread_manager.add_thread_update(
            "test_thread", "Test progress message", "progress", {"tool": "test_tool"}
        )

        assert result is True
        thread_manager._redis_client.lpush.assert_called()
        thread_manager._redis_client.ltrim.assert_called()

    @pytest.mark.asyncio
    async def test_set_thread_result(self, thread_manager):
        """Test setting thread result."""
        result_data = {"response": "Test response", "metadata": {}}

        result = await thread_manager.set_thread_result("test_thread", result_data)

        assert result is True
        thread_manager._redis_client.set.assert_called()

    @pytest.mark.asyncio
    @pytest.mark.asyncio
    async def test_delete_thread(self, thread_manager):
        """Test thread deletion."""
        result = await thread_manager.delete_thread("test_thread")

        assert result is True
        thread_manager._redis_client.delete.assert_called()


class TestProcessAgentTurn:
    """Test the main agent turn processing task."""

    @pytest.mark.asyncio
    async def test_process_agent_turn_success(self):
        """Test successful agent turn processing."""
        with (
            patch("redis_sre_agent.core.docket_tasks.get_redis_client") as mock_get_redis,
            patch("redis_sre_agent.core.docket_tasks.ThreadManager") as mock_manager_class,
            patch("redis_sre_agent.agent.get_sre_agent") as mock_get_agent,
            patch("redis_sre_agent.core.docket_tasks.run_agent_with_progress") as mock_run_agent,
            patch(
                "redis_sre_agent.agent.knowledge_agent.get_knowledge_agent"
            ) as mock_get_knowledge_agent,
            patch("redis_sre_agent.core.docket_tasks.route_to_appropriate_agent") as mock_route,
        ):
            # Mock Redis client
            mock_redis = AsyncMock()
            mock_get_redis.return_value = mock_redis

            # Mock thread manager
            mock_manager = AsyncMock()
            mock_manager_class.return_value = mock_manager
            mock_manager.get_thread.return_value = Thread(
                thread_id="test_thread",
                context={"messages": []},
                metadata=ThreadMetadata(),
            )
            mock_manager.add_thread_update.return_value = True
            mock_manager.set_thread_result.return_value = True

            # Mock routing to use Redis-focused agent (not knowledge-only)
            from redis_sre_agent.agent.router import AgentType

            # Make the mock async
            async def mock_route_func(*args, **kwargs):
                return AgentType.REDIS_FOCUSED

            mock_route.side_effect = mock_route_func

            # Mock agent
            mock_agent = AsyncMock()
            mock_get_agent.return_value = mock_agent

            # Mock knowledge agent (in case routing changes)
            mock_knowledge_agent = AsyncMock()
            mock_knowledge_agent.process_query.return_value = "Test response from agent"
            mock_get_knowledge_agent.return_value = mock_knowledge_agent

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

            # Verify manager calls
            mock_manager.add_thread_update.assert_called()
            mock_manager.set_thread_result.assert_called()

    @pytest.mark.asyncio
    async def test_process_agent_turn_thread_not_found(self):
        """Test agent turn processing with non-existent thread."""
        with (
            patch("redis_sre_agent.core.docket_tasks.get_redis_client") as mock_get_redis,
            patch("redis_sre_agent.core.docket_tasks.ThreadManager") as mock_manager_class,
        ):
            mock_redis = AsyncMock()
            mock_get_redis.return_value = mock_redis

            mock_manager = AsyncMock()
            mock_manager_class.return_value = mock_manager
            mock_manager.get_thread.return_value = None
            mock_manager.add_thread_update.return_value = True
            mock_manager.set_thread_error.return_value = True

            with pytest.raises(ValueError, match="Thread test_thread not found"):
                await process_agent_turn(thread_id="test_thread", message="Test message")

    @pytest.mark.asyncio
    async def test_process_agent_turn_agent_error(self):
        """Test agent turn processing with agent error."""
        with (
            patch("redis_sre_agent.core.docket_tasks.ThreadManager") as mock_thread_manager_class,
            patch("redis_sre_agent.core.docket_tasks.TaskManager") as mock_task_manager_class,
            patch("redis_sre_agent.agent.get_sre_agent") as mock_get_agent,
            patch("redis_sre_agent.core.docket_tasks.run_agent_with_progress") as mock_run_agent,
            patch(
                "redis_sre_agent.agent.knowledge_agent.get_knowledge_agent"
            ) as mock_get_knowledge_agent,
            patch("redis_sre_agent.core.docket_tasks.route_to_appropriate_agent") as mock_route,
        ):
            # Mock thread manager
            mock_manager = AsyncMock()
            mock_manager.get_thread.return_value = Thread(
                thread_id="test_thread",
                context={"messages": []},
                metadata=ThreadMetadata(),
            )
            mock_manager.add_thread_update.return_value = True
            mock_manager.set_thread_error.return_value = True
            mock_thread_manager_class.return_value = mock_manager

            # Mock task manager to avoid real Redis writes
            mock_task_manager = AsyncMock()
            mock_task_manager.create_task.return_value = "task-1"
            mock_task_manager.update_task_status.return_value = True
            mock_task_manager.add_task_update.return_value = True
            mock_task_manager.set_task_error.return_value = True
            mock_task_manager.get_task_state.return_value = None
            mock_task_manager_class.return_value = mock_task_manager

            # Mock routing to use Redis-focused agent (not knowledge-only)
            from redis_sre_agent.agent.router import AgentType

            # Make the mock async
            async def mock_route_func(*args, **kwargs):
                return AgentType.REDIS_FOCUSED

            mock_route.side_effect = mock_route_func

            # Mock agent
            mock_agent = AsyncMock()
            mock_get_agent.return_value = mock_agent

            # Mock knowledge agent (in case routing changes)
            mock_knowledge_agent = AsyncMock()
            mock_get_knowledge_agent.return_value = mock_knowledge_agent

            # Mock agent error
            mock_run_agent.side_effect = Exception("Agent processing failed")

            # Execute the task and expect it to raise
            with pytest.raises(Exception, match="Agent processing failed"):
                await process_agent_turn(thread_id="test_thread", message="Test message")

            # Verify error handling
            mock_manager.set_thread_error.assert_called()


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

    def test_thread_state_creation(self):
        """Test ThreadState model creation."""
        state = Thread(
            thread_id="test_thread",
            context={"query": "test"},
            updates=[ThreadUpdate(message="Test update")],
        )

        assert state.thread_id == "test_thread"
        assert state.context["query"] == "test"
        assert len(state.updates) == 1
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

    def test_thread_manager_instantiation(self):
        """Test that ThreadManager can be instantiated with a Redis client."""
        from unittest.mock import MagicMock

        mock_redis = MagicMock()
        manager = ThreadManager(redis_client=mock_redis)

        assert manager is not None
        assert isinstance(manager, ThreadManager)
        assert manager._redis_client == mock_redis
