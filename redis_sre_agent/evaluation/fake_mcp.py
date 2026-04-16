"""Scenario-scoped fake MCP catalog for eval runs."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from typing import Any, Mapping

from mcp import types as mcp_types

from redis_sre_agent.core.config import MCPServerConfig, MCPToolConfig
from redis_sre_agent.evaluation.injection import EvalMCPRuntime
from redis_sre_agent.evaluation.scenarios import EvalScenario
from redis_sre_agent.evaluation.tool_runtime import FixtureBehaviorResolver, FixtureBehaviorState
from redis_sre_agent.tools.models import ToolActionKind, ToolCapability


def _normalize_operation(value: str) -> str:
    return str(value or "").strip().lower().replace("-", "_")


def _coerce_capability(value: str | None) -> ToolCapability:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return ToolCapability.UTILITIES
    try:
        return ToolCapability(normalized)
    except ValueError:
        return ToolCapability.UTILITIES


def _tool_description(server_name: str, operation: str, description: str | None) -> str:
    if description:
        return description
    return f"Eval fixture MCP tool '{operation}' served by '{server_name}'."


def _tool_input_schema(input_schema: Mapping[str, Any] | None) -> dict[str, Any]:
    schema = dict(input_schema or {})
    if not schema:
        return {"type": "object", "properties": {}}
    if "type" not in schema:
        schema["type"] = "object"
    if "properties" not in schema:
        schema["properties"] = {}
    return schema


def _materialize_call_result(result: Any) -> mcp_types.CallToolResult:
    if isinstance(result, dict):
        text = json.dumps(result, sort_keys=True)
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(type="text", text=text)],
            structuredContent=copy.deepcopy(result),
            isError=False,
        )
    if result is None:
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(type="text", text="")],
            isError=False,
        )
    if isinstance(result, str):
        text = result
    else:
        text = json.dumps(result, sort_keys=True)
    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(type="text", text=text)],
        isError=False,
    )


class FixtureMCPClientSession:
    """Minimal MCP client-session shim backed by scenario fixtures."""

    def __init__(
        self,
        *,
        server_name: str,
        tools: list[mcp_types.Tool],
        resolver: FixtureBehaviorResolver,
    ) -> None:
        self._server_name = server_name
        self._tools = list(tools)
        self._resolver = resolver

    async def initialize(self) -> None:
        return None

    async def list_tools(self) -> mcp_types.ListToolsResult:
        return mcp_types.ListToolsResult(tools=list(self._tools))

    async def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> mcp_types.CallToolResult:
        result = self._resolver.resolve(
            provider_family="mcp",
            operation=_normalize_operation(tool_name),
            args=dict(arguments or {}),
            server_name=self._server_name,
        )
        return _materialize_call_result(result)


@dataclass
class FixtureMCPRuntime(EvalMCPRuntime):
    """Scenario-backed fake MCP catalog mounted only for one eval run."""

    server_configs: dict[str, MCPServerConfig]
    server_sessions: dict[str, FixtureMCPClientSession]
    behavior_state: FixtureBehaviorState = field(default_factory=FixtureBehaviorState)

    def get_server_configs(self) -> dict[str, MCPServerConfig]:
        return dict(self.server_configs)

    def get_server_session(self, server_name: str) -> FixtureMCPClientSession | None:
        return self.server_sessions.get(server_name)


def build_fixture_mcp_runtime(
    scenario: EvalScenario,
    *,
    state: FixtureBehaviorState | None = None,
) -> FixtureMCPRuntime | None:
    """Build a fake MCP catalog for the scenario, if it declares any MCP servers."""

    if not scenario.tools.mcp_servers:
        return None

    shared_state = state or FixtureBehaviorState()
    server_configs: dict[str, MCPServerConfig] = {}
    server_sessions: dict[str, FixtureMCPClientSession] = {}

    for server_name, server_config in scenario.tools.mcp_servers.items():
        capability = _coerce_capability(server_config.capability)
        behaviors = {
            ("mcp", _normalize_operation(operation), server_name): behavior
            for operation, behavior in server_config.tools.items()
        }
        resolver = FixtureBehaviorResolver(
            scenario=scenario,
            behaviors=behaviors,
            state=shared_state,
        )
        tools: list[mcp_types.Tool] = []
        tool_overrides: dict[str, MCPToolConfig] = {}
        for operation, behavior in server_config.tools.items():
            normalized_operation = _normalize_operation(operation)
            description = _tool_description(
                server_name,
                normalized_operation,
                behavior.description,
            )
            tools.append(
                mcp_types.Tool(
                    name=normalized_operation,
                    description=description,
                    inputSchema=_tool_input_schema(behavior.input_schema),
                )
            )
            tool_overrides[normalized_operation] = MCPToolConfig(
                capability=capability,
                description=description,
                action_kind=ToolActionKind.READ,
            )

        server_configs[server_name] = MCPServerConfig(
            url=f"http://fixture-mcp.invalid/{server_name}",
            tools=tool_overrides,
        )
        server_sessions[server_name] = FixtureMCPClientSession(
            server_name=server_name,
            tools=tools,
            resolver=resolver,
        )

    return FixtureMCPRuntime(
        server_configs=server_configs,
        server_sessions=server_sessions,
        behavior_state=shared_state,
    )


__all__ = [
    "FixtureMCPClientSession",
    "FixtureMCPRuntime",
    "build_fixture_mcp_runtime",
]
