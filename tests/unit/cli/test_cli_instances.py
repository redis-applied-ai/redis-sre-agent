"""Tests for the `instance` CLI command group."""

import logging
import os
from unittest.mock import AsyncMock, patch

from click.testing import CliRunner

from redis_sre_agent.cli.instance import instance
from redis_sre_agent.core import clusters as core_clusters
from redis_sre_agent.core import instances as core_instances


def test_instance_cli_help_lists_subcommands():
    runner = CliRunner()
    result = runner.invoke(instance, ["--help"])

    assert result.exit_code == 0
    assert "Commands:" in result.output
    # Core subcommands
    for cmd in ["list", "get", "create", "update", "delete", "test", "test-url"]:
        assert cmd in result.output


def test_instances_list_empty_prints_message():
    runner = CliRunner()

    with patch.object(core_instances, "get_instances", new=AsyncMock(return_value=[])):
        result = runner.invoke(instance, ["list"])  # pretty output path

    assert result.exit_code == 0
    assert "No instances found." in result.output


def test_instances_list_json_with_item():
    runner = CliRunner()

    # Minimal valid instance
    item = core_instances.RedisInstance(
        id="redis-dev-123",
        name="dev-cache",
        connection_url="redis://localhost:6380/0",
        environment="development",
        usage="cache",
        description="Dev cache",
        instance_type="oss_single",
    )

    with patch.object(core_instances, "get_instances", new=AsyncMock(return_value=[item])):
        result = runner.invoke(instance, ["list", "--json"])  # JSON output path

    assert result.exit_code == 0
    assert "redis-dev-123" in result.output
    assert "dev-cache" in result.output


def test_instances_create_logs_exception_trace_when_debug_enabled(caplog):
    runner = CliRunner()

    with (
        patch.dict(os.environ, {"LOG_LEVEL": "DEBUG"}, clear=False),
        patch.object(
            core_instances,
            "get_instances",
            new=AsyncMock(side_effect=RuntimeError("Connection failed")),
        ),
        caplog.at_level(logging.DEBUG),
    ):
        result = runner.invoke(
            instance,
            [
                "create",
                "--name",
                "dev-cache",
                "--connection-url",
                "redis://localhost:6380/0",
                "--environment",
                "development",
                "--usage",
                "cache",
                "--description",
                "Dev cache",
            ],
        )

    assert result.exit_code == 0
    assert "❌ Error: Connection failed" in result.output
    assert any(
        record.getMessage() == "instance CLI command failed" and record.exc_info
        for record in caplog.records
    )


def test_instance_update_set_extension_data():
    """Test setting extension_data via --set-extension."""
    runner = CliRunner()

    item = core_instances.RedisInstance(
        id="redis-dev-123",
        name="dev-cache",
        connection_url="redis://localhost:6380/0",
        environment="development",
        usage="cache",
        description="Dev cache",
        instance_type="oss_single",
    )

    with (
        patch.object(core_instances, "get_instances", new=AsyncMock(return_value=[item])),
        patch.object(
            core_instances, "save_instances", new=AsyncMock(return_value=True)
        ) as mock_save,
    ):
        result = runner.invoke(
            instance,
            [
                "update",
                "redis-dev-123",
                "--set-extension",
                "zendesk_organization_id=12345",
            ],
        )

    assert result.exit_code == 0
    assert "Updated instance" in result.output

    # Verify the saved instance has extension_data set
    # Note: numeric-looking values are parsed as JSON, so "12345" becomes int 12345
    saved_instances = mock_save.call_args[0][0]
    assert len(saved_instances) == 1
    assert saved_instances[0].extension_data == {"zendesk_organization_id": 12345}


def test_instance_update_set_multiple_extensions():
    """Test setting multiple extension_data fields."""
    runner = CliRunner()

    item = core_instances.RedisInstance(
        id="redis-dev-123",
        name="dev-cache",
        connection_url="redis://localhost:6380/0",
        environment="development",
        usage="cache",
        description="Dev cache",
        instance_type="oss_single",
    )

    with (
        patch.object(core_instances, "get_instances", new=AsyncMock(return_value=[item])),
        patch.object(
            core_instances, "save_instances", new=AsyncMock(return_value=True)
        ) as mock_save,
    ):
        result = runner.invoke(
            instance,
            [
                "update",
                "redis-dev-123",
                "--set-extension",
                "zendesk_organization_id=12345",
                "--set-extension",
                "github_repo=my-org/my-repo",
            ],
        )

    assert result.exit_code == 0

    # Note: numeric-looking values are parsed as JSON, so "12345" becomes int 12345
    saved_instances = mock_save.call_args[0][0]
    assert saved_instances[0].extension_data == {
        "zendesk_organization_id": 12345,
        "github_repo": "my-org/my-repo",
    }


def test_instance_update_unset_extension():
    """Test removing extension_data fields via --unset-extension."""
    runner = CliRunner()

    item = core_instances.RedisInstance(
        id="redis-dev-123",
        name="dev-cache",
        connection_url="redis://localhost:6380/0",
        environment="development",
        usage="cache",
        description="Dev cache",
        instance_type="oss_single",
        extension_data={"zendesk_organization_id": "12345", "keep_this": "value"},
    )

    with (
        patch.object(core_instances, "get_instances", new=AsyncMock(return_value=[item])),
        patch.object(
            core_instances, "save_instances", new=AsyncMock(return_value=True)
        ) as mock_save,
    ):
        result = runner.invoke(
            instance,
            ["update", "redis-dev-123", "--unset-extension", "zendesk_organization_id"],
        )

    assert result.exit_code == 0

    saved_instances = mock_save.call_args[0][0]
    assert saved_instances[0].extension_data == {"keep_this": "value"}


def test_instance_update_set_extension_json_value():
    """Test setting extension_data with JSON value."""
    runner = CliRunner()

    item = core_instances.RedisInstance(
        id="redis-dev-123",
        name="dev-cache",
        connection_url="redis://localhost:6380/0",
        environment="development",
        usage="cache",
        description="Dev cache",
        instance_type="oss_single",
    )

    with (
        patch.object(core_instances, "get_instances", new=AsyncMock(return_value=[item])),
        patch.object(
            core_instances, "save_instances", new=AsyncMock(return_value=True)
        ) as mock_save,
    ):
        result = runner.invoke(
            instance,
            [
                "update",
                "redis-dev-123",
                "--set-extension",
                'config={"nested": true, "count": 42}',
            ],
        )

    assert result.exit_code == 0

    saved_instances = mock_save.call_args[0][0]
    assert saved_instances[0].extension_data == {"config": {"nested": True, "count": 42}}


def test_instance_update_set_extension_invalid_format():
    """Test error handling for invalid --set-extension format."""
    runner = CliRunner()

    item = core_instances.RedisInstance(
        id="redis-dev-123",
        name="dev-cache",
        connection_url="redis://localhost:6380/0",
        environment="development",
        usage="cache",
        description="Dev cache",
        instance_type="oss_single",
    )

    with patch.object(core_instances, "get_instances", new=AsyncMock(return_value=[item])):
        result = runner.invoke(
            instance,
            ["update", "redis-dev-123", "--set-extension", "invalid_no_equals"],
        )

    assert result.exit_code == 0  # CLI doesn't fail, but shows error
    assert "Invalid --set-extension format" in result.output


def test_instance_get_shows_extension_data():
    """Test that instance get displays extension_data."""
    runner = CliRunner()

    item = core_instances.RedisInstance(
        id="redis-dev-123",
        name="dev-cache",
        connection_url="redis://localhost:6380/0",
        environment="development",
        usage="cache",
        description="Dev cache",
        instance_type="oss_single",
        extension_data={"zendesk_organization_id": "12345"},
    )

    with patch.object(core_instances, "get_instance_by_id", new=AsyncMock(return_value=item)):
        result = runner.invoke(instance, ["get", "redis-dev-123", "--json"])

    assert result.exit_code == 0
    assert "extension_data" in result.output
    assert "zendesk_organization_id" in result.output
    assert "12345" in result.output


def test_instance_create_accepts_cluster_id_when_cluster_exists_and_is_compatible():
    runner = CliRunner()
    linked_cluster = core_clusters.RedisCluster(
        id="cluster-prod-1",
        name="prod-enterprise",
        cluster_type=core_clusters.RedisClusterType.redis_enterprise,
        environment="production",
        description="Production enterprise cluster",
        admin_url="https://cluster.example.com:9443",
        admin_username="admin@example.com",
        admin_password="secret",
    )

    with (
        patch.object(core_instances, "get_instances", new=AsyncMock(return_value=[])),
        patch.object(
            core_instances, "save_instances", new=AsyncMock(return_value=True)
        ) as mock_save,
        patch.object(
            core_clusters, "get_cluster_by_id", new=AsyncMock(return_value=linked_cluster)
        ),
        patch(
            "redis_sre_agent.cli.instance.ULID",
            return_value="01HXTESTINSTANCEID123456789",
        ),
    ):
        result = runner.invoke(
            instance,
            [
                "create",
                "--name",
                "prod-db",
                "--connection-url",
                "redis://localhost:6380/0",
                "--environment",
                "production",
                "--usage",
                "cache",
                "--description",
                "Prod db instance",
                "--instance-type",
                "redis_enterprise",
                "--cluster-id",
                "cluster-prod-1",
            ],
        )

    assert result.exit_code == 0
    assert "Created instance" in result.output
    saved_instances = mock_save.call_args[0][0]
    assert len(saved_instances) == 1
    assert saved_instances[0].id == "redis-production-01HXTESTINSTANCEID123456789"
    assert saved_instances[0].cluster_id == "cluster-prod-1"


def test_instance_create_rejects_missing_cluster_id_reference():
    runner = CliRunner()

    with (
        patch.object(core_instances, "get_instances", new=AsyncMock(return_value=[])),
        patch.object(core_clusters, "get_cluster_by_id", new=AsyncMock(return_value=None)),
    ):
        result = runner.invoke(
            instance,
            [
                "create",
                "--name",
                "prod-db",
                "--connection-url",
                "redis://localhost:6380/0",
                "--environment",
                "production",
                "--usage",
                "cache",
                "--description",
                "Prod db instance",
                "--instance-type",
                "redis_enterprise",
                "--cluster-id",
                "cluster-does-not-exist",
            ],
        )

    assert result.exit_code == 0
    assert "Cluster with ID 'cluster-does-not-exist' not found" in result.output


def test_instance_create_rejects_incompatible_instance_and_cluster_types():
    runner = CliRunner()
    linked_cluster = core_clusters.RedisCluster(
        id="cluster-dev-1",
        name="dev-oss-cluster",
        cluster_type=core_clusters.RedisClusterType.oss_cluster,
        environment="development",
        description="Development oss cluster",
    )

    with (
        patch.object(core_instances, "get_instances", new=AsyncMock(return_value=[])),
        patch.object(
            core_clusters, "get_cluster_by_id", new=AsyncMock(return_value=linked_cluster)
        ),
    ):
        result = runner.invoke(
            instance,
            [
                "create",
                "--name",
                "prod-db",
                "--connection-url",
                "redis://localhost:6380/0",
                "--environment",
                "production",
                "--usage",
                "cache",
                "--description",
                "Prod db instance",
                "--instance-type",
                "redis_enterprise",
                "--cluster-id",
                "cluster-dev-1",
            ],
        )

    assert result.exit_code == 0
    assert "is incompatible with cluster_type 'oss_cluster'" in result.output


def test_instance_create_warns_when_deprecated_admin_fields_are_used():
    runner = CliRunner()

    with (
        patch.object(core_instances, "get_instances", new=AsyncMock(return_value=[])),
        patch.object(core_instances, "save_instances", new=AsyncMock(return_value=True)),
    ):
        result = runner.invoke(
            instance,
            [
                "create",
                "--name",
                "prod-db",
                "--connection-url",
                "redis://localhost:6380/0",
                "--environment",
                "production",
                "--usage",
                "cache",
                "--description",
                "Prod db instance",
                "--instance-type",
                "redis_enterprise",
                "--admin-url",
                "https://cluster.example.com:9443",
                "--admin-username",
                "admin@example.com",
                "--admin-password",
                "secret",
            ],
        )

    assert result.exit_code == 0
    assert "DEPRECATED" in result.output
    assert "admin_*" in result.output


def test_instance_update_rejects_incompatible_cluster_type():
    runner = CliRunner()

    current_instance = core_instances.RedisInstance(
        id="redis-prod-1",
        name="prod-db",
        connection_url="redis://localhost:6380/0",
        environment="production",
        usage="cache",
        description="Prod db instance",
        instance_type="redis_enterprise",
    )
    linked_cluster = core_clusters.RedisCluster(
        id="cluster-dev-1",
        name="dev-oss-cluster",
        cluster_type=core_clusters.RedisClusterType.oss_cluster,
        environment="development",
        description="Development oss cluster",
    )

    with (
        patch.object(
            core_instances, "get_instances", new=AsyncMock(return_value=[current_instance])
        ),
        patch.object(
            core_clusters, "get_cluster_by_id", new=AsyncMock(return_value=linked_cluster)
        ),
    ):
        result = runner.invoke(
            instance,
            [
                "update",
                "redis-prod-1",
                "--cluster-id",
                "cluster-dev-1",
            ],
        )

    assert result.exit_code == 0
    assert "is incompatible with cluster_type 'oss_cluster'" in result.output
