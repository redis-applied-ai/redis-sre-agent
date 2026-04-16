"""Shared tool execution helpers."""

from __future__ import annotations

import json
from typing import Any, Dict, List

from langchain_core.messages import ToolMessage


def _serialize_tool_result(result: Any) -> str:
    if isinstance(result, str):
        return result
    try:
        return json.dumps(result, default=str)
    except Exception:
        return str(result)


async def execute_tool_call_with_gate(
    *,
    tool_manager: Any,
    tool_name: str,
    tool_args: Dict[str, Any],
) -> Any:
    """Execute a single tool call through the shared approval-aware boundary."""
    results = await tool_manager.execute_tool_calls(
        [{"name": tool_name, "args": dict(tool_args or {})}]
    )
    return results[0] if results else None


async def execute_tool_calls_with_gate(
    *,
    tool_manager: Any,
    tool_calls: List[Dict[str, Any]],
) -> List[ToolMessage]:
    """Execute tool calls via the shared approval-aware runtime boundary."""

    normalized_tool_calls = [
        {
            "id": str(tool_call.get("id") or tool_call.get("tool_call_id") or ""),
            "name": str(tool_call.get("name", "")),
            "args": dict(tool_call.get("args") or {}),
        }
        for tool_call in tool_calls or []
    ]
    results = await tool_manager.execute_tool_calls(
        [{"name": tool_call["name"], "args": tool_call["args"]} for tool_call in normalized_tool_calls]
    )

    tool_messages: List[ToolMessage] = []

    for tool_call, result in zip(normalized_tool_calls, results):
        tool_name = tool_call["name"]
        tool_messages.append(
            ToolMessage(
                content=_serialize_tool_result(result),
                tool_call_id=tool_call["id"],
                name=tool_name,
            )
        )

    return tool_messages
