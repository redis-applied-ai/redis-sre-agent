"""Tests for the `instance` CLI command group."""

from unittest.mock import AsyncMock, patch

from click.testing import CliRunner

from redis_sre_agent.cli.instance import instance
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
