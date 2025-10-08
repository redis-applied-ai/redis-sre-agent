"""Tests for deployment providers manager."""

import pytest

from redis_sre_agent.api.instances import RedisInstance
from redis_sre_agent.models.provider_config import (
    DeploymentProvidersConfig,
    RedisDirectMetricsConfig,
)
from redis_sre_agent.tools.deployment_providers import (
    DeploymentProviders,
    reset_deployment_providers,
)


@pytest.fixture
def minimal_config():
    """Create minimal deployment config with only Redis Direct Metrics."""
    return DeploymentProvidersConfig(redis_direct_metrics=RedisDirectMetricsConfig())


@pytest.fixture
def redis_instance():
    """Create a test Redis instance."""
    return RedisInstance(
        id="test-1",
        name="test-redis",
        connection_url="redis://test:6379",
        environment="testing",
        usage="cache",
        description="Test instance",
    )


@pytest.fixture
def multiple_instances():
    """Create multiple test Redis instances."""
    return [
        RedisInstance(
            id="prod-1",
            name="prod-redis-1",
            connection_url="redis://prod1:6379",
            environment="production",
            usage="cache",
            description="Production 1",
        ),
        RedisInstance(
            id="prod-2",
            name="prod-redis-2",
            connection_url="redis://prod2:6379",
            environment="production",
            usage="cache",
            description="Production 2",
        ),
        RedisInstance(
            id="staging-1",
            name="staging-redis",
            connection_url="redis://staging:6379",
            environment="staging",
            usage="cache",
            description="Staging",
        ),
    ]


def test_initialization(minimal_config):
    """Test deployment providers initialization."""
    providers = DeploymentProviders(minimal_config)

    assert providers.config == minimal_config
    assert len(providers.provider_types) == 1
    assert "redis_direct_metrics" in providers.provider_types


def test_get_enabled_provider_names(minimal_config):
    """Test getting enabled provider names."""
    providers = DeploymentProviders(minimal_config)

    names = providers.get_enabled_provider_names()
    assert names == ["redis_direct_metrics"]


def test_get_provider_type(minimal_config):
    """Test getting a provider type by name."""
    providers = DeploymentProviders(minimal_config)

    provider_type = providers.get_provider_type("redis_direct_metrics")
    assert provider_type is not None
    assert provider_type.provider_type_name == "redis_metrics"


def test_get_provider_type_not_found(minimal_config):
    """Test getting a non-existent provider type."""
    providers = DeploymentProviders(minimal_config)

    provider_type = providers.get_provider_type("nonexistent")
    assert provider_type is None


def test_create_tools_for_instance(minimal_config, redis_instance):
    """Test creating tools for a single instance."""
    providers = DeploymentProviders(minimal_config)

    tools = providers.create_tools_for_instance(redis_instance)

    # Should create 3 tools from Redis Direct Metrics
    assert len(tools) == 3

    # Check tool names
    tool_names = [tool.name for tool in tools]
    assert "redis_metrics_test_redis_list_metrics" in tool_names
    assert "redis_metrics_test_redis_query_metrics" in tool_names
    assert "redis_metrics_test_redis_get_summary" in tool_names


def test_create_tools_for_multiple_instances(minimal_config, multiple_instances):
    """Test creating tools for multiple instances."""
    providers = DeploymentProviders(minimal_config)

    tools = providers.create_tools_for_instances(multiple_instances)

    # Should create 3 tools per instance (3 instances * 3 tools = 9 tools)
    assert len(tools) == 9

    # Check that tools for each instance exist
    tool_names = [tool.name for tool in tools]
    assert "redis_metrics_prod_redis_1_list_metrics" in tool_names
    assert "redis_metrics_prod_redis_2_list_metrics" in tool_names
    assert "redis_metrics_staging_redis_list_metrics" in tool_names


def test_tools_have_unique_names(minimal_config, multiple_instances):
    """Test that tools for different instances have unique names."""
    providers = DeploymentProviders(minimal_config)

    tools = providers.create_tools_for_instances(multiple_instances)

    tool_names = [tool.name for tool in tools]

    # All tool names should be unique
    assert len(tool_names) == len(set(tool_names))


def test_empty_config():
    """Test deployment providers with empty config."""
    config = DeploymentProvidersConfig()
    providers = DeploymentProviders(config)

    # Should have no provider types
    assert len(providers.provider_types) == 0
    assert providers.get_enabled_provider_names() == []


def test_create_tools_with_empty_config(redis_instance):
    """Test creating tools with no providers configured."""
    config = DeploymentProvidersConfig()
    providers = DeploymentProviders(config)

    tools = providers.create_tools_for_instance(redis_instance)

    # Should create no tools
    assert len(tools) == 0


@pytest.mark.asyncio
async def test_health_check_all(minimal_config):
    """Test health check for all providers."""
    providers = DeploymentProviders(minimal_config)

    health = await providers.health_check_all()

    assert "redis_direct_metrics" in health
    assert health["redis_direct_metrics"]["status"] == "healthy"


@pytest.mark.asyncio
async def test_health_check_empty_config():
    """Test health check with no providers."""
    config = DeploymentProvidersConfig()
    providers = DeploymentProviders(config)

    health = await providers.health_check_all()

    # Should return empty dict
    assert health == {}


def test_str_repr(minimal_config):
    """Test string representations."""
    providers = DeploymentProviders(minimal_config)

    str_repr = str(providers)
    assert "DeploymentProviders" in str_repr
    assert "redis_direct_metrics" in str_repr

    repr_str = repr(providers)
    assert "DeploymentProviders" in repr_str
    assert "redis_direct_metrics" in repr_str
    assert "count=1" in repr_str


def test_global_singleton(minimal_config, monkeypatch):
    """Test global singleton pattern."""
    from redis_sre_agent.core import config as config_module
    from redis_sre_agent.tools.deployment_providers import get_deployment_providers

    # Reset singleton
    reset_deployment_providers()

    # Mock settings to return our test config
    class MockSettings:
        @property
        def providers(self):
            return minimal_config

    monkeypatch.setattr(config_module, "settings", MockSettings())

    # Get singleton
    providers1 = get_deployment_providers()
    providers2 = get_deployment_providers()

    # Should be the same instance
    assert providers1 is providers2

    # Reset for other tests
    reset_deployment_providers()


def test_reset_deployment_providers():
    """Test resetting the global singleton."""
    from redis_sre_agent.tools.deployment_providers import (
        reset_deployment_providers,
    )

    # Reset
    reset_deployment_providers()

    # Should be None after reset
    from redis_sre_agent.tools import deployment_providers as dp_module

    assert dp_module._deployment_providers is None


def test_tool_descriptions_include_instance_info(minimal_config, redis_instance):
    """Test that tool descriptions include instance information."""
    providers = DeploymentProviders(minimal_config)

    tools = providers.create_tools_for_instance(redis_instance)

    for tool in tools:
        # Each tool description should include instance context
        assert "test-redis" in tool.description
        assert "redis://test:6379" in tool.description
        assert "testing" in tool.description


def test_tool_parameters_are_valid_json_schema(minimal_config, redis_instance):
    """Test that tool parameters are valid JSON schemas."""
    providers = DeploymentProviders(minimal_config)

    tools = providers.create_tools_for_instance(redis_instance)

    for tool in tools:
        params = tool.parameters

        # Should have required JSON schema fields
        assert "type" in params
        assert params["type"] == "object"
        assert "properties" in params
        assert "required" in params


def test_tools_are_callable(minimal_config, redis_instance):
    """Test that all tools have callable functions."""
    providers = DeploymentProviders(minimal_config)

    tools = providers.create_tools_for_instance(redis_instance)

    for tool in tools:
        assert callable(tool.function)


def test_tools_convert_to_openai_schema(minimal_config, redis_instance):
    """Test that tools can be converted to OpenAI schema."""
    providers = DeploymentProviders(minimal_config)

    tools = providers.create_tools_for_instance(redis_instance)

    for tool in tools:
        schema = tool.to_openai_schema()

        assert schema["type"] == "function"
        assert "function" in schema
        assert "name" in schema["function"]
        assert "description" in schema["function"]
        assert "parameters" in schema["function"]
