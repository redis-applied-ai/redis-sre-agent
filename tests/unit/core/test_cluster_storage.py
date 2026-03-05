"""Unit tests for cluster storage and query helpers."""

import json
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import SecretStr

from redis_sre_agent.core.clusters import (
    RedisCluster,
    RedisClusterType,
    _upsert_cluster_index_doc,
    delete_cluster_index_doc,
    get_cluster_by_id,
    get_clusters,
    query_clusters,
    save_clusters,
)


def _enterprise_cluster(cluster_id: str = "cluster-1") -> RedisCluster:
    return RedisCluster(
        id=cluster_id,
        name="Enterprise Cluster",
        cluster_type=RedisClusterType.redis_enterprise,
        environment="production",
        description="Primary enterprise cluster",
        admin_url="https://cluster.example.com:9443",
        admin_username="admin@redis.com",
        admin_password=SecretStr("super-secret"),
    )


class TestClusterStorage:
    @pytest.mark.asyncio
    async def test_get_clusters_success(self):
        mock_index = AsyncMock()
        cluster_data = {
            "id": "cluster-1",
            "name": "Enterprise Cluster",
            "cluster_type": "redis_enterprise",
            "environment": "production",
            "description": "Primary enterprise cluster",
            "admin_url": "https://cluster.example.com:9443",
            "admin_username": "admin@redis.com",
            "admin_password": "encrypted-password",
        }
        mock_index.query = AsyncMock(
            side_effect=[
                1,
                [{"data": json.dumps(cluster_data)}],
            ]
        )

        with (
            patch(
                "redis_sre_agent.core.clusters._ensure_clusters_index_exists",
                new_callable=AsyncMock,
            ),
            patch(
                "redis_sre_agent.core.clusters.get_clusters_index",
                new_callable=AsyncMock,
                return_value=mock_index,
            ),
            patch("redis_sre_agent.core.clusters.get_secret_value", side_effect=lambda x: x),
        ):
            clusters = await get_clusters()

        assert len(clusters) == 1
        assert clusters[0].id == "cluster-1"
        assert clusters[0].admin_password.get_secret_value() == "encrypted-password"

    @pytest.mark.asyncio
    async def test_query_clusters_success(self):
        mock_index = AsyncMock()
        cluster_data = {
            "id": "cluster-1",
            "name": "Enterprise Cluster",
            "cluster_type": "redis_enterprise",
            "environment": "production",
            "description": "Primary enterprise cluster",
            "admin_url": "https://cluster.example.com:9443",
            "admin_username": "admin@redis.com",
            "admin_password": "encrypted-password",
        }
        mock_index.query = AsyncMock(
            side_effect=[
                1,
                [{"data": json.dumps(cluster_data)}],
            ]
        )

        with (
            patch(
                "redis_sre_agent.core.clusters._ensure_clusters_index_exists",
                new_callable=AsyncMock,
            ),
            patch(
                "redis_sre_agent.core.clusters.get_clusters_index",
                new_callable=AsyncMock,
                return_value=mock_index,
            ),
            patch("redis_sre_agent.core.clusters.get_secret_value", side_effect=lambda x: x),
        ):
            result = await query_clusters(environment="production", cluster_type="redis_enterprise")

        assert result.total == 1
        assert len(result.clusters) == 1
        assert result.clusters[0].id == "cluster-1"

    @pytest.mark.asyncio
    async def test_upsert_cluster_index_doc_encrypts_admin_password(self):
        mock_client = AsyncMock()
        cluster = _enterprise_cluster("cluster-enc")

        with (
            patch(
                "redis_sre_agent.core.clusters._ensure_clusters_index_exists",
                new_callable=AsyncMock,
            ),
            patch("redis_sre_agent.core.clusters.get_redis_client", return_value=mock_client),
            patch(
                "redis_sre_agent.core.clusters.encrypt_secret", side_effect=lambda x: f"enc::{x}"
            ),
        ):
            result = await _upsert_cluster_index_doc(cluster)

        assert result is True
        mock_client.hset.assert_awaited_once()
        mapping = mock_client.hset.await_args.kwargs["mapping"]
        assert mapping["cluster_type"] == "redis_enterprise"
        data = json.loads(mapping["data"])
        assert data["admin_password"] == "enc::super-secret"

    @pytest.mark.asyncio
    async def test_save_clusters_deletes_stale_docs(self):
        mock_client = AsyncMock()
        mock_index = AsyncMock()
        mock_index.query = AsyncMock(
            side_effect=[
                2,
                [
                    {"data": json.dumps({"id": "cluster-1"})},
                    {"data": json.dumps({"id": "cluster-old"})},
                ],
            ]
        )
        cluster = _enterprise_cluster("cluster-1")

        with (
            patch("redis_sre_agent.core.clusters.get_redis_client", return_value=mock_client),
            patch(
                "redis_sre_agent.core.clusters._ensure_clusters_index_exists",
                new_callable=AsyncMock,
            ),
            patch(
                "redis_sre_agent.core.clusters._upsert_clusters_index_docs",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "redis_sre_agent.core.clusters.get_clusters_index",
                new_callable=AsyncMock,
                return_value=mock_index,
            ),
        ):
            result = await save_clusters([cluster])

        assert result is True
        mock_client.delete.assert_any_await("sre_clusters:cluster-old")

    @pytest.mark.asyncio
    async def test_get_cluster_by_id_success(self):
        mock_client = AsyncMock()
        cluster_data = {
            "id": "cluster-1",
            "name": "Enterprise Cluster",
            "cluster_type": "redis_enterprise",
            "environment": "production",
            "description": "Primary enterprise cluster",
            "admin_url": "https://cluster.example.com:9443",
            "admin_username": "admin@redis.com",
            "admin_password": "encrypted-password",
        }
        mock_client.hget = AsyncMock(return_value=json.dumps(cluster_data))

        with (
            patch("redis_sre_agent.core.clusters.get_redis_client", return_value=mock_client),
            patch("redis_sre_agent.core.clusters.get_secret_value", side_effect=lambda x: x),
        ):
            cluster = await get_cluster_by_id("cluster-1")

        assert cluster is not None
        assert cluster.id == "cluster-1"
        assert cluster.admin_password.get_secret_value() == "encrypted-password"

    @pytest.mark.asyncio
    async def test_delete_cluster_index_doc(self):
        mock_client = AsyncMock()

        with patch("redis_sre_agent.core.clusters.get_redis_client", return_value=mock_client):
            await delete_cluster_index_doc("cluster-1")

        mock_client.delete.assert_awaited_once_with("sre_clusters:cluster-1")
