"""Tests for the `cluster` CLI command group."""

import os
from unittest.mock import AsyncMock, patch

from click.testing import CliRunner

from redis_sre_agent.cli.cluster import cluster
from redis_sre_agent.cli.main import main
from redis_sre_agent.core import clusters as core_clusters
from redis_sre_agent.core.migrations.instances_to_clusters import (
    InstanceToClusterMigrationSummary,
)


def _enterprise_cluster(cluster_id: str = "cluster-prod-1") -> core_clusters.RedisCluster:
    return core_clusters.RedisCluster(
        id=cluster_id,
        name="prod-enterprise",
        cluster_type=core_clusters.RedisClusterType.redis_enterprise,
        environment="production",
        description="Production enterprise cluster",
        admin_url="https://cluster.example.com:9443",
        admin_username="admin@example.com",
        admin_password="secret",
    )


def test_cluster_cli_help_lists_subcommands():
    runner = CliRunner()
    result = runner.invoke(cluster, ["--help"])

    assert result.exit_code == 0
    assert "Commands:" in result.output
    for cmd in ["list", "get", "create", "update", "delete", "backfill-instance-links"]:
        assert cmd in result.output


def test_cluster_command_is_registered_in_main_cli():
    runner = CliRunner()
    result = runner.invoke(main, ["cluster", "--help"])

    assert result.exit_code == 0
    assert "Manage Redis clusters" in result.output


def test_clusters_list_json_with_item():
    runner = CliRunner()
    item = _enterprise_cluster()

    with patch.object(core_clusters, "get_clusters", new=AsyncMock(return_value=[item])):
        result = runner.invoke(cluster, ["list", "--json"])

    assert result.exit_code == 0
    assert "cluster-prod-1" in result.output
    assert "prod-enterprise" in result.output
    assert '"admin_password": "***"' in result.output


def test_cluster_create_redis_enterprise_success():
    runner = CliRunner()

    with (
        patch.object(core_clusters, "get_clusters", new=AsyncMock(return_value=[])),
        patch.object(core_clusters, "save_clusters", new=AsyncMock(return_value=True)) as mock_save,
        patch(
            "redis_sre_agent.cli.cluster.ULID",
            return_value="01HXTESTCLUSTERID1234567890",
        ),
    ):
        result = runner.invoke(
            cluster,
            [
                "create",
                "--name",
                "prod-enterprise",
                "--cluster-type",
                "redis_enterprise",
                "--environment",
                "production",
                "--description",
                "Production enterprise cluster",
                "--admin-url",
                "https://cluster.example.com:9443",
                "--admin-username",
                "admin@example.com",
                "--admin-password",
                "secret",
            ],
        )

    assert result.exit_code == 0
    assert "Created cluster" in result.output
    saved_clusters = mock_save.call_args[0][0]
    assert len(saved_clusters) == 1
    assert saved_clusters[0].id == "cluster-production-01HXTESTCLUSTERID1234567890"
    assert saved_clusters[0].cluster_type == core_clusters.RedisClusterType.redis_enterprise


def test_cluster_create_redis_enterprise_success_with_env_defaults():
    runner = CliRunner()

    with (
        patch.dict(
            os.environ,
            {
                "REDIS_ENTERPRISE_ADMIN_URL": "https://env-cluster.example.com:9443",
                "REDIS_ENTERPRISE_ADMIN_USERNAME": "env-admin@example.com",
                "REDIS_ENTERPRISE_ADMIN_PASSWORD": "env-secret",
            },
            clear=False,
        ),
        patch.object(core_clusters, "get_clusters", new=AsyncMock(return_value=[])),
        patch.object(core_clusters, "save_clusters", new=AsyncMock(return_value=True)) as mock_save,
    ):
        result = runner.invoke(
            cluster,
            [
                "create",
                "--name",
                "prod-enterprise",
                "--cluster-type",
                "redis_enterprise",
                "--environment",
                "production",
                "--description",
                "Production enterprise cluster",
            ],
        )

    assert result.exit_code == 0
    assert "Created cluster" in result.output
    saved_clusters = mock_save.call_args[0][0]
    assert len(saved_clusters) == 1
    assert saved_clusters[0].admin_url == "https://env-cluster.example.com:9443"
    assert saved_clusters[0].admin_username == "env-admin@example.com"
    assert saved_clusters[0].admin_password is not None
    assert saved_clusters[0].admin_password.get_secret_value() == "env-secret"


def test_cluster_create_redis_enterprise_missing_admin_fields_shows_env_hint():
    runner = CliRunner()

    with (
        patch.dict(
            os.environ,
            {
                "REDIS_ENTERPRISE_ADMIN_URL": "",
                "REDIS_ENTERPRISE_ADMIN_USERNAME": "",
                "REDIS_ENTERPRISE_ADMIN_PASSWORD": "",
            },
            clear=False,
        ),
        patch.object(core_clusters, "get_clusters", new=AsyncMock(return_value=[])),
    ):
        result = runner.invoke(
            cluster,
            [
                "create",
                "--name",
                "prod-enterprise",
                "--cluster-type",
                "redis_enterprise",
                "--environment",
                "production",
                "--description",
                "Production enterprise cluster",
            ],
        )

    assert result.exit_code == 0
    assert "requires admin_url, admin_username, and admin_password" in result.output
    assert "REDIS_ENTERPRISE_ADMIN_URL" in result.output


def test_cluster_create_rejects_non_enterprise_with_admin_credentials():
    runner = CliRunner()

    with patch.object(core_clusters, "get_clusters", new=AsyncMock(return_value=[])):
        result = runner.invoke(
            cluster,
            [
                "create",
                "--name",
                "dev-oss-cluster",
                "--cluster-type",
                "oss_cluster",
                "--environment",
                "development",
                "--description",
                "Development OSS cluster",
                "--admin-url",
                "https://cluster.example.com:9443",
            ],
        )

    assert result.exit_code == 0
    assert "only valid for cluster_type=redis_enterprise" in result.output


def test_cluster_update_rejects_invalid_enterprise_credentials():
    runner = CliRunner()
    item = _enterprise_cluster()

    with patch.object(core_clusters, "get_clusters", new=AsyncMock(return_value=[item])):
        result = runner.invoke(
            cluster,
            [
                "update",
                item.id,
                "--admin-password",
                "",
            ],
        )

    assert result.exit_code == 0
    assert "requires admin_url, admin_username, and admin_password" in result.output


def test_cluster_backfill_instance_links_json_output():
    runner = CliRunner()
    summary = InstanceToClusterMigrationSummary(
        source="unit_test",
        dry_run=True,
        run_id="run-1",
        started_at="2026-03-04T00:00:00+00:00",
        finished_at="2026-03-04T00:00:01+00:00",
        scanned=2,
        eligible=1,
        clusters_created=1,
        clusters_reused=0,
        instances_linked=1,
    )

    with patch(
        "redis_sre_agent.cli.cluster.run_instances_to_clusters_migration",
        new=AsyncMock(return_value=summary),
    ) as mock_backfill:
        result = runner.invoke(cluster, ["backfill-instance-links", "--dry-run", "--json"])

    assert result.exit_code == 0
    assert '"dry_run": true' in result.output
    assert '"scanned": 2' in result.output
    assert '"clusters_created": 1' in result.output
    mock_backfill.assert_awaited_once()
