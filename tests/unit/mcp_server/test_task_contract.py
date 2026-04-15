from unittest.mock import AsyncMock, patch

import pytest

from redis_sre_agent.mcp_server.task_contract import (
    cancel_background_task,
    runtime_task_execution_context,
    submit_background_task_call,
)


class TestSubmitBackgroundTaskCall:
    @pytest.mark.asyncio
    async def test_queues_with_async_docket_add_result(self):
        processor = AsyncMock()
        task_callable = AsyncMock(return_value="docket-1")
        docket_instance = AsyncMock()
        docket_instance.__aenter__.return_value = docket_instance
        docket_instance.__aexit__.return_value = False
        docket_instance.add = AsyncMock(return_value=task_callable)

        with (
            patch(
                "redis_sre_agent.core.docket_tasks.get_redis_url",
                new_callable=AsyncMock,
                return_value="redis://test",
            ),
            patch("docket.Docket", return_value=docket_instance),
        ):
            result = await submit_background_task_call(
                processor=processor,
                key="task-1",
                processor_kwargs={"task_id": "task-1"},
            )

        assert result == {
            "mode": "agent_task",
            "task_system": "sre",
            "result": "docket-1",
        }
        docket_instance.add.assert_awaited_once_with(processor, key="task-1")
        task_callable.assert_awaited_once_with(task_id="task-1")
        processor.assert_not_called()

    @pytest.mark.asyncio
    async def test_executes_inline_under_runtime_context(self):
        processor = AsyncMock(return_value={"response": "ok"})

        with runtime_task_execution_context({"outerTaskId": "runtime-task-1"}):
            result = await submit_background_task_call(
                processor=processor,
                key="task-1",
                processor_kwargs={"task_id": "task-1"},
            )

        assert result == {
            "mode": "inline",
            "task_system": "runtime",
            "result": {"response": "ok"},
        }
        processor.assert_awaited_once_with(task_id="task-1")


class TestCancelBackgroundTask:
    @pytest.mark.asyncio
    async def test_cancels_native_docket_task(self):
        docket_instance = AsyncMock()
        docket_instance.__aenter__.return_value = docket_instance
        docket_instance.__aexit__.return_value = False

        with (
            patch(
                "redis_sre_agent.core.docket_tasks.get_redis_url",
                new_callable=AsyncMock,
                return_value="redis://test",
            ),
            patch("docket.Docket", return_value=docket_instance),
        ):
            result = await cancel_background_task(task_id="task-1")

        assert result == {
            "mode": "agent_task",
            "task_system": "sre",
            "cancelled": True,
            "message": "Cancelled Docket task task-1",
        }
        docket_instance.cancel.assert_awaited_once_with("task-1")

    @pytest.mark.asyncio
    async def test_skips_cancel_in_runtime_context(self):
        with patch("docket.Docket") as mock_docket:
            with runtime_task_execution_context({"outerTaskId": "runtime-task-1"}):
                result = await cancel_background_task(task_id="task-1")

        assert result == {
            "mode": "inline",
            "task_system": "runtime",
            "cancelled": False,
            "message": "Runtime execution has no nested Docket task to cancel",
        }
        mock_docket.assert_not_called()
