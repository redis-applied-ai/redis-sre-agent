"""Unit tests for MCP connection pool."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from redis_sre_agent.tools.mcp.pool import MCPConnectionPool, PooledConnection


class TestMCPConnectionPool:
    """Test MCPConnectionPool functionality."""

    def setup_method(self):
        """Reset singleton before each test."""
        MCPConnectionPool.reset_instance()

    def teardown_method(self):
        """Reset singleton after each test."""
        MCPConnectionPool.reset_instance()

    def test_singleton_pattern(self):
        """Test that get_instance returns the same instance."""
        pool1 = MCPConnectionPool.get_instance()
        pool2 = MCPConnectionPool.get_instance()
        assert pool1 is pool2

    def test_reset_instance(self):
        """Test that reset_instance clears the singleton."""
        pool1 = MCPConnectionPool.get_instance()
        MCPConnectionPool.reset_instance()
        pool2 = MCPConnectionPool.get_instance()
        assert pool1 is not pool2

    def test_stats_before_start(self):
        """Test stats before pool is started."""
        pool = MCPConnectionPool.get_instance()
        stats = pool.stats()
        assert stats["started"] is False
        assert stats["servers_connected"] == 0

    def test_get_connection_before_start(self):
        """Test get_connection returns None before start."""
        pool = MCPConnectionPool.get_instance()
        conn = pool.get_connection("some_server")
        assert conn is None

    @pytest.mark.asyncio
    async def test_start_with_no_servers(self):
        """Test start when no MCP servers are configured."""
        pool = MCPConnectionPool.get_instance()

        with patch("redis_sre_agent.core.config.settings") as mock_settings:
            mock_settings.mcp_servers = {}
            status = await pool.start()

        assert status == {}
        assert pool._started is True

    @pytest.mark.asyncio
    async def test_start_connects_to_servers(self):
        """Test start connects to configured servers."""
        pool = MCPConnectionPool.get_instance()

        mock_config = MagicMock()
        mock_config.command = "test-command"
        mock_config.url = None

        # Mock the settings to return one server
        with patch("redis_sre_agent.core.config.settings") as mock_settings:
            mock_settings.mcp_servers = {"test-server": mock_config}

            # Mock the connection method
            with patch.object(pool, "_connect_server") as mock_connect:
                mock_connect.return_value = True
                status = await pool.start()

        assert status == {"test-server": True}
        mock_connect.assert_called_once_with("test-server", mock_config)

    @pytest.mark.asyncio
    async def test_get_connection_after_start(self):
        """Test get_connection returns connection after start."""
        pool = MCPConnectionPool.get_instance()

        # Manually add a connection
        mock_session = MagicMock()
        mock_tools = [MagicMock()]
        mock_exit_stack = MagicMock()
        pool._connections["test-server"] = PooledConnection(
            server_name="test-server",
            session=mock_session,
            tools=mock_tools,
            exit_stack=mock_exit_stack,
        )
        pool._started = True

        conn = pool.get_connection("test-server")
        assert conn is not None
        assert conn.session is mock_session
        assert conn.tools == mock_tools

    def test_get_connection_unknown_server(self):
        """Test get_connection returns None for unknown server."""
        pool = MCPConnectionPool.get_instance()
        pool._started = True

        conn = pool.get_connection("unknown-server")
        assert conn is None

    @pytest.mark.asyncio
    async def test_shutdown_clears_connections(self):
        """Test shutdown clears all connections."""
        pool = MCPConnectionPool.get_instance()
        pool._started = True

        # Add a mock connection
        mock_exit_stack = AsyncMock()
        pool._connections["test-server"] = PooledConnection(
            server_name="test-server",
            session=MagicMock(),
            tools=[],
            exit_stack=mock_exit_stack,
        )

        await pool.shutdown()

        assert len(pool._connections) == 0
        assert pool._started is False

    def test_stats_after_connections(self):
        """Test stats reflects connection state."""
        pool = MCPConnectionPool.get_instance()
        pool._started = True

        # Add mock connections
        pool._connections["server1"] = PooledConnection(
            server_name="server1",
            session=MagicMock(),
            tools=[MagicMock(), MagicMock()],
            exit_stack=MagicMock(),
        )
        pool._connections["server2"] = PooledConnection(
            server_name="server2",
            session=MagicMock(),
            tools=[MagicMock()],
            exit_stack=MagicMock(),
        )

        stats = pool.stats()
        assert stats["started"] is True
        assert stats["servers_connected"] == 2
        assert "server1" in stats["connections"]
        assert stats["connections"]["server1"]["tools"] == 2
        assert stats["connections"]["server2"]["tools"] == 1
