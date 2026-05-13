from __future__ import annotations

import asyncio

import runtime_agent


def test_dispatch_mcp_tool_exposes_internal_runtime_capabilities(monkeypatch) -> None:
    capabilities = {
        "tools": [{"name": "demo_tool", "description": "Demo tool"}],
        "resources": [],
        "prompts": [],
    }
    monkeypatch.setattr(runtime_agent, "_build_mcp_capabilities", lambda: capabilities)

    result = asyncio.run(
        runtime_agent._dispatch_mcp_tool(
            {"tool": runtime_agent.INTERNAL_MCP_CAPABILITIES_TOOL, "arguments": {}}
        )
    )

    assert result == {
        "ok": True,
        "mode": "mcp",
        "tool": runtime_agent.INTERNAL_MCP_CAPABILITIES_TOOL,
        "result": capabilities,
    }
