"""Tests for MCP server tools."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from redis_sre_agent.mcp_server.server import (
    mcp,
    redis_sre_create_instance,
    redis_sre_database_chat,
    redis_sre_deep_triage,
    redis_sre_general_chat,
    redis_sre_get_task_status,
    redis_sre_get_thread,
    redis_sre_knowledge_query,
    redis_sre_knowledge_search,
    redis_sre_list_instances,
)


class TestMCPServerSetup:
    """Test MCP server configuration."""

    def test_mcp_server_name(self):
        """Test that the MCP server has correct name."""
        assert mcp.name == "redis-sre-agent"

    def test_mcp_server_has_instructions(self):
        """Test that the MCP server has instructions."""
        assert mcp.instructions is not None
        assert "Redis SRE Agent" in mcp.instructions

    def test_mcp_server_has_tools(self):
        """Test that all expected tools are registered."""
        tool_names = [t.name for t in mcp._tool_manager._tools.values()]
        assert "redis_sre_deep_triage" in tool_names
        assert "redis_sre_general_chat" in tool_names
        assert "redis_sre_database_chat" in tool_names
        assert "redis_sre_knowledge_search" in tool_names
        assert "redis_sre_knowledge_query" in tool_names
        assert "redis_sre_get_thread" in tool_names
        assert "redis_sre_get_task_status" in tool_names
        assert "redis_sre_list_instances" in tool_names
        assert "redis_sre_create_instance" in tool_names


class TestDeepTriageTool:
    """Test the redis_sre_deep_triage MCP tool."""

    @pytest.mark.asyncio
    async def test_deep_triage_success(self):
        """Test successful deep triage request."""
        mock_result = {
            "thread_id": "thread-123",
            "task_id": "task-456",
            "status": "queued",
            "message": "Task created",
        }

        with (
            patch("redis_sre_agent.core.redis.get_redis_client"),
            patch("redis_sre_agent.core.tasks.create_task", new_callable=AsyncMock) as mock_create,
        ):
            mock_create.return_value = mock_result

            result = await redis_sre_deep_triage(
                query="High memory usage on Redis",
                instance_id="redis-prod-1",
                user_id="user-123",
            )

            assert result["thread_id"] == "thread-123"
            assert result["task_id"] == "task-456"
            assert "status" in result
            mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_deep_triage_error_handling(self):
        """Test deep triage error handling."""
        with (
            patch("redis_sre_agent.core.redis.get_redis_client"),
            patch("redis_sre_agent.core.tasks.create_task", new_callable=AsyncMock) as mock_create,
        ):
            mock_create.side_effect = Exception("Redis connection failed")

            result = await redis_sre_deep_triage(query="Test query")

            assert result["status"] == "failed"
            assert "error" in result


class TestGeneralChatTool:
    """Test the redis_sre_general_chat MCP tool.

    Note: The chat tool creates a task and returns task_id/thread_id
    instead of running synchronously. This matches the triage pattern.
    """

    @pytest.mark.asyncio
    async def test_general_chat_creates_task(self):
        """Test that general_chat creates a task and returns task_id."""
        mock_result = {
            "thread_id": "thread-123",
            "task_id": "task-456",
            "status": "queued",
            "message": "Task created",
        }

        with (
            patch("redis_sre_agent.core.redis.get_redis_client"),
            patch("redis_sre_agent.core.tasks.create_task", new_callable=AsyncMock) as mock_create,
        ):
            mock_create.return_value = mock_result

            result = await redis_sre_general_chat(query="What's the memory usage?")

            assert result["thread_id"] == "thread-123"
            assert result["task_id"] == "task-456"
            assert "status" in result
            mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_general_chat_with_instance_id(self):
        """Test general_chat with a specific instance includes it in context."""
        mock_result = {
            "thread_id": "thread-123",
            "task_id": "task-456",
            "status": "queued",
        }

        with (
            patch("redis_sre_agent.core.redis.get_redis_client"),
            patch("redis_sre_agent.core.tasks.create_task", new_callable=AsyncMock) as mock_create,
        ):
            mock_create.return_value = mock_result

            result = await redis_sre_general_chat(query="Check status", instance_id="redis-prod-1")

            assert result["task_id"] == "task-456"
            # Verify instance_id was passed in context
            call_kwargs = mock_create.call_args.kwargs
            assert call_kwargs["context"]["instance_id"] == "redis-prod-1"

    @pytest.mark.asyncio
    async def test_general_chat_error_handling(self):
        """Test general_chat error handling."""
        with (
            patch("redis_sre_agent.core.redis.get_redis_client"),
            patch("redis_sre_agent.core.tasks.create_task", new_callable=AsyncMock) as mock_create,
        ):
            mock_create.side_effect = Exception("Redis connection failed")

            result = await redis_sre_general_chat(query="Test query")

            assert result["status"] == "failed"
            assert "error" in result


class TestDatabaseChatTool:
    """Test the redis_sre_database_chat MCP tool with category exclusion."""

    @pytest.mark.asyncio
    async def test_database_chat_excludes_all_mcp_by_default(self):
        """Test that database_chat excludes all MCP categories by default."""
        mock_result = {
            "thread_id": "thread-123",
            "task_id": "task-456",
            "status": "queued",
        }

        with (
            patch("redis_sre_agent.core.redis.get_redis_client"),
            patch("redis_sre_agent.core.tasks.create_task", new_callable=AsyncMock) as mock_create,
        ):
            mock_create.return_value = mock_result

            result = await redis_sre_database_chat(query="What's the memory usage?")

            assert result["task_id"] == "task-456"
            # Verify that exclude_mcp_categories is set in context
            call_kwargs = mock_create.call_args.kwargs
            assert "exclude_mcp_categories" in call_kwargs["context"]

    @pytest.mark.asyncio
    async def test_database_chat_with_selective_exclusion(self):
        """Test database_chat with selective category exclusion."""
        mock_result = {
            "thread_id": "thread-123",
            "task_id": "task-456",
            "status": "queued",
        }

        with (
            patch("redis_sre_agent.core.redis.get_redis_client"),
            patch("redis_sre_agent.core.tasks.create_task", new_callable=AsyncMock) as mock_create,
        ):
            mock_create.return_value = mock_result

            # Only exclude tickets and repos
            result = await redis_sre_database_chat(
                query="Check status",
                exclude_mcp_categories=["tickets", "repos"],
            )

            assert result["task_id"] == "task-456"
            call_kwargs = mock_create.call_args.kwargs
            assert call_kwargs["context"]["exclude_mcp_categories"] == ["tickets", "repos"]


class TestKnowledgeSearchTool:
    """Test the redis_sre_knowledge_search MCP tool."""

    @pytest.mark.asyncio
    async def test_knowledge_search_success(self):
        """Test successful knowledge search."""
        mock_result = {
            "results": [
                {
                    "title": "Redis Memory Management",
                    "content": "Redis uses memory...",
                    "source": "docs",
                    "category": "documentation",
                }
            ]
        }

        with patch(
            "redis_sre_agent.core.knowledge_helpers.search_knowledge_base_helper",
            new_callable=AsyncMock,
        ) as mock_search:
            mock_search.return_value = mock_result

            result = await redis_sre_knowledge_search(query="memory management", limit=5)

            assert result["query"] == "memory management"
            assert len(result["results"]) == 1
            assert result["results"][0]["title"] == "Redis Memory Management"
            mock_search.assert_called_once()

    @pytest.mark.asyncio
    async def test_knowledge_search_limit_clamped(self):
        """Test that limit is clamped to valid range."""
        with patch(
            "redis_sre_agent.core.knowledge_helpers.search_knowledge_base_helper",
            new_callable=AsyncMock,
        ) as mock_search:
            mock_search.return_value = {"results": []}

            # Test with too high limit (max is 50)
            await redis_sre_knowledge_search(query="test", limit=100)
            call_args = mock_search.call_args
            assert call_args.kwargs["limit"] == 50

            # Test with too low limit
            await redis_sre_knowledge_search(query="test", limit=0)
            call_args = mock_search.call_args
            assert call_args.kwargs["limit"] == 1

    @pytest.mark.asyncio
    async def test_knowledge_search_error_handling(self):
        """Test knowledge search error handling."""
        with patch(
            "redis_sre_agent.core.knowledge_helpers.search_knowledge_base_helper",
            new_callable=AsyncMock,
        ) as mock_search:
            mock_search.side_effect = Exception("Search failed")

            result = await redis_sre_knowledge_search(query="test")

            assert "error" in result
            assert result["results"] == []
            assert result["total_results"] == 0


class TestKnowledgeQueryTool:
    """Test the redis_sre_knowledge_query MCP tool.

    The knowledge_query tool creates a task that uses the KnowledgeOnlyAgent
    to answer questions about SRE practices and Redis.
    """

    @pytest.mark.asyncio
    async def test_knowledge_query_creates_task(self):
        """Test that knowledge_query creates a task and returns task_id."""
        mock_result = {
            "thread_id": "thread-123",
            "task_id": "task-456",
            "status": "queued",
            "message": "Task created",
        }

        with (
            patch("redis_sre_agent.core.redis.get_redis_client"),
            patch("redis_sre_agent.core.tasks.create_task", new_callable=AsyncMock) as mock_create,
        ):
            mock_create.return_value = mock_result

            result = await redis_sre_knowledge_query(query="What are Redis eviction policies?")

            assert result["thread_id"] == "thread-123"
            assert result["task_id"] == "task-456"
            assert "status" in result
            mock_create.assert_called_once()
            # Verify agent_type is set in context
            call_kwargs = mock_create.call_args.kwargs
            assert call_kwargs["context"]["agent_type"] == "knowledge"

    @pytest.mark.asyncio
    async def test_knowledge_query_error_handling(self):
        """Test knowledge_query error handling."""
        with (
            patch("redis_sre_agent.core.redis.get_redis_client"),
            patch("redis_sre_agent.core.tasks.create_task", new_callable=AsyncMock) as mock_create,
        ):
            mock_create.side_effect = Exception("Redis connection failed")

            result = await redis_sre_knowledge_query(query="Test query")

            assert result["status"] == "failed"
            assert "error" in result


class TestListInstancesTool:
    """Test the redis_sre_list_instances MCP tool."""

    @pytest.mark.asyncio
    async def test_list_instances_success(self):
        """Test successful instance listing."""
        from redis_sre_agent.core.instances import InstanceQueryResult

        mock_instance = MagicMock()
        mock_instance.id = "redis-prod-1"
        mock_instance.name = "Production Redis"
        mock_instance.environment = "production"
        mock_instance.usage = "cache"
        mock_instance.description = "Main cache"
        mock_instance.instance_type = "redis_cloud"
        mock_instance.repo_url = "https://github.com/example/repo"

        mock_result = InstanceQueryResult(
            instances=[mock_instance],
            total=1,
            limit=100,
            offset=0,
        )

        with patch(
            "redis_sre_agent.core.instances.query_instances",
            new_callable=AsyncMock,
        ) as mock_query:
            mock_query.return_value = mock_result

            result = await redis_sre_list_instances()

            assert result["total"] == 1
            assert result["instances"][0]["id"] == "redis-prod-1"
            assert result["instances"][0]["name"] == "Production Redis"
            assert result["instances"][0]["repo_url"] == "https://github.com/example/repo"

    @pytest.mark.asyncio
    async def test_list_instances_empty(self):
        """Test empty instance list."""
        from redis_sre_agent.core.instances import InstanceQueryResult

        mock_result = InstanceQueryResult(
            instances=[],
            total=0,
            limit=100,
            offset=0,
        )

        with patch(
            "redis_sre_agent.core.instances.query_instances",
            new_callable=AsyncMock,
        ) as mock_query:
            mock_query.return_value = mock_result

            result = await redis_sre_list_instances()

            assert result["total"] == 0
            assert result["instances"] == []

    @pytest.mark.asyncio
    async def test_list_instances_with_filters(self):
        """Test instance listing with filter parameters."""
        from redis_sre_agent.core.instances import InstanceQueryResult

        mock_instance = MagicMock()
        mock_instance.id = "redis-prod-1"
        mock_instance.name = "Production Redis"
        mock_instance.environment = "production"
        mock_instance.usage = "cache"
        mock_instance.description = "Main cache"
        mock_instance.instance_type = "redis_cloud"
        mock_instance.repo_url = None

        mock_result = InstanceQueryResult(
            instances=[mock_instance],
            total=1,
            limit=100,
            offset=0,
        )

        with patch(
            "redis_sre_agent.core.instances.query_instances",
            new_callable=AsyncMock,
        ) as mock_query:
            mock_query.return_value = mock_result

            result = await redis_sre_list_instances(
                environment="production",
                usage="cache",
                status="healthy",
            )

            # Verify query_instances was called with the correct parameters
            mock_query.assert_called_once()
            call_kwargs = mock_query.call_args[1]
            assert call_kwargs["environment"] == "production"
            assert call_kwargs["usage"] == "cache"
            assert call_kwargs["status"] == "healthy"

            assert result["total"] == 1
            assert result["instances"][0]["environment"] == "production"

    @pytest.mark.asyncio
    async def test_list_instances_with_search(self):
        """Test instance listing with search parameter."""
        from redis_sre_agent.core.instances import InstanceQueryResult

        mock_instance = MagicMock()
        mock_instance.id = "redis-prod-1"
        mock_instance.name = "Production Redis"
        mock_instance.environment = "production"
        mock_instance.usage = "cache"
        mock_instance.description = "Main cache"
        mock_instance.instance_type = "redis_cloud"
        mock_instance.repo_url = None

        mock_result = InstanceQueryResult(
            instances=[mock_instance],
            total=1,
            limit=100,
            offset=0,
        )

        with patch(
            "redis_sre_agent.core.instances.query_instances",
            new_callable=AsyncMock,
        ) as mock_query:
            mock_query.return_value = mock_result

            result = await redis_sre_list_instances(search="Production")

            # Verify query_instances was called with the search parameter
            mock_query.assert_called_once()
            call_kwargs = mock_query.call_args[1]
            assert call_kwargs["search"] == "Production"

            assert result["total"] == 1
            assert result["instances"][0]["name"] == "Production Redis"

    @pytest.mark.asyncio
    async def test_list_instances_error(self):
        """Test list instances error handling."""
        with patch(
            "redis_sre_agent.core.instances.query_instances",
            new_callable=AsyncMock,
        ) as mock_query:
            mock_query.side_effect = Exception("Connection failed")

            result = await redis_sre_list_instances()

            assert "error" in result
            assert result["instances"] == []


class TestCreateInstanceTool:
    """Test the redis_sre_create_instance MCP tool."""

    @pytest.mark.asyncio
    async def test_create_instance_success(self):
        """Test successful instance creation."""
        with (
            patch(
                "redis_sre_agent.core.instances.get_instances",
                new_callable=AsyncMock,
            ) as mock_get,
            patch(
                "redis_sre_agent.core.instances.save_instances",
                new_callable=AsyncMock,
            ) as mock_save,
        ):
            mock_get.return_value = []
            mock_save.return_value = True

            result = await redis_sre_create_instance(
                name="test-redis",
                connection_url="redis://localhost:6379",
                environment="development",
                usage="cache",
                description="Test instance",
            )

            assert result["status"] == "created"
            assert result["name"] == "test-redis"
            assert "id" in result

    @pytest.mark.asyncio
    async def test_create_instance_invalid_environment(self):
        """Test create instance with invalid environment."""
        result = await redis_sre_create_instance(
            name="test-redis",
            connection_url="redis://localhost:6379",
            environment="invalid",
            usage="cache",
            description="Test",
        )

        assert result["status"] == "failed"
        assert "error" in result
        assert "environment" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_create_instance_invalid_usage(self):
        """Test create instance with invalid usage."""
        result = await redis_sre_create_instance(
            name="test-redis",
            connection_url="redis://localhost:6379",
            environment="development",
            usage="invalid",
            description="Test",
        )

        assert result["status"] == "failed"
        assert "error" in result
        assert "usage" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_create_instance_duplicate_name(self):
        """Test create instance with duplicate name."""
        from unittest.mock import MagicMock

        existing = MagicMock()
        existing.name = "test-redis"

        with patch(
            "redis_sre_agent.core.instances.get_instances",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_get.return_value = [existing]

            result = await redis_sre_create_instance(
                name="test-redis",
                connection_url="redis://localhost:6379",
                environment="development",
                usage="cache",
                description="Test",
            )

            assert result["status"] == "failed"
            assert "already exists" in result["error"]


class TestGetThreadTool:
    """Test the redis_sre_get_thread MCP tool."""

    @pytest.mark.asyncio
    async def test_get_thread_success(self):
        """Test successful thread retrieval."""
        from redis_sre_agent.core.threads import Message, Thread, ThreadMetadata

        # Create a proper Thread object with messages
        mock_thread = Thread(
            thread_id="thread-123",
            messages=[
                Message(role="user", content="Check memory"),
                Message(role="assistant", content="Analyzing..."),
            ],
            context={},
            metadata=ThreadMetadata(),
        )

        mock_redis = AsyncMock()
        mock_redis.zrevrange = AsyncMock(return_value=[])  # No tasks

        with (
            patch("redis_sre_agent.core.redis.get_redis_client", return_value=mock_redis),
            patch(
                "redis_sre_agent.core.threads.ThreadManager.get_thread",
                new_callable=AsyncMock,
            ) as mock_get,
        ):
            mock_get.return_value = mock_thread

            result = await redis_sre_get_thread(thread_id="thread-123")

            assert result["thread_id"] == "thread-123"
            assert result["message_count"] == 2
            assert result["messages"][0]["role"] == "user"

    @pytest.mark.asyncio
    async def test_get_thread_not_found(self):
        """Test thread not found."""
        with (
            patch("redis_sre_agent.core.redis.get_redis_client"),
            patch(
                "redis_sre_agent.core.threads.ThreadManager.get_thread",
                new_callable=AsyncMock,
            ) as mock_get,
        ):
            mock_get.return_value = None

            result = await redis_sre_get_thread(thread_id="nonexistent")

            assert "error" in result
            assert "not found" in result["error"]


class TestGetTaskStatusTool:
    """Test the redis_sre_get_task_status MCP tool."""

    @pytest.mark.asyncio
    async def test_get_task_status_success(self):
        """Test successful task status retrieval."""
        # Mock returns data in the format that get_task_by_id actually returns
        mock_task = {
            "task_id": "task-123",
            "thread_id": "thread-456",
            "status": "done",
            "updates": [
                {"timestamp": "2024-01-01T00:00:30Z", "message": "Processing", "type": "progress"}
            ],
            "result": {"summary": "Complete"},
            "error_message": None,
            "metadata": {
                "subject": "Health check",
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-01T00:01:00Z",
                "user_id": None,
            },
            "context": {},
        }

        with patch(
            "redis_sre_agent.core.tasks.get_task_by_id",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_get.return_value = mock_task

            result = await redis_sre_get_task_status(task_id="task-123")

            assert result["task_id"] == "task-123"
            assert result["status"] == "done"
            assert result["thread_id"] == "thread-456"
            assert result["subject"] == "Health check"
            assert result["created_at"] == "2024-01-01T00:00:00Z"
            assert result["updated_at"] == "2024-01-01T00:01:00Z"
            assert result["updates"] == mock_task["updates"]
            assert result["result"] == {"summary": "Complete"}

    @pytest.mark.asyncio
    async def test_get_task_status_not_found(self):
        """Test task not found."""
        with patch(
            "redis_sre_agent.core.tasks.get_task_by_id",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_get.side_effect = ValueError("Task task-999 not found")

            result = await redis_sre_get_task_status(task_id="task-999")

            assert result["status"] == "not_found"
            assert "error" in result
