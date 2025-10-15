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
    """Test that knowledge tools are loaded."""
    async with ToolManager() as mgr:
        tools = mgr.get_tools()
        tool_names = [t.name for t in tools]

        # Should have knowledge, prometheus, and redis_cli tools (default providers)
        knowledge_tools = [n for n in tool_names if "knowledge_" in n]
        prometheus_tools = [n for n in tool_names if "prometheus_" in n]
        redis_cli_tools = [n for n in tool_names if "redis_cli_" in n]

        # Knowledge tools
        assert len(knowledge_tools) == 2  # search and ingest
        assert any("search" in n for n in knowledge_tools)
        assert any("ingest" in n for n in knowledge_tools)

        # Prometheus tools (enabled by default)
        assert len(prometheus_tools) == 3  # query, query_range, search_metrics

        # Redis CLI tools (enabled by default)
        assert len(redis_cli_tools) == 10  # All diagnostic tools


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
