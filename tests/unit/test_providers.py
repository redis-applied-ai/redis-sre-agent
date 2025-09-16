"""Tests for concrete SRE tool provider implementations."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from redis_sre_agent.tools.protocols import TimeRange
from redis_sre_agent.tools.providers.redis_cli_metrics import RedisCLIMetricsProvider
from redis_sre_agent.tools.providers.prometheus_metrics import PrometheusMetricsProvider
from redis_sre_agent.tools.providers.comprehensive_provider import (
    AWSProvider,
    GitHubProvider,
    RedisProvider,
)


class TestRedisCLIMetricsProvider:
    """Test Redis CLI metrics provider."""
    
    def test_provider_properties(self):
        """Test provider basic properties."""
        provider = RedisCLIMetricsProvider("redis://localhost:6379")
        
        assert provider.provider_name == "Redis CLI (redis://localhost:6379)"
        assert provider.supports_time_queries is False
    
    @pytest.mark.asyncio
    async def test_list_metrics(self):
        """Test listing available metrics."""
        provider = RedisCLIMetricsProvider("redis://localhost:6379")
        
        metrics = await provider.list_metrics()
        
        assert len(metrics) > 0
        metric_names = [m.name for m in metrics]
        assert "used_memory" in metric_names
        assert "connected_clients" in metric_names
        assert "keyspace_hits" in metric_names
    
    @pytest.mark.asyncio
    async def test_get_current_value_success(self):
        """Test getting current metric value successfully."""
        provider = RedisCLIMetricsProvider("redis://localhost:6379")
        
        # Mock Redis client
        mock_client = AsyncMock()
        mock_client.info.return_value = {
            "used_memory": 1024,
            "connected_clients": 5,
            "keyspace_hits": 100,
            "keyspace_misses": 10
        }
        
        with patch.object(provider, '_get_client', return_value=mock_client):
            value = await provider.get_current_value("used_memory")
        
        assert value is not None
        assert value.value == 1024
    
    @pytest.mark.asyncio
    async def test_get_current_value_calculated_metric(self):
        """Test getting calculated metric (hit rate)."""
        provider = RedisCLIMetricsProvider("redis://localhost:6379")
        
        mock_client = AsyncMock()
        mock_client.info.return_value = {
            "keyspace_hits": 90,
            "keyspace_misses": 10
        }
        
        with patch.object(provider, '_get_client', return_value=mock_client):
            value = await provider.get_current_value("keyspace_hit_rate")
        
        assert value is not None
        assert value.value == 0.9  # 90 / (90 + 10)
    
    @pytest.mark.asyncio
    async def test_get_current_value_database_metric(self):
        """Test getting database-specific metric."""
        provider = RedisCLIMetricsProvider("redis://localhost:6379")
        
        mock_client = AsyncMock()
        mock_client.info.return_value = {
            "db0": {"keys": 100, "expires": 50, "avg_ttl": 3600}
        }
        
        with patch.object(provider, '_get_client', return_value=mock_client):
            value = await provider.get_current_value("db_keys", labels={"database": "0"})
        
        assert value is not None
        assert value.value == 100
    
    @pytest.mark.asyncio
    async def test_query_time_range_not_supported(self):
        """Test that time range queries raise NotImplementedError."""
        provider = RedisCLIMetricsProvider("redis://localhost:6379")
        time_range = TimeRange(datetime.now() - timedelta(hours=1), datetime.now())
        
        with pytest.raises(NotImplementedError):
            await provider.query_time_range("used_memory", time_range)
    
    @pytest.mark.asyncio
    async def test_health_check_success(self):
        """Test successful health check."""
        provider = RedisCLIMetricsProvider("redis://localhost:6379")
        
        mock_client = AsyncMock()
        mock_client.ping.return_value = True
        mock_client.info.return_value = {
            "redis_version": "7.0.0",
            "uptime_in_seconds": 3600
        }
        
        with patch.object(provider, '_get_client', return_value=mock_client):
            health = await provider.health_check()
        
        assert health["status"] == "healthy"
        assert health["connected"] is True
        assert health["redis_version"] == "7.0.0"
    
    @pytest.mark.asyncio
    async def test_health_check_failure(self):
        """Test health check failure."""
        provider = RedisCLIMetricsProvider("redis://localhost:6379")
        
        mock_client = AsyncMock()
        mock_client.ping.side_effect = Exception("Connection failed")
        
        with patch.object(provider, '_get_client', return_value=mock_client):
            health = await provider.health_check()
        
        assert health["status"] == "unhealthy"
        assert health["connected"] is False
        assert "Connection failed" in health["error"]


class TestPrometheusMetricsProvider:
    """Test Prometheus metrics provider."""
    
    def test_provider_properties(self):
        """Test provider basic properties."""
        provider = PrometheusMetricsProvider("http://localhost:9090")
        
        assert provider.provider_name == "Prometheus (http://localhost:9090)"
        assert provider.supports_time_queries is True
    
    @pytest.mark.asyncio
    async def test_list_metrics(self):
        """Test listing available metrics."""
        provider = PrometheusMetricsProvider("http://localhost:9090")
        
        metrics = await provider.list_metrics()
        
        assert len(metrics) > 0
        metric_names = [m.name for m in metrics]
        assert "redis_memory_used_bytes" in metric_names
        assert "redis_connected_clients" in metric_names
    
    @pytest.mark.asyncio
    async def test_get_current_value_success(self):
        """Test getting current metric value from Prometheus."""
        provider = PrometheusMetricsProvider("http://localhost:9090")

        # Create a proper async context manager mock
        class MockResponse:
            def __init__(self):
                self.status = 200

            async def json(self):
                return {
                    "status": "success",
                    "data": {
                        "result": [{
                            "metric": {"instance": "localhost:6379"},
                            "value": [1640995200, "1024"]
                        }]
                    }
                }

        class MockContextManager:
            async def __aenter__(self):
                return MockResponse()

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return None

        mock_session = MagicMock()
        mock_session.get.return_value = MockContextManager()

        with patch.object(provider, '_get_session', return_value=mock_session):
            value = await provider.get_current_value("redis_memory_used_bytes")

        assert value is not None
        assert value.value == 1024.0
        assert value.labels["instance"] == "localhost:6379"
    
    @pytest.mark.asyncio
    async def test_query_time_range_success(self):
        """Test querying time range from Prometheus."""
        provider = PrometheusMetricsProvider("http://localhost:9090")

        # Create a proper async context manager mock
        class MockResponse:
            def __init__(self):
                self.status = 200

            async def json(self):
                return {
                    "status": "success",
                    "data": {
                        "result": [{
                            "metric": {"instance": "localhost:6379"},
                            "values": [
                                [1640995200, "1024"],
                                [1640995260, "1100"],
                                [1640995320, "1200"]
                            ]
                        }]
                    }
                }

        class MockContextManager:
            async def __aenter__(self):
                return MockResponse()

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return None

        mock_session = MagicMock()
        mock_session.get.return_value = MockContextManager()

        time_range = TimeRange(datetime.now() - timedelta(hours=1), datetime.now())

        with patch.object(provider, '_get_session', return_value=mock_session):
            values = await provider.query_time_range("redis_memory_used_bytes", time_range)

        assert len(values) == 3
        assert values[0].value == 1024.0
        assert values[1].value == 1100.0
        assert values[2].value == 1200.0
    
    @pytest.mark.asyncio
    async def test_health_check_success(self):
        """Test successful Prometheus health check."""
        provider = PrometheusMetricsProvider("http://localhost:9090")

        # Create a proper async context manager mock
        class MockResponse:
            def __init__(self):
                self.status = 200

            async def json(self):
                return {
                    "status": "success",
                    "data": {"result": []}
                }

        class MockContextManager:
            async def __aenter__(self):
                return MockResponse()

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return None

        mock_session = MagicMock()
        mock_session.get.return_value = MockContextManager()

        with patch.object(provider, '_get_session', return_value=mock_session):
            health = await provider.health_check()

        assert health["status"] == "healthy"
        assert health["connected"] is True
        assert health["prometheus_status"] == "up"


class TestComprehensiveProviders:
    """Test comprehensive provider implementations."""
    
    def test_aws_provider_capabilities(self):
        """Test AWS provider capabilities."""
        provider = AWSProvider()
        
        assert provider.provider_name == "AWS SRE Provider (us-east-1)"
        assert len(provider.capabilities) == 2
        assert provider.capabilities[0].value == "logs"
        assert provider.capabilities[1].value == "traces"
    
    @pytest.mark.asyncio
    async def test_aws_provider_get_providers(self):
        """Test AWS provider returns correct sub-providers."""
        provider = AWSProvider()
        
        metrics_provider = await provider.get_metrics_provider()
        logs_provider = await provider.get_logs_provider()
        traces_provider = await provider.get_traces_provider()
        tickets_provider = await provider.get_tickets_provider()
        repos_provider = await provider.get_repos_provider()
        
        assert metrics_provider is None
        assert logs_provider is not None
        assert traces_provider is not None
        assert tickets_provider is None
        assert repos_provider is None
    
    def test_github_provider_capabilities(self):
        """Test GitHub provider capabilities."""
        provider = GitHubProvider("token", "org", "org/repo")
        
        assert provider.provider_name == "GitHub SRE Provider (org)"
        assert len(provider.capabilities) == 2
        assert provider.capabilities[0].value == "tickets"
        assert provider.capabilities[1].value == "repos"
    
    @pytest.mark.asyncio
    async def test_github_provider_get_providers(self):
        """Test GitHub provider returns correct sub-providers."""
        provider = GitHubProvider("token", "org", "org/repo")
        
        metrics_provider = await provider.get_metrics_provider()
        logs_provider = await provider.get_logs_provider()
        tickets_provider = await provider.get_tickets_provider()
        repos_provider = await provider.get_repos_provider()
        traces_provider = await provider.get_traces_provider()
        
        assert metrics_provider is None
        assert logs_provider is None
        assert tickets_provider is not None
        assert repos_provider is not None
        assert traces_provider is None
    
    def test_redis_provider_capabilities(self):
        """Test Redis provider capabilities."""
        provider = RedisProvider("redis://localhost:6379")
        
        assert provider.provider_name == "Redis SRE Provider (redis://localhost:6379)"
        assert len(provider.capabilities) == 1
        assert provider.capabilities[0].value == "metrics"
    
    @pytest.mark.asyncio
    async def test_redis_provider_prefers_prometheus(self):
        """Test Redis provider prefers Prometheus over Redis CLI."""
        provider = RedisProvider("redis://localhost:6379", "http://localhost:9090")
        
        metrics_provider = await provider.get_metrics_provider()
        
        # Should return Prometheus provider when available
        assert metrics_provider is not None
        assert "Prometheus" in metrics_provider.provider_name
    
    @pytest.mark.asyncio
    async def test_redis_provider_fallback_to_cli(self):
        """Test Redis provider falls back to CLI when Prometheus unavailable."""
        provider = RedisProvider("redis://localhost:6379")  # No Prometheus URL
        
        metrics_provider = await provider.get_metrics_provider()
        
        # Should return Redis CLI provider
        assert metrics_provider is not None
        assert "Redis CLI" in metrics_provider.provider_name
    
    @pytest.mark.asyncio
    async def test_provider_health_checks(self):
        """Test comprehensive provider health checks."""
        provider = AWSProvider()
        
        # Mock the sub-providers' health checks
        with patch.object(provider, 'get_logs_provider') as mock_logs, \
             patch.object(provider, 'get_traces_provider') as mock_traces:
            
            mock_logs_provider = AsyncMock()
            mock_logs_provider.health_check.return_value = {"status": "healthy"}
            mock_logs.return_value = mock_logs_provider
            
            mock_traces_provider = AsyncMock()
            mock_traces_provider.health_check.return_value = {"status": "healthy"}
            mock_traces.return_value = mock_traces_provider
            
            health = await provider.health_check()
        
        assert health["status"] == "healthy"
        assert "services" in health
        assert "logs" in health["services"]
        assert "traces" in health["services"]
    
    @pytest.mark.asyncio
    async def test_provider_initialization(self):
        """Test provider initialization with config."""
        provider = AWSProvider()
        
        config = {
            "region_name": "us-west-2",
            "aws_access_key_id": "test_key",
            "aws_secret_access_key": "test_secret"
        }
        
        await provider.initialize(config)
        
        assert provider.region_name == "us-west-2"
        assert provider.aws_access_key_id == "test_key"
        assert provider.aws_secret_access_key == "test_secret"
