"""Tests for Redis Cloud Management API tool provider."""

from unittest.mock import AsyncMock, patch

import pytest

from redis_sre_agent.tools.cloud.redis_cloud import (
    RedisCloudConfig,
    RedisCloudToolProvider,
)
from redis_sre_agent.tools.protocols import ToolCapability


@pytest.fixture
def mock_config():
    """Create a mock configuration."""
    return RedisCloudConfig(
        api_key="test-api-key",
        api_secret_key="test-secret-key",
        base_url="https://api.redislabs.com/v1",
    )


@pytest.fixture
def provider(mock_config):
    """Create a provider instance with mock config."""
    return RedisCloudToolProvider(config=mock_config)


@pytest.mark.asyncio
async def test_provider_initialization(mock_config):
    """Test provider initialization."""
    provider = RedisCloudToolProvider(config=mock_config)
    assert provider.provider_name == "redis_cloud"
    assert provider.config == mock_config


@pytest.mark.asyncio
async def test_create_tool_schemas(provider):
    """Test tool schema creation."""
    schemas = provider.create_tool_schemas()

    # Should have multiple tools
    assert len(schemas) > 0

    # Check that tool names are properly formatted
    for schema in schemas:
        assert schema.name.startswith("redis_cloud_")
        assert schema.description
        assert schema.parameters
        assert schema.capability == ToolCapability.DIAGNOSTICS

    # Check for expected tools
    tool_names = [s.name for s in schemas]
    assert any("get_account" in name for name in tool_names)
    assert any("list_subscriptions" in name for name in tool_names)
    assert any("list_databases" in name for name in tool_names)


@pytest.mark.asyncio
async def test_get_client(provider):
    """Test client lazy initialization."""
    # Client should be None initially
    assert provider._client is None

    # Get client should create it
    client = provider.get_client()
    assert client is not None
    # Generated client type
    from redis_sre_agent.tools.cloud.redis_cloud.api_client.client import Client as GeneratedClient

    assert isinstance(client, GeneratedClient)

    # Should return same instance on subsequent calls
    client2 = provider.get_client()
    assert client is client2


@pytest.mark.asyncio
async def test_context_manager(mock_config):
    """Test async context manager."""
    provider = RedisCloudToolProvider(config=mock_config)

    async with provider as p:
        assert p is provider
        # Client should be created when accessed
        client = p.get_client()
        assert client is not None

    # Client should be closed after context exit
    assert provider._client is None


@pytest.mark.asyncio
async def test_resolve_tool_call_get_account(provider):
    """Test get_account using the concrete provider method."""

    # Patch the generated API function used by the provider
    class Dummy:
        def to_dict(self):
            return {"id": 12345, "name": "Test Account"}

    with patch(
        "redis_sre_agent.tools.cloud.redis_cloud.provider.get_current_account.asyncio",
        new=AsyncMock(return_value=Dummy()),
    ):
        result = await provider.get_account()

    assert result["id"] == 12345
    assert result["name"] == "Test Account"


@pytest.mark.asyncio
async def test_resolve_tool_call_list_subscriptions(provider):
    """Test list_subscriptions using the concrete provider method."""

    class Dummy:
        def to_dict(self):
            return {"subscriptions": [{"id": 1, "name": "Sub 1"}, {"id": 2, "name": "Sub 2"}]}

    with patch(
        "redis_sre_agent.tools.cloud.redis_cloud.provider.pro_list_subscriptions.asyncio",
        new=AsyncMock(return_value=Dummy()),
    ):
        result = await provider.list_subscriptions()

    assert len(result.get("subscriptions", [])) == 2
    assert result["subscriptions"][0]["name"] == "Sub 1"


@pytest.mark.asyncio
async def test_resolve_tool_call_get_database(mock_config):
    """Test get_database using configured instance IDs via the concrete method."""
    # Create provider with a redis_cloud instance that supplies IDs
    fake_instance = type(
        "Instance",
        (),
        {
            "id": "test-instance-id",
            "instance_type": "redis_cloud",
            "redis_cloud_subscription_id": 12345,
            "redis_cloud_database_id": 67890,
            "redis_cloud_subscription_type": "essentials",
        },
    )()
    provider = RedisCloudToolProvider(redis_instance=fake_instance, config=mock_config)

    # Patch essentials get-by-id path
    class Dummy:
        def to_dict(self):
            return {"id": 67890, "name": "Test DB", "status": "active"}

    with patch(
        "redis_sre_agent.tools.cloud.redis_cloud.provider.ess_get_subscription_database_by_id.asyncio",
        new=AsyncMock(return_value=Dummy()),
    ):
        result = await provider.get_database()

    assert result["id"] == 67890
    assert result["name"] == "Test DB"


@pytest.mark.asyncio
async def test_client_authentication_headers(mock_config):
    """Test that generated client sets correct authentication headers via provider."""
    provider = RedisCloudToolProvider(config=mock_config)
    client = provider.get_client()

    httpx_client = client.get_async_httpx_client()
    assert httpx_client.headers["x-api-key"] == mock_config.api_key.get_secret_value()
    assert httpx_client.headers["x-api-secret-key"] == mock_config.api_secret_key.get_secret_value()
    assert httpx_client.headers["Content-Type"] == "application/json"


@pytest.mark.asyncio
async def test_client_base_url(mock_config):
    """Test that generated client uses correct base URL."""
    provider = RedisCloudToolProvider(config=mock_config)
    client = provider.get_client()

    # Generated client stores base url in _base_url
    assert client._base_url == mock_config.base_url
    # httpx adds a trailing slash to base_url on the underlying client
    assert str(client.get_async_httpx_client().base_url) == f"{mock_config.base_url}/"
