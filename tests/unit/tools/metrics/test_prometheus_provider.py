"""Unit tests for PrometheusToolProvider."""

from unittest.mock import MagicMock, patch

import pytest

from redis_sre_agent.core.instances import RedisInstance
from redis_sre_agent.tools.metrics.prometheus.provider import (
    PrometheusConfig,
    PrometheusToolProvider,
)
from redis_sre_agent.tools.models import ToolCapability


class TestPrometheusConfig:
    """Test PrometheusConfig model."""

    def test_default_values(self):
        """Test default configuration values."""
        with patch.dict("os.environ", {}, clear=True):
            config = PrometheusConfig()
            assert config.url == "http://localhost:9090"
            assert config.disable_ssl is False

    def test_custom_values(self):
        """Test configuration with custom values."""
        config = PrometheusConfig(url="http://prometheus:9090", disable_ssl=True)
        assert config.url == "http://prometheus:9090"
        assert config.disable_ssl is True

    def test_env_prefix(self):
        """Test that config loads from environment with prefix."""
        with patch.dict("os.environ", {"TOOLS_PROMETHEUS_URL": "http://custom:9090"}, clear=False):
            config = PrometheusConfig()
            assert config.url == "http://custom:9090"


class TestPrometheusToolProviderInit:
    """Test PrometheusToolProvider initialization."""

    def test_init_with_default_config(self):
        """Test initialization with default config."""
        provider = PrometheusToolProvider()
        assert provider.config is not None
        assert provider._client is None

    def test_init_with_custom_config(self):
        """Test initialization with custom config."""
        config = PrometheusConfig(url="http://custom:9090")
        provider = PrometheusToolProvider(config=config)
        assert provider.config.url == "http://custom:9090"

    def test_init_with_redis_instance(self):
        """Test initialization with Redis instance."""
        instance = RedisInstance(
            id="test-id",
            name="test-instance",
            connection_url="redis://localhost:6379",
            environment="development",
            usage="cache",
            description="Test instance",
            instance_type="oss_single",
        )
        provider = PrometheusToolProvider(redis_instance=instance)
        assert provider.redis_instance is instance


class TestPrometheusToolProviderProperties:
    """Test PrometheusToolProvider properties."""

    def test_provider_name(self):
        """Test provider_name property."""
        provider = PrometheusToolProvider()
        assert provider.provider_name == "prometheus"


class TestPrometheusToolProviderSchemas:
    """Test PrometheusToolProvider tool schemas."""

    def test_create_tool_schemas_returns_list(self):
        """Test create_tool_schemas returns list of ToolDefinitions."""
        provider = PrometheusToolProvider()
        schemas = provider.create_tool_schemas()

        assert isinstance(schemas, list)
        assert len(schemas) > 0

    def test_tool_schemas_have_metrics_capability(self):
        """Test all tool schemas have METRICS capability."""
        provider = PrometheusToolProvider()
        schemas = provider.create_tool_schemas()

        for schema in schemas:
            assert schema.capability == ToolCapability.METRICS

    def test_tool_schemas_include_query(self):
        """Test tool schemas include query tool."""
        provider = PrometheusToolProvider()
        schemas = provider.create_tool_schemas()

        tool_names = [s.name for s in schemas]
        assert any("query" in name for name in tool_names)


class TestPrometheusToolProviderClient:
    """Test PrometheusToolProvider client management."""

    def test_client_lazy_initialization(self):
        """Test client is lazily initialized."""
        provider = PrometheusToolProvider()
        assert provider._client is None

    @patch("redis_sre_agent.tools.metrics.prometheus.provider.PrometheusConnect")
    def test_get_client_creates_connection(self, mock_prom_connect):
        """Test get_client creates PrometheusConnect instance."""
        mock_client = MagicMock()
        mock_prom_connect.return_value = mock_client

        config = PrometheusConfig(url="http://test:9090", disable_ssl=True)
        provider = PrometheusToolProvider(config=config)

        # Access the get_client method
        client = provider.get_client()

        mock_prom_connect.assert_called_once_with(
            url="http://test:9090",
            disable_ssl=True,
        )
        assert client is mock_client

    @patch("redis_sre_agent.tools.metrics.prometheus.provider.PrometheusConnect")
    def test_client_cached_after_first_call(self, mock_prom_connect):
        """Test client is cached after first creation."""
        mock_client = MagicMock()
        mock_prom_connect.return_value = mock_client

        provider = PrometheusToolProvider()

        # Call twice
        client1 = provider.get_client()
        client2 = provider.get_client()

        # Should only create once
        assert mock_prom_connect.call_count == 1
        assert client1 is client2


class TestPrometheusToolProviderContextManager:
    """Test PrometheusToolProvider async context manager."""

    @pytest.mark.asyncio
    async def test_async_context_manager_enter(self):
        """Test async context manager __aenter__."""
        provider = PrometheusToolProvider()
        async with provider as p:
            assert p is provider

    @pytest.mark.asyncio
    async def test_async_context_manager_exit(self):
        """Test async context manager __aexit__ is no-op."""
        provider = PrometheusToolProvider()
        async with provider:
            pass
        # No cleanup needed, just verify no errors


class TestPrometheusToolProviderSchemaDetails:
    """Test PrometheusToolProvider schema details."""

    def test_schemas_have_parameters(self):
        """Test all schemas have parameters."""
        provider = PrometheusToolProvider()
        schemas = provider.create_tool_schemas()
        for schema in schemas:
            assert isinstance(schema.parameters, dict)
            assert "type" in schema.parameters
            assert schema.parameters["type"] == "object"

    def test_schemas_have_descriptions(self):
        """Test all schemas have descriptions."""
        provider = PrometheusToolProvider()
        schemas = provider.create_tool_schemas()
        for schema in schemas:
            assert schema.description
            assert len(schema.description) > 10

    def test_query_schema_has_query_param(self):
        """Test query schema has query parameter."""
        provider = PrometheusToolProvider()
        schemas = provider.create_tool_schemas()
        query_schema = next(s for s in schemas if "query" in s.name and "range" not in s.name)
        assert "query" in query_schema.parameters.get("properties", {})

    def test_query_range_schema_has_required_params(self):
        """Test query_range schema has required parameters."""
        provider = PrometheusToolProvider()
        schemas = provider.create_tool_schemas()
        range_schema = next(s for s in schemas if "query_range" in s.name)
        props = range_schema.parameters.get("properties", {})
        assert "query" in props
        assert "start_time" in props
        assert "end_time" in props


class TestPrometheusToolProviderRequiresInstance:
    """Test requires_redis_instance property."""

    def test_requires_redis_instance_is_false(self):
        """Test requires_redis_instance is False by default."""
        provider = PrometheusToolProvider()
        assert provider.requires_redis_instance is False


class TestPrometheusToolProviderQueryMethod:
    """Test query async method."""

    @pytest.mark.asyncio
    async def test_query_success(self):
        """Test query method success."""
        provider = PrometheusToolProvider()

        with patch.object(provider, "_wait_for_targets", return_value=None):
            with patch.object(
                provider,
                "_http_get_json",
                return_value={
                    "status": "success",
                    "data": {"result": [{"metric": {"__name__": "up"}, "value": [1700000000, "1"]}]},
                },
            ):
                result = await provider.query("up")

                assert result["status"] == "success"
                assert result["query"] == "up"
                assert len(result["data"]) == 1

    @pytest.mark.asyncio
    async def test_query_error_response(self):
        """Test query method with error response."""
        provider = PrometheusToolProvider()

        with patch.object(provider, "_wait_for_targets", return_value=None):
            with patch.object(
                provider,
                "_http_get_json",
                return_value={"status": "error", "error": "Invalid query"},
            ):
                result = await provider.query("invalid{")

                assert result["status"] == "error"
                assert "Invalid query" in result["error"]

    @pytest.mark.asyncio
    async def test_query_exception(self):
        """Test query method exception handling."""
        provider = PrometheusToolProvider()

        with patch.object(provider, "_wait_for_targets", side_effect=Exception("Network error")):
            result = await provider.query("up")

            assert result["status"] == "error"
            assert "Network error" in result["error"]


class TestPrometheusToolProviderHttpGetJson:
    """Test _http_get_json helper."""

    @pytest.mark.asyncio
    async def test_http_get_json_success(self):
        """Test _http_get_json success."""
        provider = PrometheusToolProvider()

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"status": "success", "data": {"result": []}}

        with patch("asyncio.to_thread", return_value=mock_resp):
            result = await provider._http_get_json("/api/v1/query", params={"query": "up"})
            assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_http_get_json_network_error(self):
        """Test _http_get_json with network error."""
        provider = PrometheusToolProvider()

        with patch("asyncio.to_thread", side_effect=Exception("Connection refused")):
            result = await provider._http_get_json("/api/v1/query")
            assert result["status"] == "error"
            assert "Connection refused" in result["error"]


class TestPrometheusToolProviderWaitForTargets:
    """Test _wait_for_targets helper."""

    @pytest.mark.asyncio
    async def test_wait_for_targets_success(self):
        """Test _wait_for_targets success."""
        provider = PrometheusToolProvider()

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "status": "success",
            "data": {"activeTargets": [{"labels": {"job": "redis"}}]},
        }

        with patch("requests.get", return_value=mock_resp):
            # Should return quickly when targets are active
            await provider._wait_for_targets(timeout_seconds=1.0)

    @pytest.mark.asyncio
    async def test_wait_for_targets_timeout(self):
        """Test _wait_for_targets timeout (no error raised)."""
        provider = PrometheusToolProvider()

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"status": "success", "data": {"activeTargets": []}}

        with patch("requests.get", return_value=mock_resp):
            # Should not raise even if no targets
            await provider._wait_for_targets(timeout_seconds=0.1)
