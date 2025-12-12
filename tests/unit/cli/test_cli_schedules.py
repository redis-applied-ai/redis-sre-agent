"""Unit tests for schedules CLI commands."""

from unittest.mock import AsyncMock, patch

import pytest
from click.testing import CliRunner

from redis_sre_agent.cli.schedules import schedule


@pytest.fixture
def cli_runner():
    """Create a CLI runner for testing."""
    return CliRunner()


class TestScheduleListCLI:
    """Tests for the schedule list command."""

    def test_list_help_shows_options(self, cli_runner):
        """Test that list help shows all options."""
        result = cli_runner.invoke(schedule, ["list", "--help"])

        assert result.exit_code == 0
        assert "--json" in result.output
        assert "--tz" in result.output
        assert "--limit" in result.output or "-l" in result.output

    def test_list_displays_schedules(self, cli_runner):
        """Test that list displays schedules."""
        mock_schedules = [
            {
                "id": "sched-1",
                "name": "Test Schedule",
                "enabled": True,
                "interval_type": "hours",
                "interval_value": 1,
                "next_run": "2024-01-01T00:00:00Z",
                "last_run": "2023-12-31T23:00:00Z",
            }
        ]

        with patch(
            "redis_sre_agent.core.schedules.list_schedules",
            new_callable=AsyncMock,
            return_value=mock_schedules,
        ):
            result = cli_runner.invoke(schedule, ["list"])

            assert result.exit_code == 0
            # Should show table with schedules
            assert "Test Schedule" in result.output or "Schedules" in result.output

    def test_list_json_output(self, cli_runner):
        """Test that --json flag outputs JSON."""
        mock_schedules = [
            {
                "id": "sched-1",
                "name": "Test Schedule",
                "enabled": True,
                "interval_type": "hours",
                "interval_value": 1,
            }
        ]

        with patch(
            "redis_sre_agent.core.schedules.list_schedules",
            new_callable=AsyncMock,
            return_value=mock_schedules,
        ):
            result = cli_runner.invoke(schedule, ["list", "--json"])

            assert result.exit_code == 0
            import json

            output_data = json.loads(result.output)
            assert isinstance(output_data, list)
            assert len(output_data) == 1
            assert output_data[0]["name"] == "Test Schedule"

    def test_list_empty_schedules(self, cli_runner):
        """Test list with no schedules."""
        with patch(
            "redis_sre_agent.core.schedules.list_schedules",
            new_callable=AsyncMock,
            return_value=[],
        ):
            result = cli_runner.invoke(schedule, ["list"])

            assert result.exit_code == 0
            assert "No schedules found" in result.output


class TestScheduleGetCLI:
    """Tests for the schedule get command."""

    def test_get_help_shows_options(self, cli_runner):
        """Test that get help shows options."""
        result = cli_runner.invoke(schedule, ["get", "--help"])

        assert result.exit_code == 0
        assert "SCHEDULE_ID" in result.output or "schedule_id" in result.output.lower()


class TestScheduleCreateCLI:
    """Tests for the schedule create command."""

    def test_create_help_shows_options(self, cli_runner):
        """Test that create help shows all options."""
        result = cli_runner.invoke(schedule, ["create", "--help"])

        assert result.exit_code == 0
        assert "--name" in result.output
        assert "--instance" in result.output or "instance" in result.output.lower()


class TestScheduleEnableDisableCLI:
    """Tests for schedule enable/disable commands."""

    def test_enable_help(self, cli_runner):
        """Test that enable help is available."""
        result = cli_runner.invoke(schedule, ["enable", "--help"])

        assert result.exit_code == 0
        assert "SCHEDULE_ID" in result.output or "schedule_id" in result.output.lower()

    def test_disable_help(self, cli_runner):
        """Test that disable help is available."""
        result = cli_runner.invoke(schedule, ["disable", "--help"])

        assert result.exit_code == 0
        assert "SCHEDULE_ID" in result.output or "schedule_id" in result.output.lower()


class TestScheduleDeleteCLI:
    """Tests for the schedule delete command."""

    def test_delete_help(self, cli_runner):
        """Test that delete help is available."""
        result = cli_runner.invoke(schedule, ["delete", "--help"])

        assert result.exit_code == 0
        assert "SCHEDULE_ID" in result.output or "schedule_id" in result.output.lower()


class TestScheduleRunNowCLI:
    """Tests for the schedule run-now command."""

    def test_run_now_help(self, cli_runner):
        """Test that run-now help is available."""
        result = cli_runner.invoke(schedule, ["run-now", "--help"])

        assert result.exit_code == 0
        assert "SCHEDULE_ID" in result.output or "schedule_id" in result.output.lower()
