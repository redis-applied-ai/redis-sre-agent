"""Tests for ToolManager."""

import pytest

from redis_sre_agent.tools.manager import ToolManager
from redis_sre_agent.tools.tool_definition import ToolDefinition


@pytest.mark.asyncio
async def test_tool_manager_initialization():
    """Test that ToolManager initializes and loads knowledge provider."""
    async with ToolManager() as mgr:
        tools = mgr.get_tools()

        # Should have at least knowledge tools
        assert len(tools) >= 2

        # All tools should be ToolDefinition objects
        for tool in tools:
            assert isinstance(tool, ToolDefinition)
            assert tool.name
            assert tool.description
            assert tool.parameters

        # Should have routing table entries
        assert len(mgr._routing_table) == len(tools)


@pytest.mark.asyncio
async def test_tool_manager_knowledge_tools():
    """Test that knowledge tools are loaded without instance."""
    async with ToolManager() as mgr:
        tools = mgr.get_tools()
        tool_names = [t.name for t in tools]

        # Without an instance, only knowledge tools should be loaded
        knowledge_tools = [n for n in tool_names if "knowledge_" in n]
        prometheus_tools = [n for n in tool_names if "prometheus_" in n]
        redis_cli_tools = [n for n in tool_names if "redis_cli_" in n]

        # Knowledge tools (always loaded)
        assert len(knowledge_tools) == 4  # search, ingest, get_all_fragments, get_related_fragments
        assert any("search" in n for n in knowledge_tools)
        assert any("ingest" in n for n in knowledge_tools)
        assert any("get_all_fragments" in n for n in knowledge_tools)
        assert any("get_related_fragments" in n for n in knowledge_tools)

        # Instance-specific tools should NOT be loaded without an instance
        assert len(prometheus_tools) == 0
        assert len(redis_cli_tools) == 0


@pytest.mark.asyncio
async def test_tool_manager_with_instance():
    """Test that instance-specific tools are loaded when instance is provided."""
    from redis_sre_agent.core.instances import RedisInstance

    # Create a test instance
    test_instance = RedisInstance(
        id="test-instance",
        name="Test Redis",
        connection_url="redis://localhost:6379",
        environment="test",
        usage="cache",
        description="Test instance",
        instance_type="oss_single",
    )

    async with ToolManager(redis_instance=test_instance) as mgr:
        tools = mgr.get_tools()
        tool_names = [t.name for t in tools]

        # Should have knowledge, prometheus, and redis_cli tools
        knowledge_tools = [n for n in tool_names if "knowledge_" in n]
        prometheus_tools = [n for n in tool_names if "prometheus_" in n]
        redis_cli_tools = [n for n in tool_names if "redis_command_" in n]

        # Knowledge tools (always loaded)
        assert len(knowledge_tools) == 4  # search, ingest, get_all_fragments, get_related_fragments

        # Instance-specific tools should be loaded
        assert len(prometheus_tools) == 3  # query, query_range, search_metrics
        assert len(redis_cli_tools) == 11  # All diagnostic tools


@pytest.mark.asyncio
async def test_tool_manager_routing():
    """Test that ToolManager can route tool calls."""
    async with ToolManager() as mgr:
        tools = mgr.get_tools()

        # Get a tool name
        tool_name = tools[0].name

        # Should be able to find provider in routing table
        provider = mgr._routing_table.get(tool_name)
        assert provider is not None
        assert provider.provider_name == "knowledge"


@pytest.mark.asyncio
async def test_tool_manager_unknown_tool():
    """Test that ToolManager raises error for unknown tools."""
    async with ToolManager() as mgr:
        with pytest.raises(ValueError, match="Unknown tool"):
            await mgr.resolve_tool_call("nonexistent_tool", {})


@pytest.mark.asyncio
async def test_tool_manager_context_cleanup():
    """Test that ToolManager cleans up properly."""
    mgr = ToolManager()

    # Before entering context
    assert mgr._stack is None
    assert len(mgr._tools) == 0

    # Enter context
    await mgr.__aenter__()
    assert mgr._stack is not None
    assert len(mgr._tools) > 0

    # Exit context
    await mgr.__aexit__(None, None, None)

    # Stack should still exist but be closed
    assert mgr._stack is not None


def test_mask_redis_url_credentials():
    """Test that Redis URL credentials are properly masked."""
    from redis_sre_agent.agent.langgraph_agent import _mask_redis_url_credentials

    # Test with username and password
    url_with_creds = "redis://user:password@localhost:6379/0"
    masked = _mask_redis_url_credentials(url_with_creds)
    assert masked == "redis://***:***@localhost:6379/0"
    assert "user" not in masked
    assert "password" not in masked

    # Test with URL-encoded credentials (common in Redis Enterprise)
    url_encoded = "redis://admin%40redis.com:admin@redis-enterprise:12000/0"
    masked = _mask_redis_url_credentials(url_encoded)
    assert masked == "redis://***:***@redis-enterprise:12000/0"
    assert "admin" not in masked

    # Test without credentials
    url_no_creds = "redis://localhost:6379"
    masked = _mask_redis_url_credentials(url_no_creds)
    assert masked == "redis://localhost:6379"

    # Test with only password (edge case)
    url_only_pass = "redis://:password@localhost:6379"
    masked = _mask_redis_url_credentials(url_only_pass)
    assert masked == "redis://***:***@localhost:6379"
    assert "password" not in masked

    # Test with special characters in password
    url_special_chars = "redis://user:p@ssw0rd!@localhost:6379"
    masked = _mask_redis_url_credentials(url_special_chars)
    assert masked == "redis://***:***@localhost:6379"
    assert "p@ssw0rd!" not in masked
    assert "user" not in masked

    # Test with database number
    url_with_db = "redis://user:pass@localhost:6379/5"
    masked = _mask_redis_url_credentials(url_with_db)
    assert masked == "redis://***:***@localhost:6379/5"
    assert "user" not in masked
    assert "pass" not in masked

    # Test with query parameters
    url_with_query = "redis://user:pass@localhost:6379/0?timeout=5"
    masked = _mask_redis_url_credentials(url_with_query)
    assert masked == "redis://***:***@localhost:6379/0?timeout=5"
    assert "user" not in masked
    assert "pass" not in masked

    # Test with non-standard port
    url_enterprise_port = "redis://admin:secret@redis-enterprise:12000/0"
    masked = _mask_redis_url_credentials(url_enterprise_port)
    assert masked == "redis://***:***@redis-enterprise:12000/0"
    assert "admin" not in masked
    assert "secret" not in masked
    # Verify hostname and port are preserved
    assert "redis-enterprise" in masked
    assert "12000" in masked

    # Test with rediss:// (SSL)
    url_ssl = "rediss://user:pass@secure-redis:6380/0"
    masked = _mask_redis_url_credentials(url_ssl)
    assert masked == "rediss://***:***@secure-redis:6380/0"
    assert "user" not in masked
    assert "pass" not in masked

    # Test with complex username (email-like)
    url_email_user = "redis://admin@company.com:password123@redis-host:6379"
    masked = _mask_redis_url_credentials(url_email_user)
    assert masked == "redis://***:***@redis-host:6379"
    assert "admin@company.com" not in masked
    assert "password123" not in masked
    assert "redis-host" in masked
