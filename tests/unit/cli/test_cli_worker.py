"""Unit tests for worker CLI command."""

import socket
from unittest.mock import MagicMock, patch

import psutil
import pytest
from click.testing import CliRunner

from redis_sre_agent.cli.worker import (
    _validate_worker_process,
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

    def test_status_redis_connected_with_workers(self, cli_runner):
        """Test status shows connected and worker count."""
        mock_settings = MagicMock()
        mock_settings.redis_url.get_secret_value.return_value = "redis://localhost:6379"

        mock_redis = MagicMock()
        mock_worker = MagicMock()
        mock_worker.name = "myhost#1234"
        mock_worker.tasks = ["task1", "task2"]

        with (
            patch("redis_sre_agent.cli.worker.settings", mock_settings),
            patch("redis.Redis.from_url") as mock_from_url,
            patch("redis_sre_agent.cli.worker.asyncio.run", return_value=[mock_worker]),
        ):
            mock_from_url.return_value.__enter__.return_value = mock_redis

            result = cli_runner.invoke(worker, ["status"])

            assert result.exit_code == 0
            assert "Redis: Connected" in result.output
            assert "Workers: 1 active" in result.output
            assert "Worker name: myhost#1234" in result.output
            assert "Registered tasks: 2" in result.output

    def test_status_redis_connected_no_workers(self, cli_runner):
        """Test status shows no active workers when none running."""
        mock_settings = MagicMock()
        mock_settings.redis_url.get_secret_value.return_value = "redis://localhost:6379"

        mock_redis = MagicMock()

        with (
            patch("redis_sre_agent.cli.worker.settings", mock_settings),
            patch("redis.Redis.from_url") as mock_from_url,
            patch("redis_sre_agent.cli.worker.asyncio.run", return_value=[]),
        ):
            mock_from_url.return_value.__enter__.return_value = mock_redis

            result = cli_runner.invoke(worker, ["status"])

            assert result.exit_code == 0
            assert "Redis: Connected" in result.output
            assert "No active workers found" in result.output

    def test_status_verbose_shows_task_names(self, cli_runner):
        """Test status verbose mode shows task names."""
        mock_settings = MagicMock()
        mock_settings.redis_url.get_secret_value.return_value = "redis://localhost:6379"

        mock_redis = MagicMock()
        mock_worker = MagicMock()
        mock_worker.name = "myhost#1234"
        mock_worker.tasks = ["sre_task_one", "sre_task_two", "health_check"]

        with (
            patch("redis_sre_agent.cli.worker.settings", mock_settings),
            patch("redis.Redis.from_url") as mock_from_url,
            patch("redis_sre_agent.cli.worker.asyncio.run", return_value=[mock_worker]),
        ):
            mock_from_url.return_value.__enter__.return_value = mock_redis

            result = cli_runner.invoke(worker, ["status", "--verbose"])

            assert result.exit_code == 0
            assert "sre_task_one" in result.output
            assert "sre_task_two" in result.output
            assert "health_check" in result.output

    def test_status_non_verbose_hides_task_names(self, cli_runner):
        """Test status non-verbose mode does not show task names."""
        mock_settings = MagicMock()
        mock_settings.redis_url.get_secret_value.return_value = "redis://localhost:6379"

        mock_redis = MagicMock()
        mock_worker = MagicMock()
        mock_worker.name = "myhost#1234"
        mock_worker.tasks = ["sre_task_one", "sre_task_two"]

        with (
            patch("redis_sre_agent.cli.worker.settings", mock_settings),
            patch("redis.Redis.from_url") as mock_from_url,
            patch("redis_sre_agent.cli.worker.asyncio.run", return_value=[mock_worker]),
        ):
            mock_from_url.return_value.__enter__.return_value = mock_redis

            result = cli_runner.invoke(worker, ["status"])

            assert result.exit_code == 0
            # Task count is shown, but not individual task names
            assert "Registered tasks: 2" in result.output
            assert "Task name:" not in result.output

    def test_status_multiple_workers(self, cli_runner):
        """Test status shows multiple workers correctly."""
        mock_settings = MagicMock()
        mock_settings.redis_url.get_secret_value.return_value = "redis://localhost:6379"

        mock_redis = MagicMock()
        mock_worker1 = MagicMock()
        mock_worker1.name = "host1#1111"
        mock_worker1.tasks = ["task1"]
        mock_worker2 = MagicMock()
        mock_worker2.name = "host2#2222"
        mock_worker2.tasks = ["task1", "task2", "task3"]

        with (
            patch("redis_sre_agent.cli.worker.settings", mock_settings),
            patch("redis.Redis.from_url") as mock_from_url,
            patch(
                "redis_sre_agent.cli.worker.asyncio.run",
                return_value=[mock_worker1, mock_worker2],
            ),
        ):
            mock_from_url.return_value.__enter__.return_value = mock_redis

            result = cli_runner.invoke(worker, ["status"])

            assert result.exit_code == 0
            assert "Workers: 2 active" in result.output
            assert "host1#1111" in result.output
            assert "host2#2222" in result.output

    def test_status_redis_connection_error(self, cli_runner):
        """Test status handles Redis connection errors."""
        mock_settings = MagicMock()
        mock_settings.redis_url.get_secret_value.return_value = "redis://localhost:6379"

        with (
            patch("redis_sre_agent.cli.worker.settings", mock_settings),
            patch(
                "redis.Redis.from_url",
                side_effect=Exception("Connection refused"),
            ),
        ):
            result = cli_runner.invoke(worker, ["status"])

            assert result.exit_code != 0
            assert "Failed to connect" in result.output
            assert "Connection refused" in result.output
            assert "Worker cannot run without Redis" in result.output


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

    def test_stop_no_workers_running(self, cli_runner):
        """Test stop when no workers are running."""
        mock_settings = MagicMock()
        mock_settings.redis_url.get_secret_value.return_value = "redis://localhost:6379"

        mock_redis = MagicMock()

        with (
            patch("redis_sre_agent.cli.worker.settings", mock_settings),
            patch("redis.Redis.from_url") as mock_from_url,
            patch("redis_sre_agent.cli.worker.asyncio.run", return_value=[]),
        ):
            mock_from_url.return_value.__enter__.return_value = mock_redis

            result = cli_runner.invoke(worker, ["stop"])

            assert result.exit_code == 0
            assert "No workers are currently running" in result.output

    def test_stop_pid_parsing_failure(self, cli_runner):
        """Test stop when worker name has invalid PID format."""
        mock_settings = MagicMock()
        mock_settings.redis_url.get_secret_value.return_value = "redis://localhost:6379"

        mock_redis = MagicMock()
        mock_worker = MagicMock()
        mock_worker.name = "hostname#not-a-number"

        with (
            patch("redis_sre_agent.cli.worker.settings", mock_settings),
            patch("redis.Redis.from_url") as mock_from_url,
            patch("redis_sre_agent.cli.worker.asyncio.run", return_value=[mock_worker]),
        ):
            mock_from_url.return_value.__enter__.return_value = mock_redis

            result = cli_runner.invoke(worker, ["stop"])

            assert result.exit_code == 0
            assert "Could not parse PID from worker name" in result.output

    def test_stop_validation_failure_skips_worker(self, cli_runner):
        """Test stop skips worker when validation fails."""
        mock_settings = MagicMock()
        mock_settings.redis_url.get_secret_value.return_value = "redis://localhost:6379"

        mock_redis = MagicMock()
        mock_worker = MagicMock()
        mock_worker.name = "other-host#1234"

        with (
            patch("redis_sre_agent.cli.worker.settings", mock_settings),
            patch("redis.Redis.from_url") as mock_from_url,
            patch("redis_sre_agent.cli.worker.asyncio.run", return_value=[mock_worker]),
            patch(
                "redis_sre_agent.cli.worker._validate_worker_process",
                return_value=(False, "hostname mismatch"),
            ),
        ):
            mock_from_url.return_value.__enter__.return_value = mock_redis

            result = cli_runner.invoke(worker, ["stop"])

            assert result.exit_code == 0
            assert "Skipping worker" in result.output
            assert "hostname mismatch" in result.output

    def test_stop_successful_sigterm(self, cli_runner):
        """Test stop successfully sends SIGTERM to worker."""
        mock_settings = MagicMock()
        mock_settings.redis_url.get_secret_value.return_value = "redis://localhost:6379"

        mock_redis = MagicMock()
        mock_worker = MagicMock()
        mock_worker.name = "myhost#1234"

        with (
            patch("redis_sre_agent.cli.worker.settings", mock_settings),
            patch("redis.Redis.from_url") as mock_from_url,
            patch("redis_sre_agent.cli.worker.asyncio.run", return_value=[mock_worker]),
            patch(
                "redis_sre_agent.cli.worker._validate_worker_process",
                return_value=(True, "validated"),
            ),
            patch("redis_sre_agent.cli.worker.os.kill") as mock_kill,
        ):
            mock_from_url.return_value.__enter__.return_value = mock_redis

            result = cli_runner.invoke(worker, ["stop"])

            assert result.exit_code == 0
            mock_kill.assert_called_once_with(1234, 15)  # signal.SIGTERM = 15
            assert "Stopping worker" in result.output
            assert "Sent SIGTERM" in result.output

    def test_stop_process_not_found(self, cli_runner):
        """Test stop handles ProcessLookupError gracefully."""
        mock_settings = MagicMock()
        mock_settings.redis_url.get_secret_value.return_value = "redis://localhost:6379"

        mock_redis = MagicMock()
        mock_worker = MagicMock()
        mock_worker.name = "myhost#1234"

        with (
            patch("redis_sre_agent.cli.worker.settings", mock_settings),
            patch("redis.Redis.from_url") as mock_from_url,
            patch("redis_sre_agent.cli.worker.asyncio.run", return_value=[mock_worker]),
            patch(
                "redis_sre_agent.cli.worker._validate_worker_process",
                return_value=(True, "validated"),
            ),
            patch("redis_sre_agent.cli.worker.os.kill", side_effect=ProcessLookupError),
        ):
            mock_from_url.return_value.__enter__.return_value = mock_redis

            result = cli_runner.invoke(worker, ["stop"])

            assert result.exit_code == 0
            assert "not found" in result.output
            assert "may have already stopped" in result.output

    def test_stop_permission_denied(self, cli_runner):
        """Test stop handles PermissionError gracefully."""
        mock_settings = MagicMock()
        mock_settings.redis_url.get_secret_value.return_value = "redis://localhost:6379"

        mock_redis = MagicMock()
        mock_worker = MagicMock()
        mock_worker.name = "myhost#1234"

        with (
            patch("redis_sre_agent.cli.worker.settings", mock_settings),
            patch("redis.Redis.from_url") as mock_from_url,
            patch("redis_sre_agent.cli.worker.asyncio.run", return_value=[mock_worker]),
            patch(
                "redis_sre_agent.cli.worker._validate_worker_process",
                return_value=(True, "validated"),
            ),
            patch("redis_sre_agent.cli.worker.os.kill", side_effect=PermissionError),
        ):
            mock_from_url.return_value.__enter__.return_value = mock_redis

            result = cli_runner.invoke(worker, ["stop"])

            assert result.exit_code == 0
            assert "Permission denied" in result.output

    def test_stop_redis_connection_error(self, cli_runner):
        """Test stop handles Redis connection errors."""
        mock_settings = MagicMock()
        mock_settings.redis_url.get_secret_value.return_value = "redis://localhost:6379"

        with (
            patch("redis_sre_agent.cli.worker.settings", mock_settings),
            patch(
                "redis.Redis.from_url",
                side_effect=Exception("Connection refused"),
            ),
        ):
            result = cli_runner.invoke(worker, ["stop"])

            assert result.exit_code != 0
            assert "Connection refused" in result.output


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
