from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Any, Awaitable, Callable, Dict, Mapping

_RUNTIME_EXECUTION_CONTEXT: ContextVar[dict[str, Any] | None] = ContextVar(
    "redis_sre_runtime_execution_context",
    default=None,
)

_ASYNC_TOOL_NAMES = frozenset(
    {
        "redis_sre_database_chat",
        "redis_sre_deep_triage",
        "redis_sre_general_chat",
        "redis_sre_knowledge_query",
    }
)

_STATUS_TOOL = "redis_sre_get_task_status"
_RESULT_TOOL = "redis_sre_get_thread"
_CANCEL_TOOL = "redis_sre_delete_task"


def tool_execution_contract(tool_name: str) -> dict[str, object]:
    native_mode = "agent_task" if tool_name in _ASYNC_TOOL_NAMES else "inline"
    contract: dict[str, object] = {
        "nativeMode": native_mode,
        "runtimeMode": "inline",
    }
    if tool_name in _ASYNC_TOOL_NAMES:
        contract.update(
            {
                "statusTool": _STATUS_TOOL,
                "resultTool": _RESULT_TOOL,
                "cancelTool": _CANCEL_TOOL,
            }
        )
    return contract


@contextmanager
def runtime_task_execution_context(task_input: Mapping[str, Any] | None = None):
    payload = dict(task_input or {})
    outer_task_id = payload.get("outerTaskId")
    if not isinstance(outer_task_id, str) or not outer_task_id.strip():
        outer_task_id = None
    token: Token = _RUNTIME_EXECUTION_CONTEXT.set({"outer_task_id": outer_task_id})
    try:
        yield
    finally:
        _RUNTIME_EXECUTION_CONTEXT.reset(token)


def _status_value(raw_status: object) -> str:
    if hasattr(raw_status, "value"):
        return str(getattr(raw_status, "value"))
    return str(raw_status)


def _build_task_response(
    *,
    task_record: Mapping[str, Any],
    status: str,
    message: str,
    tool_name: str,
    mode: str,
    task_system: str,
    final: bool,
    result: object | None = None,
) -> Dict[str, Any]:
    response: Dict[str, Any] = {
        "thread_id": str(task_record["thread_id"]),
        "task_id": str(task_record["task_id"]),
        "status": status,
        "message": message,
        "task": {
            "task_id": str(task_record["task_id"]),
            "thread_id": str(task_record["thread_id"]),
            "status_tool": _STATUS_TOOL,
            "result_tool": _RESULT_TOOL,
            "cancel_tool": _CANCEL_TOOL,
        },
        "execution": {
            "tool": tool_name,
            "mode": mode,
            "task_system": task_system,
            "final": final,
            "status_tool": _STATUS_TOOL,
            "result_tool": _RESULT_TOOL,
            "cancel_tool": _CANCEL_TOOL,
        },
    }
    runtime_context = _RUNTIME_EXECUTION_CONTEXT.get()
    if runtime_context and runtime_context.get("outer_task_id"):
        response["execution"]["outer_task_id"] = runtime_context["outer_task_id"]
    if result is not None:
        response["result"] = result
    return response


async def submit_async_tool_task(
    *,
    tool_name: str,
    message: str,
    context: Mapping[str, Any] | None,
    processor: Callable[..., Awaitable[Dict[str, Any]]],
    processor_kwargs: Mapping[str, Any] | None,
    native_message: str,
    runtime_message: str,
) -> Dict[str, Any]:
    from docket import Docket

    from redis_sre_agent.core.docket_tasks import get_redis_url
    from redis_sre_agent.core.redis import get_redis_client
    from redis_sre_agent.core.tasks import create_task

    redis_client = get_redis_client()
    task_record = await create_task(
        message=message,
        context=dict(context or {}),
        redis_client=redis_client,
    )
    task_id = str(task_record["task_id"])
    thread_id = str(task_record["thread_id"])
    payload = dict(processor_kwargs or {})
    payload.update({"task_id": task_id, "thread_id": thread_id})

    runtime_context = _RUNTIME_EXECUTION_CONTEXT.get()
    if runtime_context is not None:
        result = await processor(**payload)
        return _build_task_response(
            task_record=task_record,
            status="done",
            message=runtime_message,
            tool_name=tool_name,
            mode="inline",
            task_system="runtime",
            final=True,
            result=result,
        )

    async with Docket(url=await get_redis_url(), name="sre_docket") as docket:
        task_func = docket.add(processor, key=task_id)
        await task_func(**payload)

    return _build_task_response(
        task_record=task_record,
        status=_status_value(task_record.get("status", "queued")),
        message=native_message,
        tool_name=tool_name,
        mode="agent_task",
        task_system="sre",
        final=False,
    )
