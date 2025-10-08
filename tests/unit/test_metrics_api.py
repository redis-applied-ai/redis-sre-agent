"""Tests for the metrics API endpoint."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from redis_sre_agent.api.metrics import (
    format_prometheus_metric,
    get_application_metrics,
    metrics_health,
    prometheus_metrics,
)


class TestFormatPrometheusMetric:
    """Test Prometheus metric formatting."""

    def test_format_simple_metric(self):
        """Test formatting a simple metric without labels."""
        result = format_prometheus_metric("test_metric", 42.0)
        assert result == "test_metric 42.0"

    def test_format_metric_with_help(self):
        """Test formatting a metric with help text."""
        result = format_prometheus_metric("test_metric", 42.0, help_text="This is a test metric")
        assert "# HELP test_metric This is a test metric" in result
        assert "# TYPE test_metric gauge" in result
        assert "test_metric 42.0" in result

    def test_format_metric_with_labels(self):
        """Test formatting a metric with labels."""
        result = format_prometheus_metric(
            "test_metric", 42.0, labels={"env": "prod", "region": "us-east-1"}
        )
        assert 'test_metric{env="prod",region="us-east-1"} 42.0' in result

    def test_format_metric_with_labels_and_help(self):
        """Test formatting a metric with both labels and help text."""
        result = format_prometheus_metric(
            "test_metric",
            42.0,
            labels={"env": "prod"},
            help_text="Test metric with labels",
        )
        assert "# HELP test_metric Test metric with labels" in result
        assert "# TYPE test_metric gauge" in result
        assert 'test_metric{env="prod"} 42.0' in result

    def test_format_metric_with_zero_value(self):
        """Test formatting a metric with zero value."""
        result = format_prometheus_metric("test_metric", 0.0)
        assert "test_metric 0.0" in result

    def test_format_metric_with_float_value(self):
        """Test formatting a metric with float value."""
        result = format_prometheus_metric("test_metric", 3.14159)
        assert "test_metric 3.14159" in result


class TestGetApplicationMetrics:
    """Test application metrics collection."""

    @pytest.mark.asyncio
    async def test_get_metrics_basic_info(self):
        """Test that basic application info is included."""
        with patch(
            "redis_sre_agent.api.metrics.test_redis_connection", AsyncMock(return_value=True)
        ):
            with patch("redis_sre_agent.core.redis.get_knowledge_index") as mock_index:
                mock_index_instance = MagicMock()
                mock_index_instance.exists = AsyncMock(return_value=True)
                mock_index.return_value = mock_index_instance

                with patch("redis_sre_agent.api.metrics.get_redis_client") as mock_redis:
                    mock_redis_instance = MagicMock()
                    mock_redis_instance.hlen = AsyncMock(return_value=10)
                    mock_redis.return_value = mock_redis_instance

                    metrics = await get_application_metrics()

                    assert "sre_agent_info" in metrics
                    assert metrics["sre_agent_info"]["value"] == 1
                    assert "labels" in metrics["sre_agent_info"]
                    assert "version" in metrics["sre_agent_info"]["labels"]

    @pytest.mark.asyncio
    async def test_get_metrics_redis_connected(self):
        """Test Redis connection status when connected."""
        with patch(
            "redis_sre_agent.api.metrics.test_redis_connection", AsyncMock(return_value=True)
        ):
            with patch("redis_sre_agent.core.redis.get_knowledge_index") as mock_index:
                mock_index_instance = MagicMock()
                mock_index_instance.exists = AsyncMock(return_value=True)
                mock_index.return_value = mock_index_instance

                with patch("redis_sre_agent.api.metrics.get_redis_client") as mock_redis:
                    mock_redis_instance = MagicMock()
                    mock_redis_instance.hlen = AsyncMock(return_value=10)
                    mock_redis.return_value = mock_redis_instance

                    metrics = await get_application_metrics()

                    assert "sre_agent_redis_connection_status" in metrics
                    assert metrics["sre_agent_redis_connection_status"]["value"] == 1

    @pytest.mark.asyncio
    async def test_get_metrics_redis_disconnected(self):
        """Test Redis connection status when disconnected."""
        with patch(
            "redis_sre_agent.api.metrics.test_redis_connection", AsyncMock(return_value=False)
        ):
            with patch("redis_sre_agent.core.redis.get_knowledge_index") as mock_index:
                mock_index_instance = MagicMock()
                mock_index_instance.exists = AsyncMock(return_value=False)
                mock_index.return_value = mock_index_instance

                with patch("redis_sre_agent.api.metrics.get_redis_client") as mock_redis:
                    mock_redis_instance = MagicMock()
                    mock_redis_instance.hlen = AsyncMock(side_effect=Exception("Connection failed"))
                    mock_redis.return_value = mock_redis_instance

                    metrics = await get_application_metrics()

                    assert "sre_agent_redis_connection_status" in metrics
                    assert metrics["sre_agent_redis_connection_status"]["value"] == 0

    @pytest.mark.asyncio
    async def test_get_metrics_vector_index_exists(self):
        """Test vector index status when index exists."""
        with patch(
            "redis_sre_agent.api.metrics.test_redis_connection", AsyncMock(return_value=True)
        ):
            with patch("redis_sre_agent.core.redis.get_knowledge_index") as mock_index:
                mock_index_instance = MagicMock()
                mock_index_instance.exists = AsyncMock(return_value=True)
                mock_index.return_value = mock_index_instance

                with patch("redis_sre_agent.api.metrics.get_redis_client") as mock_redis:
                    mock_redis_instance = MagicMock()
                    mock_redis_instance.hlen = AsyncMock(return_value=10)
                    mock_redis.return_value = mock_redis_instance

                    metrics = await get_application_metrics()

                    assert "sre_agent_vector_index_status" in metrics
                    assert metrics["sre_agent_vector_index_status"]["value"] == 1

    @pytest.mark.asyncio
    async def test_get_metrics_vector_index_missing(self):
        """Test vector index status when index doesn't exist."""
        with patch(
            "redis_sre_agent.api.metrics.test_redis_connection", AsyncMock(return_value=True)
        ):
            with patch("redis_sre_agent.core.redis.get_knowledge_index") as mock_index:
                mock_index_instance = MagicMock()
                mock_index_instance.exists = AsyncMock(return_value=False)
                mock_index.return_value = mock_index_instance

                with patch("redis_sre_agent.api.metrics.get_redis_client") as mock_redis:
                    mock_redis_instance = MagicMock()
                    mock_redis_instance.hlen = AsyncMock(return_value=0)
                    mock_redis.return_value = mock_redis_instance

                    metrics = await get_application_metrics()

                    assert "sre_agent_vector_index_status" in metrics
                    assert metrics["sre_agent_vector_index_status"]["value"] == 0

    @pytest.mark.asyncio
    async def test_get_metrics_knowledge_documents_count(self):
        """Test knowledge documents count metric."""
        with patch(
            "redis_sre_agent.api.metrics.test_redis_connection", AsyncMock(return_value=True)
        ):
            with patch("redis_sre_agent.core.redis.get_knowledge_index") as mock_index:
                mock_index_instance = MagicMock()
                mock_index_instance.exists = AsyncMock(return_value=True)
                mock_index.return_value = mock_index_instance

                with patch("redis_sre_agent.api.metrics.get_redis_client") as mock_redis:
                    mock_redis_instance = MagicMock()
                    mock_redis_instance.hlen = AsyncMock(return_value=42)
                    mock_redis.return_value = mock_redis_instance

                    metrics = await get_application_metrics()

                    assert "sre_agent_knowledge_documents_total" in metrics
                    assert metrics["sre_agent_knowledge_documents_total"]["value"] == 42

    @pytest.mark.asyncio
    async def test_get_metrics_handles_errors_gracefully(self):
        """Test that metrics collection handles errors gracefully."""
        with patch(
            "redis_sre_agent.api.metrics.test_redis_connection",
            AsyncMock(side_effect=Exception("Redis error")),
        ):
            with patch(
                "redis_sre_agent.core.redis.get_knowledge_index",
                side_effect=Exception("Index error"),
            ):
                with patch(
                    "redis_sre_agent.api.metrics.get_redis_client",
                    side_effect=Exception("Client error"),
                ):
                    metrics = await get_application_metrics()

                    # Should still return metrics with error values
                    assert "sre_agent_redis_connection_status" in metrics
                    assert metrics["sre_agent_redis_connection_status"]["value"] == 0
                    assert "sre_agent_vector_index_status" in metrics
                    assert metrics["sre_agent_vector_index_status"]["value"] == 0

    @pytest.mark.asyncio
    async def test_get_metrics_includes_start_time(self):
        """Test that start time metric is included."""
        with patch(
            "redis_sre_agent.api.metrics.test_redis_connection", AsyncMock(return_value=True)
        ):
            with patch("redis_sre_agent.core.redis.get_knowledge_index") as mock_index:
                mock_index_instance = MagicMock()
                mock_index_instance.exists = AsyncMock(return_value=True)
                mock_index.return_value = mock_index_instance

                with patch("redis_sre_agent.api.metrics.get_redis_client") as mock_redis:
                    mock_redis_instance = MagicMock()
                    mock_redis_instance.hlen = AsyncMock(return_value=10)
                    mock_redis.return_value = mock_redis_instance

                    metrics = await get_application_metrics()

                    assert "sre_agent_start_time_seconds" in metrics
                    assert isinstance(metrics["sre_agent_start_time_seconds"]["value"], float)
                    assert metrics["sre_agent_start_time_seconds"]["value"] > 0


class TestPrometheusMetricsEndpoint:
    """Test the Prometheus metrics endpoint."""

    @pytest.mark.asyncio
    async def test_prometheus_metrics_returns_text(self):
        """Test that metrics endpoint returns plain text."""
        with patch("redis_sre_agent.api.metrics.get_application_metrics") as mock_get_metrics:
            mock_get_metrics.return_value = {"test_metric": {"value": 42.0, "help": "Test metric"}}

            result = await prometheus_metrics()

            assert isinstance(result, str)
            assert "test_metric 42.0" in result

    @pytest.mark.asyncio
    async def test_prometheus_metrics_handles_errors(self):
        """Test that metrics endpoint handles errors gracefully."""
        with patch(
            "redis_sre_agent.api.metrics.get_application_metrics",
            side_effect=Exception("Test error"),
        ):
            result = await prometheus_metrics()

            assert isinstance(result, str)
            assert "sre_agent_metrics_error" in result
            assert "1" in result

    @pytest.mark.asyncio
    async def test_metrics_health_endpoint(self):
        """Test the metrics health check endpoint."""
        result = await metrics_health()

        assert isinstance(result, str)
        assert "sre_agent_metrics_up" in result
        assert "1" in result
        assert "Metrics endpoint is responding" in result
