import pytest

from redis_sre_agent.tools.logs.loki.provider import LokiConfig, LokiToolProvider


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
