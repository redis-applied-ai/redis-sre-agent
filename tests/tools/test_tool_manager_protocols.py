import pytest

from redis_sre_agent.tools.manager import ToolManager
from redis_sre_agent.tools.protocols import (
    KnowledgeProviderProtocol,
    UtilitiesProviderProtocol,
)


@pytest.mark.asyncio
async def test_protocol_selection_for_knowledge_search_only():
    async with ToolManager(redis_instance=None) as mgr:
        tools = mgr.get_tools_for_protocol(KnowledgeProviderProtocol, allowed_ops={"search"})
        assert tools, "Expected at least one knowledge search tool"
        # All should be knowledge_*_search
        for t in tools:
            assert t.name.startswith("knowledge_"), f"Unexpected provider prefix: {t.name}"
            # Extract operation using the same logic as manager
            op = (
                t.name.split("_", 2)[2] if len(t.name.split("_", 2)) >= 3 else t.name.split("_")[-1]
            )
            assert op == "search", f"Unexpected knowledge op: {op} from {t.name}"


@pytest.mark.asyncio
async def test_protocol_selection_for_utilities_subset():
    allowed = {"calculator", "date_math", "timezone_converter", "http_head"}
    async with ToolManager(redis_instance=None) as mgr:
        tools = mgr.get_tools_for_protocol(UtilitiesProviderProtocol, allowed_ops=allowed)
        assert tools, "Expected utilities tools for the allowed set"
        # Ensure only utilities tools are present and ops are within allowed
        for t in tools:
            assert t.name.startswith("utilities_"), f"Unexpected provider prefix: {t.name}"
            op = (
                t.name.split("_", 2)[2] if len(t.name.split("_", 2)) >= 3 else t.name.split("_")[-1]
            )
            assert op in allowed, f"Unexpected utilities op: {op} from {t.name}"
        # Check that at least 3 of the 4 are available in always-on provider
        ops_seen = {t.name.split("_", 2)[2] for t in tools if len(t.name.split("_", 2)) >= 3}
        assert {"calculator", "date_math", "timezone_converter"}.issubset(ops_seen), (
            f"Missing expected utilities operations in always-on tools: {ops_seen}"
        )
