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

    with patch.object(
        core_instances, "get_instance_by_id", new=AsyncMock(return_value=item)
    ):
        result = runner.invoke(instance, ["get", "redis-dev-123", "--json"])

    assert result.exit_code == 0
    assert "extension_data" in result.output
    assert "zendesk_organization_id" in result.output
    assert "12345" in result.output
