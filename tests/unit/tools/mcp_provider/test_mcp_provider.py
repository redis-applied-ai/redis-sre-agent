"""Unit tests for MCP tool provider."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from redis_sre_agent.core.config import MCPServerConfig, MCPToolConfig
from redis_sre_agent.evaluation.fake_mcp import build_fixture_mcp_runtime
from redis_sre_agent.evaluation.injection import eval_injection_scope
from redis_sre_agent.evaluation.scenarios import EvalScenario
from redis_sre_agent.tools.mcp.provider import MCPToolProvider
from redis_sre_agent.tools.models import ToolActionKind, ToolCapability


class TestMCPToolProvider:
    """Test MCPToolProvider functionality."""

    def test_provider_name(self):
        """Test that provider name is based on server name."""
        config = MCPServerConfig(command="test")
        provider = MCPToolProvider(server_name="memory", server_config=config)
        assert provider.provider_name == "mcp_memory"

    def test_provider_name_with_special_chars(self):
        """Test provider name with various server names."""
        config = MCPServerConfig(command="test")

        provider = MCPToolProvider(server_name="my_server", server_config=config)
        assert provider.provider_name == "mcp_my_server"

        provider = MCPToolProvider(server_name="test123", server_config=config)
        assert provider.provider_name == "mcp_test123"

    def test_should_include_tool_no_filter(self):
        """Test that all tools are included when no filter is specified."""
        config = MCPServerConfig(command="test")
        provider = MCPToolProvider(server_name="test", server_config=config)

        assert provider._should_include_tool("any_tool") is True
        assert provider._should_include_tool("another_tool") is True

    def test_should_include_tool_with_filter(self):
        """Test that only specified tools are included when filter is set."""
        config = MCPServerConfig(
            command="test",
            tools={
                "allowed_tool": MCPToolConfig(),
                "another_allowed": MCPToolConfig(),
            },
        )
        provider = MCPToolProvider(server_name="test", server_config=config)

        assert provider._should_include_tool("allowed_tool") is True
        assert provider._should_include_tool("another_allowed") is True
        assert provider._should_include_tool("not_allowed") is False

    def test_get_capability_default(self):
        """Test that default capability is UTILITIES."""
        config = MCPServerConfig(command="test")
        provider = MCPToolProvider(server_name="test", server_config=config)

        assert provider._get_capability("any_tool") == ToolCapability.UTILITIES

    def test_get_capability_with_override(self):
        """Test that capability override is respected."""
        config = MCPServerConfig(
            command="test",
            tools={
                "search_tool": MCPToolConfig(capability=ToolCapability.LOGS),
                "metrics_tool": MCPToolConfig(capability=ToolCapability.METRICS),
                "no_override": MCPToolConfig(),
            },
        )
        provider = MCPToolProvider(server_name="test", server_config=config)

        assert provider._get_capability("search_tool") == ToolCapability.LOGS
        assert provider._get_capability("metrics_tool") == ToolCapability.METRICS
        assert provider._get_capability("no_override") == ToolCapability.UTILITIES
        assert provider._get_capability("unknown_tool") == ToolCapability.UTILITIES

    def test_get_description_default(self):
        """Test that MCP description is used by default."""
        config = MCPServerConfig(command="test")
        provider = MCPToolProvider(server_name="test", server_config=config)

        mcp_desc = "Original MCP description"
        assert provider._get_description("any_tool", mcp_desc) == mcp_desc

    def test_get_description_with_override(self):
        """Test that description override is respected."""
        config = MCPServerConfig(
            command="test",
            tools={
                "custom_tool": MCPToolConfig(description="Custom description"),
                "no_override": MCPToolConfig(),
            },
        )
        provider = MCPToolProvider(server_name="test", server_config=config)

        assert provider._get_description("custom_tool", "MCP desc") == "Custom description"
        assert provider._get_description("no_override", "MCP desc") == "MCP desc"
        assert provider._get_description("unknown", "MCP desc") == "MCP desc"

    def test_get_description_with_original_template(self):
        """Test that {original} placeholder is replaced with MCP description."""
        config = MCPServerConfig(
            command="test",
            tools={
                "templated_tool": MCPToolConfig(description="Custom context. {original}"),
                "prepended": MCPToolConfig(
                    description="WARNING: Use carefully. {original} See docs for details."
                ),
            },
        )
        provider = MCPToolProvider(server_name="test", server_config=config)

        # Template should replace {original} with the MCP description
        assert (
            provider._get_description("templated_tool", "Original MCP description")
            == "Custom context. Original MCP description"
        )
        assert (
            provider._get_description("prepended", "Search for files.")
            == "WARNING: Use carefully. Search for files. See docs for details."
        )

    def test_get_action_kind_with_override(self):
        """Test that action kind override is respected."""
        config = MCPServerConfig(
            command="test",
            tools={
                "query_tool": MCPToolConfig(action_kind=ToolActionKind.READ),
                "mutate_tool": MCPToolConfig(action_kind=ToolActionKind.WRITE),
            },
        )
        provider = MCPToolProvider(server_name="test", server_config=config)

        assert (
            provider._get_action_kind("query_tool", "Read current state.", ToolCapability.UTILITIES)
            == ToolActionKind.READ
        )
        assert (
            provider._get_action_kind(
                "mutate_tool", "Write current state.", ToolCapability.UTILITIES
            )
            == ToolActionKind.WRITE
        )

    def test_get_action_kind_infers_from_mcp_tool_name_and_description(self):
        """Test that MCP tools infer action kinds when no override is configured."""
        config = MCPServerConfig(command="test")
        provider = MCPToolProvider(server_name="github", server_config=config)

        assert (
            provider._get_action_kind(
                "_create_branch",
                "Create a new branch in the given repository.",
                ToolCapability.REPOS,
            )
            == ToolActionKind.WRITE
        )
        assert (
            provider._get_action_kind(
                "_search_repositories",
                "Search for a repository by name or description.",
                ToolCapability.REPOS,
            )
            == ToolActionKind.READ
        )
        assert (
            provider._get_action_kind(
                "custom_operation",
                "Runs a custom operation for the current selection.",
                ToolCapability.REPOS,
            )
            == ToolActionKind.UNKNOWN
        )

    def test_get_action_kind_keeps_leading_verb_for_resolved_mcp_operation_names(self):
        """Test that already-resolved MCP operation names still infer write intent."""
        config = MCPServerConfig(command="test")
        provider = MCPToolProvider(server_name="github", server_config=config)

        assert (
            provider._get_action_kind(
                "_update_repository",
                "Operate on repository settings for the selected repo.",
                ToolCapability.UTILITIES,
            )
            == ToolActionKind.WRITE
        )

    def test_get_action_kind_keeps_read_verb_for_multi_part_mcp_operation_names(self):
        """Test that resolved MCP operation names like list_pull_requests stay intact."""
        config = MCPServerConfig(command="test")
        provider = MCPToolProvider(server_name="github", server_config=config)

        assert (
            provider._get_action_kind(
                "list_pull_requests",
                "Operate on the selected pull request collection.",
                ToolCapability.REPOS,
            )
            == ToolActionKind.READ
        )

    def test_get_tool_config(self):
        """Test getting tool config."""
        tool_config = MCPToolConfig(
            capability=ToolCapability.LOGS,
            description="Test description",
        )
        config = MCPServerConfig(
            command="test",
            tools={"my_tool": tool_config},
        )
        provider = MCPToolProvider(server_name="test", server_config=config)

        assert provider._get_tool_config("my_tool") == tool_config
        assert provider._get_tool_config("unknown") is None

    def test_get_tool_config_no_tools_defined(self):
        """Test getting tool config when no tools are defined."""
        config = MCPServerConfig(command="test")
        provider = MCPToolProvider(server_name="test", server_config=config)

        assert provider._get_tool_config("any_tool") is None


class TestMCPToolProviderAsync:
    """Test async functionality of MCPToolProvider."""

    @pytest.mark.asyncio
    async def test_tools_returns_empty_list_without_connection(self):
        """Test that tools() returns empty list when not connected."""
        config = MCPServerConfig(command="test")
        provider = MCPToolProvider(server_name="test", server_config=config)

        # Without connecting, tools should be empty
        tools = provider.tools()
        assert tools == []

    @pytest.mark.asyncio
    async def test_create_tool_schemas_empty_without_connection(self):
        """Test that create_tool_schemas returns empty when not connected."""
        config = MCPServerConfig(command="test")
        provider = MCPToolProvider(server_name="test", server_config=config)

        # Without connecting, schemas should be empty
        schemas = provider.create_tool_schemas()
        assert schemas == []

    @pytest.mark.asyncio
    async def test_get_input_schemas_returns_raw_schema_by_operation_name(self):
        """Test that raw MCP schemas stay keyed by original tool names."""
        config = MCPServerConfig(
            command="test",
            tools={"file_write": MCPToolConfig()},
        )
        provider = MCPToolProvider(server_name="afs_gateway", server_config=config)
        provider._mcp_tools = [
            SimpleNamespace(
                name="file_write",
                description="Write a file",
                inputSchema={
                    "title": "file_writeArguments",
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "title": "Path"},
                        "content": {"type": "string", "title": "Content"},
                    },
                    "required": ["path", "content"],
                    "additionalProperties": False,
                },
            )
        ]

        schemas = provider.get_input_schemas()

        assert schemas == {
            "file_write": {
                "title": "file_writeArguments",
                "type": "object",
                "properties": {
                    "path": {"type": "string", "title": "Path"},
                    "content": {"type": "string", "title": "Content"},
                },
                "required": ["path", "content"],
                "additionalProperties": False,
            }
        }

    @pytest.mark.asyncio
    async def test_get_input_schemas_coerces_model_like_input_schema(self):
        """Test that MCP model objects are serialized into plain dict schemas."""
        config = MCPServerConfig(
            command="test",
            tools={"analyzer_list_accounts": MCPToolConfig()},
        )
        provider = MCPToolProvider(server_name="re_analyzer", server_config=config)

        class _SchemaModel:
            def model_dump(self, mode: str = "json") -> dict[str, object]:
                assert mode == "json"
                return {
                    "$schema": "http://json-schema.org/draft-07/schema#",
                    "type": "object",
                    "properties": {"limit": {"type": "integer"}},
                }

        provider._mcp_tools = [
            SimpleNamespace(
                name="analyzer_list_accounts",
                description="List accounts",
                inputSchema=_SchemaModel(),
            )
        ]

        schemas = provider.get_input_schemas()

        assert schemas == {
            "analyzer_list_accounts": {
                "$schema": "http://json-schema.org/draft-07/schema#",
                "type": "object",
                "properties": {"limit": {"type": "integer"}},
            }
        }

    @pytest.mark.asyncio
    async def test_call_mcp_tool_not_connected(self):
        """Test that _call_mcp_tool returns error when not connected."""
        config = MCPServerConfig(command="test")
        provider = MCPToolProvider(server_name="test", server_config=config)

        result = await provider._call_mcp_tool("some_tool", {"arg": "value"})
        assert result["status"] == "error"
        assert "not connected" in result["error"]

    @pytest.mark.asyncio
    async def test_connect_uses_pool_when_available(self):
        """Test that _connect uses pooled connection when available."""
        from unittest.mock import MagicMock

        from redis_sre_agent.tools.mcp.pool import MCPConnectionPool, PooledConnection

        # Reset and set up the pool
        MCPConnectionPool.reset_instance()
        pool = MCPConnectionPool.get_instance()

        # Create a mock pooled connection
        mock_session = MagicMock()
        mock_tools = [MagicMock(name="tool1")]
        pool._connections["test-server"] = PooledConnection(
            server_name="test-server",
            session=mock_session,
            tools=mock_tools,
            exit_stack=MagicMock(),
        )
        pool._started = True

        config = MCPServerConfig(command="test")
        provider = MCPToolProvider(server_name="test-server", server_config=config, use_pool=True)

        await provider._connect()

        assert provider._session is mock_session
        assert provider._using_pooled_connection is True

        # Cleanup
        MCPConnectionPool.reset_instance()

    @pytest.mark.asyncio
    async def test_disconnect_does_not_close_pooled_connection(self):
        """Test that _disconnect doesn't close pooled connections."""
        from unittest.mock import MagicMock

        config = MCPServerConfig(command="test")
        provider = MCPToolProvider(server_name="test", server_config=config)

        # Simulate using a pooled connection
        provider._session = MagicMock()
        provider._using_pooled_connection = True

        await provider._disconnect()

        # Session should be cleared but not closed
        assert provider._session is None
        assert provider._using_pooled_connection is False

    @pytest.mark.asyncio
    async def test_connect_uses_eval_fake_mcp_runtime_before_network(self):
        """Test that eval fake MCP catalogs bypass network transports."""
        scenario = EvalScenario.model_validate(
            {
                "id": "fake-mcp-provider",
                "name": "Fake MCP provider",
                "provenance": {
                    "source_kind": "synthetic",
                    "source_pack": "fixture-pack",
                    "source_pack_version": "2026-04-14",
                    "golden": {"expectation_basis": "human_authored"},
                },
                "execution": {
                    "lane": "full_turn",
                    "query": "Check memory pressure.",
                },
                "tools": {
                    "mcp_servers": {
                        "metrics_eval": {
                            "capability": "metrics",
                            "tools": {
                                "query_metrics": {
                                    "description": "Query fixture metrics.",
                                    "input_schema": {
                                        "properties": {
                                            "query": {"type": "string"},
                                        },
                                        "required": ["query"],
                                    },
                                    "result": {
                                        "series": "memory_pressure",
                                        "value": 91,
                                    },
                                }
                            },
                        }
                    }
                },
            }
        )
        runtime = build_fixture_mcp_runtime(scenario)
        assert runtime is not None

        provider = MCPToolProvider(
            server_name="metrics_eval",
            server_config=runtime.get_server_configs()["metrics_eval"],
            use_pool=False,
        )

        with (
            eval_injection_scope(
                mcp_servers=runtime.get_server_configs(),
                mcp_runtime=runtime,
            ),
            patch(
                "redis_sre_agent.tools.mcp.provider.streamablehttp_client",
                side_effect=AssertionError("network transport should not run"),
            ),
        ):
            await provider._connect()
            tools = provider.tools()
            result = await provider._call_mcp_tool(
                "query_metrics",
                {"query": "memory pressure"},
            )

        assert provider._using_eval_runtime is True
        assert len(tools) == 1
        assert tools[0].definition.name.endswith("_query_metrics")
        assert tools[0].definition.capability is ToolCapability.METRICS
        assert tools[0].metadata.action_kind is ToolActionKind.READ
        assert result["status"] == "success"
        assert result["data"]["series"] == "memory_pressure"
