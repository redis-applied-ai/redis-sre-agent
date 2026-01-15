from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from redis_sre_agent.tools.logs.loki.provider import (
    LokiConfig,
    LokiInstanceConfig,
    LokiToolProvider,
)
from redis_sre_agent.tools.models import ToolCapability


class TestLokiConfig:
    """Test LokiConfig model."""

    def test_default_values(self):
        """Test default configuration values."""
        with patch.dict("os.environ", {}, clear=True):
            config = LokiConfig()
            assert config.url == "http://localhost:3100"
            assert config.tenant_id is None
            assert config.timeout == 30.0
            assert config.default_selector is None

    def test_custom_values(self):
        """Test configuration with custom values."""
        config = LokiConfig(
            url="http://loki:3100",
            tenant_id="tenant-1",
            timeout=60.0,
            default_selector='{job="redis"}',
        )
        assert config.url == "http://loki:3100"
        assert config.tenant_id == "tenant-1"
        assert config.timeout == 60.0
        assert config.default_selector == '{job="redis"}'


class TestLokiInstanceConfig:
    """Test LokiInstanceConfig model."""

    def test_default_values(self):
        """Test default instance config values."""
        config = LokiInstanceConfig()
        assert config.prefer_streams is None
        assert config.keywords is None
        assert config.default_selector is None

    def test_custom_values(self):
        """Test instance config with custom values."""
        config = LokiInstanceConfig(
            prefer_streams=[{"job": "redis", "instance": "prod"}],
            keywords=["error", "warning"],
            default_selector='{service="redis"}',
        )
        assert len(config.prefer_streams) == 1
        assert config.prefer_streams[0]["job"] == "redis"
        assert config.keywords == ["error", "warning"]


class TestLokiToolProviderInit:
    """Test LokiToolProvider initialization."""

    def test_init_with_default_config(self):
        """Test initialization with default config."""
        provider = LokiToolProvider()
        assert provider.config is not None
        # Config loads from env, just check it has a URL
        assert provider.config.url is not None

    def test_init_with_custom_config(self):
        """Test initialization with custom config."""
        config = LokiConfig(url="http://custom-loki:3100")
        provider = LokiToolProvider(config=config)
        assert provider.config.url == "http://custom-loki:3100"


class TestLokiToolProviderProperties:
    """Test LokiToolProvider properties."""

    def test_provider_name(self):
        """Test provider_name property."""
        provider = LokiToolProvider()
        assert provider.provider_name == "loki"

    def test_headers_without_tenant(self):
        """Test _headers without tenant ID."""
        provider = LokiToolProvider()
        headers = provider._headers()
        assert headers == {"Accept": "application/json"}
        assert "X-Scope-OrgID" not in headers

    def test_headers_with_tenant(self):
        """Test _headers with tenant ID."""
        config = LokiConfig(tenant_id="my-tenant")
        provider = LokiToolProvider(config=config)
        headers = provider._headers()
        assert headers["Accept"] == "application/json"
        assert headers["X-Scope-OrgID"] == "my-tenant"


class TestLokiToolProviderSchemas:
    """Test LokiToolProvider tool schemas."""

    def test_create_tool_schemas_returns_list(self):
        """Test create_tool_schemas returns list of ToolDefinitions."""
        provider = LokiToolProvider()
        schemas = provider.create_tool_schemas()

        assert isinstance(schemas, list)
        assert len(schemas) > 0

    def test_tool_schemas_have_logs_capability(self):
        """Test all tool schemas have LOGS capability."""
        provider = LokiToolProvider()
        schemas = provider.create_tool_schemas()

        for schema in schemas:
            assert schema.capability == ToolCapability.LOGS

    def test_tool_schemas_include_query(self):
        """Test tool schemas include query tool."""
        provider = LokiToolProvider()
        schemas = provider.create_tool_schemas()

        tool_names = [s.name for s in schemas]
        assert any("query" in name for name in tool_names)

    def test_tool_schemas_include_labels(self):
        """Test tool schemas include labels tool."""
        provider = LokiToolProvider()
        schemas = provider.create_tool_schemas()

        tool_names = [s.name for s in schemas]
        assert any("labels" in name for name in tool_names)


class TestLokiToolProviderTimeHelpers:
    """Test LokiToolProvider time helper methods."""

    def test_now_epoch_ns_returns_string(self):
        """Test _now_epoch_ns returns a string."""
        provider = LokiToolProvider()
        result = provider._now_epoch_ns()

        assert isinstance(result, str)
        assert len(result) > 15  # Nanoseconds should be long

    def test_parse_time_to_epoch_ns_with_iso(self):
        """Test _parse_time_to_epoch_ns parses ISO format."""
        provider = LokiToolProvider()
        result = provider._parse_time_to_epoch_ns("2024-01-15T10:00:00Z")

        assert isinstance(result, str)
        assert len(result) > 15


@pytest.mark.asyncio
async def test_query_range_rewrites_empty_selector(monkeypatch):
    provider = LokiToolProvider(config=LokiConfig(default_selector='{job=~".+"}'))

    captured = {}

    async def fake_request(method, path, params=None, data=None):
        captured["method"] = method
        captured["path"] = path
        captured["params"] = params or {}
        return {"status": "success", "code": 200, "data": {}}

    monkeypatch.setattr(provider, "_request", fake_request)

    q = '{} |= "rebalance"'
    res = await provider.query_range(
        query=q,
        start="2025-10-24T17:45:00Z",
        end="2025-10-24T21:45:00Z",
        limit=200,
        direction="backward",
    )

    assert res["status"] == "success"
    assert captured["path"] == "/loki/api/v1/query_range"
    # Should inject a non-empty-compatible selector
    assert captured["params"]["query"].startswith('{job=~".+"}')
    assert ' |= "rebalance"' in captured["params"]["query"]


@pytest.mark.asyncio
async def test_query_rewrites_empty_selector(monkeypatch):
    provider = LokiToolProvider(config=LokiConfig(default_selector='{job=~".+"}'))

    captured = {}

    async def fake_request(method, path, params=None, data=None):
        captured["method"] = method
        captured["path"] = path
        captured["params"] = params or {}
        return {"status": "success", "code": 200, "data": {}}

    monkeypatch.setattr(provider, "_request", fake_request)

    q = '{} |= "migrate_shard"'
    res = await provider.query(query=q)

    assert res["status"] == "success"
    assert captured["path"] == "/loki/api/v1/query"
    assert captured["params"]["query"].startswith('{job=~".+"}')
    assert ' |= "migrate_shard"' in captured["params"]["query"]


@pytest.mark.asyncio
async def test_empty_selector_union_fallback_when_no_default(monkeypatch):
    provider = LokiToolProvider()  # no default_selector configured

    captured = {}

    async def fake_request(method, path, params=None, data=None):
        captured["params"] = params or {}
        return {"status": "success", "code": 200, "data": {}}

    monkeypatch.setattr(provider, "_request", fake_request)

    q = '{} |= "rebalance"'
    await provider.query(query=q)

    qq = captured["params"]["query"]
    assert " or " in qq
    assert '({job=~".+"}' in qq and '({service=~".+"}' in qq
    assert ' |= "rebalance"' in qq


@pytest.mark.asyncio
async def test_empty_selector_prefers_instance_streams_single(monkeypatch):
    from pydantic import SecretStr

    from redis_sre_agent.core.instances import RedisInstance, RedisInstanceType

    instance = RedisInstance(
        id="inst-1",
        name="demo",
        connection_url=SecretStr("redis://localhost:6379"),
        environment="development",
        usage="cache",
        description="demo",
        instance_type=RedisInstanceType.oss_single,
        extension_data={
            "loki": {
                "prefer_streams": [
                    {"job": "node-exporter", "instance": "demo-host"},
                ]
            }
        },
    )

    provider = LokiToolProvider(redis_instance=instance)

    captured = {}

    async def fake_request(method, path, params=None, data=None):
        captured["path"] = path
        captured["params"] = params or {}
        return {"status": "success", "code": 200, "data": {}}

    monkeypatch.setattr(provider, "_request", fake_request)

    q = '{} |= "oom-killer"'
    await provider.query(query=q)

    qq = captured["params"]["query"]
    assert qq.startswith('{job="node-exporter",instance="demo-host"}')
    assert ' |= "oom-killer"' in qq


@pytest.mark.asyncio
async def test_empty_selector_prefers_instance_streams_union(monkeypatch):
    from pydantic import SecretStr

    from redis_sre_agent.core.instances import RedisInstance, RedisInstanceType

    instance = RedisInstance(
        id="inst-2",
        name="demo",
        connection_url=SecretStr("redis://localhost:6379"),
        environment="development",
        usage="cache",
        description="demo",
        instance_type=RedisInstanceType.oss_single,
        extension_data={
            "loki": {
                "prefer_streams": [
                    {"job": "node-exporter", "instance": "demo-host"},
                    {"job": "docker", "host": "docker-desktop"},
                ]
            }
        },
    )

    provider = LokiToolProvider(redis_instance=instance)

    captured = {}

    async def fake_request(method, path, params=None, data=None):
        captured["path"] = path
        captured["params"] = params or {}
        return {"status": "success", "code": 200, "data": {}}

    monkeypatch.setattr(provider, "_request", fake_request)

    q = '{} |= "kswapd"'
    await provider.query(query=q)

    qq = captured["params"]["query"]
    # Should build an OR-union of both selectors, each wrapped in parentheses
    assert " or " in qq
    assert '({job="node-exporter",instance="demo-host"}' in qq
    assert '({job="docker",host="docker-desktop"}' in qq
    assert ' |= "kswapd"' in qq


@pytest.mark.asyncio
async def test_empty_selector_uses_instance_default_selector(monkeypatch):
    from pydantic import SecretStr

    from redis_sre_agent.core.instances import RedisInstance, RedisInstanceType

    instance = RedisInstance(
        id="inst-3",
        name="demo",
        connection_url=SecretStr("redis://localhost:6379"),
        environment="development",
        usage="cache",
        description="demo",
        instance_type=RedisInstanceType.oss_single,
        extension_data={"loki": {"default_selector": '{container="redis-demo"}'}},
    )

    provider = LokiToolProvider(redis_instance=instance)

    captured = {}

    async def fake_request(method, path, params=None, data=None):
        captured["params"] = params or {}
        return {"status": "success", "code": 200, "data": {}}

    monkeypatch.setattr(provider, "_request", fake_request)

    await provider.query(query='{} |= "ready"')
    qq = captured["params"]["query"]
    assert qq.startswith('{container="redis-demo"}')
    assert ' |= "ready"' in qq


@pytest.mark.asyncio
async def test_empty_selector_instance_and_env_defaults_union(monkeypatch):
    from pydantic import SecretStr

    from redis_sre_agent.core.instances import RedisInstance, RedisInstanceType

    instance = RedisInstance(
        id="inst-4",
        name="demo",
        connection_url=SecretStr("redis://localhost:6379"),
        environment="development",
        usage="cache",
        description="demo",
        instance_type=RedisInstanceType.oss_single,
        extension_data={"loki": {"default_selector": '{container="redis-demo"}'}},
    )

    provider = LokiToolProvider(
        redis_instance=instance, config=LokiConfig(default_selector='{job=~".+"}')
    )

    captured = {}

    async def fake_request(method, path, params=None, data=None):
        captured["params"] = params or {}
        return {"status": "success", "code": 200, "data": {}}

    monkeypatch.setattr(provider, "_request", fake_request)

    await provider.query(query='{} |= "ping"')
    qq = captured["params"]["query"]
    assert " or " in qq
    assert '({container="redis-demo"}' in qq
    assert '({job=~".+"}' in qq
    assert ' |= "ping"' in qq


@pytest.mark.asyncio
async def test_non_empty_selector_is_unchanged(monkeypatch):
    provider = LokiToolProvider(config=LokiConfig(default_selector='{job=~".+"}'))

    captured = {}

    async def fake_request(method, path, params=None, data=None):
        captured["params"] = params or {}
        return {"status": "success", "code": 200, "data": {}}

    monkeypatch.setattr(provider, "_request", fake_request)

    original = '{job="node-exporter"} |= "cpu"'
    await provider.query(query=original)
    assert captured["params"]["query"] == original


@pytest.mark.asyncio
async def test_flat_keys_for_loki_defaults(monkeypatch):
    from pydantic import SecretStr

    from redis_sre_agent.core.instances import RedisInstance, RedisInstanceType

    instance = RedisInstance(
        id="inst-5",
        name="demo",
        connection_url=SecretStr("redis://localhost:6379"),
        environment="development",
        usage="cache",
        description="demo",
        instance_type=RedisInstanceType.oss_single,
        extension_data={"loki.default_selector": '{service="redis-demo"}'},
    )

    provider = LokiToolProvider(redis_instance=instance)

    captured = {}

    async def fake_request(method, path, params=None, data=None):
        captured["params"] = params or {}
        return {"status": "success", "code": 200, "data": {}}

    monkeypatch.setattr(provider, "_request", fake_request)

    await provider.query(query='{} |= "boom"')
    qq = captured["params"]["query"]
    assert qq.startswith('{service="redis-demo"}')


@pytest.mark.asyncio
async def test_flat_keys_for_prefer_streams(monkeypatch):
    from pydantic import SecretStr

    from redis_sre_agent.core.instances import RedisInstance, RedisInstanceType

    instance = RedisInstance(
        id="inst-6",
        name="demo",
        connection_url=SecretStr("redis://localhost:6379"),
        environment="development",
        usage="cache",
        description="demo",
        instance_type=RedisInstanceType.oss_single,
        extension_data={"loki.prefer_streams": [{"service": "redis-demo"}]},
    )

    provider = LokiToolProvider(redis_instance=instance)

    captured = {}

    async def fake_request(method, path, params=None, data=None):
        captured["params"] = params or {}
        return {"status": "success", "code": 200, "data": {}}

    monkeypatch.setattr(provider, "_request", fake_request)

    await provider.query(query='{} |= "event"')
    qq = captured["params"]["query"]
    assert qq.startswith('{service="redis-demo"}')


class TestLokiToolProviderRequest:
    """Test _request helper method."""

    @pytest.mark.asyncio
    async def test_request_success_json(self):
        """Test _request returns JSON on success."""
        provider = LokiToolProvider()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/json"}
        mock_response.json.return_value = {"data": {"result": []}}

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.request = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            result = await provider._request("GET", "/loki/api/v1/query", params={"query": "{}"})

            assert result["status"] == "success"
            assert result["code"] == 200

    @pytest.mark.asyncio
    async def test_request_non_json_response(self):
        """Test _request handles non-JSON response."""
        provider = LokiToolProvider()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "text/plain"}
        mock_response.text = "OK"

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.request = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            result = await provider._request("GET", "/loki/api/v1/labels")

            assert result["status"] == "success"
            assert result["data"]["raw"] == "OK"

    @pytest.mark.asyncio
    async def test_request_error_status(self):
        """Test _request handles error status codes."""
        provider = LokiToolProvider()

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.headers = {"content-type": "application/json"}
        mock_response.json.return_value = {"message": "Bad Request"}

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.request = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            result = await provider._request("GET", "/loki/api/v1/query")

            assert result["status"] == "error"
            assert result["code"] == 400

    @pytest.mark.asyncio
    async def test_request_exception(self):
        """Test _request handles exceptions."""
        provider = LokiToolProvider()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.request = AsyncMock(side_effect=Exception("Connection failed"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            result = await provider._request("GET", "/loki/api/v1/query")

            assert result["status"] == "error"
            assert "Connection failed" in result["error"]


class TestLokiToolProviderSelectorFromLabels:
    """Test _selector_from_labels helper."""

    def test_selector_from_labels_empty(self):
        """Test _selector_from_labels with empty labels."""
        provider = LokiToolProvider()
        result = provider._selector_from_labels({})
        assert result == "{}"

    def test_selector_from_labels_single(self):
        """Test _selector_from_labels with single label."""
        provider = LokiToolProvider()
        result = provider._selector_from_labels({"job": "redis"})
        assert result == '{job="redis"}'

    def test_selector_from_labels_multiple(self):
        """Test _selector_from_labels with multiple labels."""
        provider = LokiToolProvider()
        result = provider._selector_from_labels({"job": "redis", "instance": "prod"})
        # Order may vary, check both are present
        assert "job" in result
        assert "instance" in result


class TestLokiToolProviderContextManager:
    """Test async context manager."""

    @pytest.mark.asyncio
    async def test_async_context_manager(self):
        """Test async context manager enter/exit."""
        provider = LokiToolProvider()
        async with provider as p:
            assert p is provider


class TestLokiToolProviderRequiresInstance:
    """Test requires_redis_instance property."""

    def test_requires_redis_instance_is_false(self):
        """Test requires_redis_instance is False."""
        provider = LokiToolProvider()
        assert provider.requires_redis_instance is False
