"""Unit tests for RedisInstance -> RedisCluster backfill migration."""

from unittest.mock import AsyncMock, patch

import pytest

from redis_sre_agent.core.clusters import RedisCluster, RedisClusterType
from redis_sre_agent.core.instances import RedisInstance, RedisInstanceType
from redis_sre_agent.core.migrations.instances_to_clusters import (
    MIGRATION_DONE_KEY,
    MIGRATION_LOCK_KEY,
    run_instances_to_clusters_migration,
)


def _enterprise_instance(instance_id: str = "redis-1") -> RedisInstance:
    return RedisInstance(
        id=instance_id,
        name="enterprise-db",
        connection_url="redis://localhost:12000",
        environment="production",
        usage="cache",
        description="legacy enterprise instance",
        instance_type=RedisInstanceType.redis_enterprise,
        cluster_id=None,
        admin_url="https://cluster.example.com:9443",
        admin_username="admin@example.com",
        admin_password="secret",
    )


def _oss_cluster_instance(instance_id: str) -> RedisInstance:
    return RedisInstance(
        id=instance_id,
        name=f"oss-cluster-{instance_id}",
        connection_url="redis://localhost:6379",
        environment="development",
        usage="cache",
        description="oss cluster db",
        instance_type=RedisInstanceType.oss_cluster,
        cluster_id=None,
    )


@pytest.mark.asyncio
async def test_migration_creates_enterprise_cluster_and_links_instance():
    mock_client = AsyncMock()
    mock_client.set = AsyncMock(side_effect=[True, True])  # lock + marker
    mock_client.exists = AsyncMock(return_value=False)
    mock_client.eval = AsyncMock(return_value=1)
    mock_client.aclose = AsyncMock(return_value=None)

    instance = _enterprise_instance()

    with (
        patch(
            "redis_sre_agent.core.migrations.instances_to_clusters.get_redis_client",
            return_value=mock_client,
        ),
        patch(
            "redis_sre_agent.core.migrations.instances_to_clusters.core_instances.get_instances",
            new=AsyncMock(return_value=[instance]),
        ),
        patch(
            "redis_sre_agent.core.migrations.instances_to_clusters.core_clusters.get_clusters",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "redis_sre_agent.core.migrations.instances_to_clusters.core_clusters.save_clusters",
            new=AsyncMock(return_value=True),
        ) as mock_save_clusters,
        patch(
            "redis_sre_agent.core.migrations.instances_to_clusters.core_instances.save_instances",
            new=AsyncMock(return_value=True),
        ) as mock_save_instances,
    ):
        summary = await run_instances_to_clusters_migration(source="unit_test")

    assert summary.skipped_due_lock is False
    assert summary.skipped_due_marker is False
    assert summary.eligible == 1
    assert summary.clusters_created == 1
    assert summary.instances_linked == 1
    assert summary.errors == []

    saved_clusters = mock_save_clusters.await_args.args[0]
    assert len(saved_clusters) == 1
    assert saved_clusters[0].cluster_type == RedisClusterType.redis_enterprise
    assert saved_clusters[0].admin_url == "https://cluster.example.com:9443"

    saved_instances = mock_save_instances.await_args.args[0]
    assert len(saved_instances) == 1
    assert saved_instances[0].cluster_id
    assert saved_instances[0].admin_url == "https://cluster.example.com:9443"
    assert saved_instances[0].admin_username == "admin@example.com"
    assert saved_instances[0].admin_password is not None

    mock_client.set.assert_any_await(MIGRATION_LOCK_KEY, mock_client.set.await_args_list[0].args[1], nx=True, ex=120)
    mock_client.set.assert_any_await(MIGRATION_DONE_KEY, mock_client.set.await_args_list[-1].args[1])


@pytest.mark.asyncio
async def test_migration_reuses_existing_enterprise_cluster_by_fingerprint():
    mock_client = AsyncMock()
    mock_client.set = AsyncMock(side_effect=[True, True])  # lock + marker
    mock_client.exists = AsyncMock(return_value=False)
    mock_client.eval = AsyncMock(return_value=1)
    mock_client.aclose = AsyncMock(return_value=None)

    instance = _enterprise_instance()
    existing_cluster = RedisCluster(
        id="cluster-existing-1",
        name="existing-enterprise",
        cluster_type=RedisClusterType.redis_enterprise,
        environment="production",
        description="existing enterprise cluster",
        admin_url="https://cluster.example.com:9443",
        admin_username="admin@example.com",
        admin_password="secret",
    )

    with (
        patch(
            "redis_sre_agent.core.migrations.instances_to_clusters.get_redis_client",
            return_value=mock_client,
        ),
        patch(
            "redis_sre_agent.core.migrations.instances_to_clusters.core_instances.get_instances",
            new=AsyncMock(return_value=[instance]),
        ),
        patch(
            "redis_sre_agent.core.migrations.instances_to_clusters.core_clusters.get_clusters",
            new=AsyncMock(return_value=[existing_cluster]),
        ),
        patch(
            "redis_sre_agent.core.migrations.instances_to_clusters.core_clusters.save_clusters",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "redis_sre_agent.core.migrations.instances_to_clusters.core_instances.save_instances",
            new=AsyncMock(return_value=True),
        ) as mock_save_instances,
    ):
        summary = await run_instances_to_clusters_migration(source="unit_test")

    assert summary.clusters_created == 0
    assert summary.clusters_reused == 1
    assert summary.instances_linked == 1
    saved_instances = mock_save_instances.await_args.args[0]
    assert saved_instances[0].cluster_id == "cluster-existing-1"


@pytest.mark.asyncio
async def test_migration_creates_one_cluster_per_oss_instance():
    mock_client = AsyncMock()
    mock_client.set = AsyncMock(side_effect=[True, True])  # lock + marker
    mock_client.exists = AsyncMock(return_value=False)
    mock_client.eval = AsyncMock(return_value=1)
    mock_client.aclose = AsyncMock(return_value=None)

    inst_one = _oss_cluster_instance("oss-1")
    inst_two = _oss_cluster_instance("oss-2")

    with (
        patch(
            "redis_sre_agent.core.migrations.instances_to_clusters.get_redis_client",
            return_value=mock_client,
        ),
        patch(
            "redis_sre_agent.core.migrations.instances_to_clusters.core_instances.get_instances",
            new=AsyncMock(return_value=[inst_one, inst_two]),
        ),
        patch(
            "redis_sre_agent.core.migrations.instances_to_clusters.core_clusters.get_clusters",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "redis_sre_agent.core.migrations.instances_to_clusters.core_clusters.save_clusters",
            new=AsyncMock(return_value=True),
        ) as mock_save_clusters,
        patch(
            "redis_sre_agent.core.migrations.instances_to_clusters.core_instances.save_instances",
            new=AsyncMock(return_value=True),
        ),
    ):
        summary = await run_instances_to_clusters_migration(source="unit_test")

    assert summary.eligible == 2
    assert summary.clusters_created == 2
    assert summary.instances_linked == 2
    saved_clusters = mock_save_clusters.await_args.args[0]
    assert len(saved_clusters) == 2
    assert all(c.cluster_type == RedisClusterType.oss_cluster for c in saved_clusters)
    assert all(c.admin_url is None for c in saved_clusters)


@pytest.mark.asyncio
async def test_migration_dry_run_does_not_write():
    mock_client = AsyncMock()
    mock_client.set = AsyncMock(return_value=True)  # lock only
    mock_client.exists = AsyncMock(return_value=False)
    mock_client.eval = AsyncMock(return_value=1)
    mock_client.aclose = AsyncMock(return_value=None)

    instance = _enterprise_instance("redis-dry-run")

    with (
        patch(
            "redis_sre_agent.core.migrations.instances_to_clusters.get_redis_client",
            return_value=mock_client,
        ),
        patch(
            "redis_sre_agent.core.migrations.instances_to_clusters.core_instances.get_instances",
            new=AsyncMock(return_value=[instance]),
        ),
        patch(
            "redis_sre_agent.core.migrations.instances_to_clusters.core_clusters.get_clusters",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "redis_sre_agent.core.migrations.instances_to_clusters.core_clusters.save_clusters",
            new=AsyncMock(return_value=True),
        ) as mock_save_clusters,
        patch(
            "redis_sre_agent.core.migrations.instances_to_clusters.core_instances.save_instances",
            new=AsyncMock(return_value=True),
        ) as mock_save_instances,
    ):
        summary = await run_instances_to_clusters_migration(source="unit_test", dry_run=True)

    assert summary.dry_run is True
    assert summary.clusters_created == 1
    assert summary.instances_linked == 1
    mock_save_clusters.assert_not_awaited()
    mock_save_instances.assert_not_awaited()
    assert mock_client.set.await_count == 1  # lock only; no marker in dry-run


@pytest.mark.asyncio
async def test_migration_skips_when_lock_not_acquired():
    mock_client = AsyncMock()
    mock_client.set = AsyncMock(return_value=False)
    mock_client.aclose = AsyncMock(return_value=None)

    with patch(
        "redis_sre_agent.core.migrations.instances_to_clusters.get_redis_client",
        return_value=mock_client,
    ):
        summary = await run_instances_to_clusters_migration(source="unit_test")

    assert summary.skipped_due_lock is True
    assert summary.skipped_due_marker is False
    assert summary.scanned == 0


@pytest.mark.asyncio
async def test_migration_skips_when_done_marker_exists():
    mock_client = AsyncMock()
    mock_client.set = AsyncMock(return_value=True)  # lock acquired
    mock_client.exists = AsyncMock(return_value=True)  # marker exists
    mock_client.eval = AsyncMock(return_value=1)
    mock_client.aclose = AsyncMock(return_value=None)

    with (
        patch(
            "redis_sre_agent.core.migrations.instances_to_clusters.get_redis_client",
            return_value=mock_client,
        ),
        patch(
            "redis_sre_agent.core.migrations.instances_to_clusters.core_instances.get_instances",
            new=AsyncMock(return_value=[]),
        ) as mock_get_instances,
    ):
        summary = await run_instances_to_clusters_migration(source="unit_test")

    assert summary.skipped_due_marker is True
    assert summary.skipped_due_lock is False
    mock_get_instances.assert_not_awaited()
    mock_client.eval.assert_awaited_once()

