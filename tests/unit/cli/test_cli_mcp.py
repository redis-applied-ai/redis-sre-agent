"""Unit tests for MCP CLI commands."""

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from redis_sre_agent.cli.mcp import mcp


@pytest.fixture
def cli_runner():
    """Create a CLI runner for testing."""
    return CliRunner()


class TestMCPServeCLI:
    """Tests for the mcp serve command."""

    def test_serve_help_shows_options(self, cli_runner):
        """Test that serve help shows all options."""
        result = cli_runner.invoke(mcp, ["serve", "--help"])

        assert result.exit_code == 0
        assert "--transport" in result.output
        assert "--host" in result.output
        assert "--port" in result.output
        assert "stdio" in result.output
        assert "http" in result.output
        assert "sse" in result.output

    def test_serve_default_transport_is_stdio(self, cli_runner):
        """Test that default transport is stdio."""
        with patch("redis_sre_agent.mcp_server.server.run_stdio") as mock_run:
            cli_runner.invoke(mcp, ["serve"])

            # stdio mode doesn't print anything
            mock_run.assert_called_once()

    def test_serve_http_mode(self, cli_runner):
        """Test serve in HTTP mode."""
        with patch("redis_sre_agent.mcp_server.server.run_http") as mock_run:
            result = cli_runner.invoke(mcp, ["serve", "--transport", "http"])

            assert result.exit_code == 0
            mock_run.assert_called_once_with(host="0.0.0.0", port=8081)
            assert "HTTP mode" in result.output

    def test_serve_sse_mode(self, cli_runner):
        """Test serve in SSE mode."""
        with patch("redis_sre_agent.mcp_server.server.run_sse") as mock_run:
            result = cli_runner.invoke(mcp, ["serve", "--transport", "sse"])

            assert result.exit_code == 0
            mock_run.assert_called_once_with(host="0.0.0.0", port=8081)
            assert "SSE mode" in result.output

    def test_serve_custom_host_and_port(self, cli_runner):
        """Test serve with custom host and port."""
        with patch("redis_sre_agent.mcp_server.server.run_http") as mock_run:
            result = cli_runner.invoke(
                mcp, ["serve", "--transport", "http", "--host", "127.0.0.1", "--port", "9000"]
            )

            assert result.exit_code == 0
            mock_run.assert_called_once_with(host="127.0.0.1", port=9000)


class TestMCPListToolsCLI:
    """Tests for the mcp list-tools command."""

    def test_list_tools_help(self, cli_runner):
        """Test that list-tools help is available."""
        result = cli_runner.invoke(mcp, ["list-tools", "--help"])

        assert result.exit_code == 0
        assert "List available MCP tools" in result.output

    def test_list_tools_displays_tools(self, cli_runner):
        """Test that list-tools displays available tools."""
        mock_tool = MagicMock()
        mock_tool.name = "test_tool"
        mock_tool.description = "A test tool for testing"

        mock_mcp_server = MagicMock()
        mock_mcp_server._tool_manager._tools = {"test_tool": mock_tool}

        # Patch at the import location inside the function
        with patch(
            "redis_sre_agent.mcp_server.server.mcp",
            mock_mcp_server,
        ):
            result = cli_runner.invoke(mcp, ["list-tools"])

            assert result.exit_code == 0
            assert "Available MCP tools" in result.output
