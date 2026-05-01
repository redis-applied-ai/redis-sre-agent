from redis_sre_agent.tools.models import (
    ToolActionKind,
    ToolCapability,
    ToolDefinition,
    ToolMetadata,
)
from redis_sre_agent.tools.protocols import ToolProvider


class _StubToolProvider(ToolProvider):
    @property
    def provider_name(self) -> str:
        return "redis_command"

    def create_tool_schemas(self):
        return [
            ToolDefinition(
                name=self._make_tool_name("list_nodes"),
                description="List Redis nodes.",
                capability=ToolCapability.DIAGNOSTICS,
                parameters={"type": "object", "properties": {}, "required": []},
            ),
            ToolDefinition(
                name=self._make_tool_name("delete_node"),
                description="Delete Redis node.",
                capability=ToolCapability.DIAGNOSTICS,
                parameters={"type": "object", "properties": {}, "required": []},
            ),
        ]

    async def list_nodes(self):
        return {"status": "ok"}

    async def delete_node(self):
        return {"status": "ok"}


def test_tool_metadata_infers_read_action_for_builtin_read_operations():
    metadata = ToolMetadata(
        name="redis_command_deadbeef_info",
        description="Execute Redis INFO command to inspect server state.",
        capability=ToolCapability.DIAGNOSTICS,
        provider_name="redis_command",
        requires_instance=True,
    )

    assert metadata.action_kind is ToolActionKind.READ


def test_tool_metadata_infers_write_action_for_builtin_mutating_operations():
    metadata = ToolMetadata(
        name="redis_cloud_deadbeef_update_tags",
        description="Update Redis Cloud database tags.",
        capability=ToolCapability.DIAGNOSTICS,
        provider_name="redis_cloud",
    )

    assert metadata.action_kind is ToolActionKind.WRITE


def test_tool_metadata_infers_write_action_for_mcp_mutating_operations():
    metadata = ToolMetadata(
        name="mcp_github_deadbeef__create_branch",
        description="Create a new branch in the repository.",
        capability=ToolCapability.UTILITIES,
        provider_name="mcp_github",
    )

    assert metadata.action_kind is ToolActionKind.WRITE


def test_tool_metadata_infers_read_action_for_mcp_read_operations():
    metadata = ToolMetadata(
        name="mcp_github_deadbeef__search_repositories",
        description="Search repositories within the user's installations.",
        capability=ToolCapability.REPOS,
        provider_name="mcp_github",
    )

    assert metadata.action_kind is ToolActionKind.READ


def test_tool_metadata_respects_explicit_action_override():
    metadata = ToolMetadata(
        name="redis_command_deadbeef_info",
        description="Execute Redis INFO command to inspect server state.",
        capability=ToolCapability.DIAGNOSTICS,
        provider_name="redis_command",
        action_kind=ToolActionKind.UNKNOWN,
    )

    assert metadata.action_kind is ToolActionKind.UNKNOWN


def test_tool_metadata_treats_builtin_utilities_as_read():
    metadata = ToolMetadata(
        name="utilities_deadbeef_calculator",
        description="Evaluate arithmetic expressions.",
        capability=ToolCapability.UTILITIES,
        provider_name="utilities",
    )

    assert metadata.action_kind is ToolActionKind.READ


def test_tool_metadata_does_not_treat_set_noun_as_write_marker():
    metadata = ToolMetadata(
        name="redis_command_deadbeef_custom_action",
        description="Returns a set of configuration details for the selected database.",
        capability=ToolCapability.DIAGNOSTICS,
        provider_name="redis_command",
    )

    assert metadata.action_kind is ToolActionKind.READ


def test_tool_metadata_uses_write_description_marker_at_start_of_sentence():
    metadata = ToolMetadata(
        name="redis_command_deadbeef_custom_action",
        description="Update Redis database tags for the selected instance.",
        capability=ToolCapability.DIAGNOSTICS,
        provider_name="redis_command",
    )

    assert metadata.action_kind is ToolActionKind.WRITE


def test_tool_provider_tools_propagate_inferred_action_kind():
    provider = _StubToolProvider()
    tools = {tool.definition.name: tool for tool in provider.tools()}

    read_tool = next(tool for name, tool in tools.items() if name.endswith("_list_nodes"))
    write_tool = next(tool for name, tool in tools.items() if name.endswith("_delete_node"))

    assert read_tool.metadata.action_kind is ToolActionKind.READ
    assert write_tool.metadata.action_kind is ToolActionKind.WRITE
