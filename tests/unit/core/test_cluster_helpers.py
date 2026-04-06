"""Tests for cluster MCP helpers."""

from unittest.mock import AsyncMock, patch

import pytest
from pydantic import SecretStr

from redis_sre_agent.core.cluster_helpers import (
    _mask_cluster_payload,
    backfill_instance_links_helper,
    create_cluster_helper,
    delete_cluster_helper,
    get_cluster_helper,
    list_clusters_helper,
    update_cluster_helper,
)
from redis_sre_agent.core.clusters import ClusterQueryResult, RedisCluster, RedisClusterType
from redis_sre_agent.core.migrations.instances_to_clusters import InstanceToClusterMigrationSummary


def _cluster(**overrides) -> RedisCluster:
    data = {
        "id": "cluster-1",
        "name": "prod-cluster",
        "cluster_type": RedisClusterType.redis_enterprise,
        "environment": "production",
        "description": "Primary cluster",
        "admin_url": "https://cluster.example.com:9443",
        "admin_username": "admin@example.com",
        "admin_password": SecretStr("secret"),
        "created_by": "user",
    }
    data.update(overrides)
    return RedisCluster(**data)


class TestMaskClusterPayload:
    def test_mask_cluster_payload_masks_password(self):
        payload = _mask_cluster_payload(_cluster())

        assert payload["admin_password"] == "***"


class TestClusterReadHelpers:
    @pytest.mark.asyncio
    async def test_list_clusters_helper_masks_payloads(self):
        result = ClusterQueryResult(clusters=[_cluster()], total=1, limit=10, offset=0)

        with patch(
            "redis_sre_agent.core.cluster_helpers.core_clusters.query_clusters",
            new_callable=AsyncMock,
            return_value=result,
        ) as mock_query:
            payload = await list_clusters_helper(environment="production", limit=10, offset=0)

        assert payload["total"] == 1
        assert payload["clusters"][0]["admin_password"] == "***"
        mock_query.assert_awaited_once_with(
            environment="production",
            status=None,
            cluster_type=None,
            user_id=None,
            search=None,
            limit=10,
            offset=0,
        )

    @pytest.mark.asyncio
    async def test_get_cluster_helper_returns_masked_payload(self):
        with patch(
            "redis_sre_agent.core.cluster_helpers.core_clusters.get_cluster_by_id",
            new_callable=AsyncMock,
            return_value=_cluster(),
        ):
            payload = await get_cluster_helper("cluster-1")

        assert payload["id"] == "cluster-1"
        assert payload["admin_password"] == "***"

    @pytest.mark.asyncio
    async def test_get_cluster_helper_returns_error_when_missing(self):
        with patch(
            "redis_sre_agent.core.cluster_helpers.core_clusters.get_cluster_by_id",
            new_callable=AsyncMock,
            return_value=None,
        ):
            payload = await get_cluster_helper("cluster-404")

        assert payload == {"error": "Cluster not found", "id": "cluster-404"}


class TestClusterMutationHelpers:
    @pytest.mark.asyncio
    async def test_create_cluster_helper_creates_cluster(self):
        with (
            patch(
                "redis_sre_agent.core.cluster_helpers.core_clusters.get_clusters",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "redis_sre_agent.core.cluster_helpers.core_clusters.save_clusters",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_save,
            patch(
                "redis_sre_agent.core.cluster_helpers.ULID",
                return_value="01HXTESTCLUSTERID1234567890",
            ),
        ):
            payload = await create_cluster_helper(
                name="prod-cluster",
                cluster_type="redis_enterprise",
                environment="production",
                description="Primary cluster",
                admin_url="https://cluster.example.com:9443",
                admin_username="admin@example.com",
                admin_password="secret",
            )

        assert payload == {
            "id": "cluster-production-01HXTESTCLUSTERID1234567890",
            "status": "created",
        }
        saved_cluster = mock_save.await_args.args[0][0]
        assert saved_cluster.name == "prod-cluster"

    @pytest.mark.asyncio
    async def test_create_cluster_helper_generates_unique_ulid_based_ids(self):
        with (
            patch(
                "redis_sre_agent.core.cluster_helpers.core_clusters.get_clusters",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "redis_sre_agent.core.cluster_helpers.core_clusters.save_clusters",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "redis_sre_agent.core.cluster_helpers.ULID",
                side_effect=["01HXFIRSTCLUSTERID123456789", "01HXSECONDCLUSTERID12345678"],
            ),
        ):
            first = await create_cluster_helper(
                name="prod-cluster-a",
                environment="production",
                description="Primary cluster A",
            )
            second = await create_cluster_helper(
                name="prod-cluster-b",
                environment="production",
                description="Primary cluster B",
            )

        assert first["id"] != second["id"]
        assert first["id"].startswith("cluster-production-")
        assert second["id"].startswith("cluster-production-")

    @pytest.mark.asyncio
    async def test_create_cluster_helper_rejects_duplicate_names(self):
        with patch(
            "redis_sre_agent.core.cluster_helpers.core_clusters.get_clusters",
            new_callable=AsyncMock,
            return_value=[_cluster()],
        ):
            with pytest.raises(RuntimeError, match="already exists"):
                await create_cluster_helper(
                    name="prod-cluster",
                    environment="production",
                    description="Primary cluster",
                )

    @pytest.mark.asyncio
    async def test_create_cluster_helper_requires_enterprise_admin_fields(self):
        with patch(
            "redis_sre_agent.core.cluster_helpers.core_clusters.get_clusters",
            new_callable=AsyncMock,
            return_value=[],
        ):
            with pytest.raises(RuntimeError, match="cluster_type=redis_enterprise requires"):
                await create_cluster_helper(
                    name="prod-cluster",
                    cluster_type="redis_enterprise",
                    environment="production",
                    description="Primary cluster",
                )

    @pytest.mark.asyncio
    async def test_create_cluster_helper_raises_when_save_fails(self):
        with (
            patch(
                "redis_sre_agent.core.cluster_helpers.core_clusters.get_clusters",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "redis_sre_agent.core.cluster_helpers.core_clusters.save_clusters",
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch(
                "redis_sre_agent.core.cluster_helpers.ULID",
                return_value="01HXTESTCLUSTERID1234567890",
            ),
        ):
            with pytest.raises(RuntimeError, match="Failed to save cluster"):
                await create_cluster_helper(
                    name="prod-cluster",
                    environment="production",
                    description="Primary cluster",
                )

    @pytest.mark.asyncio
    async def test_update_cluster_helper_updates_existing_cluster(self):
        existing = _cluster()

        with (
            patch(
                "redis_sre_agent.core.cluster_helpers.core_clusters.get_clusters",
                new_callable=AsyncMock,
                return_value=[existing],
            ),
            patch(
                "redis_sre_agent.core.cluster_helpers.core_clusters.save_clusters",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_save,
        ):
            payload = await update_cluster_helper(
                "cluster-1",
                name="prod-cluster-2",
                environment="staging",
                status="healthy",
            )

        assert payload == {"id": "cluster-1", "status": "updated"}
        updated = mock_save.await_args.args[0][0]
        assert updated.name == "prod-cluster-2"
        assert updated.environment == "staging"
        assert updated.admin_password.get_secret_value() == "secret"

    @pytest.mark.asyncio
    async def test_update_cluster_helper_updates_all_optional_fields(self):
        existing = _cluster()

        with (
            patch(
                "redis_sre_agent.core.cluster_helpers.core_clusters.get_clusters",
                new_callable=AsyncMock,
                return_value=[existing],
            ),
            patch(
                "redis_sre_agent.core.cluster_helpers.core_clusters.save_clusters",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_save,
        ):
            await update_cluster_helper(
                "cluster-1",
                cluster_type="redis_enterprise",
                description="Updated description",
                notes="Updated notes",
                admin_url="https://new.example.com:9443",
                admin_username="new-admin@example.com",
                admin_password="new-secret",
                version="7.4.0",
                last_checked="2026-03-25T00:00:00+00:00",
                created_by="agent",
                user_id="user-2",
            )

        updated = mock_save.await_args.args[0][0]
        assert updated.cluster_type == RedisClusterType.redis_enterprise
        assert updated.description == "Updated description"
        assert updated.notes == "Updated notes"
        assert updated.admin_url == "https://new.example.com:9443"
        assert updated.admin_username == "new-admin@example.com"
        assert updated.admin_password.get_secret_value() == "new-secret"
        assert updated.version == "7.4.0"
        assert updated.last_checked == "2026-03-25T00:00:00+00:00"
        assert updated.created_by == "agent"
        assert updated.user_id == "user-2"

    @pytest.mark.asyncio
    async def test_update_cluster_helper_preserves_existing_secret_fields(self):
        existing = _cluster(admin_password="persist-me")

        with (
            patch(
                "redis_sre_agent.core.cluster_helpers.core_clusters.get_clusters",
                new_callable=AsyncMock,
                return_value=[existing],
            ),
            patch(
                "redis_sre_agent.core.cluster_helpers.core_clusters.save_clusters",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_save,
        ):
            await update_cluster_helper("cluster-1", name="prod-cluster-2")

        updated = mock_save.await_args.args[0][0]
        assert updated.admin_password.get_secret_value() == "persist-me"

    @pytest.mark.asyncio
    async def test_update_cluster_helper_rejects_missing_cluster(self):
        with patch(
            "redis_sre_agent.core.cluster_helpers.core_clusters.get_clusters",
            new_callable=AsyncMock,
            return_value=[],
        ):
            with pytest.raises(RuntimeError, match="Cluster not found"):
                await update_cluster_helper("cluster-404")

    @pytest.mark.asyncio
    async def test_update_cluster_helper_raises_when_save_fails(self):
        with (
            patch(
                "redis_sre_agent.core.cluster_helpers.core_clusters.get_clusters",
                new_callable=AsyncMock,
                return_value=[_cluster()],
            ),
            patch(
                "redis_sre_agent.core.cluster_helpers.core_clusters.save_clusters",
                new_callable=AsyncMock,
                return_value=False,
            ),
        ):
            with pytest.raises(RuntimeError, match="Failed to save updated cluster"):
                await update_cluster_helper("cluster-1", description="Updated")

    @pytest.mark.asyncio
    async def test_delete_cluster_helper_requires_confirmation(self):
        payload = await delete_cluster_helper("cluster-1", confirm=False)

        assert payload == {
            "error": "Confirmation required",
            "id": "cluster-1",
            "status": "cancelled",
        }

    @pytest.mark.asyncio
    async def test_delete_cluster_helper_rejects_missing_cluster(self):
        with patch(
            "redis_sre_agent.core.cluster_helpers.core_clusters.get_clusters",
            new_callable=AsyncMock,
            return_value=[],
        ):
            with pytest.raises(RuntimeError, match="Cluster not found"):
                await delete_cluster_helper("cluster-404", confirm=True)

    @pytest.mark.asyncio
    async def test_delete_cluster_helper_deletes_cluster(self):
        with (
            patch(
                "redis_sre_agent.core.cluster_helpers.core_clusters.get_clusters",
                new_callable=AsyncMock,
                return_value=[_cluster()],
            ),
            patch(
                "redis_sre_agent.core.cluster_helpers.core_clusters.save_clusters",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "redis_sre_agent.core.cluster_helpers.core_clusters.delete_cluster_index_doc",
                new_callable=AsyncMock,
                side_effect=RuntimeError("ignore me"),
            ),
        ):
            payload = await delete_cluster_helper("cluster-1", confirm=True)

        assert payload == {"id": "cluster-1", "status": "deleted"}

    @pytest.mark.asyncio
    async def test_delete_cluster_helper_raises_when_save_fails(self):
        with (
            patch(
                "redis_sre_agent.core.cluster_helpers.core_clusters.get_clusters",
                new_callable=AsyncMock,
                return_value=[_cluster()],
            ),
            patch(
                "redis_sre_agent.core.cluster_helpers.core_clusters.save_clusters",
                new_callable=AsyncMock,
                return_value=False,
            ),
        ):
            with pytest.raises(RuntimeError, match="Failed to save after deletion"):
                await delete_cluster_helper("cluster-1", confirm=True)

    @pytest.mark.asyncio
    async def test_backfill_instance_links_helper_returns_summary(self):
        summary = InstanceToClusterMigrationSummary(
            scanned=4,
            eligible=3,
            clusters_created=1,
            clusters_reused=1,
            instances_linked=2,
        )

        with patch(
            "redis_sre_agent.core.cluster_helpers.run_instances_to_clusters_migration",
            new_callable=AsyncMock,
            return_value=summary,
        ) as mock_backfill:
            payload = await backfill_instance_links_helper(dry_run=True, force=False)

        assert payload["clusters_created"] == 1
        mock_backfill.assert_awaited_once_with(
            dry_run=True,
            force=False,
            source="mcp_cluster_backfill",
        )
