"""Tests for thread management and async task execution."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from redis_sre_agent.core.docket_tasks import process_agent_turn
from redis_sre_agent.core.threads import (
    Message,
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
        thread_manager._redis_client.lrange.return_value = [
            json.dumps(
                {
                    "role": "user",
                    "content": "Test message",
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
        assert len(state.messages) == 1
        assert state.messages[0].content == "Test message"
        assert state.messages[0].role == "user"
        assert state.metadata.user_id == "test_user"

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
                messages=[],
                context={},
                metadata=ThreadMetadata(),
            )
            mock_manager._save_thread_state.return_value = True

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

            # Verify thread manager saved state
            mock_manager._save_thread_state.assert_called()

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
            mock_manager.append_messages.return_value = True
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

            # Verify error handling - now uses task_manager.set_task_error
            mock_task_manager.set_task_error.assert_called()


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
        """Test Thread model creation."""
        from redis_sre_agent.core.threads import Message

        state = Thread(
            thread_id="test_thread",
            context={"query": "test"},
            messages=[Message(role="user", content="Test message")],
        )

        assert state.thread_id == "test_thread"
        assert state.context["query"] == "test"
        assert len(state.messages) == 1
        assert state.messages[0].content == "Test message"
        assert state.messages[0].role == "user"

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
        mock_redis = MagicMock()
        manager = ThreadManager(redis_client=mock_redis)

        assert manager is not None
        assert isinstance(manager, ThreadManager)
        assert manager._redis_client == mock_redis


class TestGenerateThreadSubject:
    """Test thread subject generation."""

    @pytest.fixture
    def thread_manager(self):
        """Create thread manager with mocked Redis."""
        mock_redis = AsyncMock()
        manager = ThreadManager(redis_client=mock_redis)
        return manager

    @pytest.mark.asyncio
    async def test_generate_thread_subject_success(self, thread_manager):
        """Test successful subject generation via OpenAI."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Redis memory at 95%"

        with patch("redis_sre_agent.core.threads.AsyncOpenAI") as mock_openai:
            mock_client = AsyncMock()
            mock_openai.return_value = mock_client
            mock_client.chat.completions.create.return_value = mock_response

            subject = await thread_manager._generate_thread_subject(
                "My Redis server is running out of memory"
            )

            assert subject == "Redis memory at 95%"
            mock_client.chat.completions.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_thread_subject_strips_quotes(self, thread_manager):
        """Test that quotes are stripped from generated subject."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '"Redis memory issue"'

        with patch("redis_sre_agent.core.threads.AsyncOpenAI") as mock_openai:
            mock_client = AsyncMock()
            mock_openai.return_value = mock_client
            mock_client.chat.completions.create.return_value = mock_response

            subject = await thread_manager._generate_thread_subject("test query")
            assert subject == "Redis memory issue"

    @pytest.mark.asyncio
    async def test_generate_thread_subject_truncates_long_subject(self, thread_manager):
        """Test that subject is truncated to 50 characters."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "A" * 100

        with patch("redis_sre_agent.core.threads.AsyncOpenAI") as mock_openai:
            mock_client = AsyncMock()
            mock_openai.return_value = mock_client
            mock_client.chat.completions.create.return_value = mock_response

            subject = await thread_manager._generate_thread_subject("test query")
            assert len(subject) == 50

    @pytest.mark.asyncio
    async def test_generate_thread_subject_fallback_on_error(self, thread_manager):
        """Test fallback to truncated original message on error."""
        with patch("redis_sre_agent.core.threads.AsyncOpenAI") as mock_openai:
            mock_client = AsyncMock()
            mock_openai.return_value = mock_client
            mock_client.chat.completions.create.side_effect = Exception("API error")

            original = "This is a test query for Redis troubleshooting"
            subject = await thread_manager._generate_thread_subject(original)
            assert subject == original[:50].strip()

    @pytest.mark.asyncio
    async def test_generate_thread_subject_long_original_fallback(self, thread_manager):
        """Test fallback adds ellipsis for long messages."""
        with patch("redis_sre_agent.core.threads.AsyncOpenAI") as mock_openai:
            mock_client = AsyncMock()
            mock_openai.return_value = mock_client
            mock_client.chat.completions.create.side_effect = Exception("API error")

            original = "A" * 100
            subject = await thread_manager._generate_thread_subject(original)
            assert subject.endswith("...")
            assert len(subject) == 53  # 50 chars + "..."


class TestUpdateThreadSubject:
    """Test update_thread_subject method."""

    @pytest.fixture
    def thread_manager(self):
        """Create thread manager with mocked Redis."""
        mock_redis = AsyncMock()
        mock_redis.hset.return_value = True
        manager = ThreadManager(redis_client=mock_redis)
        return manager

    @pytest.mark.asyncio
    async def test_update_thread_subject_success(self, thread_manager):
        """Test successful thread subject update."""
        with (
            patch.object(
                thread_manager, "_generate_thread_subject", return_value="Generated subject"
            ),
            patch.object(thread_manager, "_upsert_thread_search_doc", return_value=True),
        ):
            result = await thread_manager.update_thread_subject("thread-1", "test message")
            assert result is True
            thread_manager._redis_client.hset.assert_called()

    @pytest.mark.asyncio
    async def test_update_thread_subject_failure(self, thread_manager):
        """Test thread subject update failure."""
        with patch.object(
            thread_manager, "_generate_thread_subject", side_effect=Exception("Error")
        ):
            result = await thread_manager.update_thread_subject("thread-1", "test message")
            assert result is False


class TestSetThreadSubject:
    """Test set_thread_subject method."""

    @pytest.fixture
    def thread_manager(self):
        """Create thread manager with mocked Redis."""
        mock_redis = AsyncMock()
        mock_redis.hset.return_value = True
        manager = ThreadManager(redis_client=mock_redis)
        return manager

    @pytest.mark.asyncio
    async def test_set_thread_subject_success(self, thread_manager):
        """Test successful explicit subject setting."""
        with patch.object(thread_manager, "_upsert_thread_search_doc", return_value=True):
            result = await thread_manager.set_thread_subject("thread-1", "My custom subject")
            assert result is True
            thread_manager._redis_client.hset.assert_called()

    @pytest.mark.asyncio
    async def test_set_thread_subject_empty(self, thread_manager):
        """Test setting empty subject."""
        with patch.object(thread_manager, "_upsert_thread_search_doc", return_value=True):
            result = await thread_manager.set_thread_subject("thread-1", "")
            assert result is True

    @pytest.mark.asyncio
    async def test_set_thread_subject_failure(self, thread_manager):
        """Test subject setting failure."""
        thread_manager._redis_client.hset.side_effect = Exception("Redis error")
        result = await thread_manager.set_thread_subject("thread-1", "subject")
        assert result is False


class TestUpsertThreadSearchDoc:
    """Test _upsert_thread_search_doc method."""

    @pytest.fixture
    def thread_manager(self):
        """Create thread manager with mocked Redis."""
        mock_redis = AsyncMock()
        mock_redis.hgetall.return_value = {
            b"subject": b"Test subject",
            b"user_id": b"user-1",
            b"created_at": b"2024-01-01T00:00:00+00:00",
            b"updated_at": b"2024-01-01T00:00:00+00:00",
            b"tags": b'["tag1", "tag2"]',
            b"priority": b"1",
        }
        mock_redis.hset.return_value = True
        mock_redis.expire.return_value = True
        manager = ThreadManager(redis_client=mock_redis)
        return manager

    @pytest.mark.asyncio
    async def test_upsert_thread_search_doc_success(self, thread_manager):
        """Test successful search doc upsert."""
        with patch("redis_sre_agent.core.threads.get_threads_index") as mock_get_index:
            mock_index = AsyncMock()
            mock_index.exists.return_value = True
            mock_get_index.return_value = mock_index

            result = await thread_manager._upsert_thread_search_doc("thread-1")
            assert result is True
            thread_manager._redis_client.hset.assert_called()
            thread_manager._redis_client.expire.assert_called()

    @pytest.mark.asyncio
    async def test_upsert_thread_search_doc_creates_index_if_missing(self, thread_manager):
        """Test that index is created if it doesn't exist."""
        with patch("redis_sre_agent.core.threads.get_threads_index") as mock_get_index:
            mock_index = AsyncMock()
            mock_index.exists.return_value = False
            mock_index.create.return_value = True
            mock_get_index.return_value = mock_index

            result = await thread_manager._upsert_thread_search_doc("thread-1")
            assert result is True
            mock_index.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_upsert_thread_search_doc_handles_invalid_tags(self, thread_manager):
        """Test handling of invalid tags format."""
        thread_manager._redis_client.hgetall.return_value = {
            b"tags": b"not-json-list",
            b"priority": b"invalid",
        }

        with patch("redis_sre_agent.core.threads.get_threads_index") as mock_get_index:
            mock_index = AsyncMock()
            mock_index.exists.return_value = True
            mock_get_index.return_value = mock_index

            result = await thread_manager._upsert_thread_search_doc("thread-1")
            assert result is True

    @pytest.mark.asyncio
    async def test_upsert_thread_search_doc_failure(self, thread_manager):
        """Test search doc upsert failure."""
        thread_manager._redis_client.hgetall.side_effect = Exception("Redis error")

        result = await thread_manager._upsert_thread_search_doc("thread-1")
        assert result is False



class TestListThreads:
    """Test list_threads method."""

    @pytest.fixture
    def thread_manager(self):
        """Create thread manager with mocked Redis."""
        mock_redis = AsyncMock()
        manager = ThreadManager(redis_client=mock_redis)
        return manager

    @pytest.mark.asyncio
    async def test_list_threads_success(self, thread_manager):
        """Test successful thread listing."""
        # list_threads queries index and returns List[Dict], not tuple
        mock_doc = {
            "id": "sre_threads:thread-1",
            "subject": "Test subject",
            "user_id": "user-1",
            "instance_id": "instance-1",
            "created_at": "1704067200.0",
            "updated_at": "1704067200.0",
            "tags": "tag1,tag2",
            "priority": "1",
        }

        with patch("redis_sre_agent.core.threads.get_threads_index") as mock_get_index:
            mock_index = AsyncMock()
            mock_index.query.return_value = [mock_doc]
            mock_get_index.return_value = mock_index

            threads = await thread_manager.list_threads()
            assert len(threads) == 1
            assert threads[0]["thread_id"] == "thread-1"

    @pytest.mark.asyncio
    async def test_list_threads_with_user_filter(self, thread_manager):
        """Test thread listing with user_id filter."""
        with patch("redis_sre_agent.core.threads.get_threads_index") as mock_get_index:
            mock_index = AsyncMock()
            mock_index.query.return_value = []
            mock_get_index.return_value = mock_index

            threads = await thread_manager.list_threads(user_id="user-1")
            assert threads == []
            # Check query was called
            mock_index.query.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_threads_empty_result(self, thread_manager):
        """Test thread listing with empty results."""
        with patch("redis_sre_agent.core.threads.get_threads_index") as mock_get_index:
            mock_index = AsyncMock()
            mock_index.query.return_value = []
            mock_get_index.return_value = mock_index

            threads = await thread_manager.list_threads()
            assert threads == []

    @pytest.mark.asyncio
    async def test_list_threads_handles_object_results(self, thread_manager):
        """Test thread listing handles result objects (not dicts)."""
        mock_doc = MagicMock()
        mock_doc.__dict__ = {
            "id": "sre_threads:thread-1",
            "subject": "Test subject",
            "user_id": "user-1",
            "instance_id": "instance-1",
            "priority": "1",
            "created_at": "1704067200.0",
            "updated_at": "1704067200.0",
        }

        with patch("redis_sre_agent.core.threads.get_threads_index") as mock_get_index:
            mock_index = AsyncMock()
            mock_index.query.return_value = [mock_doc]
            mock_get_index.return_value = mock_index

            threads = await thread_manager.list_threads()
            assert len(threads) == 1


class TestUpdateThreadContext:
    """Test update_thread_context method."""

    @pytest.fixture
    def thread_manager(self):
        """Create thread manager with mocked Redis."""
        mock_redis = AsyncMock()
        mock_redis.hgetall.return_value = {b"existing_key": b"existing_value"}
        mock_redis.hset.return_value = True
        mock_redis.delete.return_value = True
        manager = ThreadManager(redis_client=mock_redis)
        return manager

    @pytest.mark.asyncio
    async def test_update_thread_context_merge(self, thread_manager):
        """Test context update with merge strategy."""
        result = await thread_manager.update_thread_context(
            "thread-1", {"new_key": "new_value"}, merge=True
        )
        assert result is True
        thread_manager._redis_client.hgetall.assert_called()

    @pytest.mark.asyncio
    async def test_update_thread_context_replace(self, thread_manager):
        """Test context update with replace strategy (clears and replaces)."""
        result = await thread_manager.update_thread_context(
            "thread-1", {"new_key": "new_value"}, merge=False
        )
        assert result is True
        # When merge=False, delete is called on context key
        thread_manager._redis_client.delete.assert_called()

    @pytest.mark.asyncio
    async def test_update_thread_context_with_complex_values(self, thread_manager):
        """Test context update with dict and list values."""
        result = await thread_manager.update_thread_context(
            "thread-1",
            {"dict_key": {"nested": "value"}, "list_key": [1, 2, 3], "null_key": None},
            merge=True,
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_update_thread_context_failure(self, thread_manager):
        """Test context update failure."""
        thread_manager._redis_client.hgetall.side_effect = Exception("Redis error")
        result = await thread_manager.update_thread_context(
            "thread-1", {"key": "value"}
        )
        assert result is False


class TestAppendMessages:
    """Test append_messages method."""

    @pytest.fixture
    def thread_manager(self):
        """Create thread manager with mocked Redis."""
        mock_redis = AsyncMock()
        mock_redis.rpush.return_value = 1
        mock_redis.hset.return_value = True
        manager = ThreadManager(redis_client=mock_redis)
        return manager

    @pytest.mark.asyncio
    async def test_append_messages_success(self, thread_manager):
        """Test successful message append."""
        # append_messages expects List[Dict], not Message objects
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
        ]
        with patch.object(thread_manager, "_upsert_thread_search_doc", return_value=True):
            result = await thread_manager.append_messages("thread-1", messages)
            assert result is True
            assert thread_manager._redis_client.rpush.call_count == 2

    @pytest.mark.asyncio
    async def test_append_messages_skips_empty_content(self, thread_manager):
        """Test that messages without content are skipped."""
        messages = [
            {"role": "user", "content": ""},  # empty content
            {"role": "user", "content": "Valid"},
        ]
        with patch.object(thread_manager, "_upsert_thread_search_doc", return_value=True):
            result = await thread_manager.append_messages("thread-1", messages)
            assert result is True
            # Only the valid message should be pushed
            assert thread_manager._redis_client.rpush.call_count == 1

    @pytest.mark.asyncio
    async def test_append_messages_normalizes_role(self, thread_manager):
        """Test that invalid roles are normalized to 'user'."""
        messages = [{"role": "invalid_role", "content": "Test"}]
        with patch.object(thread_manager, "_upsert_thread_search_doc", return_value=True):
            result = await thread_manager.append_messages("thread-1", messages)
            assert result is True

    @pytest.mark.asyncio
    async def test_append_messages_failure(self, thread_manager):
        """Test message append failure."""
        thread_manager._redis_client.rpush.side_effect = Exception("Redis error")
        messages = [{"role": "user", "content": "Hello"}]
        result = await thread_manager.append_messages("thread-1", messages)
        assert result is False


class TestSaveThreadState:
    """Test _save_thread_state method."""

    def _create_pipeline_mock(self):
        """Create a proper async context manager mock for pipeline."""
        mock_pipeline = MagicMock()
        mock_pipeline.delete = MagicMock()
        mock_pipeline.rpush = MagicMock()
        mock_pipeline.hset = MagicMock()
        mock_pipeline.expire = MagicMock()
        mock_pipeline.execute = AsyncMock(return_value=[True] * 10)

        # Create an object that acts as an async context manager
        class AsyncContextManager:
            async def __aenter__(self):
                return mock_pipeline

            async def __aexit__(self, *args):
                return None

        return AsyncContextManager()

    @pytest.fixture
    def thread_manager(self):
        """Create thread manager with mocked Redis."""
        # Use MagicMock for the redis client so pipeline() doesn't return a coroutine
        mock_redis = MagicMock()
        manager = ThreadManager(redis_client=mock_redis)
        return manager

    @pytest.mark.asyncio
    async def test_save_thread_state_success(self, thread_manager):
        """Test successful thread state save."""
        # pipeline() must return an async context manager directly (not a coroutine)
        thread_manager._redis_client.pipeline.return_value = self._create_pipeline_mock()

        thread = Thread(
            thread_id="thread-1",
            messages=[Message(role="user", content="Hello")],
            context={"key": "value"},
            metadata=ThreadMetadata(user_id="user-1"),
        )

        result = await thread_manager._save_thread_state(thread)
        assert result is True
        thread_manager._redis_client.pipeline.assert_called()

    @pytest.mark.asyncio
    async def test_save_thread_state_with_complex_context(self, thread_manager):
        """Test saving thread with complex context values."""
        thread_manager._redis_client.pipeline.return_value = self._create_pipeline_mock()

        thread = Thread(
            thread_id="thread-1",
            messages=[],
            context={"dict_val": {"nested": True}, "list_val": [1, 2, 3], "none_val": None},
            metadata=ThreadMetadata(),
        )

        result = await thread_manager._save_thread_state(thread)
        assert result is True

    @pytest.mark.asyncio
    async def test_save_thread_state_failure(self, thread_manager):
        """Test thread state save failure."""

        class FailingContextManager:
            async def __aenter__(self):
                raise Exception("Redis error")

            async def __aexit__(self, *args):
                return None

        thread_manager._redis_client.pipeline.return_value = FailingContextManager()

        thread = Thread(
            thread_id="thread-1",
            messages=[],
            context={},
            metadata=ThreadMetadata(),
        )

        result = await thread_manager._save_thread_state(thread)
        assert result is False


class TestRemoveFromThreadIndex:
    """Test _remove_from_thread_index method."""

    @pytest.fixture
    def thread_manager(self):
        """Create thread manager with mocked Redis."""
        mock_redis = AsyncMock()
        mock_redis.zrem.return_value = 1
        manager = ThreadManager(redis_client=mock_redis)
        return manager

    @pytest.mark.asyncio
    async def test_remove_from_thread_index_success(self, thread_manager):
        """Test successful removal from thread index."""
        result = await thread_manager._remove_from_thread_index("thread-1")
        assert result is True
        thread_manager._redis_client.zrem.assert_called()

    @pytest.mark.asyncio
    async def test_remove_from_thread_index_with_user_id(self, thread_manager):
        """Test removal with user_id also removes from user index."""
        result = await thread_manager._remove_from_thread_index("thread-1", user_id="user-1")
        assert result is True
        # zrem should be called twice (global index and user index)
        assert thread_manager._redis_client.zrem.call_count == 2

    @pytest.mark.asyncio
    async def test_remove_from_thread_index_failure(self, thread_manager):
        """Test removal failure."""
        thread_manager._redis_client.zrem.side_effect = Exception("Redis error")
        result = await thread_manager._remove_from_thread_index("thread-1")
        assert result is False


class TestDeleteThread:
    """Test delete_thread method additional cases."""

    @pytest.fixture
    def thread_manager(self):
        """Create thread manager with mocked Redis."""
        mock_redis = AsyncMock()
        mock_redis.hgetall.return_value = {b"user_id": b"user-1"}
        mock_redis.delete.return_value = 3
        mock_redis.zrem.return_value = 1
        manager = ThreadManager(redis_client=mock_redis)
        return manager

    @pytest.mark.asyncio
    async def test_delete_thread_with_index_removal(self, thread_manager):
        """Test thread deletion with index removal."""
        result = await thread_manager.delete_thread("thread-1")
        assert result is True
        # delete is called twice: once for thread keys, once for search doc
        assert thread_manager._redis_client.delete.call_count >= 1
        # zrem is called for index cleanup
        thread_manager._redis_client.zrem.assert_called()

    @pytest.mark.asyncio
    async def test_delete_thread_without_user_id(self, thread_manager):
        """Test thread deletion when no user_id in metadata."""
        thread_manager._redis_client.hgetall.return_value = {}
        result = await thread_manager.delete_thread("thread-1")
        assert result is True

    @pytest.mark.asyncio
    async def test_delete_thread_failure(self, thread_manager):
        """Test thread deletion failure."""
        thread_manager._redis_client.hgetall.side_effect = Exception("Redis error")
        result = await thread_manager.delete_thread("thread-1")
        assert result is False


class TestGetThreadEdgeCases:
    """Test get_thread edge cases."""

    @pytest.fixture
    def thread_manager(self):
        """Create thread manager with mocked Redis."""
        mock_redis = AsyncMock()
        mock_redis.exists.return_value = True
        manager = ThreadManager(redis_client=mock_redis)
        return manager

    @pytest.mark.asyncio
    async def test_get_thread_with_complex_message(self, thread_manager):
        """Test getting thread with complex message structure."""
        thread_manager._redis_client.lrange.return_value = [
            json.dumps({
                "role": "assistant",
                "content": "Test response with **markdown**",
                "metadata": {"tool_calls": [{"name": "test_tool"}]},
            })
        ]
        thread_manager._redis_client.hgetall.side_effect = [
            {b"instance_id": b"instance-1", b"key": b'{"nested": "value"}'},  # context
            {
                b"created_at": b"2023-01-01T00:00:00Z",
                b"updated_at": b"2023-01-01T00:00:00Z",
                b"user_id": b"user-1",
                b"tags": b'["tag1"]',
                b"priority": b"2",
            },
        ]

        state = await thread_manager.get_thread("thread-1")
        assert state is not None
        assert state.messages[0].role == "assistant"
        # instance_id is in context, not metadata
        assert state.context.get("instance_id") == "instance-1"
        assert state.metadata.priority == 2

    @pytest.mark.asyncio
    async def test_get_thread_with_invalid_message_json(self, thread_manager):
        """Test getting thread with invalid message JSON (should skip)."""
        thread_manager._redis_client.lrange.return_value = [
            "invalid-json",
            json.dumps({"role": "user", "content": "Valid message"}),
        ]
        thread_manager._redis_client.hgetall.side_effect = [
            {},
            {
                b"created_at": b"2023-01-01T00:00:00Z",
                b"updated_at": b"2023-01-01T00:00:00Z",
            },
        ]

        state = await thread_manager.get_thread("thread-1")
        assert state is not None
        # Only the valid message should be included
        assert len(state.messages) == 1

    @pytest.mark.asyncio
    async def test_get_thread_with_empty_metadata(self, thread_manager):
        """Test getting thread with minimal metadata."""
        thread_manager._redis_client.lrange.return_value = []
        thread_manager._redis_client.hgetall.side_effect = [
            {},  # empty context
            {},  # empty metadata
        ]

        state = await thread_manager.get_thread("thread-1")
        assert state is not None
        assert state.messages == []
        assert state.context == {}



class TestModuleLevelHelpers:
    """Test module-level helper functions."""

    @pytest.mark.asyncio
    async def test_build_initial_context_basic(self):
        """Test basic context building."""
        from redis_sre_agent.core.threads import _build_initial_context

        ctx = await _build_initial_context("test query", priority=1)
        assert ctx["original_query"] == "test query"
        assert ctx["priority"] == 1
        assert ctx["messages"] == []

    @pytest.mark.asyncio
    async def test_build_initial_context_with_base_context(self):
        """Test context building with base context."""
        from redis_sre_agent.core.threads import _build_initial_context

        base = {"custom_key": "custom_value"}
        ctx = await _build_initial_context("test", base_context=base)
        assert ctx["custom_key"] == "custom_value"
        assert ctx["original_query"] == "test"

    @pytest.mark.asyncio
    async def test_build_initial_context_with_instance_id(self):
        """Test context building with instance enrichment."""
        from redis_sre_agent.core.threads import _build_initial_context

        mock_instance = MagicMock()
        mock_instance.id = "inst-1"
        mock_instance.name = "Test Instance"

        # Patch at the source module since it's a local import
        with patch(
            "redis_sre_agent.core.instances.get_instances",
            new=AsyncMock(return_value=[mock_instance]),
        ):
            ctx = await _build_initial_context("test", instance_id="inst-1")
            assert ctx["instance_id"] == "inst-1"
            assert ctx["instance_name"] == "Test Instance"

    @pytest.mark.asyncio
    async def test_build_initial_context_instance_lookup_failure(self):
        """Test context building when instance lookup fails."""
        from redis_sre_agent.core.threads import _build_initial_context

        # Patch at the source module since it's a local import
        with patch(
            "redis_sre_agent.core.instances.get_instances",
            new=AsyncMock(side_effect=Exception("DB error")),
        ):
            # Should not raise, just log and continue
            ctx = await _build_initial_context("test", instance_id="inst-1")
            assert ctx["instance_id"] == "inst-1"
            assert "instance_name" not in ctx


class TestCreateThreadFunction:
    """Test module-level create_thread function."""

    @pytest.mark.asyncio
    async def test_create_thread_success(self):
        """Test successful thread creation."""
        from redis_sre_agent.core.threads import create_thread as create_thread_fn

        mock_redis = AsyncMock()

        with (
            patch("redis_sre_agent.core.threads.ThreadManager") as mock_manager_class,
            patch(
                "redis_sre_agent.core.threads._build_initial_context",
                new=AsyncMock(return_value={"original_query": "test", "priority": 0, "messages": []}),
            ),
            patch("docket.Docket") as mock_docket,
            patch(
                "redis_sre_agent.core.docket_tasks.get_redis_url",
                new=AsyncMock(return_value="redis://localhost:6379"),
            ),
        ):
            mock_manager = AsyncMock()
            mock_manager.create_thread.return_value = "thread-123"
            mock_manager.update_thread_subject.return_value = True
            mock_manager_class.return_value = mock_manager

            # Create a proper async context manager for Docket
            class MockDocketContextManager:
                async def __aenter__(self):
                    return self

                async def __aexit__(self, *args):
                    return None

                def add(self, func):
                    # docket.add returns a callable that returns a coroutine when called
                    async def task_wrapper(**kwargs):
                        return None

                    return task_wrapper

            mock_docket.return_value = MockDocketContextManager()

            result = await create_thread_fn(query="test query", redis_client=mock_redis)

            assert result["thread_id"] == "thread-123"
            assert "message" in result
            mock_manager.create_thread.assert_called_once()


class TestContinueThreadFunction:
    """Test module-level continue_thread function."""

    @pytest.mark.asyncio
    async def test_continue_thread_success(self):
        """Test successful thread continuation."""
        from redis_sre_agent.core.threads import continue_thread as continue_thread_fn

        mock_redis = AsyncMock()

        with (
            patch("redis_sre_agent.core.threads.ThreadManager") as mock_manager_class,
            patch("docket.Docket") as mock_docket,
            patch(
                "redis_sre_agent.core.docket_tasks.get_redis_url",
                new=AsyncMock(return_value="redis://localhost:6379"),
            ),
        ):
            mock_manager = AsyncMock()
            mock_manager.get_thread.return_value = Thread(
                thread_id="thread-123",
                messages=[],
                context={},
                metadata=ThreadMetadata(),
            )
            mock_manager_class.return_value = mock_manager

            # Create a proper async context manager for Docket
            class MockDocketContextManager:
                async def __aenter__(self):
                    return self

                async def __aexit__(self, *args):
                    return None

                def add(self, func):
                    async def task_wrapper(**kwargs):
                        return None

                    return task_wrapper

            mock_docket.return_value = MockDocketContextManager()

            result = await continue_thread_fn(
                thread_id="thread-123", query="follow up", redis_client=mock_redis
            )

            assert result["thread_id"] == "thread-123"
            assert "message" in result

    @pytest.mark.asyncio
    async def test_continue_thread_not_found(self):
        """Test thread continuation when thread doesn't exist."""
        from redis_sre_agent.core.threads import continue_thread as continue_thread_fn

        mock_redis = AsyncMock()

        with patch("redis_sre_agent.core.threads.ThreadManager") as mock_manager_class:
            mock_manager = AsyncMock()
            mock_manager.get_thread.return_value = None
            mock_manager_class.return_value = mock_manager

            with pytest.raises(ValueError, match="Thread .* not found"):
                await continue_thread_fn(
                    thread_id="nonexistent", query="follow up", redis_client=mock_redis
                )


class TestCancelThreadFunction:
    """Test module-level cancel_thread function."""

    @pytest.mark.asyncio
    async def test_cancel_thread_success(self):
        """Test successful thread cancellation."""
        from redis_sre_agent.core.threads import cancel_thread as cancel_thread_fn

        mock_redis = AsyncMock()
        # Mock zrevrange to return a task_id
        mock_redis.zrevrange.return_value = [b"task-123"]

        with (
            patch("redis_sre_agent.core.threads.ThreadManager") as mock_manager_class,
            patch("redis_sre_agent.core.tasks.TaskManager") as mock_task_manager_class,
        ):
            mock_manager = AsyncMock()
            mock_manager.get_thread.return_value = Thread(
                thread_id="thread-123",
                messages=[],
                context={},
                metadata=ThreadMetadata(),
            )
            mock_manager_class.return_value = mock_manager

            mock_task_manager = AsyncMock()
            mock_task_manager.add_task_update.return_value = True
            mock_task_manager_class.return_value = mock_task_manager

            result = await cancel_thread_fn(thread_id="thread-123", redis_client=mock_redis)

            assert result["cancelled"] is True
            mock_task_manager.add_task_update.assert_called_once()

    @pytest.mark.asyncio
    async def test_cancel_thread_not_found(self):
        """Test thread cancellation when thread doesn't exist."""
        from redis_sre_agent.core.threads import cancel_thread as cancel_thread_fn

        mock_redis = AsyncMock()

        with patch("redis_sre_agent.core.threads.ThreadManager") as mock_manager_class:
            mock_manager = AsyncMock()
            mock_manager.get_thread.return_value = None
            mock_manager_class.return_value = mock_manager

            with pytest.raises(ValueError, match="Thread .* not found"):
                await cancel_thread_fn(thread_id="nonexistent", redis_client=mock_redis)


class TestDeleteThreadFunction:
    """Test module-level delete_thread function."""

    @pytest.mark.asyncio
    async def test_delete_thread_function_success(self):
        """Test successful thread deletion via module function."""
        from redis_sre_agent.core.threads import delete_thread as delete_thread_fn

        mock_redis = AsyncMock()

        with patch("redis_sre_agent.core.threads.ThreadManager") as mock_manager_class:
            mock_manager = AsyncMock()
            mock_manager.delete_thread.return_value = True
            mock_manager_class.return_value = mock_manager

            result = await delete_thread_fn(thread_id="thread-123", redis_client=mock_redis)

            assert result["deleted"] is True

    @pytest.mark.asyncio
    async def test_delete_thread_function_failure(self):
        """Test thread deletion failure via module function."""
        from redis_sre_agent.core.threads import delete_thread as delete_thread_fn

        mock_redis = AsyncMock()

        with patch("redis_sre_agent.core.threads.ThreadManager") as mock_manager_class:
            mock_manager = AsyncMock()
            mock_manager.delete_thread.return_value = False
            mock_manager_class.return_value = mock_manager

            with pytest.raises(RuntimeError, match="Failed to delete thread"):
                await delete_thread_fn(thread_id="thread-123", redis_client=mock_redis)
