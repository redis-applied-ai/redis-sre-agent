"""Tests for the `index` CLI commands."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from redis_sre_agent.cli.index import index


@pytest.fixture
def cli_runner():
    """Click CLI test runner."""
    return CliRunner()


class TestIndexListCLI:
    """Test index list CLI command."""

    def test_list_help_shows_options(self, cli_runner):
        """Test that list command shows expected options in help."""
        result = cli_runner.invoke(index, ["list", "--help"])

        assert result.exit_code == 0
        assert "--json" in result.output

    def test_list_displays_indices(self, cli_runner):
        """Test that list command displays indices."""
        mock_index = MagicMock()
        mock_index.exists = AsyncMock(return_value=True)
        mock_index._redis_client = MagicMock()
        mock_index._redis_client.execute_command = AsyncMock(
            return_value=[b"num_docs", b"100"]
        )

        with patch(
            "redis_sre_agent.core.redis.get_knowledge_index",
            new_callable=AsyncMock,
            return_value=mock_index,
        ), patch(
            "redis_sre_agent.core.redis.get_schedules_index",
            new_callable=AsyncMock,
            return_value=mock_index,
        ), patch(
            "redis_sre_agent.core.redis.get_threads_index",
            new_callable=AsyncMock,
            return_value=mock_index,
        ), patch(
            "redis_sre_agent.core.redis.get_tasks_index",
            new_callable=AsyncMock,
            return_value=mock_index,
        ), patch(
            "redis_sre_agent.core.redis.get_instances_index",
            new_callable=AsyncMock,
            return_value=mock_index,
        ):
            result = cli_runner.invoke(index, ["list"])

            assert result.exit_code == 0
            # Should show table with indices
            assert "knowledge" in result.output or "RediSearch" in result.output

    def test_list_json_output(self, cli_runner):
        """Test that --json flag outputs JSON."""
        mock_index = MagicMock()
        mock_index.exists = AsyncMock(return_value=True)
        mock_index._redis_client = MagicMock()
        mock_index._redis_client.execute_command = AsyncMock(
            return_value=[b"num_docs", b"50"]
        )

        with patch(
            "redis_sre_agent.core.redis.get_knowledge_index",
            new_callable=AsyncMock,
            return_value=mock_index,
        ), patch(
            "redis_sre_agent.core.redis.get_schedules_index",
            new_callable=AsyncMock,
            return_value=mock_index,
        ), patch(
            "redis_sre_agent.core.redis.get_threads_index",
            new_callable=AsyncMock,
            return_value=mock_index,
        ), patch(
            "redis_sre_agent.core.redis.get_tasks_index",
            new_callable=AsyncMock,
            return_value=mock_index,
        ), patch(
            "redis_sre_agent.core.redis.get_instances_index",
            new_callable=AsyncMock,
            return_value=mock_index,
        ):
            result = cli_runner.invoke(index, ["list", "--json"])

            assert result.exit_code == 0
            import json

            output_data = json.loads(result.output)
            assert isinstance(output_data, list)
            assert len(output_data) == 5  # 5 indices


class TestIndexRecreateCLI:
    """Test index recreate CLI command."""

    def test_recreate_help_shows_options(self, cli_runner):
        """Test that recreate command shows expected options in help."""
        result = cli_runner.invoke(index, ["recreate", "--help"])

        assert result.exit_code == 0
        assert "--index-name" in result.output
        assert "--yes" in result.output
        assert "-y" in result.output
        assert "--json" in result.output
        assert "knowledge" in result.output
        assert "schedules" in result.output
        assert "all" in result.output

    def test_recreate_requires_confirmation(self, cli_runner):
        """Test that recreate requires confirmation without -y."""
        result = cli_runner.invoke(index, ["recreate"], input="n\n")

        assert result.exit_code == 0
        assert "Aborted" in result.output

    def test_recreate_with_yes_flag(self, cli_runner):
        """Test that -y flag skips confirmation."""
        mock_result = {"success": True, "indices": {"knowledge": "recreated"}}

        with patch(
            "redis_sre_agent.core.redis.recreate_indices",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_recreate:
            result = cli_runner.invoke(index, ["recreate", "-y"])

            assert result.exit_code == 0
            mock_recreate.assert_called_once_with(None)  # None means all
            assert "Successfully" in result.output or "✅" in result.output

    def test_recreate_specific_index(self, cli_runner):
        """Test recreating a specific index."""
        mock_result = {"success": True, "indices": {"knowledge": "recreated"}}

        with patch(
            "redis_sre_agent.core.redis.recreate_indices",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_recreate:
            result = cli_runner.invoke(
                index, ["recreate", "--index-name", "knowledge", "-y"]
            )

            assert result.exit_code == 0
            mock_recreate.assert_called_once_with("knowledge")

    def test_recreate_json_output(self, cli_runner):
        """Test that --json flag outputs JSON."""
        mock_result = {"success": True, "indices": {"knowledge": "recreated"}}

        with patch(
            "redis_sre_agent.core.redis.recreate_indices",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            result = cli_runner.invoke(index, ["recreate", "--json"])

            assert result.exit_code == 0
            import json

            output_data = json.loads(result.output)
            assert output_data["success"] is True
