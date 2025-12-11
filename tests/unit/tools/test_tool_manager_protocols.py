import pytest

from redis_sre_agent.tools.manager import ToolManager
from redis_sre_agent.tools.protocols import (
    ToolCapability,
)


@pytest.mark.asyncio
async def test_protocol_selection_for_knowledge_search_only():
    async with ToolManager(redis_instance=None) as mgr:
        # Use capability-based selection; manager no longer filters by op name
        tools = mgr.get_tools_for_capability(ToolCapability.KNOWLEDGE)
        assert tools, "Expected at least one knowledge tool"

        # All should be knowledge provider tools, and there should be a search op
        has_search = False
        for t in tools:
            assert t.name.startswith("knowledge_"), f"Unexpected provider prefix: {t.name}"
            parts = t.name.split("_", 2)
            op = parts[2] if len(parts) >= 3 else parts[-1]
            if op == "search":
                has_search = True

        assert has_search, "Expected at least one knowledge search tool among knowledge tools"


@pytest.mark.asyncio
async def test_protocol_selection_for_utilities_subset():
    allowed = {"calculator", "date_math", "timezone_converter", "http_head"}
    async with ToolManager(redis_instance=None) as mgr:
        # Use capability-based selection; manager no longer filters by op name
        tools = mgr.get_tools_for_capability(ToolCapability.UTILITIES)
        assert tools, "Expected utilities tools for the allowed set"

        # Collect ops from utilities_* tools only (MCP tools may also have UTILITIES capability)
        ops_seen = set()
        for t in tools:
            # Skip MCP tools which have a different naming convention (mcp_servername_hash_toolname)
            if t.name.startswith("mcp_"):
                continue
            assert t.name.startswith("utilities_"), f"Unexpected provider prefix: {t.name}"
            parts = t.name.split("_", 2)
            op = parts[2] if len(parts) >= 3 else parts[-1]
            ops_seen.add(op)

        # At least the core utility operations should be present; additional ones are allowed
        assert allowed.issubset(ops_seen), f"Missing expected utilities operations: {ops_seen}"
