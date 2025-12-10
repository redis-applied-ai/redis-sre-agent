"""Tests for MCP server tools."""

from unittest.mock import AsyncMock, patch

import pytest

from redis_sre_agent.mcp_server.server import (
    create_instance,
    knowledge_search,
    list_instances,
    mcp,
    triage,
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
        assert "triage" in tool_names
        assert "knowledge_search" in tool_names
        assert "list_instances" in tool_names
        assert "create_instance" in tool_names


class TestTriageTool:
    """Test the triage MCP tool."""

    @pytest.mark.asyncio
    async def test_triage_success(self):
        """Test successful triage request."""
        mock_result = {
            "thread_id": "thread-123",
            "task_id": "task-456",
            "status": "queued",
            "message": "Task created",
        }

        with patch(
            "redis_sre_agent.core.redis.get_redis_client"
        ) as mock_redis, patch(
            "redis_sre_agent.core.tasks.create_task", new_callable=AsyncMock
        ) as mock_create:
            mock_create.return_value = mock_result

            result = await triage(
                query="High memory usage on Redis",
                instance_id="redis-prod-1",
                user_id="user-123",
            )

            assert result["thread_id"] == "thread-123"
            assert result["task_id"] == "task-456"
            assert "status" in result
            mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_triage_error_handling(self):
        """Test triage error handling."""
        with patch(
            "redis_sre_agent.core.redis.get_redis_client"
        ) as mock_redis, patch(
            "redis_sre_agent.core.tasks.create_task", new_callable=AsyncMock
        ) as mock_create:
            mock_create.side_effect = Exception("Redis connection failed")

            result = await triage(query="Test query")

            assert result["status"] == "failed"
            assert "error" in result


class TestKnowledgeSearchTool:
    """Test the knowledge_search MCP tool."""

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

            result = await knowledge_search(query="memory management", limit=5)

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

            # Test with too high limit
            await knowledge_search(query="test", limit=100)
            call_args = mock_search.call_args
            assert call_args.kwargs["limit"] == 20

            # Test with too low limit
            await knowledge_search(query="test", limit=0)
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

            result = await knowledge_search(query="test")

            assert "error" in result
            assert result["results"] == []
            assert result["total_results"] == 0


class TestListInstancesTool:
    """Test the list_instances MCP tool."""

    @pytest.mark.asyncio
    async def test_list_instances_success(self):
        """Test successful instance listing."""
        from unittest.mock import MagicMock

        mock_instance = MagicMock()
        mock_instance.id = "redis-prod-1"
        mock_instance.name = "Production Redis"
        mock_instance.environment = "production"
        mock_instance.usage = "cache"
        mock_instance.description = "Main cache"
        mock_instance.instance_type = "redis_cloud"

        with patch(
            "redis_sre_agent.core.instances.get_instances",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_get.return_value = [mock_instance]

            result = await list_instances()

            assert result["total"] == 1
            assert result["instances"][0]["id"] == "redis-prod-1"
            assert result["instances"][0]["name"] == "Production Redis"

    @pytest.mark.asyncio
    async def test_list_instances_empty(self):
        """Test empty instance list."""
        with patch(
            "redis_sre_agent.core.instances.get_instances",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_get.return_value = []

            result = await list_instances()

            assert result["total"] == 0
            assert result["instances"] == []

    @pytest.mark.asyncio
    async def test_list_instances_error(self):
        """Test list instances error handling."""
        with patch(
            "redis_sre_agent.core.instances.get_instances",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_get.side_effect = Exception("Connection failed")

            result = await list_instances()

            assert "error" in result
            assert result["instances"] == []


class TestCreateInstanceTool:
    """Test the create_instance MCP tool."""

    @pytest.mark.asyncio
    async def test_create_instance_success(self):
        """Test successful instance creation."""
        with patch(
            "redis_sre_agent.core.instances.get_instances",
            new_callable=AsyncMock,
        ) as mock_get, patch(
            "redis_sre_agent.core.instances.save_instances",
            new_callable=AsyncMock,
        ) as mock_save:
            mock_get.return_value = []
            mock_save.return_value = True

            result = await create_instance(
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
        result = await create_instance(
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
        result = await create_instance(
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

            result = await create_instance(
                name="test-redis",
                connection_url="redis://localhost:6379",
                environment="development",
                usage="cache",
                description="Test",
            )

            assert result["status"] == "failed"
            assert "already exists" in result["error"]
