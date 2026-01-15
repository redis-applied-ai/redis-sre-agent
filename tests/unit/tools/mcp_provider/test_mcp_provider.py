"""Unit tests for MCP tool provider."""

import pytest

from redis_sre_agent.core.config import MCPServerConfig, MCPToolConfig
from redis_sre_agent.tools.mcp.provider import MCPToolProvider
from redis_sre_agent.tools.models import ToolCapability


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
    async def test_call_mcp_tool_not_connected(self):
        """Test that _call_mcp_tool returns error when not connected."""
        config = MCPServerConfig(command="test")
        provider = MCPToolProvider(server_name="test", server_config=config)

        result = await provider._call_mcp_tool("some_tool", {"arg": "value"})
        assert result["status"] == "error"
        assert "not connected" in result["error"]


class TestMCPToolProviderDefaults:
    """Test MCPToolProvider defaults and constants."""

    def test_default_capability_is_utilities(self):
        """Test DEFAULT_CAPABILITY is UTILITIES."""
        assert MCPToolProvider.DEFAULT_CAPABILITY == ToolCapability.UTILITIES

    def test_server_config_accessible(self):
        """Test server_config is accessible."""
        config = MCPServerConfig(command="test")
        provider = MCPToolProvider(server_name="test", server_config=config)
        assert provider._server_config == config

    def test_server_name_accessible(self):
        """Test server_name is accessible."""
        config = MCPServerConfig(command="test")
        provider = MCPToolProvider(server_name="my_server", server_config=config)
        assert provider._server_name == "my_server"

    def test_session_initially_none(self):
        """Test session is initially None."""
        config = MCPServerConfig(command="test")
        provider = MCPToolProvider(server_name="test", server_config=config)
        assert provider._session is None

    def test_exit_stack_initially_none(self):
        """Test exit_stack is initially None."""
        config = MCPServerConfig(command="test")
        provider = MCPToolProvider(server_name="test", server_config=config)
        assert provider._exit_stack is None

    def test_mcp_tools_initially_empty(self):
        """Test mcp_tools is initially empty."""
        config = MCPServerConfig(command="test")
        provider = MCPToolProvider(server_name="test", server_config=config)
        assert provider._mcp_tools == []

    def test_tool_cache_initially_empty(self):
        """Test tool_cache is initially empty."""
        config = MCPServerConfig(command="test")
        provider = MCPToolProvider(server_name="test", server_config=config)
        assert provider._tool_cache == []


class TestMCPServerConfig:
    """Test MCPServerConfig model."""

    def test_config_with_command_only(self):
        """Test config with just a command."""
        config = MCPServerConfig(command="npx")
        assert config.command == "npx"
        assert config.args is None
        assert config.url is None
        assert config.tools is None

    def test_config_with_url(self):
        """Test config with URL-based transport."""
        config = MCPServerConfig(url="http://localhost:8080/mcp")
        assert config.url == "http://localhost:8080/mcp"
        assert config.command is None

    def test_config_with_tools_filter(self):
        """Test config with tools filter."""
        config = MCPServerConfig(
            command="test",
            tools={
                "tool1": MCPToolConfig(capability=ToolCapability.LOGS),
                "tool2": MCPToolConfig(description="Custom desc"),
            },
        )
        assert len(config.tools) == 2
        assert "tool1" in config.tools
        assert "tool2" in config.tools

    def test_config_with_headers(self):
        """Test config with headers."""
        config = MCPServerConfig(
            url="http://example.com",
            headers={"Authorization": "Bearer token123"},
        )
        assert config.headers["Authorization"] == "Bearer token123"

    def test_config_with_transport_type(self):
        """Test config with transport type."""
        config = MCPServerConfig(url="http://example.com", transport="sse")
        assert config.transport == "sse"

        config2 = MCPServerConfig(url="http://example.com", transport="streamable_http")
        assert config2.transport == "streamable_http"

    def test_config_env_with_shell_variable_syntax(self):
        """Test that env can contain shell-style variable references.

        The MCPServerConfig stores the literal string; expansion happens
        in the provider when connecting to the server.
        """
        config = MCPServerConfig(
            command="npx",
            args=["-y", "@modelcontextprotocol/server-github"],
            env={"GITHUB_PERSONAL_ACCESS_TOKEN": "${GITHUB_PERSONAL_ACCESS_TOKEN}"},
        )
        # Config stores literal string - expansion happens at runtime in provider
        assert config.env["GITHUB_PERSONAL_ACCESS_TOKEN"] == "${GITHUB_PERSONAL_ACCESS_TOKEN}"


class TestMCPToolProviderEnvExpansion:
    """Test environment variable expansion in MCP provider."""

    def test_env_var_expansion_expands_shell_vars(self, monkeypatch):
        """Test that ${VAR} patterns are expanded from environment."""
        import os

        monkeypatch.setenv("TEST_TOKEN", "secret-value-123")

        config = MCPServerConfig(
            command="test",
            env={"MY_VAR": "${TEST_TOKEN}", "PLAIN_VAR": "plain-value"},
        )
        provider = MCPToolProvider(server_name="test", server_config=config)

        # Simulate what happens in __aenter__ for env expansion
        config_env = {}
        for key, value in (provider._server_config.env or {}).items():
            config_env[key] = os.path.expandvars(value)

        assert config_env["MY_VAR"] == "secret-value-123"
        assert config_env["PLAIN_VAR"] == "plain-value"

    def test_env_var_expansion_unset_var_stays_literal(self, monkeypatch):
        """Test that undefined ${VAR} patterns remain as-is (no error)."""
        import os

        # Ensure the var is NOT set
        monkeypatch.delenv("UNDEFINED_VAR", raising=False)

        config = MCPServerConfig(
            command="test",
            env={"MY_VAR": "${UNDEFINED_VAR}"},
        )
        provider = MCPToolProvider(server_name="test", server_config=config)

        config_env = {}
        for key, value in (provider._server_config.env or {}).items():
            config_env[key] = os.path.expandvars(value)

        # os.path.expandvars leaves unset vars as-is
        assert config_env["MY_VAR"] == "${UNDEFINED_VAR}"
