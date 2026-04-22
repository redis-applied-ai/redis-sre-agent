"""Shared tool execution helpers."""

from __future__ import annotations

import inspect
import json
from typing import Any, Dict, List, Optional

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
    local_tools: Optional[Dict[str, Any]] = None,
) -> Any:
    """Execute a single tool call through the shared approval-aware boundary."""
    local_tool = (local_tools or {}).get(tool_name)
    if local_tool is not None:
        result = local_tool(**dict(tool_args or {}))
        if inspect.isawaitable(result):
            return await result
        return result

    results = await tool_manager.execute_tool_calls(
        [{"name": tool_name, "args": dict(tool_args or {})}]
    )
    return results[0] if results else None


async def execute_tool_calls_with_gate(
    *,
    tool_manager: Any,
    tool_calls: List[Dict[str, Any]],
    local_tools: Optional[Dict[str, Any]] = None,
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

    tool_results: List[Any] = [None] * len(normalized_tool_calls)
    manager_tool_calls: List[Dict[str, Any]] = []
    manager_indices: List[int] = []
    local_tool_map = local_tools or {}

    for idx, tool_call in enumerate(normalized_tool_calls):
        local_tool = local_tool_map.get(tool_call["name"])
        if local_tool is not None:
            result = local_tool(**tool_call["args"])
            if inspect.isawaitable(result):
                result = await result
            tool_results[idx] = result
            continue

        manager_tool_calls.append({"name": tool_call["name"], "args": tool_call["args"]})
        manager_indices.append(idx)

    manager_results: List[Any] = []
    if manager_tool_calls:
        manager_results = await tool_manager.execute_tool_calls(manager_tool_calls)

    if len(manager_results) != len(manager_tool_calls):
        raise RuntimeError(
            "Tool manager returned a mismatched number of results for the requested tool calls"
        )

    for idx, result in zip(manager_indices, manager_results):
        tool_results[idx] = result

    tool_messages: List[ToolMessage] = []

    for tool_call, result in zip(normalized_tool_calls, tool_results):
        tool_name = tool_call["name"]
        tool_messages.append(
            ToolMessage(
                content=_serialize_tool_result(result),
                tool_call_id=tool_call["id"],
                name=tool_name,
            )
        )

    return tool_messages
