"""Tests for Redis direct diagnostics provider type."""

import pytest

from redis_sre_agent.api.instances import RedisInstance
from redis_sre_agent.models.provider_config import RedisDirectDiagnosticsConfig
from redis_sre_agent.tools.protocols import ToolCapability
from redis_sre_agent.tools.provider_types.redis_direct_diagnostics import (
    RedisDirectDiagnosticsProviderType,
)


@pytest.fixture
def diagnostics_config():
    """Create a Redis direct diagnostics config."""
    return RedisDirectDiagnosticsConfig(
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


def test_provider_type_name(diagnostics_config):
    """Test provider type name."""
    provider = RedisDirectDiagnosticsProviderType(diagnostics_config)
    assert provider.provider_type_name == "redis_diagnostics"


def test_get_capabilities(diagnostics_config):
    """Test get capabilities."""
    provider = RedisDirectDiagnosticsProviderType(diagnostics_config)
    capabilities = provider.get_capabilities()

    assert len(capabilities) == 1
    assert ToolCapability.DIAGNOSTICS in capabilities


def test_create_tools_scoped_to_instance(diagnostics_config, redis_instance):
    """Test creating tools scoped to an instance."""
    provider = RedisDirectDiagnosticsProviderType(diagnostics_config)
    tools = provider.create_tools_scoped_to_instance(redis_instance)

    # Should create 4 tools
    assert len(tools) == 4

    # Check tool names
    tool_names = [tool.name for tool in tools]
    assert "redis_diagnostics_test_redis_1_capture_diagnostics" in tool_names
    assert "redis_diagnostics_test_redis_1_capture_sections" in tool_names
    assert "redis_diagnostics_test_redis_1_sample_keys" in tool_names
    assert "redis_diagnostics_test_redis_1_analyze_keys" in tool_names


def test_tool_names_sanitize_hyphens(diagnostics_config):
    """Test that tool names sanitize hyphens in instance names."""
    instance = RedisInstance(
        id="test-instance-2",
        name="prod-redis-cluster-1",  # Has hyphens
        connection_url="redis://prod:6379",
        environment="production",
        usage="cache",
        description="Production Redis",
    )

    provider = RedisDirectDiagnosticsProviderType(diagnostics_config)
    tools = provider.create_tools_scoped_to_instance(instance)

    # Tool names should have underscores instead of hyphens
    tool_names = [tool.name for tool in tools]
    assert "redis_diagnostics_prod_redis_cluster_1_capture_diagnostics" in tool_names
    assert "redis_diagnostics_prod_redis_cluster_1_analyze_keys" in tool_names
    assert all("-" not in name for name in tool_names)


def test_capture_diagnostics_tool_structure(diagnostics_config, redis_instance):
    """Test the structure of the capture_diagnostics tool."""
    provider = RedisDirectDiagnosticsProviderType(diagnostics_config)
    tools = provider.create_tools_scoped_to_instance(redis_instance)

    capture_tool = next(t for t in tools if "capture_diagnostics" in t.name)

    # Check tool structure
    assert capture_tool.name == "redis_diagnostics_test_redis_1_capture_diagnostics"
    assert "test-redis-1" in capture_tool.description
    assert "COMPREHENSIVE" in capture_tool.description
    assert capture_tool.parameters["type"] == "object"
    assert capture_tool.parameters["required"] == []
    assert callable(capture_tool.function)


def test_capture_sections_tool_structure(diagnostics_config, redis_instance):
    """Test the structure of the capture_sections tool."""
    provider = RedisDirectDiagnosticsProviderType(diagnostics_config)
    tools = provider.create_tools_scoped_to_instance(redis_instance)

    sections_tool = next(t for t in tools if "capture_sections" in t.name)

    # Check tool structure
    assert sections_tool.name == "redis_diagnostics_test_redis_1_capture_sections"
    assert "test-redis-1" in sections_tool.description
    assert "SPECIFIC" in sections_tool.description
    assert "sections" in sections_tool.parameters["properties"]
    assert sections_tool.parameters["required"] == ["sections"]
    assert callable(sections_tool.function)

    # Check that all valid sections are mentioned in description
    description = sections_tool.description
    assert "memory" in description
    assert "performance" in description
    assert "clients" in description
    assert "slowlog" in description


def test_sample_keys_tool_structure(diagnostics_config, redis_instance):
    """Test the structure of the sample_keys tool."""
    provider = RedisDirectDiagnosticsProviderType(diagnostics_config)
    tools = provider.create_tools_scoped_to_instance(redis_instance)

    sample_tool = next(t for t in tools if "sample_keys" in t.name)

    # Check tool structure
    assert sample_tool.name == "redis_diagnostics_test_redis_1_sample_keys"
    assert "test-redis-1" in sample_tool.description
    assert "SCAN" in sample_tool.description
    assert "pattern" in sample_tool.parameters["properties"]
    assert "count" in sample_tool.parameters["properties"]
    assert "database" in sample_tool.parameters["properties"]
    assert sample_tool.parameters["required"] == []
    assert callable(sample_tool.function)


def test_analyze_keys_tool_structure(diagnostics_config, redis_instance):
    """Test the structure of the analyze_keys tool."""
    provider = RedisDirectDiagnosticsProviderType(diagnostics_config)
    tools = provider.create_tools_scoped_to_instance(redis_instance)

    analyze_tool = next(t for t in tools if "analyze_keys" in t.name)

    # Check tool structure
    assert analyze_tool.name == "redis_diagnostics_test_redis_1_analyze_keys"
    assert "test-redis-1" in analyze_tool.description
    assert "TTL" in analyze_tool.description
    assert "memory" in analyze_tool.description.lower()
    assert "type distribution" in analyze_tool.description.lower()
    assert "pattern" in analyze_tool.parameters["properties"]
    assert "sample_size" in analyze_tool.parameters["properties"]
    assert "database" in analyze_tool.parameters["properties"]
    assert analyze_tool.parameters["required"] == []
    assert callable(analyze_tool.function)


def test_tool_to_openai_schema(diagnostics_config, redis_instance):
    """Test converting tools to OpenAI schema."""
    provider = RedisDirectDiagnosticsProviderType(diagnostics_config)
    tools = provider.create_tools_scoped_to_instance(redis_instance)

    for tool in tools:
        schema = tool.to_openai_schema()

        assert schema["type"] == "function"
        assert "function" in schema
        assert "name" in schema["function"]
        assert "description" in schema["function"]
        assert "parameters" in schema["function"]


@pytest.mark.asyncio
async def test_health_check(diagnostics_config):
    """Test health check."""
    provider = RedisDirectDiagnosticsProviderType(diagnostics_config)
    health = await provider.health_check()

    assert health["provider_type"] == "redis_diagnostics"
    assert health["status"] == "healthy"
    assert "config" in health
    assert health["config"]["connection_timeout"] == 5
    assert health["config"]["socket_timeout"] == 10


def test_supports_instance_type(diagnostics_config):
    """Test instance type support."""
    provider = RedisDirectDiagnosticsProviderType(diagnostics_config)

    # Should support all instance types by default
    assert provider.supports_instance_type("redis-oss")
    assert provider.supports_instance_type("redis-enterprise")
    assert provider.supports_instance_type("redis-cloud")


def test_multiple_instances_create_different_tools(diagnostics_config):
    """Test that different instances get different tools."""
    provider = RedisDirectDiagnosticsProviderType(diagnostics_config)

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
    assert "redis_diagnostics_redis_1_capture_diagnostics" in names1
    assert "redis_diagnostics_redis_2_capture_diagnostics" in names2


def test_provider_str_repr(diagnostics_config):
    """Test string representations."""
    provider = RedisDirectDiagnosticsProviderType(diagnostics_config)

    str_repr = str(provider)
    assert "RedisDirectDiagnosticsProviderType" in str_repr
    assert "redis_diagnostics" in str_repr

    repr_str = repr(provider)
    assert "RedisDirectDiagnosticsProviderType" in repr_str
    assert "redis_diagnostics" in repr_str
    assert "diagnostics" in repr_str.lower()


def test_tool_descriptions_include_instance_context(diagnostics_config, redis_instance):
    """Test that tool descriptions include instance context."""
    provider = RedisDirectDiagnosticsProviderType(diagnostics_config)
    tools = provider.create_tools_scoped_to_instance(redis_instance)

    for tool in tools:
        # Each tool description should include instance context
        assert "test-redis-1" in tool.description
        assert "redis://test:6379" in tool.description
        assert "testing" in tool.description
