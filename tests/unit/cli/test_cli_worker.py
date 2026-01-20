"""Unit tests for worker CLI command."""

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from redis_sre_agent.cli.worker import start, status, stop, worker


@pytest.fixture
def cli_runner():
    """Create a CLI runner for testing."""
    return CliRunner()


class TestWorkerGroup:
    """Tests for the worker command group."""

    def test_worker_help_shows_subcommands(self, cli_runner):
        """Test that worker help shows all subcommands."""
        result = cli_runner.invoke(worker, ["--help"])

        assert result.exit_code == 0
        assert "start" in result.output
        assert "status" in result.output
        assert "stop" in result.output
        assert "Manage the Docket worker" in result.output


class TestWorkerStartCommand:
    """Tests for the worker start subcommand."""

    def test_start_help_shows_options(self, cli_runner):
        """Test that start help shows all options."""
        result = cli_runner.invoke(worker, ["start", "--help"])

        assert result.exit_code == 0
        assert "--concurrency" in result.output or "-c" in result.output
        assert "Number of concurrent tasks" in result.output

    def test_start_concurrency_option_exists(self, cli_runner):
        """Test that concurrency option exists."""
        result = cli_runner.invoke(worker, ["start", "--help"])

        assert result.exit_code == 0
        # Verify the option exists
        assert "--concurrency" in result.output or "-c" in result.output
        assert "INTEGER" in result.output

    def test_start_requires_redis_url(self, cli_runner):
        """Test that start requires Redis URL."""
        mock_settings = MagicMock()
        mock_settings.redis_url = None

        with patch(
            "redis_sre_agent.cli.worker.settings",
            mock_settings,
        ):
            result = cli_runner.invoke(worker, ["start"])

            # Should fail without Redis URL
            assert result.exit_code != 0 or "Redis URL not configured" in result.output


class TestWorkerStatusCommand:
    """Tests for the worker status subcommand."""

    def test_status_help_shows_options(self, cli_runner):
        """Test that status help shows verbose option."""
        result = cli_runner.invoke(worker, ["status", "--help"])

        assert result.exit_code == 0
        assert "--verbose" in result.output or "-v" in result.output
        assert "Check the status" in result.output

    def test_status_requires_redis_url(self, cli_runner):
        """Test that status requires Redis URL."""
        mock_settings = MagicMock()
        mock_settings.redis_url = None

        with patch(
            "redis_sre_agent.cli.worker.settings",
            mock_settings,
        ):
            result = cli_runner.invoke(worker, ["status"])

            # Should fail without Redis URL
            assert result.exit_code != 0 or "Redis URL not configured" in result.output


class TestWorkerStopCommand:
    """Tests for the worker stop subcommand."""

    def test_stop_help(self, cli_runner):
        """Test that stop help shows description."""
        result = cli_runner.invoke(worker, ["stop", "--help"])

        assert result.exit_code == 0
        assert "Stop the Docket worker" in result.output

    def test_stop_requires_redis_url(self, cli_runner):
        """Test that stop requires Redis URL."""
        mock_settings = MagicMock()
        mock_settings.redis_url = None

        with patch(
            "redis_sre_agent.cli.worker.settings",
            mock_settings,
        ):
            result = cli_runner.invoke(worker, ["stop"])

            # Should fail without Redis URL
            assert result.exit_code != 0 or "Redis URL not configured" in result.output
