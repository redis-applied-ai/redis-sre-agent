from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from redis_sre_agent.agent.tool_execution import execute_tool_calls_with_gate


@pytest.mark.asyncio
async def test_execute_tool_calls_with_gate_uses_manager_batch_boundary():
    tool_manager = SimpleNamespace(
        execute_tool_calls=AsyncMock(
            return_value=[{"status": "blocked", "reason": "read_only_mode"}]
        ),
    )

    tool_messages = await execute_tool_calls_with_gate(
        tool_manager=tool_manager,
        tool_calls=[
            {
                "id": "tool-call-1",
                "name": "redis_cloud_deadbeef_update_database",
                "args": {"database_id": 7},
            }
        ],
    )

    assert len(tool_messages) == 1
    assert "read_only_mode" in tool_messages[0].content
    tool_manager.execute_tool_calls.assert_awaited_once_with(
        [
            {
                "name": "redis_cloud_deadbeef_update_database",
                "args": {"database_id": 7},
            }
        ]
    )


@pytest.mark.asyncio
async def test_execute_tool_calls_with_gate_propagates_manager_errors():
    tool_manager = SimpleNamespace(
        execute_tool_calls=AsyncMock(side_effect=RuntimeError("manager gate interrupted")),
    )

    with pytest.raises(RuntimeError, match="manager gate interrupted"):
        await execute_tool_calls_with_gate(
            tool_manager=tool_manager,
            tool_calls=[
                {
                    "id": "tool-call-1",
                    "name": "redis_cloud_deadbeef_update_database",
                    "args": {"database_id": 7},
                }
            ],
        )

    tool_manager.execute_tool_calls.assert_awaited_once_with(
        [
            {
                "name": "redis_cloud_deadbeef_update_database",
                "args": {"database_id": 7},
            }
        ]
    )


@pytest.mark.asyncio
async def test_execute_tool_calls_with_gate_rejects_mismatched_result_counts():
    tool_manager = SimpleNamespace(
        execute_tool_calls=AsyncMock(return_value=[{"status": "ok"}]),
    )

    with pytest.raises(RuntimeError, match="mismatched number of results"):
        await execute_tool_calls_with_gate(
            tool_manager=tool_manager,
            tool_calls=[
                {
                    "id": "tool-call-1",
                    "name": "redis_cloud_deadbeef_update_database",
                    "args": {"database_id": 7},
                },
                {
                    "id": "tool-call-2",
                    "name": "redis_cloud_deadbeef_delete_database",
                    "args": {"database_id": 8},
                },
            ],
        )


@pytest.mark.asyncio
async def test_execute_tool_calls_with_gate_executes_local_tools_without_manager():
    tool_manager = SimpleNamespace(execute_tool_calls=AsyncMock())

    tool_messages = await execute_tool_calls_with_gate(
        tool_manager=tool_manager,
        tool_calls=[
            {
                "id": "tool-call-1",
                "name": "expand_evidence",
                "args": {"tool_key": "demo"},
            }
        ],
        local_tools={
            "expand_evidence": lambda tool_key: {
                "status": "success",
                "tool_key": tool_key,
            }
        },
    )

    assert len(tool_messages) == 1
    assert '"tool_key": "demo"' in tool_messages[0].content
    tool_manager.execute_tool_calls.assert_not_awaited()


@pytest.mark.asyncio
async def test_execute_tool_calls_with_gate_preserves_order_with_local_and_manager_tools():
    tool_manager = SimpleNamespace(
        execute_tool_calls=AsyncMock(return_value=[{"status": "ok", "source": "manager"}]),
    )

    tool_messages = await execute_tool_calls_with_gate(
        tool_manager=tool_manager,
        tool_calls=[
            {
                "id": "tool-call-1",
                "name": "expand_evidence",
                "args": {"tool_key": "demo"},
            },
            {
                "id": "tool-call-2",
                "name": "redis_cloud_deadbeef_update_database",
                "args": {"database_id": 7},
            },
        ],
        local_tools={
            "expand_evidence": lambda tool_key: {
                "status": "success",
                "tool_key": tool_key,
                "source": "local",
            }
        },
    )

    assert [message.name for message in tool_messages] == [
        "expand_evidence",
        "redis_cloud_deadbeef_update_database",
    ]
    assert '"source": "local"' in tool_messages[0].content
    assert '"source": "manager"' in tool_messages[1].content
    tool_manager.execute_tool_calls.assert_awaited_once_with(
        [
            {
                "name": "redis_cloud_deadbeef_update_database",
                "args": {"database_id": 7},
            }
        ]
    )
