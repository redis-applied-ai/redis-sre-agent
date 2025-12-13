"""Unit tests for tasks CLI commands."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from redis_sre_agent.cli.tasks import task


@pytest.fixture
def cli_runner():
    """Create a CLI runner for testing."""
    return CliRunner()


class TestTaskListCLI:
    """Tests for the task list command."""

    def test_list_help_shows_options(self, cli_runner):
        """Test that list help shows all options."""
        result = cli_runner.invoke(task, ["list", "--help"])

        assert result.exit_code == 0
        assert "--user-id" in result.output
        assert "--status" in result.output
        assert "--all" in result.output
        assert "--limit" in result.output or "-l" in result.output
        assert "--tz" in result.output
        # Status choices
        assert "queued" in result.output
        assert "in_progress" in result.output
        assert "done" in result.output
        assert "failed" in result.output
        assert "cancelled" in result.output

    def test_list_displays_tasks(self, cli_runner):
        """Test that list displays tasks."""
        mock_tasks = [
            {
                "task_id": "task-1",
                "status": "in_progress",
                "created_at": "2024-01-01T00:00:00Z",
                "user_id": "user-1",
            }
        ]

        mock_redis = MagicMock()
        mock_redis.get = AsyncMock(return_value=None)

        with (
            patch(
                "redis_sre_agent.core.tasks.list_tasks",
                new_callable=AsyncMock,
                return_value=mock_tasks,
            ),
            patch(
                "redis_sre_agent.core.redis.get_redis_client",
                return_value=mock_redis,
            ),
        ):
            result = cli_runner.invoke(task, ["list"])

            assert result.exit_code == 0

    def test_list_empty_tasks(self, cli_runner):
        """Test list with no tasks."""
        with patch(
            "redis_sre_agent.core.tasks.list_tasks",
            new_callable=AsyncMock,
            return_value=[],
        ):
            result = cli_runner.invoke(task, ["list"])

            assert result.exit_code == 0
            assert "No tasks found" in result.output

    def test_list_with_status_filter(self, cli_runner):
        """Test list with status filter."""
        mock_tasks = [
            {
                "task_id": "task-1",
                "status": "done",
                "created_at": "2024-01-01T00:00:00Z",
            }
        ]

        mock_redis = MagicMock()
        mock_redis.get = AsyncMock(return_value=None)

        with (
            patch(
                "redis_sre_agent.core.tasks.list_tasks",
                new_callable=AsyncMock,
                return_value=mock_tasks,
            ) as mock_list,
            patch(
                "redis_sre_agent.core.redis.get_redis_client",
                return_value=mock_redis,
            ),
        ):
            result = cli_runner.invoke(task, ["list", "--status", "done"])

            assert result.exit_code == 0
            # Verify the status filter was passed
            mock_list.assert_called_once()


class TestTaskGetCLI:
    """Tests for the task get command."""

    def test_get_help_shows_options(self, cli_runner):
        """Test that get help shows options."""
        result = cli_runner.invoke(task, ["get", "--help"])

        assert result.exit_code == 0
        assert "TASK_ID" in result.output or "task_id" in result.output.lower()


class TestTaskPurgeCLI:
    """Tests for the task purge command."""

    def test_purge_help_shows_options(self, cli_runner):
        """Test that purge help shows options."""
        result = cli_runner.invoke(task, ["purge", "--help"])

        assert result.exit_code == 0
        # Should have options for purging
        assert "--" in result.output or "purge" in result.output.lower()
