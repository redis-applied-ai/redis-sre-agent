"""Tests for SRE tool registry system."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from redis_sre_agent.tools.protocols import ToolCapability
from redis_sre_agent.tools.registry import (
    SREToolRegistry,
    auto_register_default_providers,
    get_global_registry,
    register_provider,
)


@pytest.fixture
def registry():
    """Create a fresh registry for testing."""
    return SREToolRegistry()


@pytest.fixture
def mock_provider():
    """Mock SRE tool provider."""
    provider = MagicMock()
    provider.provider_name = "Test Provider"
    provider.capabilities = [ToolCapability.METRICS, ToolCapability.LOGS]
    return provider


@pytest.fixture
def mock_metrics_only_provider():
    """Mock provider with only metrics capability."""
    provider = MagicMock()
    provider.provider_name = "Metrics Only Provider"
    provider.capabilities = [ToolCapability.METRICS]
    return provider


class TestSREToolRegistry:
    """Test SREToolRegistry class."""

    def test_init(self, registry):
        """Test registry initialization."""
        assert len(registry._providers) == 0
        assert len(registry._capability_map) == len(ToolCapability)
        for capability in ToolCapability:
            assert capability in registry._capability_map
            assert registry._capability_map[capability] == []

    def test_register_provider(self, registry, mock_provider):
        """Test provider registration."""
        registry.register_provider("test", mock_provider)

        assert "test" in registry._providers
        assert registry._providers["test"] == mock_provider
        assert "test" in registry._capability_map[ToolCapability.METRICS]
        assert "test" in registry._capability_map[ToolCapability.LOGS]

    def test_register_provider_replacement(
        self, registry, mock_provider, mock_metrics_only_provider
    ):
        """Test provider replacement."""
        # Register first provider
        registry.register_provider("test", mock_provider)
        assert "test" in registry._capability_map[ToolCapability.METRICS]
        assert "test" in registry._capability_map[ToolCapability.LOGS]

        # Replace with second provider
        registry.register_provider("test", mock_metrics_only_provider)
        assert registry._providers["test"] == mock_metrics_only_provider
        assert "test" in registry._capability_map[ToolCapability.METRICS]
        assert "test" not in registry._capability_map[ToolCapability.LOGS]

    def test_unregister_provider(self, registry, mock_provider):
        """Test provider unregistration."""
        # Register provider
        registry.register_provider("test", mock_provider)
        assert "test" in registry._providers

        # Unregister provider
        result = registry.unregister_provider("test")
        assert result is True
        assert "test" not in registry._providers
        assert "test" not in registry._capability_map[ToolCapability.METRICS]
        assert "test" not in registry._capability_map[ToolCapability.LOGS]

    def test_unregister_nonexistent_provider(self, registry):
        """Test unregistering a provider that doesn't exist."""
        result = registry.unregister_provider("nonexistent")
        assert result is False

    def test_get_provider(self, registry, mock_provider):
        """Test getting a provider by name."""
        registry.register_provider("test", mock_provider)

        provider = registry.get_provider("test")
        assert provider == mock_provider

        nonexistent = registry.get_provider("nonexistent")
        assert nonexistent is None

    def test_list_providers(self, registry, mock_provider, mock_metrics_only_provider):
        """Test listing all providers."""
        registry.register_provider("test1", mock_provider)
        registry.register_provider("test2", mock_metrics_only_provider)

        providers = registry.list_providers()
        assert "test1" in providers
        assert "test2" in providers
        assert len(providers) == 2

    def test_get_providers_by_capability(self, registry, mock_provider, mock_metrics_only_provider):
        """Test getting providers by capability."""
        registry.register_provider("test1", mock_provider)
        registry.register_provider("test2", mock_metrics_only_provider)

        # Both providers have metrics capability
        metrics_providers = registry.get_providers_by_capability(ToolCapability.METRICS)
        assert len(metrics_providers) == 2

        # Only one provider has logs capability
        logs_providers = registry.get_providers_by_capability(ToolCapability.LOGS)
        assert len(logs_providers) == 1
        assert logs_providers[0] == "test1"

        # No providers have tickets capability
        tickets_providers = registry.get_providers_by_capability(ToolCapability.TICKETS)
        assert len(tickets_providers) == 0

    def test_get_capabilities(self, registry, mock_provider):
        """Test getting all available capabilities."""
        registry.register_provider("test", mock_provider)

        capabilities = registry.get_capabilities()
        assert ToolCapability.METRICS in capabilities
        assert ToolCapability.LOGS in capabilities
        assert ToolCapability.TICKETS not in capabilities

    @pytest.mark.asyncio
    async def test_health_check_all_healthy(self, registry, mock_provider):
        """Test health check when all providers are healthy."""
        mock_provider.health_check = AsyncMock(return_value={"status": "healthy"})
        registry.register_provider("test", mock_provider)

        health = await registry.health_check_all()
        assert health["overall_status"] == "healthy"
        assert "test" in health["providers"]
        assert health["providers"]["test"]["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_health_check_some_unhealthy(
        self, registry, mock_provider, mock_metrics_only_provider
    ):
        """Test health check when some providers are unhealthy."""
        mock_provider.health_check = AsyncMock(return_value={"status": "healthy"})
        mock_metrics_only_provider.health_check = AsyncMock(return_value={"status": "unhealthy"})

        registry.register_provider("healthy", mock_provider)
        registry.register_provider("unhealthy", mock_metrics_only_provider)

        health = await registry.health_check_all()
        assert health["overall_status"] == "unhealthy"
        assert health["providers"]["healthy"]["status"] == "healthy"
        assert health["providers"]["unhealthy"]["status"] == "unhealthy"

    @pytest.mark.asyncio
    async def test_health_check_provider_error(self, registry, mock_provider):
        """Test health check when provider raises an error."""
        mock_provider.health_check = AsyncMock(side_effect=Exception("Health check failed"))
        registry.register_provider("test", mock_provider)

        health = await registry.health_check_all()
        assert health["overall_status"] == "unhealthy"
        assert "error" in health["providers"]["test"]


class TestGlobalRegistry:
    """Test global registry functions."""

    def test_get_global_registry_singleton(self):
        """Test that get_global_registry returns the same instance."""
        registry1 = get_global_registry()
        registry2 = get_global_registry()
        assert registry1 is registry2

    def test_register_provider_global(self, mock_provider):
        """Test registering provider with global registry."""
        # Clear any existing providers
        registry = get_global_registry()
        registry._providers.clear()
        registry._capability_map = {cap: [] for cap in ToolCapability}

        register_provider("test", mock_provider)

        assert "test" in registry._providers
        assert registry._providers["test"] == mock_provider


class TestAutoRegisterDefaultProviders:
    """Test auto-registration of default providers."""

    def test_auto_register_redis_only(self):
        """Test auto-registration with only Redis URL."""
        config = {"redis_url": "redis://localhost:6379"}

        # This should not raise an error
        auto_register_default_providers(config)

        registry = get_global_registry()
        providers = registry.list_providers()
        assert "redis" in providers

    def test_auto_register_with_prometheus(self):
        """Test auto-registration with Redis and Prometheus."""
        config = {"redis_url": "redis://localhost:6379", "prometheus_url": "http://localhost:9090"}

        auto_register_default_providers(config)

        registry = get_global_registry()
        providers = registry.list_providers()
        assert "redis" in providers

    def test_auto_register_with_github(self):
        """Test auto-registration with GitHub token."""
        config = {
            "redis_url": "redis://localhost:6379",
            "github_token": "ghp_test_token",
            "github_organization": "test-org",
        }

        auto_register_default_providers(config)

        registry = get_global_registry()
        providers = registry.list_providers()
        assert "redis" in providers
        assert "github" in providers

    def test_auto_register_with_aws(self):
        """Test auto-registration with AWS credentials."""
        config = {
            "redis_url": "redis://localhost:6379",
            "aws_region": "us-east-1",
            "aws_access_key_id": "AKIA...",
            "aws_secret_access_key": "secret",
        }

        auto_register_default_providers(config)

        registry = get_global_registry()
        providers = registry.list_providers()
        assert "redis" in providers
        assert "aws" in providers

    def test_auto_register_empty_config(self):
        """Test auto-registration with empty config."""
        config = {}

        # Should not raise an error, but also shouldn't register anything
        auto_register_default_providers(config)

        # We can't easily test this without clearing the global registry
        # since other tests may have registered providers

    def test_auto_register_minimal_config(self):
        """Test auto-registration with minimal valid config."""
        config = {"redis_url": "redis://localhost:6379"}

        auto_register_default_providers(config)

        registry = get_global_registry()
        providers = registry.list_providers()
        # Should at least have redis provider
        assert len(providers) >= 1
