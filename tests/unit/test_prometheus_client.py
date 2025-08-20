"""Tests for Prometheus client."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import aiohttp
import pytest

from redis_sre_agent.tools.prometheus_client import PrometheusClient, get_prometheus_client


class TestPrometheusClient:
    """Test Prometheus client functionality."""

    @pytest.fixture
    def prometheus_client(self):
        """Create Prometheus client instance."""
        return PrometheusClient("http://test-prometheus:9090")

    def test_init_with_url(self):
        """Test client initialization with custom URL."""
        client = PrometheusClient("http://custom:9090")
        assert client.prometheus_url == "http://custom:9090"
        assert client.session is None

    def test_init_with_default_url(self):
        """Test client initialization with default URL."""
        with patch("redis_sre_agent.tools.prometheus_client.settings") as mock_settings:
            mock_settings.prometheus_url = "http://default:9090"
            client = PrometheusClient()
            assert client.prometheus_url == "http://default:9090"

    @pytest.mark.asyncio
    async def test_get_session_creates_new(self, prometheus_client):
        """Test session creation on first access."""
        session = await prometheus_client._get_session()

        assert isinstance(session, aiohttp.ClientSession)
        assert prometheus_client.session is session

        # Subsequent calls should return same session
        session2 = await prometheus_client._get_session()
        assert session2 is session

        # Cleanup
        await prometheus_client.close()

    @pytest.mark.asyncio
    async def test_close_session(self, prometheus_client):
        """Test session cleanup."""
        # Create session
        await prometheus_client._get_session()
        assert prometheus_client.session is not None

        # Close session
        await prometheus_client.close()
        assert prometheus_client.session is None

    @pytest.mark.asyncio
    async def test_query_success(self, prometheus_client):
        """Test successful Prometheus query."""
        mock_response_data = {
            "status": "success",
            "data": {
                "resultType": "vector",
                "result": [
                    {
                        "metric": {"__name__": "up", "instance": "localhost:9090"},
                        "value": [1642694400, "1"],
                    }
                ],
            },
        }

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=mock_response_data)

        mock_session = AsyncMock()
        mock_session.get.return_value.__aenter__ = AsyncMock(return_value=mock_response)
        mock_session.get.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch.object(prometheus_client, "_get_session", return_value=mock_session):
            result = await prometheus_client.query("up")

        assert result == mock_response_data["data"]
        mock_session.get.assert_called_once()

        # Check URL and params
        call_args = mock_session.get.call_args
        assert "query" in call_args[1]["params"]
        assert call_args[1]["params"]["query"] == "up"

    @pytest.mark.asyncio
    async def test_query_with_time(self, prometheus_client):
        """Test query with specific time parameter."""
        test_time = datetime(2025, 1, 20, 12, 0, 0)

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"status": "success", "data": {}})

        mock_session = AsyncMock()
        mock_session.get.return_value.__aenter__ = AsyncMock(return_value=mock_response)
        mock_session.get.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch.object(prometheus_client, "_get_session", return_value=mock_session):
            await prometheus_client.query("cpu_usage", time=test_time)

        call_args = mock_session.get.call_args
        params = call_args[1]["params"]
        assert "time" in params
        assert params["time"] == test_time.timestamp()

    @pytest.mark.asyncio
    async def test_query_http_error(self, prometheus_client):
        """Test query with HTTP error response."""
        mock_response = AsyncMock()
        mock_response.status = 404
        mock_response.text = AsyncMock(return_value="Not Found")

        mock_session = AsyncMock()
        mock_session.get.return_value.__aenter__ = AsyncMock(return_value=mock_response)
        mock_session.get.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch.object(prometheus_client, "_get_session", return_value=mock_session):
            result = await prometheus_client.query("invalid_metric")

        assert result == {}

    @pytest.mark.asyncio
    async def test_query_prometheus_error(self, prometheus_client):
        """Test query with Prometheus API error."""
        mock_response_data = {"status": "error", "error": "invalid query syntax"}

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=mock_response_data)

        mock_session = AsyncMock()
        mock_session.get.return_value.__aenter__ = AsyncMock(return_value=mock_response)
        mock_session.get.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch.object(prometheus_client, "_get_session", return_value=mock_session):
            result = await prometheus_client.query("invalid{syntax")

        assert result == {}

    @pytest.mark.asyncio
    async def test_query_range_success(self, prometheus_client):
        """Test successful range query."""
        mock_response_data = {
            "status": "success",
            "data": {
                "resultType": "matrix",
                "result": [
                    {
                        "metric": {"__name__": "cpu_usage"},
                        "values": [
                            [1642694400, "10.5"],
                            [1642694415, "12.3"],
                            [1642694430, "11.8"],
                        ],
                    }
                ],
            },
        }

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=mock_response_data)

        mock_session = AsyncMock()
        mock_session.get.return_value.__aenter__ = AsyncMock(return_value=mock_response)
        mock_session.get.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch.object(prometheus_client, "_get_session", return_value=mock_session):
            result = await prometheus_client.query_range("cpu_usage", time_range="1h", step="15s")

        assert "values" in result
        assert "query" in result
        assert "start_time" in result
        assert "end_time" in result
        assert result["values"] == mock_response_data["data"]["result"][0]["values"]

        # Check API call parameters
        call_args = mock_session.get.call_args
        params = call_args[1]["params"]
        assert params["query"] == "cpu_usage"
        assert params["step"] == "15s"
        assert "start" in params
        assert "end" in params

    @pytest.mark.asyncio
    async def test_query_range_no_results(self, prometheus_client):
        """Test range query with no results."""
        mock_response_data = {"status": "success", "data": {"resultType": "matrix", "result": []}}

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=mock_response_data)

        mock_session = AsyncMock()
        mock_session.get.return_value.__aenter__ = AsyncMock(return_value=mock_response)
        mock_session.get.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch.object(prometheus_client, "_get_session", return_value=mock_session):
            result = await prometheus_client.query_range("nonexistent_metric")

        assert result["values"] == []
        assert result["query"] == "nonexistent_metric"

    def test_parse_time_range(self, prometheus_client):
        """Test time range parsing."""
        end_time = datetime(2025, 1, 20, 12, 0, 0)

        test_cases = [
            ("30s", timedelta(seconds=30)),
            ("15m", timedelta(minutes=15)),
            ("2h", timedelta(hours=2)),
            ("7d", timedelta(days=7)),
            ("invalid", timedelta(hours=1)),  # Default fallback
        ]

        for time_range, expected_delta in test_cases:
            result = prometheus_client._parse_time_range(time_range, end_time)
            expected_start = end_time - expected_delta
            assert result == expected_start

    @pytest.mark.asyncio
    async def test_get_targets_success(self, prometheus_client):
        """Test successful targets retrieval."""
        mock_targets = [
            {
                "discoveredLabels": {"__address__": "localhost:9090"},
                "labels": {"instance": "localhost:9090", "job": "prometheus"},
                "scrapePool": "prometheus",
                "scrapeUrl": "http://localhost:9090/metrics",
                "health": "up",
            }
        ]

        mock_response_data = {
            "status": "success",
            "data": {"activeTargets": mock_targets, "droppedTargets": []},
        }

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=mock_response_data)

        mock_session = AsyncMock()
        mock_session.get.return_value.__aenter__ = AsyncMock(return_value=mock_response)
        mock_session.get.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch.object(prometheus_client, "_get_session", return_value=mock_session):
            result = await prometheus_client.get_targets()

        assert result == mock_targets

    @pytest.mark.asyncio
    async def test_get_labels_success(self, prometheus_client):
        """Test successful labels retrieval."""
        mock_labels = ["__name__", "instance", "job", "cpu", "memory"]

        mock_response_data = {"status": "success", "data": mock_labels}

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=mock_response_data)

        mock_session = AsyncMock()
        mock_session.get.return_value.__aenter__ = AsyncMock(return_value=mock_response)
        mock_session.get.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch.object(prometheus_client, "_get_session", return_value=mock_session):
            result = await prometheus_client.get_labels()

        assert result == mock_labels

    @pytest.mark.asyncio
    async def test_health_check_healthy(self, prometheus_client):
        """Test health check with healthy Prometheus."""
        mock_response_data = {
            "status": "success",
            "data": {
                "result": [
                    {"value": [1642694400, "1"]},  # Target up
                    {"value": [1642694400, "1"]},  # Another target up
                    {"value": [1642694400, "0"]},  # One target down
                ]
            },
        }

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=mock_response_data)

        mock_session = AsyncMock()
        mock_session.get.return_value.__aenter__ = AsyncMock(return_value=mock_response)
        mock_session.get.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch.object(prometheus_client, "_get_session", return_value=mock_session):
            result = await prometheus_client.health_check()

        assert result["status"] == "healthy"
        assert result["targets_up"] == 2
        assert result["total_targets"] == 3
        assert result["prometheus_url"] == prometheus_client.prometheus_url

    @pytest.mark.asyncio
    async def test_health_check_connection_error(self, prometheus_client):
        """Test health check with connection error."""
        mock_session = AsyncMock()
        mock_session.get.side_effect = aiohttp.ClientError("Connection failed")

        with patch.object(prometheus_client, "_get_session", return_value=mock_session):
            result = await prometheus_client.health_check()

        assert result["status"] == "error"
        assert "Connection failed" in result["error"]

    @pytest.mark.asyncio
    async def test_get_common_redis_metrics_success(self, prometheus_client):
        """Test retrieval of common Redis metrics."""

        # Mock successful responses for different metrics
        def mock_query_response(query):
            mock_responses = {
                "redis_memory_used_bytes": {"result": [{"value": [1642694400, "1048576"]}]},  # 1MB
                "redis_connected_clients": {"result": [{"value": [1642694400, "50"]}]},
                "rate(redis_commands_processed_total[1m])": {
                    "result": [{"value": [1642694400, "1000"]}]
                },
                "redis_keyspace_hits_total": {"result": [{"value": [1642694400, "5000"]}]},
                "redis_keyspace_misses_total": {"result": [{"value": [1642694400, "100"]}]},
                "rate(process_cpu_seconds_total{job='redis'}[1m]) * 100": {
                    "result": [{"value": [1642694400, "25.5"]}]
                },
            }
            return mock_responses.get(query, {"result": []})

        with patch.object(prometheus_client, "query", side_effect=mock_query_response):
            result = await prometheus_client.get_common_redis_metrics()

        expected_metrics = [
            "memory_usage",
            "connected_clients",
            "ops_per_sec",
            "keyspace_hits",
            "keyspace_misses",
            "cpu_usage",
        ]

        for metric in expected_metrics:
            assert metric in result
            assert "value" in result[metric]
            assert isinstance(result[metric]["value"], float)

        # Check specific values
        assert result["memory_usage"]["value"] == 1048576.0
        assert result["connected_clients"]["value"] == 50.0
        assert result["cpu_usage"]["value"] == 25.5

    @pytest.mark.asyncio
    async def test_get_common_redis_metrics_with_errors(self, prometheus_client):
        """Test Redis metrics retrieval with some metrics failing."""

        def mock_query_response(query):
            if "memory" in query:
                raise Exception("Memory metric failed")
            elif "clients" in query:
                return {"result": []}  # No results
            else:
                return {"result": [{"value": [1642694400, "100"]}]}

        with patch.object(prometheus_client, "query", side_effect=mock_query_response):
            result = await prometheus_client.get_common_redis_metrics()

        # Should handle errors gracefully
        assert "memory_usage" in result
        assert "error" in result["memory_usage"]

        assert "connected_clients" in result
        assert "error" in result["connected_clients"]

        # Other metrics should work
        assert "ops_per_sec" in result
        assert "value" in result["ops_per_sec"]


class TestPrometheusClientSingleton:
    """Test Prometheus client singleton functionality."""

    def test_get_prometheus_client_singleton(self):
        """Test that get_prometheus_client returns singleton instance."""
        with patch("redis_sre_agent.tools.prometheus_client.settings") as mock_settings:
            mock_settings.prometheus_url = "http://test:9090"

            client1 = get_prometheus_client()
            client2 = get_prometheus_client()

            assert client1 is client2
            assert client1.prometheus_url == "http://test:9090"

    def test_get_prometheus_client_with_default_url(self):
        """Test singleton with default URL when settings don't have prometheus_url."""
        with patch("redis_sre_agent.tools.prometheus_client.settings", spec=[]) as mock_settings:
            # Mock settings without prometheus_url attribute

            client = get_prometheus_client()

            assert client.prometheus_url == "http://localhost:9090"
