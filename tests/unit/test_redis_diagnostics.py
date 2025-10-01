"""Tests for Redis diagnostics functionality."""

from unittest.mock import AsyncMock, patch

import pytest

from redis_sre_agent.tools.redis_diagnostics import (
    RedisDiagnostics,
    capture_redis_diagnostics,
    get_redis_diagnostics,
)


@pytest.fixture
def mock_redis_client():
    """Mock Redis client."""
    client = AsyncMock()

    # Mock INFO responses
    client.info.return_value = {
        # Memory section
        "used_memory": 1048576,  # 1MB
        "used_memory_human": "1.00M",
        "used_memory_rss": 2097152,  # 2MB
        "used_memory_peak": 1572864,  # 1.5MB
        "used_memory_peak_human": "1.50M",
        "mem_fragmentation_ratio": 2.0,
        "maxmemory": 0,
        "maxmemory_human": "0B",
        "maxmemory_policy": "noeviction",
        # Performance section
        "instantaneous_ops_per_sec": 100,
        "total_commands_processed": 1000000,
        "keyspace_hits": 800000,
        "keyspace_misses": 200000,
        "expired_keys": 1000,
        "evicted_keys": 0,
        # Client section
        "connected_clients": 10,
        "client_recent_max_input_buffer": 4096,
        "client_recent_max_output_buffer": 8192,
        "blocked_clients": 0,
        "rejected_connections": 0,
        # Replication section
        "role": "master",
        "connected_slaves": 2,
        # Persistence section
        "rdb_last_save_time": 1640995200,  # Unix timestamp
        "rdb_changes_since_last_save": 100,
        "aof_enabled": 0,
        "aof_rewrite_in_progress": 0,
        # CPU section
        "used_cpu_sys": 10.5,
        "used_cpu_user": 15.2,
        "used_cpu_sys_children": 1.0,
        "used_cpu_user_children": 2.0,
        # Server section
        "redis_version": "7.0.0",
        "uptime_in_seconds": 86400,  # 1 day
        "tcp_port": 6379,
    }

    # Mock SLOWLOG response
    client.slowlog_get.return_value = [
        {
            "id": 1,
            "start_time": 1640995200,
            "duration": 50000,  # 50ms in microseconds
            "command": ["GET", "slow_key"],
            "client_addr": "127.0.0.1:12345",
            "client_name": "test_client",
        },
        {
            "id": 2,
            "start_time": 1640995100,
            "duration": 100000,  # 100ms
            "command": ["KEYS", "*"],
            "client_addr": "127.0.0.1:12346",
            "client_name": "bad_client",
        },
    ]

    # Mock CONFIG GET response
    client.config_get.return_value = {
        "maxmemory": "0",
        "maxmemory-policy": "noeviction",
        "timeout": "0",
        "tcp-keepalive": "300",
        "slowlog-log-slower-than": "10000",
        "slowlog-max-len": "128",
    }

    # Mock DBSIZE response
    client.dbsize.return_value = 10000

    return client


class TestCaptureRedisDiagnostics:
    """Test capture_redis_diagnostics function."""

    @pytest.mark.asyncio
    async def test_capture_all_sections(self, mock_redis_client):
        """Test capturing all diagnostic sections."""
        with patch("redis.asyncio.from_url") as mock_from_url:
            mock_from_url.return_value = mock_redis_client

            result = await capture_redis_diagnostics("redis://localhost:6379")

            assert result["redis_url"] == "redis://localhost:6379"
            assert result["timestamp"] is not None
            assert "diagnostics" in result
            diagnostics = result["diagnostics"]
            assert "memory" in diagnostics
            assert "performance" in diagnostics
            assert "clients" in diagnostics
            assert "slowlog" in diagnostics
            assert "configuration" in diagnostics
            assert "keyspace" in diagnostics
            assert "replication" in diagnostics
            assert "persistence" in diagnostics
            assert "cpu" in diagnostics

    @pytest.mark.asyncio
    async def test_capture_specific_sections(self, mock_redis_client):
        """Test capturing specific diagnostic sections."""
        with patch("redis.asyncio.from_url") as mock_from_url:
            mock_from_url.return_value = mock_redis_client

            result = await capture_redis_diagnostics(
                "redis://localhost:6379", sections=["memory", "performance"]
            )

            assert "diagnostics" in result
            diagnostics = result["diagnostics"]
            assert "memory" in diagnostics
            assert "performance" in diagnostics
            assert "clients" not in diagnostics
            assert "slowlog" not in diagnostics

    @pytest.mark.asyncio
    async def test_capture_connection_error(self):
        """Test handling connection errors."""
        # Mock the _test_connection method directly to return an error
        with patch(
            "redis_sre_agent.tools.redis_diagnostics.get_redis_diagnostics"
        ) as mock_get_diagnostics:
            mock_diagnostics = AsyncMock()
            mock_diagnostics._test_connection.return_value = {
                "error": "Connection failed",
                "ping_duration_ms": None,
                "basic_operations_test": False,
            }
            mock_get_diagnostics.return_value = mock_diagnostics

            result = await capture_redis_diagnostics("redis://localhost:6379")

            assert result["capture_status"] == "success"  # Overall capture succeeds
            assert "diagnostics" in result
            assert "connection" in result["diagnostics"]
            connection = result["diagnostics"]["connection"]
            assert "error" in connection
            assert "Connection failed" in connection["error"]


class TestRedisDiagnostics:
    """Test RedisDiagnostics class."""

    @pytest.mark.asyncio
    async def test_init_with_url(self):
        """Test initialization with Redis URL."""
        diagnostics = RedisDiagnostics("redis://test:6379")
        assert diagnostics.redis_url == "redis://test:6379"
        assert diagnostics._client is None

    @pytest.mark.asyncio
    async def test_init_requires_url(self):
        """Test that initialization requires an explicit redis_url."""
        with pytest.raises(ValueError, match="redis_url is required"):
            RedisDiagnostics(redis_url=None)

        with pytest.raises(ValueError, match="redis_url is required"):
            RedisDiagnostics(redis_url="")

        # Should work with valid URL
        diagnostics = RedisDiagnostics(redis_url="redis://target:6379")
        assert diagnostics.redis_url == "redis://target:6379"

    @pytest.mark.asyncio
    async def test_get_client(self):
        """Test getting Redis client."""
        with patch("redis.asyncio.from_url") as mock_from_url:
            mock_client = AsyncMock()
            mock_from_url.return_value = mock_client

            diagnostics = RedisDiagnostics("redis://test:6379")
            client = await diagnostics.get_client()

            assert client == mock_client
            assert diagnostics._client == mock_client
            mock_from_url.assert_called_once_with(
                "redis://test:6379",
                decode_responses=True,
                socket_timeout=10,
                socket_connect_timeout=5,
            )

    @pytest.mark.asyncio
    async def test_close_connection(self):
        """Test closing Redis connection."""
        mock_client = AsyncMock()

        diagnostics = RedisDiagnostics("redis://test:6379")
        diagnostics._client = mock_client

        await diagnostics.close()

        mock_client.aclose.assert_called_once()
        assert diagnostics._client is None


class TestGetRedisDiagnostics:
    """Test get_redis_diagnostics function."""

    def test_get_redis_diagnostics(self):
        """Test getting RedisDiagnostics instance."""
        diagnostics = get_redis_diagnostics("redis://test:6379")
        assert isinstance(diagnostics, RedisDiagnostics)
        assert diagnostics.redis_url == "redis://test:6379"
