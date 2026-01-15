"""Tests for Redis Enterprise admin API tool provider.

These are unit tests with mocked HTTP responses - no actual Redis Enterprise cluster required.
Mock responses are validated against Pydantic schemas derived from the official API documentation.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from redis_sre_agent.core.instances import RedisInstance
from redis_sre_agent.tools.admin.redis_enterprise.provider import (
    RedisEnterpriseAdminConfig,
    RedisEnterpriseAdminToolProvider,
)

# Import test-only schemas for validating mock responses
from tests.tools.redis_enterprise_schemas import (
    ActionObject,
    BDBObject,
    ClusterObject,
    NodeObject,
)


@pytest.fixture
def redis_instance():
    """Create a test Redis instance with admin API configuration."""
    return RedisInstance(
        id="test-redis-1",
        name="test-cluster",
        connection_url="redis://localhost:6379",
        environment="test",
        usage="cache",
        description="Test Redis Enterprise cluster",
        instance_type="redis_enterprise",
        admin_url="https://test-cluster.example.com:9443",
        admin_username="test@example.com",
        admin_password="test-password",
    )


@pytest.fixture
def config():
    """Create a test configuration."""
    return RedisEnterpriseAdminConfig(verify_ssl=False)


@pytest.fixture
def provider(redis_instance, config):
    """Create a test provider instance."""
    return RedisEnterpriseAdminToolProvider(redis_instance=redis_instance, config=config)


@pytest.mark.asyncio
async def test_provider_initialization(provider, config, redis_instance):
    """Test provider initialization."""
    assert provider.provider_name == "re_admin"  # Shortened to avoid OpenAI 64-char tool name limit
    assert provider.config == config
    assert provider.redis_instance == redis_instance
    assert provider._client is None


@pytest.mark.asyncio
async def test_provider_requires_instance():
    """Test that provider requires a RedisInstance."""
    with pytest.raises(ValueError, match="RedisInstance is required"):
        RedisEnterpriseAdminToolProvider(redis_instance=None)


@pytest.mark.asyncio
async def test_provider_requires_admin_url():
    """Test that provider requires admin_url in instance."""
    instance = RedisInstance(
        id="test-redis-1",
        name="test-cluster",
        connection_url="redis://localhost:6379",
        environment="test",
        usage="cache",
        description="Test Redis cluster without admin URL",
        instance_type="redis_enterprise",
        # Missing admin_url
    )
    with pytest.raises(ValueError, match="must have admin_url set"):
        RedisEnterpriseAdminToolProvider(redis_instance=instance)


@pytest.mark.asyncio
async def test_create_tool_schemas(provider):
    """Test tool schema creation."""
    schemas = provider.create_tool_schemas()

    assert len(schemas) > 0

    # Check that all expected tools are present
    tool_names = [schema.name for schema in schemas]

    # All tools should have the provider name and hash
    for name in tool_names:
        assert name.startswith("re_admin_")  # Shortened provider name

    # Check for specific tools
    assert any("cluster" in name and "info" in name for name in tool_names)
    assert any("databases" in name for name in tool_names)
    assert any("nodes" in name for name in tool_names)
    assert any("modules" in name for name in tool_names)
    assert any("actions" in name for name in tool_names)
    assert any("shards" in name for name in tool_names)


@pytest.mark.asyncio
async def test_get_cluster_info_success(provider):
    """Test successful cluster info retrieval with schema validation."""
    # Create a mock response that matches the ClusterObject schema
    cluster_data = {
        "name": "test-cluster",
        "nodes_count": 3,
        "shards_count": 10,
        "rack_aware": False,
        "email_alerts": True,
        "created_time": "2024-01-01T00:00:00Z",
    }

    # Validate against schema
    ClusterObject(**cluster_data)

    mock_response = MagicMock()
    mock_response.json.return_value = cluster_data
    mock_response.raise_for_status = MagicMock()

    with patch.object(provider, "get_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_get_client.return_value = mock_client

        result = await provider.get_cluster_info()

        assert result["status"] == "success"
        assert "data" in result
        assert result["data"]["name"] == "test-cluster"
        assert "timestamp" in result

        mock_client.get.assert_called_once_with("/v1/cluster")


@pytest.mark.asyncio
async def test_list_databases_success(provider):
    """Test successful database listing with schema validation."""
    # Create mock databases that match the BDBObject schema
    databases = [
        {
            "uid": 1,
            "name": "db1",
            "type": "redis",
            "memory_size": 1073741824,
            "status": "active",
            "shards_count": 2,
            "replication": True,
        },
        {
            "uid": 2,
            "name": "db2",
            "type": "redis",
            "memory_size": 2147483648,
            "status": "active",
            "shards_count": 4,
            "replication": False,
        },
    ]

    # Validate each database against schema
    for db in databases:
        BDBObject(**db)

    mock_response = MagicMock()
    mock_response.json.return_value = databases
    mock_response.raise_for_status = MagicMock()

    with patch.object(provider, "get_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_get_client.return_value = mock_client

        result = await provider.list_databases()

        assert result["status"] == "success"
        assert result["count"] == 2
        assert len(result["databases"]) == 2
        assert result["databases"][0]["name"] == "db1"

        mock_client.get.assert_called_once_with("/v1/bdbs", params={})


@pytest.mark.asyncio
async def test_list_databases_with_fields(provider):
    """Test database listing with field filtering."""
    mock_response = MagicMock()
    mock_response.json.return_value = [
        {"uid": 1, "name": "db1"},
        {"uid": 2, "name": "db2"},
    ]
    mock_response.raise_for_status = MagicMock()

    with patch.object(provider, "get_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_get_client.return_value = mock_client

        result = await provider.list_databases(fields="uid,name")

        assert result["status"] == "success"
        mock_client.get.assert_called_once_with("/v1/bdbs", params={"fields": "uid,name"})


@pytest.mark.asyncio
async def test_get_database_success(provider):
    """Test successful database retrieval with schema validation."""
    database_data = {
        "uid": 1,
        "name": "test-db",
        "type": "redis",
        "memory_size": 1073741824,
        "status": "active",
        "shards_count": 2,
        "replication": True,
        "data_persistence": "aof",
        "aof_policy": "appendfsync-every-sec",
        "eviction_policy": "volatile-lru",
        "port": 12000,
        "redis_version": "7.2",
    }

    # Validate against schema
    BDBObject(**database_data)

    mock_response = MagicMock()
    mock_response.json.return_value = database_data
    mock_response.raise_for_status = MagicMock()

    with patch.object(provider, "get_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_get_client.return_value = mock_client

        result = await provider.get_database(uid=1)

        assert result["status"] == "success"
        assert result["database"]["uid"] == 1
        assert result["database"]["name"] == "test-db"

        mock_client.get.assert_called_once_with("/v1/bdbs/1", params={})


@pytest.mark.asyncio
async def test_list_nodes_success(provider):
    """Test successful node listing with schema validation."""
    nodes = [
        {
            "uid": 1,
            "addr": "10.0.0.1",
            "status": "active",
            "accept_servers": True,
            "shard_count": 5,
            "total_memory": 17179869184,
            "available_memory": 8589934592,
            "cores": 4,
        },
        {
            "uid": 2,
            "addr": "10.0.0.2",
            "status": "active",
            "accept_servers": False,  # Maintenance mode
            "shard_count": 3,
            "total_memory": 17179869184,
            "available_memory": 10737418240,
            "cores": 4,
        },
    ]

    # Validate each node against schema
    for node in nodes:
        NodeObject(**node)

    mock_response = MagicMock()
    mock_response.json.return_value = nodes
    mock_response.raise_for_status = MagicMock()

    with patch.object(provider, "get_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_get_client.return_value = mock_client

        result = await provider.list_nodes()

        assert result["status"] == "success"
        assert result["count"] == 2
        assert len(result["nodes"]) == 2
        # Node 2 is in maintenance mode (accept_servers=False)
        assert result["nodes"][1]["accept_servers"] is False

        mock_client.get.assert_called_once_with("/v1/nodes", params={})


@pytest.mark.asyncio
async def test_list_actions_success(provider):
    """Test successful action listing with schema validation."""
    actions = [
        {
            "action_uid": "abc-123",
            "name": "SMCreateBDB",
            "status": "running",
            "progress": 45.0,
            "creation_time": 1742595918,
            "additional_info": {
                "pending_ops": {
                    "3": {
                        "op_name": "wait_for_persistence",
                        "status_description": "Waiting for AOF sync",
                        "progress": 45.0,
                    }
                }
            },
        },
        {
            "action_uid": "def-456",
            "name": "migrate_shard",
            "status": "completed",
            "progress": 100.0,
            "creation_time": 1742595800,
        },
    ]

    # Validate each action against schema
    for action in actions:
        ActionObject(**action)

    mock_response = MagicMock()
    mock_response.json.return_value = actions
    mock_response.raise_for_status = MagicMock()

    with patch.object(provider, "get_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_get_client.return_value = mock_client

        result = await provider.list_actions()

        assert result["status"] == "success"
        assert result["count"] == 2
        assert len(result["actions"]) == 2

        mock_client.get.assert_called_once_with("/v2/actions")


@pytest.mark.asyncio
async def test_resolve_tool_call(provider):
    """Test that tools() wires get_cluster_info to the provider method."""

    # Patch before calling tools() so the invoke closure captures the mock
    with patch.object(provider, "get_cluster_info", new_callable=AsyncMock) as mock_method:
        mock_method.return_value = {"status": "success", "data": {}}

        tools = provider.tools()
        tool = next(t for t in tools if t.metadata.name.endswith("get_cluster_info"))

        result = await tool.invoke({})

        assert result["status"] == "success"
        mock_method.assert_called_once_with()


@pytest.mark.asyncio
async def test_context_manager(provider):
    """Test async context manager."""
    async with provider as p:
        assert p is provider
        # Client should be None until first use
        assert p._client is None

    # After exit, client should be cleaned up
    assert provider._client is None


@pytest.mark.asyncio
async def test_error_handling(provider):
    """Test error handling for HTTP errors."""
    from httpx import HTTPStatusError, Request, Response

    mock_request = Request("GET", "https://test.com/v1/cluster")
    mock_response = Response(404, request=mock_request, text="Not Found")

    with patch.object(provider, "get_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(
            side_effect=HTTPStatusError("Not Found", request=mock_request, response=mock_response)
        )
        mock_get_client.return_value = mock_client

        result = await provider.get_cluster_info()

        assert result["status"] == "error"
        assert "HTTP 404" in result["error"]


@pytest.mark.asyncio
async def test_rebalance_status_classifies_smupdatebdb_with_detail(provider, monkeypatch):
    """SMUpdateBDB without obvious pending_ops in the list should be classified as rebalance
    after fetching action details that include migrate_shard/reshard operations.
    """
    # /v2/actions (list) - ambiguous SMUpdateBDB, no additional_info
    actions_list = [
        {
            "action_uid": "abc-123",
            "name": "SMUpdateBDB",
            "status": "running",
            "progress": 10.0,
            "creation_time": 1700000000,
            # object_name omitted in list; will appear in detail
        }
    ]

    list_resp = MagicMock()
    list_resp.json.return_value = actions_list
    list_resp.raise_for_status = MagicMock()

    # /v2/actions/abc-123 (detail) - include pending_ops that indicate migrate_shard
    action_detail = {
        "action_uid": "abc-123",
        "name": "SMUpdateBDB",
        "status": "running",
        "progress": 50.0,
        "creation_time": 1700000000,
        "object_name": "bdb:1",
        "additional_info": {
            "pending_ops": {
                "shard:1": {
                    "op_name": "migrate_shard",
                    "status_description": "moving",
                    "progress": 50.0,
                }
            }
        },
    }
    detail_resp = MagicMock()
    detail_resp.json.return_value = action_detail
    detail_resp.raise_for_status = MagicMock()

    async def get_side_effect(path, params=None):
        if path == "/v2/actions":
            return list_resp
        if path == "/v2/actions/abc-123":
            return detail_resp
        raise AssertionError(f"Unexpected GET path {path}")

    with patch.object(provider, "get_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=get_side_effect)
        mock_get_client.return_value = mock_client

        result = await provider.rebalance_status(db_uid=1)

        assert result["status"] == "success"
        # Should classify as active rebalance due to detail pending_ops
        assert len(result["active"]) == 1
        row = result["active"][0]
        assert row["action_uid"] == "abc-123"
        assert row["db_uid"] == 1
        assert "SMUpdateBDB" in row["reason"]


@pytest.mark.asyncio
async def test_rebalance_status_recent_completed_window(provider, monkeypatch):
    """Completed migrate_shard within the recent window should appear under recent_completed."""
    fixed_now = 2_000_000_000
    monkeypatch.setenv("TZ", "UTC")

    # Create a completed action 60s ago
    recent_action = {
        "action_uid": "def-456",
        "name": "migrate_shard",
        "status": "completed",
        "progress": 100.0,
        "creation_time": fixed_now - 60,
        "object_name": "bdb:2",
    }

    list_resp = MagicMock()
    list_resp.json.return_value = [recent_action]
    list_resp.raise_for_status = MagicMock()

    with (
        patch.object(provider, "get_client") as mock_get_client,
        patch("time.time", return_value=fixed_now),
    ):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=list_resp)
        mock_get_client.return_value = mock_client

        result = await provider.rebalance_status(
            db_uid=2, include_recent_completed=True, recent_seconds=120
        )

        assert result["status"] == "success"
        assert len(result["active"]) == 0
        assert len(result["recent_completed"]) == 1
        row = result["recent_completed"][0]
        assert row["action_uid"] == "def-456"
        assert row["db_uid"] == 2


@pytest.mark.asyncio
async def test_get_logs_success(provider):
    logs = [
        {"id": 1, "level": "info", "msg": "cluster started", "time": "2025-01-01T00:00:00Z"},
        {"id": 2, "level": "warn", "msg": "rebalance started", "time": "2025-01-01T00:05:00Z"},
    ]

    mock_response = MagicMock()
    mock_response.json.return_value = logs
    mock_response.raise_for_status = MagicMock()

    with patch.object(provider, "get_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_get_client.return_value = mock_client

        result = await provider.get_logs(order="desc", limit=100)

        assert result["status"] == "success"
        assert result["count"] == 2
        assert len(result["logs"]) == 2
        mock_client.get.assert_called_once_with("/v1/logs", params={"order": "desc", "limit": 100})


@pytest.mark.asyncio
async def test_get_logs_normalizes_now(provider):
    mock_response = MagicMock()
    mock_response.json.return_value = []
    mock_response.raise_for_status = MagicMock()

    with patch.object(provider, "get_client") as mock_get_client:
        mock_client = AsyncMock()
        captured = {}

        async def fake_get(path, params=None):
            captured["params"] = params or {}
            return mock_response

        mock_client.get = AsyncMock(side_effect=fake_get)
        mock_get_client.return_value = mock_client

        result = await provider.get_logs(
            order="desc", limit=10, stime="2025-01-01T00:00:00Z", etime="now"
        )

        assert result["status"] == "success"
        sent = captured["params"]
        assert sent["etime"] != "now"
        assert "+00:00" in sent["etime"]


@pytest.mark.asyncio
async def test_system_hosts_from_nodes(provider):
    nodes = [
        {"uid": 1, "addr": "10.0.0.1"},
        {"uid": 2, "addr": "10.0.0.2"},
    ]
    mock_response = MagicMock()
    mock_response.json.return_value = nodes
    mock_response.raise_for_status = MagicMock()
    with patch.object(provider, "get_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_get_client.return_value = mock_client
        hosts = await provider.system_hosts()
        hs = [h.host for h in hosts]
        assert "10.0.0.1" in hs and "10.0.0.2" in hs
        assert all(h.role == "enterprise-node" for h in hosts)


class TestRedisEnterpriseAdminConfig:
    """Test RedisEnterpriseAdminConfig model."""

    def test_default_verify_ssl_is_false(self):
        """Test default verify_ssl is False."""
        config = RedisEnterpriseAdminConfig()
        assert config.verify_ssl is False

    def test_custom_verify_ssl(self):
        """Test custom verify_ssl value."""
        config = RedisEnterpriseAdminConfig(verify_ssl=True)
        assert config.verify_ssl is True


class TestRedisEnterpriseAdminToolProviderProperties:
    """Test RedisEnterpriseAdminToolProvider properties."""

    def test_provider_name_is_re_admin(self, provider):
        """Test provider_name is re_admin."""
        assert provider.provider_name == "re_admin"

    def test_requires_redis_instance_is_true(self, provider):
        """Test requires_redis_instance is True."""
        assert provider.requires_redis_instance is True

    def test_client_initially_none(self, provider):
        """Test _client is initially None."""
        assert provider._client is None


class TestRedisEnterpriseAdminToolProviderResolveOperation:
    """Test resolve_operation method."""

    def test_resolve_operation_extracts_operation_name(self, provider):
        """Test resolve_operation extracts operation name from tool name."""
        result = provider.resolve_operation("re_admin_abc123_get_cluster_info", {})
        assert result == "get_cluster_info"

    def test_resolve_operation_with_invalid_format(self, provider):
        """Test resolve_operation returns None for invalid format."""
        result = provider.resolve_operation("invalid_tool_name", {})
        assert result is None

    def test_resolve_operation_with_complex_operation_name(self, provider):
        """Test resolve_operation with complex operation name."""
        result = provider.resolve_operation("re_admin_def456_list_database_shards", {})
        assert result == "list_database_shards"


class TestRedisEnterpriseAdminGetNode:
    """Test get_node method."""

    @pytest.mark.asyncio
    async def test_get_node_success(self, provider):
        """Test get_node method success."""
        node_data = {"uid": 1, "addr": "10.0.0.1", "status": "active"}

        mock_response = MagicMock()
        mock_response.json.return_value = node_data
        mock_response.raise_for_status = MagicMock()

        with patch.object(provider, "get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            result = await provider.get_node(uid=1)

            assert result["status"] == "success"
            assert result["node"]["uid"] == 1
            mock_client.get.assert_called_once_with("/v1/nodes/1", params={})

    @pytest.mark.asyncio
    async def test_get_node_with_fields(self, provider):
        """Test get_node with field filtering."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"uid": 1, "status": "active"}
        mock_response.raise_for_status = MagicMock()

        with patch.object(provider, "get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            result = await provider.get_node(uid=1, fields="uid,status")

            assert result["status"] == "success"
            mock_client.get.assert_called_once_with("/v1/nodes/1", params={"fields": "uid,status"})

    @pytest.mark.asyncio
    async def test_get_node_http_error(self, provider):
        """Test get_node HTTP error handling."""
        from httpx import HTTPStatusError, Request, Response

        mock_request = Request("GET", "https://test.com/v1/nodes/1")
        mock_response = Response(404, request=mock_request, text="Not Found")

        with patch.object(provider, "get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(
                side_effect=HTTPStatusError(
                    "Not Found", request=mock_request, response=mock_response
                )
            )
            mock_get_client.return_value = mock_client

            result = await provider.get_node(uid=99)

            assert result["status"] == "error"
            assert "HTTP 404" in result["error"]


class TestRedisEnterpriseAdminGetDatabase:
    """Test get_database method."""

    @pytest.mark.asyncio
    async def test_get_database_http_error(self, provider):
        """Test get_database HTTP error handling."""
        from httpx import HTTPStatusError, Request, Response

        mock_request = Request("GET", "https://test.com/v1/bdbs/99")
        mock_response = Response(404, request=mock_request, text="Database not found")

        with patch.object(provider, "get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(
                side_effect=HTTPStatusError(
                    "Not Found", request=mock_request, response=mock_response
                )
            )
            mock_get_client.return_value = mock_client

            result = await provider.get_database(uid=99)

            assert result["status"] == "error"
            assert "HTTP 404" in result["error"]


class TestRedisEnterpriseAdminListDatabases:
    """Test list_databases method."""

    @pytest.mark.asyncio
    async def test_list_databases_http_error(self, provider):
        """Test list_databases HTTP error handling."""
        from httpx import HTTPStatusError, Request, Response

        mock_request = Request("GET", "https://test.com/v1/bdbs")
        mock_response = Response(500, request=mock_request, text="Internal error")

        with patch.object(provider, "get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(
                side_effect=HTTPStatusError("Error", request=mock_request, response=mock_response)
            )
            mock_get_client.return_value = mock_client

            result = await provider.list_databases()

            assert result["status"] == "error"
            assert "HTTP 500" in result["error"]


class TestRedisEnterpriseAdminListNodes:
    """Test list_nodes method."""

    @pytest.mark.asyncio
    async def test_list_nodes_http_error(self, provider):
        """Test list_nodes HTTP error handling."""
        from httpx import HTTPStatusError, Request, Response

        mock_request = Request("GET", "https://test.com/v1/nodes")
        mock_response = Response(503, request=mock_request, text="Service unavailable")

        with patch.object(provider, "get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(
                side_effect=HTTPStatusError("Error", request=mock_request, response=mock_response)
            )
            mock_get_client.return_value = mock_client

            result = await provider.list_nodes()

            assert result["status"] == "error"
            assert "HTTP 503" in result["error"]


class TestRedisEnterpriseAdminSSLError:
    """Test SSL error handling."""

    @pytest.mark.asyncio
    async def test_cluster_info_ssl_error(self, provider):
        """Test get_cluster_info SSL error provides helpful message."""
        with patch.object(provider, "get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(
                side_effect=Exception(
                    "CERTIFICATE_VERIFY_FAILED: unable to get local issuer certificate"
                )
            )
            mock_get_client.return_value = mock_client

            result = await provider.get_cluster_info()

            assert result["status"] == "error"
            assert "SSL" in result["error"] or "certificate" in result["error"].lower()
