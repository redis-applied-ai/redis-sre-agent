"""Tests for instance mutation helpers."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import SecretStr

from redis_sre_agent.core.instance_mutation_helpers import (
    _normalize_cluster_id,
    _validate_instance_cluster_link,
    delete_instance_helper,
    update_instance_helper,
)
from redis_sre_agent.core.instances import RedisInstance, RedisInstanceType


def _build_instance() -> RedisInstance:
    return RedisInstance(
        id="redis-prod-1",
        name="Production Redis",
        connection_url=SecretStr("redis://user:pass@redis.example.com:6379/0"),
        environment="production",
        usage="cache",
        description="Primary cache",
        instance_type=RedisInstanceType.redis_cloud,
        cluster_id="cluster-123",
        extension_data={"existing": "value", "remove-me": True},
    )


class TestUpdateInstanceHelper:
    """Test shared helpers for updating instances."""

    @pytest.mark.asyncio
    async def test_update_instance_helper_updates_and_masks_payload(self):
        """Updates should persist and return a masked payload."""
        cluster = MagicMock()
        cluster.cluster_type = RedisInstanceType.redis_cloud

        with (
            patch(
                "redis_sre_agent.core.instance_mutation_helpers.get_instances",
                new_callable=AsyncMock,
                return_value=[_build_instance()],
            ),
            patch(
                "redis_sre_agent.core.instance_mutation_helpers.get_cluster_by_id",
                new_callable=AsyncMock,
                return_value=cluster,
            ),
            patch(
                "redis_sre_agent.core.instance_mutation_helpers.save_instances",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_save,
        ):
            result = await update_instance_helper(
                "redis-prod-1",
                description="Updated description",
                cluster_id=" cluster-123 ",
                set_extensions={"new-key": {"nested": True}},
                unset_extensions=["remove-me"],
            )

        assert result["id"] == "redis-prod-1"
        assert result["status"] == "updated"
        assert result["description"] == "Updated description"
        assert result["connection_url"] == "redis://***:***@redis.example.com:6379/0"
        assert result["cluster_id"] == "cluster-123"
        assert result["extension_data"] == {
            "existing": "value",
            "new-key": {"nested": True},
        }
        saved_instances = mock_save.await_args.args[0]
        assert saved_instances[0].description == "Updated description"
        assert saved_instances[0].extension_data == {
            "existing": "value",
            "new-key": {"nested": True},
        }

    @pytest.mark.asyncio
    async def test_update_instance_helper_covers_all_optional_fields(self):
        """Optional update fields should all flow into the saved instance."""
        with (
            patch(
                "redis_sre_agent.core.instance_mutation_helpers.get_instances",
                new_callable=AsyncMock,
                return_value=[_build_instance()],
            ),
            patch(
                "redis_sre_agent.core.instance_mutation_helpers.save_instances",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_save,
        ):
            result = await update_instance_helper(
                "redis-prod-1",
                name="Renamed Redis",
                connection_url="redis://new-user:new-pass@redis.example.com:6380/0",
                environment="staging",
                usage="session",
                repo_url="https://github.com/example/repo",
                notes="note",
                monitoring_identifier="monitoring-name",
                logging_identifier="logging-name",
                instance_type="redis_cloud",
                admin_url="https://admin.example.com",
                admin_username="admin",
                admin_password="secret",
                redis_cloud_subscription_id=99,
                redis_cloud_database_id=42,
                redis_cloud_subscription_type="PRO",
                redis_cloud_database_name="db-name",
                status="healthy",
                version="8.0.1",
                memory="2gb",
                connections=17,
                user_id="user-123",
            )

        assert result["name"] == "Renamed Redis"
        assert result["environment"] == "staging"
        assert result["usage"] == "session"
        assert result["repo_url"] == "https://github.com/example/repo"
        assert result["notes"] == "note"
        assert result["monitoring_identifier"] == "monitoring-name"
        assert result["logging_identifier"] == "logging-name"
        assert result["instance_type"] == "redis_cloud"
        assert result["admin_url"] == "https://admin.example.com"
        assert result["admin_username"] == "admin"
        assert result["admin_password"] == "***"
        assert result["redis_cloud_subscription_id"] == 99
        assert result["redis_cloud_database_id"] == 42
        assert result["redis_cloud_subscription_type"] == "pro"
        assert result["redis_cloud_database_name"] == "db-name"
        assert result["status"] == "updated"
        assert result["version"] == "8.0.1"
        assert result["memory"] == "2gb"
        assert result["connections"] == 17
        assert result["user_id"] == "user-123"
        saved_instance = mock_save.await_args.args[0][0]
        assert saved_instance.name == "Renamed Redis"
        assert saved_instance.environment == "staging"
        assert saved_instance.usage == "session"
        assert saved_instance.redis_cloud_subscription_type == "pro"

    @pytest.mark.asyncio
    async def test_update_instance_helper_returns_not_found_payload(self):
        """Missing instances should return a structured error payload."""
        with patch(
            "redis_sre_agent.core.instance_mutation_helpers.get_instances",
            new_callable=AsyncMock,
            return_value=[],
        ):
            result = await update_instance_helper("missing")

        assert result == {"error": "Instance not found", "id": "missing"}

    @pytest.mark.asyncio
    async def test_update_instance_helper_raises_for_save_failure(self):
        """Save failures should raise so the MCP wrapper can surface them."""
        with (
            patch(
                "redis_sre_agent.core.instance_mutation_helpers.get_instances",
                new_callable=AsyncMock,
                return_value=[_build_instance()],
            ),
            patch(
                "redis_sre_agent.core.instance_mutation_helpers.save_instances",
                new_callable=AsyncMock,
                return_value=False,
            ),
        ):
            with pytest.raises(RuntimeError, match="Failed to save updated instance"):
                await update_instance_helper("redis-prod-1", notes="updated")

    @pytest.mark.asyncio
    async def test_update_instance_helper_raises_for_incompatible_cluster(self):
        """Cluster validation should reject incompatible instance types."""
        cluster = MagicMock()
        cluster.cluster_type = RedisInstanceType.redis_enterprise

        with (
            patch(
                "redis_sre_agent.core.instance_mutation_helpers.get_instances",
                new_callable=AsyncMock,
                return_value=[_build_instance()],
            ),
            patch(
                "redis_sre_agent.core.instance_mutation_helpers.get_cluster_by_id",
                new_callable=AsyncMock,
                return_value=cluster,
            ),
        ):
            with pytest.raises(RuntimeError, match="incompatible"):
                await update_instance_helper("redis-prod-1", cluster_id="cluster-123")

    @pytest.mark.asyncio
    async def test_validate_instance_cluster_link_accepts_none(self):
        """Blank cluster ids should normalize to None without lookup."""
        with patch(
            "redis_sre_agent.core.instance_mutation_helpers.get_cluster_by_id",
            new_callable=AsyncMock,
        ) as mock_get_cluster:
            result = await _validate_instance_cluster_link(cluster_id=None, instance_type=None)

        assert result is None
        mock_get_cluster.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_validate_instance_cluster_link_raises_when_cluster_missing(self):
        """Missing clusters should raise a clear error."""
        with patch(
            "redis_sre_agent.core.instance_mutation_helpers.get_cluster_by_id",
            new_callable=AsyncMock,
            return_value=None,
        ):
            with pytest.raises(RuntimeError, match="Cluster with ID 'cluster-123' not found"):
                await _validate_instance_cluster_link(
                    cluster_id="cluster-123",
                    instance_type="redis_cloud",
                )

    @pytest.mark.asyncio
    async def test_validate_instance_cluster_link_accepts_enum_instance_type(self):
        """Enum instance types should normalize without attribute errors."""
        cluster = MagicMock()
        cluster.cluster_type = RedisInstanceType.redis_cloud

        with patch(
            "redis_sre_agent.core.instance_mutation_helpers.get_cluster_by_id",
            new_callable=AsyncMock,
            return_value=cluster,
        ):
            result = await _validate_instance_cluster_link(
                cluster_id="cluster-123",
                instance_type=RedisInstanceType.redis_cloud,
            )

        assert result == "cluster-123"


class TestDeleteInstanceHelper:
    """Test shared helpers for deleting instances."""

    @pytest.mark.asyncio
    async def test_delete_instance_helper_requires_confirmation(self):
        """Deletes should require explicit confirmation."""
        result = await delete_instance_helper("redis-prod-1", confirm=False)

        assert result == {
            "error": "Confirmation required",
            "id": "redis-prod-1",
            "status": "cancelled",
        }

    @pytest.mark.asyncio
    async def test_delete_instance_helper_returns_not_found_payload(self):
        """Missing instances should return a structured error payload."""
        with patch(
            "redis_sre_agent.core.instance_mutation_helpers.get_instances",
            new_callable=AsyncMock,
            return_value=[],
        ):
            result = await delete_instance_helper("missing", confirm=True)

        assert result == {"error": "Instance not found", "id": "missing"}

    @pytest.mark.asyncio
    async def test_delete_instance_helper_deletes_and_swallows_index_failures(self):
        """Deletes should persist even if index cleanup fails."""
        with (
            patch(
                "redis_sre_agent.core.instance_mutation_helpers.get_instances",
                new_callable=AsyncMock,
                return_value=[_build_instance()],
            ),
            patch(
                "redis_sre_agent.core.instance_mutation_helpers.save_instances",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_save,
            patch(
                "redis_sre_agent.core.instance_mutation_helpers.delete_instance_index_doc",
                new_callable=AsyncMock,
                side_effect=RuntimeError("boom"),
            ) as mock_delete_index,
        ):
            result = await delete_instance_helper("redis-prod-1", confirm=True)

        assert result == {"id": "redis-prod-1", "status": "deleted"}
        assert mock_save.await_args.args[0] == []
        mock_delete_index.assert_awaited_once_with("redis-prod-1")

    @pytest.mark.asyncio
    async def test_delete_instance_helper_raises_for_save_failure(self):
        """Delete save failures should raise for the wrapper."""
        with (
            patch(
                "redis_sre_agent.core.instance_mutation_helpers.get_instances",
                new_callable=AsyncMock,
                return_value=[_build_instance()],
            ),
            patch(
                "redis_sre_agent.core.instance_mutation_helpers.save_instances",
                new_callable=AsyncMock,
                return_value=False,
            ),
        ):
            with pytest.raises(RuntimeError, match="Failed to save after deletion"):
                await delete_instance_helper("redis-prod-1", confirm=True)


class TestInstanceMutationInternals:
    """Test small internal helpers that feed the mutation paths."""

    def test_normalize_cluster_id_handles_none_and_blank(self):
        """Cluster ids should trim and collapse blanks to None."""
        assert _normalize_cluster_id(None) is None
        assert _normalize_cluster_id("  ") is None
        assert _normalize_cluster_id(" cluster-123 ") == "cluster-123"
