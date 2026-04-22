"""Shared tool execution helpers."""

from __future__ import annotations

import inspect
import json
from typing import Any, Callable, Dict, List, Optional

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
    local_tools: Optional[Dict[str, Callable[..., Any]]] = None,
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
    local_tools: Optional[Dict[str, Callable[..., Any]]] = None,
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
    local_tool_map = dict(local_tools or {})
    manager_calls = [
        {"name": tool_call["name"], "args": tool_call["args"]}
        for tool_call in normalized_tool_calls
        if tool_call["name"] not in local_tool_map
    ]
    manager_results: List[Any] = []
    if manager_calls:
        manager_results = await tool_manager.execute_tool_calls(manager_calls)
    if len(manager_results) != len(manager_calls):
        raise RuntimeError(
            "Tool manager returned a mismatched number of results for the requested tool calls"
        )
    manager_result_iter = iter(manager_results)

    tool_messages: List[ToolMessage] = []

    for tool_call in normalized_tool_calls:
        tool_name = tool_call["name"]
        if tool_name in local_tool_map:
            result = local_tool_map[tool_name](**tool_call["args"])
            if inspect.isawaitable(result):
                result = await result
        else:
            result = next(manager_result_iter)
        tool_messages.append(
            ToolMessage(
                content=_serialize_tool_result(result),
                tool_call_id=tool_call["id"],
                name=tool_name,
            )
        )

    return tool_messages
