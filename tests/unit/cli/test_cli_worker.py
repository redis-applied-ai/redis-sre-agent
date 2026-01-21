"""Unit tests for worker CLI command."""

import socket
from unittest.mock import MagicMock, patch

import psutil
import pytest
from click.testing import CliRunner

from redis_sre_agent.cli.worker import (
    _validate_worker_process,
    start,
    status,
    stop,
    worker,
)


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


class TestValidateWorkerProcess:
    """Tests for the _validate_worker_process security function."""

    def test_rejects_worker_name_without_separator(self):
        """Test that worker names without # separator are rejected."""
        is_valid, reason = _validate_worker_process(1234, "malicious-name")

        assert is_valid is False
        assert "missing '#' separator" in reason

    def test_rejects_hostname_mismatch(self):
        """Test that workers from different hosts are rejected.

        This prevents an attacker from registering a worker on one host
        to kill processes on a different host.
        """
        current_hostname = socket.gethostname()
        fake_hostname = "attacker-machine"

        # Ensure our test is meaningful (hostnames are different)
        assert fake_hostname != current_hostname

        is_valid, reason = _validate_worker_process(1234, f"{fake_hostname}#1234")

        assert is_valid is False
        assert "does not match this machine" in reason

    def test_rejects_nonexistent_process(self):
        """Test that non-existent PIDs are rejected."""
        current_hostname = socket.gethostname()
        # Use a very high PID that's unlikely to exist
        fake_pid = 999999999

        is_valid, reason = _validate_worker_process(fake_pid, f"{current_hostname}#{fake_pid}")

        assert is_valid is False
        assert "does not exist" in reason

    def test_rejects_non_python_process(self):
        """Test that non-Python processes are rejected.

        This prevents killing arbitrary system processes even if they
        happen to have a matching PID.
        """
        current_hostname = socket.gethostname()

        # Mock a process that exists but is not Python
        mock_proc = MagicMock()
        mock_proc.name.return_value = "nginx"
        mock_proc.cmdline.return_value = ["/usr/sbin/nginx", "-g", "daemon off;"]

        with patch("redis_sre_agent.cli.worker.psutil.Process", return_value=mock_proc):
            is_valid, reason = _validate_worker_process(1234, f"{current_hostname}#1234")

        assert is_valid is False
        assert "not a Python process" in reason

    def test_rejects_python_process_without_worker_indicators(self):
        """Test that Python processes without worker indicators are rejected.

        This prevents killing unrelated Python processes.
        """
        current_hostname = socket.gethostname()

        # Mock a Python process that's not a worker
        mock_proc = MagicMock()
        mock_proc.name.return_value = "python3"
        mock_proc.cmdline.return_value = ["/usr/bin/python3", "/some/random/script.py"]

        with patch("redis_sre_agent.cli.worker.psutil.Process", return_value=mock_proc):
            is_valid, reason = _validate_worker_process(1234, f"{current_hostname}#1234")

        assert is_valid is False
        assert "does not match expected worker pattern" in reason

    def test_accepts_valid_worker_process(self):
        """Test that valid worker processes are accepted."""
        current_hostname = socket.gethostname()

        # Mock a valid worker process
        mock_proc = MagicMock()
        mock_proc.name.return_value = "python3"
        mock_proc.cmdline.return_value = [
            "/usr/bin/python3",
            "-m",
            "redis_sre_agent.cli",
            "worker",
            "start",
        ]

        with patch("redis_sre_agent.cli.worker.psutil.Process", return_value=mock_proc):
            is_valid, reason = _validate_worker_process(1234, f"{current_hostname}#1234")

        assert is_valid is True
        assert "validated as legitimate worker" in reason

    def test_accepts_docket_indicator_in_cmdline(self):
        """Test that 'docket' in command line is accepted as valid indicator."""
        current_hostname = socket.gethostname()

        mock_proc = MagicMock()
        mock_proc.name.return_value = "python"
        mock_proc.cmdline.return_value = ["/usr/bin/python", "-m", "docket.worker"]

        with patch("redis_sre_agent.cli.worker.psutil.Process", return_value=mock_proc):
            is_valid, reason = _validate_worker_process(1234, f"{current_hostname}#1234")

        assert is_valid is True

    def test_handles_access_denied_on_process_info(self):
        """Test handling of AccessDenied when accessing process info."""
        current_hostname = socket.gethostname()

        with patch(
            "redis_sre_agent.cli.worker.psutil.Process",
            side_effect=psutil.AccessDenied(1234),
        ):
            is_valid, reason = _validate_worker_process(1234, f"{current_hostname}#1234")

        assert is_valid is False
        assert "permission denied" in reason

    def test_handles_access_denied_on_cmdline(self):
        """Test handling of AccessDenied when accessing cmdline."""
        current_hostname = socket.gethostname()

        mock_proc = MagicMock()
        mock_proc.name.return_value = "python3"
        mock_proc.cmdline.side_effect = psutil.AccessDenied(1234)

        with patch("redis_sre_agent.cli.worker.psutil.Process", return_value=mock_proc):
            is_valid, reason = _validate_worker_process(1234, f"{current_hostname}#1234")

        assert is_valid is False
        assert "Cannot verify process command line" in reason
