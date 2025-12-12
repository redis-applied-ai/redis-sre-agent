"""Unit tests for runbook CLI commands."""

import pytest
from click.testing import CliRunner

from redis_sre_agent.cli.runbook import runbook


@pytest.fixture
def cli_runner():
    """Create a CLI runner for testing."""
    return CliRunner()


class TestRunbookGenerateCLI:
    """Tests for the runbook generate command."""

    def test_generate_help_shows_options(self, cli_runner):
        """Test that generate help shows all options."""
        result = cli_runner.invoke(runbook, ["generate", "--help"])

        assert result.exit_code == 0
        assert "--severity" in result.output or "-s" in result.output
        assert "--category" in result.output or "-c" in result.output
        assert "--output-file" in result.output or "-o" in result.output
        assert "--requirements" in result.output or "-r" in result.output
        assert "--max-iterations" in result.output
        assert "--auto-save" in result.output
        assert "critical" in result.output
        assert "warning" in result.output
        assert "info" in result.output

    def test_generate_requires_topic_and_description(self, cli_runner):
        """Test that generate requires topic and scenario_description."""
        result = cli_runner.invoke(runbook, ["generate"])

        assert result.exit_code != 0
        assert "Missing argument" in result.output or "Usage:" in result.output


class TestRunbookEvaluateCLI:
    """Tests for the runbook evaluate command."""

    def test_evaluate_help_shows_options(self, cli_runner):
        """Test that evaluate help shows all options."""
        result = cli_runner.invoke(runbook, ["evaluate", "--help"])

        assert result.exit_code == 0
        assert "--input-dir" in result.output or "-i" in result.output
        assert "--output-file" in result.output or "-o" in result.output
        # Default value may not be shown in help, just check the option exists
        assert "Directory containing runbook" in result.output

    def test_evaluate_with_nonexistent_dir(self, cli_runner):
        """Test evaluate with non-existent directory."""
        result = cli_runner.invoke(runbook, ["evaluate", "--input-dir", "/nonexistent/path"])

        assert result.exit_code != 0
        # Click should report the path doesn't exist
        assert "does not exist" in result.output or "Error" in result.output
