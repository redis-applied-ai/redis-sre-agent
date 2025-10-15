"""Tests for Redis Enterprise admin API tool provider."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from redis_sre_agent.tools.admin.redis_enterprise.provider import (
    RedisEnterpriseAdminConfig,
    RedisEnterpriseAdminToolProvider,
)


@pytest.fixture
def config():
    """Create a test configuration."""
    return RedisEnterpriseAdminConfig(
        url="https://test-cluster.example.com:9443",
        username="test@example.com",
        password="test-password",
        verify_ssl=False,
    )


@pytest.fixture
def provider(config):
    """Create a test provider instance."""
    return RedisEnterpriseAdminToolProvider(config=config)


@pytest.mark.asyncio
async def test_provider_initialization(provider, config):
    """Test provider initialization."""
    assert provider.provider_name == "redis_enterprise_admin"
    assert provider.config == config
    assert provider._client is None


@pytest.mark.asyncio
async def test_create_tool_schemas(provider):
    """Test tool schema creation."""
    schemas = provider.create_tool_schemas()

    assert len(schemas) > 0

    # Check that all expected tools are present
    tool_names = [schema.name for schema in schemas]

    # All tools should have the provider name and hash
    for name in tool_names:
        assert name.startswith("redis_enterprise_admin_")

    # Check for specific tools
    assert any("cluster" in name and "info" in name for name in tool_names)
    assert any("databases" in name for name in tool_names)
    assert any("nodes" in name for name in tool_names)
    assert any("modules" in name for name in tool_names)


@pytest.mark.asyncio
async def test_get_cluster_info_success(provider):
    """Test successful cluster info retrieval."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "name": "test-cluster",
        "rack_aware": False,
        "email_alerts": True,
    }
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
    """Test successful database listing."""
    mock_response = MagicMock()
    mock_response.json.return_value = [
        {"uid": 1, "name": "db1", "memory_size": 1073741824},
        {"uid": 2, "name": "db2", "memory_size": 2147483648},
    ]
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
    """Test successful database retrieval."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "uid": 1,
        "name": "test-db",
        "memory_size": 1073741824,
        "status": "active",
    }
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
    """Test successful node listing."""
    mock_response = MagicMock()
    mock_response.json.return_value = [
        {"uid": 1, "addr": "10.0.0.1", "status": "active"},
        {"uid": 2, "addr": "10.0.0.2", "status": "active"},
    ]
    mock_response.raise_for_status = MagicMock()

    with patch.object(provider, "get_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_get_client.return_value = mock_client

        result = await provider.list_nodes()

        assert result["status"] == "success"
        assert result["count"] == 2
        assert len(result["nodes"]) == 2

        mock_client.get.assert_called_once_with("/v1/nodes", params={})


@pytest.mark.asyncio
async def test_list_modules_success(provider):
    """Test successful module listing."""
    mock_response = MagicMock()
    mock_response.json.return_value = [
        {"module_name": "search", "semantic_version": "2.8.4"},
        {"module_name": "ReJSON", "semantic_version": "2.6.6"},
    ]
    mock_response.raise_for_status = MagicMock()

    with patch.object(provider, "get_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_get_client.return_value = mock_client

        result = await provider.list_modules()

        assert result["status"] == "success"
        assert result["count"] == 2
        assert len(result["modules"]) == 2

        mock_client.get.assert_called_once_with("/v1/modules")


@pytest.mark.asyncio
async def test_resolve_tool_call(provider):
    """Test tool call resolution."""
    # Mock the get_cluster_info method
    with patch.object(provider, "get_cluster_info") as mock_method:
        mock_method.return_value = {"status": "success", "data": {}}

        tool_name = f"redis_enterprise_admin_{provider._instance_hash}_get_cluster_info"
        result = await provider.resolve_tool_call(tool_name, {})

        assert result["status"] == "success"
        mock_method.assert_called_once()


@pytest.mark.asyncio
async def test_resolve_tool_call_unknown_operation(provider):
    """Test tool call resolution with unknown operation."""
    tool_name = f"redis_enterprise_admin_{provider._instance_hash}_unknown_operation"

    with pytest.raises(ValueError, match="Unknown operation"):
        await provider.resolve_tool_call(tool_name, {})


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
