"""Unit tests for the Docket worker."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from redis_sre_agent.worker import main


class TestWorkerSystem:
    """Test the Docket worker system."""

    @pytest.mark.asyncio
    async def test_worker_startup_success(self):
        """Test successful worker startup."""
        mock_worker = AsyncMock()

        with (
            patch("redis_sre_agent.worker.register_sre_tasks", return_value=None),
            patch("redis_sre_agent.worker.Worker.run", mock_worker),
            patch("redis_sre_agent.worker.settings") as mock_settings,
        ):
            mock_settings.redis_url = "redis://localhost:6379/0"

            # Mock the worker run to avoid infinite loop
            mock_worker.return_value = None

            # Test main function (will complete quickly due to mocks)
            await main()

            # Verify task registration was called
            mock_worker.assert_called_once()

    @pytest.mark.asyncio
    async def test_worker_startup_no_redis_url(self):
        """Test worker startup failure when Redis URL is missing."""
        with (
            patch("redis_sre_agent.worker.settings") as mock_settings,
            patch("sys.exit", side_effect=SystemExit) as mock_exit,
        ):
            mock_settings.redis_url = ""  # Empty Redis URL

            with pytest.raises(SystemExit):
                await main()

            # Should exit with error code 1
            mock_exit.assert_called_once_with(1)

    @pytest.mark.asyncio
    async def test_worker_task_registration_failure(self):
        """Test worker handling of task registration failure."""
        with (
            patch(
                "redis_sre_agent.worker.register_sre_tasks",
                side_effect=Exception("Registration failed"),
            ),
            patch("redis_sre_agent.worker.settings") as mock_settings,
        ):
            mock_settings.redis_url = "redis://localhost:6379/0"

            # Should raise the exception
            with pytest.raises(Exception, match="Registration failed"):
                await main()

    @pytest.mark.asyncio
    async def test_worker_run_failure(self):
        """Test worker handling of Worker.run failure."""
        with (
            patch("redis_sre_agent.worker.register_sre_tasks", return_value=None),
            patch("redis_sre_agent.worker.Worker.run", side_effect=Exception("Worker run failed")),
            patch("redis_sre_agent.worker.settings") as mock_settings,
        ):
            mock_settings.redis_url = "redis://localhost:6379/0"

            # Should raise the exception
            with pytest.raises(Exception, match="Worker run failed"):
                await main()

    @pytest.mark.asyncio
    async def test_worker_configuration(self):
        """Test worker configuration parameters."""
        mock_worker_run = AsyncMock()

        with (
            patch("redis_sre_agent.worker.register_sre_tasks", return_value=None),
            patch("redis_sre_agent.worker.Worker.run", mock_worker_run),
            patch("redis_sre_agent.worker.settings") as mock_settings,
        ):
            mock_settings.redis_url = "redis://localhost:6379/0"

            await main()

            # Check that Worker.run was called with correct parameters
            mock_worker_run.assert_called_once()
            call_args = mock_worker_run.call_args

            # Verify configuration
            assert call_args.kwargs["docket_name"] == "sre_docket"
            assert call_args.kwargs["url"] == "redis://localhost:6379/0"
            assert call_args.kwargs["concurrency"] == 2
            assert call_args.kwargs["tasks"] == ["redis_sre_agent.core.tasks:SRE_TASK_COLLECTION"]


class TestWorkerIntegration:
    """Test worker integration with task system."""

    def test_worker_module_imports(self):
        """Test that worker module imports correctly."""
        # This test verifies that all imports work
        from redis_sre_agent import worker

        assert hasattr(worker, "main")

    def test_worker_task_collection_reference(self):
        """Test that worker correctly references task collection."""
        from redis_sre_agent.core.tasks import SRE_TASK_COLLECTION

        # Verify task collection is not empty
        assert len(SRE_TASK_COLLECTION) > 0

        # Verify all tasks are callable
        for task in SRE_TASK_COLLECTION:
            assert callable(task)

    @pytest.mark.asyncio
    async def test_worker_main_function_signature(self):
        """Test that main function has correct signature for asyncio.run."""
        from redis_sre_agent.worker import main

        # Should be an async function
        assert asyncio.iscoroutinefunction(main)

        # Should accept no arguments
        import inspect

        sig = inspect.signature(main)
        assert len(sig.parameters) == 0


class TestWorkerErrorHandling:
    """Test worker error handling scenarios."""

    @pytest.mark.asyncio
    async def test_worker_keyboard_interrupt_handling(self):
        """Test worker handling of KeyboardInterrupt."""
        # This test verifies the structure exists for handling Ctrl+C
        # The actual handling happens in the if __name__ == "__main__" block

        with (
            patch("redis_sre_agent.worker.register_sre_tasks", return_value=None),
            patch(
                "redis_sre_agent.worker.Worker.run", side_effect=KeyboardInterrupt("User interrupt")
            ),
            patch("redis_sre_agent.worker.settings") as mock_settings,
        ):
            mock_settings.redis_url = "redis://localhost:6379/0"

            # KeyboardInterrupt should propagate
            with pytest.raises(KeyboardInterrupt):
                await main()

    @pytest.mark.asyncio
    async def test_worker_unexpected_error_handling(self):
        """Test worker handling of unexpected errors."""
        with (
            patch("redis_sre_agent.worker.register_sre_tasks", return_value=None),
            patch(
                "redis_sre_agent.worker.Worker.run", side_effect=RuntimeError("Unexpected error")
            ),
            patch("redis_sre_agent.worker.settings") as mock_settings,
        ):
            mock_settings.redis_url = "redis://localhost:6379/0"

            # Unexpected errors should propagate
            with pytest.raises(RuntimeError, match="Unexpected error"):
                await main()


class TestWorkerLogging:
    """Test worker logging functionality."""

    @pytest.mark.asyncio
    async def test_worker_logging_setup(self):
        """Test that worker sets up logging correctly."""
        # Verify logging is configured when module is imported
        import logging

        # Logger should exist
        logger = logging.getLogger("redis_sre_agent.worker")
        assert logger is not None

    @pytest.mark.asyncio
    async def test_worker_success_logging(self):
        """Test worker logs success messages."""
        with (
            patch("redis_sre_agent.worker.register_sre_tasks", return_value=None),
            patch("redis_sre_agent.worker.Worker.run", AsyncMock()),
            patch("redis_sre_agent.worker.settings") as mock_settings,
            patch("redis_sre_agent.worker.logger") as mock_logger,
        ):
            mock_settings.redis_url = "redis://localhost:6379/0"

            await main()

            # Should log startup and success messages
            mock_logger.info.assert_called()

            # Check for expected log messages
            log_calls = [call[0][0] for call in mock_logger.info.call_args_list]
            assert any("Starting SRE Docket worker" in msg for msg in log_calls)

    @pytest.mark.asyncio
    async def test_worker_error_logging(self):
        """Test worker logs error messages."""
        with (
            patch("redis_sre_agent.worker.register_sre_tasks", side_effect=Exception("Test error")),
            patch("redis_sre_agent.worker.settings") as mock_settings,
            patch("redis_sre_agent.worker.logger") as mock_logger,
        ):
            mock_settings.redis_url = "redis://localhost:6379/0"

            with pytest.raises(Exception):
                await main()

            # Should log error message
            mock_logger.error.assert_called()

            # Check error message content
            error_call = mock_logger.error.call_args[0][0]
            assert "Worker error" in error_call
