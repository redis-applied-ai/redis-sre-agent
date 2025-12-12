"""Unit tests for worker CLI command."""

import pytest
from click.testing import CliRunner
from unittest.mock import patch, AsyncMock, MagicMock

from redis_sre_agent.cli.worker import worker


@pytest.fixture
def cli_runner():
    """Create a CLI runner for testing."""
    return CliRunner()


class TestWorkerCLI:
    """Tests for the worker command."""

    def test_worker_help_shows_options(self, cli_runner):
        """Test that worker help shows all options."""
        result = cli_runner.invoke(worker, ["--help"])

        assert result.exit_code == 0
        assert "--concurrency" in result.output or "-c" in result.output
        assert "Number of concurrent tasks" in result.output

    def test_worker_concurrency_option_exists(self, cli_runner):
        """Test that concurrency option exists."""
        result = cli_runner.invoke(worker, ["--help"])

        assert result.exit_code == 0
        # Verify the option exists
        assert "--concurrency" in result.output or "-c" in result.output
        assert "INTEGER" in result.output

    def test_worker_requires_redis_url(self, cli_runner):
        """Test that worker requires Redis URL."""
        mock_settings = MagicMock()
        mock_settings.redis_url = None

        with patch(
            "redis_sre_agent.cli.worker.settings",
            mock_settings,
        ):
            result = cli_runner.invoke(worker)

            # Should fail without Redis URL
            assert result.exit_code != 0 or "Redis URL not configured" in result.output
