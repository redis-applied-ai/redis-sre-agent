"""Unit tests for RedisCommandToolProvider."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import SecretStr

from redis_sre_agent.core.instances import RedisInstance
from redis_sre_agent.tools.diagnostics.redis_command.provider import (
    RedisCliConfig,
    RedisCommandToolProvider,
)
from redis_sre_agent.tools.models import ToolCapability


class TestRedisCliConfig:
    """Test RedisCliConfig model."""

    def test_config_empty(self):
        """Test that config can be created empty."""
        config = RedisCliConfig()
        assert config is not None


class TestRedisCommandToolProviderInit:
    """Test RedisCommandToolProvider initialization."""

    def test_init_with_connection_url(self):
        """Test initialization with connection URL."""
        provider = RedisCommandToolProvider(connection_url="redis://localhost:6379")
        assert provider.connection_url == "redis://localhost:6379"
        assert provider._client is None

    def test_init_with_rediss_url(self):
        """Test initialization with TLS Redis URL."""
        provider = RedisCommandToolProvider(connection_url="rediss://localhost:6380")
        assert provider.connection_url == "rediss://localhost:6380"

    def test_init_with_redis_instance_string_url(self):
        """Test initialization with RedisInstance having string URL."""
        instance = RedisInstance(
            id="test-id",
            name="test-instance",
            connection_url="redis://localhost:6379",
            environment="development",
            usage="cache",
            description="Test instance",
            instance_type="oss_single",
        )
        provider = RedisCommandToolProvider(redis_instance=instance)
        assert provider.connection_url == "redis://localhost:6379"

    def test_init_with_redis_instance_secret_url(self):
        """Test initialization with RedisInstance having SecretStr URL."""
        instance = MagicMock(spec=RedisInstance)
        instance.id = "test-instance-id"
        instance.connection_url = SecretStr("redis://secret:pass@localhost:6379")

        provider = RedisCommandToolProvider(redis_instance=instance)
        assert provider.connection_url == "redis://secret:pass@localhost:6379"

    def test_init_without_url_raises(self):
        """Test initialization without URL raises ValueError."""
        with pytest.raises(
            ValueError, match="Either redis_instance or connection_url must be provided"
        ):
            RedisCommandToolProvider()

    def test_init_with_invalid_scheme_raises(self):
        """Test initialization with invalid URL scheme raises ValueError."""
        with pytest.raises(ValueError, match="Invalid Redis URL scheme"):
            RedisCommandToolProvider(connection_url="http://localhost:6379")


class TestRedisCommandToolProviderProperties:
    """Test RedisCommandToolProvider properties."""

    def test_provider_name(self):
        """Test provider_name property."""
        provider = RedisCommandToolProvider(connection_url="redis://localhost:6379")
        assert provider.provider_name == "redis_command"

    def test_requires_redis_instance(self):
        """Test requires_redis_instance property."""
        provider = RedisCommandToolProvider(connection_url="redis://localhost:6379")
        assert provider.requires_redis_instance is True


class TestRedisCommandToolProviderSchemas:
    """Test RedisCommandToolProvider tool schemas."""

    def test_create_tool_schemas_returns_list(self):
        """Test create_tool_schemas returns list of ToolDefinitions."""
        provider = RedisCommandToolProvider(connection_url="redis://localhost:6379")
        schemas = provider.create_tool_schemas()

        assert isinstance(schemas, list)
        assert len(schemas) > 0

    def test_tool_schemas_have_diagnostics_capability(self):
        """Test all tool schemas have DIAGNOSTICS capability."""
        provider = RedisCommandToolProvider(connection_url="redis://localhost:6379")
        schemas = provider.create_tool_schemas()

        for schema in schemas:
            assert schema.capability == ToolCapability.DIAGNOSTICS

    def test_tool_schemas_include_info(self):
        """Test tool schemas include INFO tool."""
        provider = RedisCommandToolProvider(connection_url="redis://localhost:6379")
        schemas = provider.create_tool_schemas()

        tool_names = [s.name for s in schemas]
        assert any("info" in name for name in tool_names)

    def test_tool_schemas_include_slowlog(self):
        """Test tool schemas include SLOWLOG tool."""
        provider = RedisCommandToolProvider(connection_url="redis://localhost:6379")
        schemas = provider.create_tool_schemas()

        tool_names = [s.name for s in schemas]
        assert any("slowlog" in name for name in tool_names)


class TestRedisCommandToolProviderClient:
    """Test RedisCommandToolProvider client management."""

    def test_get_client_lazy_initialization(self):
        """Test get_client creates client on first call."""
        provider = RedisCommandToolProvider(connection_url="redis://localhost:6379")
        assert provider._client is None

        with patch("redis_sre_agent.tools.diagnostics.redis_command.provider.Redis") as mock_redis:
            mock_client = MagicMock()
            mock_redis.from_url.return_value = mock_client

            client = provider.get_client()

            mock_redis.from_url.assert_called_once_with(
                "redis://localhost:6379", decode_responses=True
            )
            assert client is mock_client

    @pytest.mark.asyncio
    async def test_async_context_manager(self):
        """Test async context manager cleans up client."""
        provider = RedisCommandToolProvider(connection_url="redis://localhost:6379")

        with patch("redis_sre_agent.tools.diagnostics.redis_command.provider.Redis") as mock_redis:
            mock_client = AsyncMock()
            mock_redis.from_url.return_value = mock_client

            # Set client
            provider._client = mock_client

            async with provider:
                pass

            mock_client.aclose.assert_called_once()
            assert provider._client is None


class TestRedisCommandToolProviderStatusUpdate:
    """Test get_status_update method."""

    def test_status_update_info_with_section(self):
        """Test status update for INFO with section."""
        provider = RedisCommandToolProvider(connection_url="redis://localhost:6379")
        result = provider.get_status_update("redis_command_abc123_info", {"section": "memory"})
        assert result == "I'm running Redis INFO for the memory section."

    def test_status_update_info_without_section(self):
        """Test status update for INFO without section."""
        provider = RedisCommandToolProvider(connection_url="redis://localhost:6379")
        result = provider.get_status_update("redis_command_abc123_info", {})
        assert result == "I'm running Redis INFO to collect server metrics."

    def test_status_update_slowlog(self):
        """Test status update for SLOWLOG."""
        provider = RedisCommandToolProvider(connection_url="redis://localhost:6379")
        result = provider.get_status_update("redis_command_abc123_slowlog", {})
        assert result == "I'm checking Redis SLOWLOG for slow queries."

    def test_status_update_client_list(self):
        """Test status update for CLIENT LIST returns None (not handled by get_status_update)."""
        provider = RedisCommandToolProvider(connection_url="redis://localhost:6379")
        # The get_status_update method checks for "client" and "list" in tool_name
        # but the condition is: operation == "client" and "list" in tool_name
        # With tool_name "redis_command_abc123_client_list", operation is "list" not "client"
        result = provider.get_status_update("redis_command_abc123_client_list", {})
        assert result is None  # This operation is not handled by get_status_update

    def test_status_update_config_get(self):
        """Test status update for CONFIG GET."""
        provider = RedisCommandToolProvider(connection_url="redis://localhost:6379")
        result = provider.get_status_update(
            "redis_command_abc123_config_get", {"pattern": "maxmemory*"}
        )
        assert result == "I'm inspecting Redis configuration with CONFIG GET maxmemory*."

    def test_status_update_unknown_returns_none(self):
        """Test status update for unknown operation returns None."""
        provider = RedisCommandToolProvider(connection_url="redis://localhost:6379")
        result = provider.get_status_update("redis_command_abc123_unknown", {})
        assert result is None


class TestRedisCommandToolProviderResolveOperation:
    """Test resolve_operation method."""

    def test_resolve_operation_info(self):
        """Test resolve_operation for info."""
        provider = RedisCommandToolProvider(connection_url="redis://localhost:6379")
        result = provider.resolve_operation("redis_command_abc123_info", {})
        assert result == "info"

    def test_resolve_operation_cluster_info(self):
        """Test resolve_operation for cluster_info."""
        provider = RedisCommandToolProvider(connection_url="redis://localhost:6379")
        result = provider.resolve_operation("redis_command_abc123_cluster_info", {})
        assert result == "cluster_info"

    def test_resolve_operation_replication_info(self):
        """Test resolve_operation for replication_info."""
        provider = RedisCommandToolProvider(connection_url="redis://localhost:6379")
        result = provider.resolve_operation("redis_command_abc123_replication_info", {})
        assert result == "replication_info"

    def test_resolve_operation_slowlog(self):
        """Test resolve_operation for slowlog."""
        provider = RedisCommandToolProvider(connection_url="redis://localhost:6379")
        result = provider.resolve_operation("redis_command_abc123_slowlog", {})
        assert result == "slowlog"

    def test_resolve_operation_config_get(self):
        """Test resolve_operation for config_get."""
        provider = RedisCommandToolProvider(connection_url="redis://localhost:6379")
        result = provider.resolve_operation("redis_command_abc123_config_get", {})
        assert result == "config_get"

    def test_resolve_operation_client_list(self):
        """Test resolve_operation for client_list."""
        provider = RedisCommandToolProvider(connection_url="redis://localhost:6379")
        result = provider.resolve_operation("redis_command_abc123_client_list", {})
        assert result == "client_list"

    def test_resolve_operation_memory_stats(self):
        """Test resolve_operation for memory_stats."""
        provider = RedisCommandToolProvider(connection_url="redis://localhost:6379")
        result = provider.resolve_operation("redis_command_abc123_memory_stats", {})
        assert result == "memory_stats"

    def test_resolve_operation_sample_keys(self):
        """Test resolve_operation for sample_keys."""
        provider = RedisCommandToolProvider(connection_url="redis://localhost:6379")
        result = provider.resolve_operation("redis_command_abc123_sample_keys", {})
        assert result == "sample_keys"

    def test_resolve_operation_search_indexes(self):
        """Test resolve_operation for search_indexes."""
        provider = RedisCommandToolProvider(connection_url="redis://localhost:6379")
        result = provider.resolve_operation("redis_command_abc123_search_indexes", {})
        assert result == "search_indexes"

    def test_resolve_operation_acl_log(self):
        """Test resolve_operation for acl_log."""
        provider = RedisCommandToolProvider(connection_url="redis://localhost:6379")
        result = provider.resolve_operation("redis_command_abc123_acl_log", {})
        assert result == "acl_log"

    def test_resolve_operation_search_index_info(self):
        """Test resolve_operation for search_index_info."""
        provider = RedisCommandToolProvider(connection_url="redis://localhost:6379")
        result = provider.resolve_operation("redis_command_abc123_search_index_info", {})
        assert result == "search_index_info"


class TestRedisCommandToolProviderInfoMethod:
    """Test info method."""

    @pytest.mark.asyncio
    async def test_info_success(self):
        """Test info method success."""
        provider = RedisCommandToolProvider(connection_url="redis://localhost:6379")

        with patch.object(provider, "get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.info = AsyncMock(
                return_value={"redis_version": "7.2.0", "used_memory": 1024}
            )
            mock_get_client.return_value = mock_client

            result = await provider.info()

            assert result["status"] == "success"
            assert result["section"] == "all"
            assert result["data"]["redis_version"] == "7.2.0"

    @pytest.mark.asyncio
    async def test_info_with_section(self):
        """Test info method with specific section."""
        provider = RedisCommandToolProvider(connection_url="redis://localhost:6379")

        with patch.object(provider, "get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.info = AsyncMock(
                return_value={"used_memory": 1024, "used_memory_human": "1K"}
            )
            mock_get_client.return_value = mock_client

            result = await provider.info(section="memory")

            assert result["status"] == "success"
            assert result["section"] == "memory"
            mock_client.info.assert_called_once_with("memory")

    @pytest.mark.asyncio
    async def test_info_error(self):
        """Test info method error handling."""
        provider = RedisCommandToolProvider(connection_url="redis://localhost:6379")

        with patch.object(provider, "get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.info = AsyncMock(side_effect=Exception("Connection refused"))
            mock_get_client.return_value = mock_client

            result = await provider.info()

            assert result["status"] == "error"
            assert "Connection refused" in result["error"]


class TestRedisCommandToolProviderSlowlogMethod:
    """Test slowlog method."""

    @pytest.mark.asyncio
    async def test_slowlog_success(self):
        """Test slowlog method success."""
        provider = RedisCommandToolProvider(connection_url="redis://localhost:6379")

        mock_entries = [
            {
                "id": 1,
                "start_time": 1700000000,
                "duration": 5000,
                "command": ["GET", "key1"],
                "client_address": "127.0.0.1:12345",
                "client_name": "test-client",
            }
        ]

        with patch.object(provider, "get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.slowlog_get = AsyncMock(return_value=mock_entries)
            mock_get_client.return_value = mock_client

            result = await provider.slowlog(count=10)

            assert result["status"] == "success"
            assert result["count"] == 1
            assert result["entries"][0]["id"] == 1
            assert result["entries"][0]["duration_us"] == 5000

    @pytest.mark.asyncio
    async def test_slowlog_error(self):
        """Test slowlog method error handling."""
        provider = RedisCommandToolProvider(connection_url="redis://localhost:6379")

        with patch.object(provider, "get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.slowlog_get = AsyncMock(side_effect=Exception("Command not allowed"))
            mock_get_client.return_value = mock_client

            result = await provider.slowlog()

            assert result["status"] == "error"
            assert "Command not allowed" in result["error"]


class TestRedisCommandToolProviderAclLogMethod:
    """Test acl_log method."""

    @pytest.mark.asyncio
    async def test_acl_log_success(self):
        """Test acl_log method success."""
        provider = RedisCommandToolProvider(connection_url="redis://localhost:6379")

        mock_entries = [
            {
                "count": 5,
                "reason": "auth",
                "context": "toplevel",
                "object": "GET",
                "username": "default",
                "age-seconds": 10,
                "client-info": "127.0.0.1:12345",
            }
        ]

        with patch.object(provider, "get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.acl_log = AsyncMock(return_value=mock_entries)
            mock_get_client.return_value = mock_client

            result = await provider.acl_log(count=10)

            assert result["status"] == "success"
            assert result["count"] == 1
            assert result["entries"][0]["reason"] == "auth"

    @pytest.mark.asyncio
    async def test_acl_log_error(self):
        """Test acl_log method error handling."""
        provider = RedisCommandToolProvider(connection_url="redis://localhost:6379")

        with patch.object(provider, "get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.acl_log = AsyncMock(side_effect=Exception("ACL not enabled"))
            mock_get_client.return_value = mock_client

            result = await provider.acl_log()

            assert result["status"] == "error"
            assert "ACL not enabled" in result["error"]


class TestRedisCommandToolProviderConfigGet:
    """Test config_get method."""

    @pytest.mark.asyncio
    async def test_config_get_success(self):
        """Test config_get method success."""
        provider = RedisCommandToolProvider(connection_url="redis://localhost:6379")

        with patch.object(provider, "get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.config_get = AsyncMock(
                return_value={"maxmemory": "100mb", "maxclients": "10000"}
            )
            mock_get_client.return_value = mock_client

            result = await provider.config_get("max*")

            assert result["status"] == "success"
            assert result["pattern"] == "max*"
            assert result["count"] == 2

    @pytest.mark.asyncio
    async def test_config_get_error(self):
        """Test config_get method error handling."""
        provider = RedisCommandToolProvider(connection_url="redis://localhost:6379")

        with patch.object(provider, "get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.config_get = AsyncMock(side_effect=Exception("Permission denied"))
            mock_get_client.return_value = mock_client

            result = await provider.config_get("*")

            assert result["status"] == "error"
            assert "Permission denied" in result["error"]


class TestRedisCommandToolProviderClientList:
    """Test client_list method."""

    @pytest.mark.asyncio
    async def test_client_list_success(self):
        """Test client_list method success."""
        provider = RedisCommandToolProvider(connection_url="redis://localhost:6379")

        mock_clients = [
            {"id": 1, "addr": "127.0.0.1:12345", "name": "client1"},
            {"id": 2, "addr": "127.0.0.1:12346", "name": "client2"},
        ]

        with patch.object(provider, "get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.client_list = AsyncMock(return_value=mock_clients)
            mock_get_client.return_value = mock_client

            result = await provider.client_list()

            assert result["status"] == "success"
            assert result["count"] == 2
            assert result["client_type"] == "all"

    @pytest.mark.asyncio
    async def test_client_list_with_type(self):
        """Test client_list with type filter."""
        provider = RedisCommandToolProvider(connection_url="redis://localhost:6379")

        with patch.object(provider, "get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.client_list = AsyncMock(return_value=[{"id": 1}])
            mock_get_client.return_value = mock_client

            result = await provider.client_list(client_type="normal")

            assert result["status"] == "success"
            assert result["client_type"] == "normal"
            mock_client.client_list.assert_called_once_with(_type="normal")

    @pytest.mark.asyncio
    async def test_client_list_error(self):
        """Test client_list method error handling."""
        provider = RedisCommandToolProvider(connection_url="redis://localhost:6379")

        with patch.object(provider, "get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.client_list = AsyncMock(side_effect=Exception("Command failed"))
            mock_get_client.return_value = mock_client

            result = await provider.client_list()

            assert result["status"] == "error"
            assert "Command failed" in result["error"]


class TestRedisCommandToolProviderClusterInfo:
    """Test cluster_info method."""

    @pytest.mark.asyncio
    async def test_cluster_info_success(self):
        """Test cluster_info method success."""
        provider = RedisCommandToolProvider(connection_url="redis://localhost:6379")

        with patch.object(provider, "get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.cluster = AsyncMock(
                return_value="cluster_state:ok\ncluster_slots_assigned:16384"
            )
            mock_get_client.return_value = mock_client

            result = await provider.cluster_info()

            assert result["status"] == "success"
            assert "cluster_info" in result

    @pytest.mark.asyncio
    async def test_cluster_info_error(self):
        """Test cluster_info method error handling."""
        provider = RedisCommandToolProvider(connection_url="redis://localhost:6379")

        with patch.object(provider, "get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.cluster = AsyncMock(side_effect=Exception("CLUSTER not enabled"))
            mock_get_client.return_value = mock_client

            result = await provider.cluster_info()

            assert result["status"] == "error"
            assert "CLUSTER not enabled" in result["error"]


class TestRedisCommandToolProviderReplicationInfo:
    """Test replication_info method."""

    @pytest.mark.asyncio
    async def test_replication_info_success(self):
        """Test replication_info method success."""
        provider = RedisCommandToolProvider(connection_url="redis://localhost:6379")

        with patch.object(provider, "get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.info = AsyncMock(return_value={"role": "master", "connected_slaves": 2})
            mock_client.execute_command = AsyncMock(return_value=["master", 1234, []])
            mock_get_client.return_value = mock_client

            result = await provider.replication_info()

            assert result["status"] == "success"
            assert "info" in result
            assert result["role"]["type"] == "master"

    @pytest.mark.asyncio
    async def test_replication_info_error(self):
        """Test replication_info method error handling."""
        provider = RedisCommandToolProvider(connection_url="redis://localhost:6379")

        with patch.object(provider, "get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.info = AsyncMock(side_effect=Exception("Connection lost"))
            mock_get_client.return_value = mock_client

            result = await provider.replication_info()

            assert result["status"] == "error"
            assert "Connection lost" in result["error"]


class TestRedisCommandToolProviderMemoryStats:
    """Test memory_stats method."""

    @pytest.mark.asyncio
    async def test_memory_stats_success(self):
        """Test memory_stats method success."""
        provider = RedisCommandToolProvider(connection_url="redis://localhost:6379")

        with patch.object(provider, "get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.memory_stats = AsyncMock(
                return_value={"peak.allocated": 1234567, "total.allocated": 987654}
            )
            mock_get_client.return_value = mock_client

            result = await provider.memory_stats()

            assert result["status"] == "success"
            assert "stats" in result
            assert result["stats"]["peak.allocated"] == 1234567

    @pytest.mark.asyncio
    async def test_memory_stats_error(self):
        """Test memory_stats method error handling."""
        provider = RedisCommandToolProvider(connection_url="redis://localhost:6379")

        with patch.object(provider, "get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.memory_stats = AsyncMock(side_effect=Exception("MEMORY command disabled"))
            mock_get_client.return_value = mock_client

            result = await provider.memory_stats()

            assert result["status"] == "error"
            assert "MEMORY command disabled" in result["error"]
