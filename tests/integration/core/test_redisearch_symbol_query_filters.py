"""Live RediSearch regressions for symbol-heavy user search filters."""

import base64
import os
import uuid

import pytest

from redis_sre_agent.core.clusters import (
    RedisCluster,
    RedisClusterType,
    query_clusters,
    save_clusters,
)
from redis_sre_agent.core.instances import (
    RedisInstance,
    RedisInstanceType,
    query_instances,
    save_instances,
)

SYMBOL_HEAVY_SEARCHES = [
    "cache/prod",
    "cache|prod",
    "cache[prod]",
    "cache{prod}",
    "cache?prod",
    "cache prod",
    "*cache*",
]


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize("search_text", SYMBOL_HEAVY_SEARCHES)
async def test_query_instances_symbol_heavy_search_filters_execute_against_redis(
    async_redis_client,
    monkeypatch,
    search_text,
):
    monkeypatch.setenv("REDIS_SRE_MASTER_KEY", base64.b64encode(os.urandom(32)).decode("ascii"))

    instance_id = f"redis-symbol-{uuid.uuid4().hex[:8]}"
    instance = RedisInstance(
        id=instance_id,
        name=f"primary {search_text} shard",
        connection_url="redis://example-host:6379/0",
        environment="production",
        usage="cache",
        description="Symbol-heavy search regression fixture",
        instance_type=RedisInstanceType.oss_single,
    )

    assert await save_instances([instance]) is True

    result = await query_instances(environment="production", search=search_text)

    assert result.total >= 1
    assert any(found.id == instance_id for found in result.instances)


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize("search_text", SYMBOL_HEAVY_SEARCHES)
async def test_query_clusters_symbol_heavy_search_filters_execute_against_redis(
    async_redis_client,
    search_text,
):
    cluster_id = f"cluster-symbol-{uuid.uuid4().hex[:8]}"
    cluster = RedisCluster(
        id=cluster_id,
        name=f"primary {search_text} cluster",
        cluster_type=RedisClusterType.unknown,
        environment="production",
        description="Symbol-heavy search regression fixture",
    )

    assert await save_clusters([cluster]) is True

    result = await query_clusters(environment="production", search=search_text)

    assert result.total >= 1
    assert any(found.id == cluster_id for found in result.clusters)
