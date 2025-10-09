"""Tests for Redis direct metrics provider type."""

import pytest

from redis_sre_agent.api.instances import RedisInstance
from redis_sre_agent.models.provider_config import RedisDirectMetricsConfig
from redis_sre_agent.tools.protocols import ToolCapability
from redis_sre_agent.tools.provider_types.redis_direct_metrics import (
    RedisDirectMetricsProviderType,
)


@pytest.fixture
def redis_config():
    """Create a Redis direct metrics config."""
    return RedisDirectMetricsConfig(
        connection_timeout=5,
        socket_timeout=10,
    )


@pytest.fixture
def redis_instance():
    """Create a test Redis instance."""
    return RedisInstance(
        id="test-instance-1",
        name="test-redis-1",
        connection_url="redis://test:6379",
        environment="testing",
        usage="cache",
        description="Test Redis instance",
    )


def test_provider_type_name(redis_config):
    """Test provider type name."""
    provider = RedisDirectMetricsProviderType(redis_config)
    assert provider.provider_type_name == "redis_metrics"


def test_get_capabilities(redis_config):
    """Test get capabilities."""
    provider = RedisDirectMetricsProviderType(redis_config)
    capabilities = provider.get_capabilities()

    assert len(capabilities) == 1
    assert ToolCapability.METRICS in capabilities


def test_create_tools_scoped_to_instance(redis_config, redis_instance):
    """Test creating tools scoped to an instance."""
    provider = RedisDirectMetricsProviderType(redis_config)
    tools = provider.create_tools_scoped_to_instance(redis_instance)

    # Should create 3 tools
    assert len(tools) == 3

    # Check tool names
    tool_names = [tool.name for tool in tools]
    assert "redis_metrics_test-redis-1_list_metrics" in tool_names
    assert "redis_metrics_test-redis-1_query_metrics" in tool_names
    assert "redis_metrics_test-redis-1_get_summary" in tool_names


def test_tool_names_sanitize_hyphens(redis_config):
    """Test that tool names preserve hyphens in instance names."""
    instance = RedisInstance(
        id="test-instance-2",
        name="prod-redis-cluster-1",  # Has hyphens
        connection_url="redis://prod:6379",
        environment="production",
        usage="cache",
        description="Production Redis",
    )

    provider = RedisDirectMetricsProviderType(redis_config)
    tools = provider.create_tools_scoped_to_instance(instance)

    # Tool names should preserve hyphens from instance names
    tool_names = [tool.name for tool in tools]
    assert "redis_metrics_prod-redis-cluster-1_list_metrics" in tool_names


def test_list_metrics_tool_structure(redis_config, redis_instance):
    """Test the structure of the list_metrics tool."""
    provider = RedisDirectMetricsProviderType(redis_config)
    tools = provider.create_tools_scoped_to_instance(redis_instance)

    list_metrics_tool = next(t for t in tools if "list_metrics" in t.name)

    # Check tool structure
    assert list_metrics_tool.name == "redis_metrics_test-redis-1_list_metrics"
    assert "test-redis-1" in list_metrics_tool.description
    assert "redis://test:6379" in list_metrics_tool.description
    assert "testing" in list_metrics_tool.description
    assert list_metrics_tool.parameters["type"] == "object"
    assert list_metrics_tool.parameters["required"] == []
    assert callable(list_metrics_tool.function)


def test_query_metrics_tool_structure(redis_config, redis_instance):
    """Test the structure of the query_metrics tool."""
    provider = RedisDirectMetricsProviderType(redis_config)
    tools = provider.create_tools_scoped_to_instance(redis_instance)

    query_metrics_tool = next(t for t in tools if "query_metrics" in t.name)

    # Check tool structure
    assert query_metrics_tool.name == "redis_metrics_test-redis-1_query_metrics"
    assert "test-redis-1" in query_metrics_tool.description
    assert "metric_names" in query_metrics_tool.parameters["properties"]
    assert query_metrics_tool.parameters["required"] == ["metric_names"]
    assert callable(query_metrics_tool.function)


def test_get_summary_tool_structure(redis_config, redis_instance):
    """Test the structure of the get_summary tool."""
    provider = RedisDirectMetricsProviderType(redis_config)
    tools = provider.create_tools_scoped_to_instance(redis_instance)

    get_summary_tool = next(t for t in tools if "get_summary" in t.name)

    # Check tool structure
    assert get_summary_tool.name == "redis_metrics_test-redis-1_get_summary"
    assert "test-redis-1" in get_summary_tool.description
    assert "sections" in get_summary_tool.parameters["properties"]
    assert get_summary_tool.parameters["required"] == ["sections"]
    assert callable(get_summary_tool.function)


def test_tool_to_openai_schema(redis_config, redis_instance):
    """Test converting tools to OpenAI schema."""
    provider = RedisDirectMetricsProviderType(redis_config)
    tools = provider.create_tools_scoped_to_instance(redis_instance)

    for tool in tools:
        schema = tool.to_openai_schema()

        assert schema["type"] == "function"
        assert "function" in schema
        assert "name" in schema["function"]
        assert "description" in schema["function"]
        assert "parameters" in schema["function"]


@pytest.mark.asyncio
async def test_health_check(redis_config):
    """Test health check."""
    provider = RedisDirectMetricsProviderType(redis_config)
    health = await provider.health_check()

    assert health["provider_type"] == "redis_metrics"
    assert health["status"] == "healthy"
    assert "config" in health
    assert health["config"]["connection_timeout"] == 5
    assert health["config"]["socket_timeout"] == 10


def test_supports_instance_type(redis_config):
    """Test instance type support."""
    provider = RedisDirectMetricsProviderType(redis_config)

    # Should support all instance types by default
    assert provider.supports_instance_type("redis-oss")
    assert provider.supports_instance_type("redis-enterprise")
    assert provider.supports_instance_type("redis-cloud")


def test_multiple_instances_create_different_tools(redis_config):
    """Test that different instances get different tools."""
    provider = RedisDirectMetricsProviderType(redis_config)

    instance1 = RedisInstance(
        id="inst-1",
        name="redis-1",
        connection_url="redis://redis1:6379",
        environment="production",
        usage="cache",
        description="Redis 1",
    )

    instance2 = RedisInstance(
        id="inst-2",
        name="redis-2",
        connection_url="redis://redis2:6379",
        environment="production",
        usage="cache",
        description="Redis 2",
    )

    tools1 = provider.create_tools_scoped_to_instance(instance1)
    tools2 = provider.create_tools_scoped_to_instance(instance2)

    # Should have same number of tools
    assert len(tools1) == len(tools2)

    # But different names
    names1 = {tool.name for tool in tools1}
    names2 = {tool.name for tool in tools2}
    assert names1 != names2

    # Check specific names
    assert "redis_metrics_redis-1_list_metrics" in names1
    assert "redis_metrics_redis-2_list_metrics" in names2


def test_provider_str_repr(redis_config):
    """Test string representations."""
    provider = RedisDirectMetricsProviderType(redis_config)

    str_repr = str(provider)
    assert "RedisDirectMetricsProviderType" in str_repr
    assert "redis_metrics" in str_repr

    repr_str = repr(provider)
    assert "RedisDirectMetricsProviderType" in repr_str
    assert "redis_metrics" in repr_str
    assert "metrics" in repr_str.lower()
