"""Tests for the `cache` CLI command group."""

from unittest.mock import AsyncMock, patch

from click.testing import CliRunner

from redis_sre_agent.cli.cache import cache


class TestCacheCLI:
    """Tests for cache CLI commands."""

    def test_cache_cli_help_lists_subcommands(self):
        """Test that cache --help shows available subcommands."""
        runner = CliRunner()
        result = runner.invoke(cache, ["--help"])

        assert result.exit_code == 0
        assert "Commands:" in result.output
        # Core subcommands
        for cmd in ["clear", "stats"]:
            assert cmd in result.output

    def test_cache_clear_requires_instance(self):
        """Test that cache clear requires --instance flag."""
        runner = CliRunner()
        result = runner.invoke(cache, ["clear"])

        # Should fail or warn without instance
        assert result.exit_code != 0 or "instance" in result.output.lower()

    def test_cache_clear_by_instance(self):
        """Test clearing cache for a specific instance."""
        runner = CliRunner()

        mock_cache = AsyncMock()
        mock_cache.clear = AsyncMock(return_value=5)  # 5 keys deleted

        with patch("redis_sre_agent.cli.cache.get_tool_cache", return_value=mock_cache):
            result = runner.invoke(cache, ["clear", "--instance", "test-instance-123"])

        assert result.exit_code == 0
        assert "5" in result.output or "cleared" in result.output.lower()

    def test_cache_clear_all_instances(self):
        """Test clearing cache for all instances with --all flag."""
        runner = CliRunner()

        mock_cache = AsyncMock()
        mock_cache.clear_all = AsyncMock(return_value=10)

        with patch("redis_sre_agent.cli.cache.get_tool_cache", return_value=mock_cache):
            result = runner.invoke(cache, ["clear", "--all"])

        assert result.exit_code == 0
        assert "10" in result.output or "cleared" in result.output.lower()

    def test_cache_stats_by_instance(self):
        """Test getting cache stats for a specific instance."""
        runner = CliRunner()

        mock_stats = {
            "instance_id": "test-instance-123",
            "cached_keys": 15,
            "enabled": True,
        }
        mock_cache = AsyncMock()
        mock_cache.stats = AsyncMock(return_value=mock_stats)

        with patch("redis_sre_agent.cli.cache.get_tool_cache", return_value=mock_cache):
            result = runner.invoke(cache, ["stats", "--instance", "test-instance-123"])

        assert result.exit_code == 0
        assert "15" in result.output or "cached" in result.output.lower()

    def test_cache_stats_json_output(self):
        """Test getting cache stats as JSON."""
        runner = CliRunner()

        mock_stats = {
            "instance_id": "test-instance-123",
            "cached_keys": 15,
            "enabled": True,
        }
        mock_cache = AsyncMock()
        mock_cache.stats = AsyncMock(return_value=mock_stats)

        with patch("redis_sre_agent.cli.cache.get_tool_cache", return_value=mock_cache):
            result = runner.invoke(cache, ["stats", "--instance", "test-instance-123", "--json"])

        assert result.exit_code == 0
        assert "cached_keys" in result.output
        assert "15" in result.output

    def test_cache_stats_all_instances(self):
        """Test getting cache stats across all instances."""
        runner = CliRunner()

        mock_stats = {
            "total_keys": 50,
            "instances": ["inst-1", "inst-2"],
        }
        mock_cache = AsyncMock()
        mock_cache.stats_all = AsyncMock(return_value=mock_stats)

        with patch("redis_sre_agent.cli.cache.get_tool_cache", return_value=mock_cache):
            result = runner.invoke(cache, ["stats", "--all"])

        assert result.exit_code == 0
        assert "50" in result.output or "total" in result.output.lower()


class TestCacheInMainCLI:
    """Test that cache command is registered in main CLI."""

    def test_cache_in_main_cli(self):
        """Test that cache command is accessible from main CLI."""
        from redis_sre_agent.cli.main import main

        runner = CliRunner()
        result = runner.invoke(main, ["cache", "--help"])

        assert result.exit_code == 0
        assert "clear" in result.output
        assert "stats" in result.output
