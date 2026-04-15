from __future__ import annotations

import inspect
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
    is_async_tool = tool_name in _ASYNC_TOOL_NAMES
    native_mode = "agent_task" if is_async_tool else "inline"
    contract: dict[str, object] = {
        "nativeMode": native_mode,
        "runtimeMode": "inline",
        "nativeResultKind": "task_receipt" if is_async_tool else "final_result",
        "runtimeResultKind": "final_result",
    }
    if is_async_tool:
        contract.update(
            {
                "statusTool": _STATUS_TOOL,
                "resultTool": _RESULT_TOOL,
                "cancelTool": _CANCEL_TOOL,
                "taskReceipt": {
                    "taskIdField": "task_id",
                    "threadIdField": "thread_id",
                    "statusField": "status",
                    "messageField": "message",
                },
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


def in_runtime_task_execution() -> bool:
    return _RUNTIME_EXECUTION_CONTEXT.get() is not None


async def submit_background_task_call(
    *,
    processor: Callable[..., Awaitable[Any]],
    processor_kwargs: Mapping[str, Any] | None = None,
    key: str | None = None,
    when: Any | None = None,
    docket_name: str = "sre_docket",
) -> Dict[str, Any]:
    from docket import Docket

    from redis_sre_agent.core.docket_tasks import get_redis_url

    payload = dict(processor_kwargs or {})
    if in_runtime_task_execution():
        return {
            "mode": "inline",
            "task_system": "runtime",
            "result": await processor(**payload),
        }

    add_kwargs: Dict[str, Any] = {}
    if key is not None:
        add_kwargs["key"] = key
    if when is not None:
        add_kwargs["when"] = when

    async with Docket(url=await get_redis_url(), name=docket_name) as docket:
        task_func = docket.add(processor, **add_kwargs)
        if inspect.isawaitable(task_func):
            task_func = await task_func
        result = await task_func(**payload)

    return {
        "mode": "agent_task",
        "task_system": "sre",
        "result": result,
    }


async def cancel_background_task(
    *,
    task_id: str,
    docket_name: str = "sre_docket",
) -> Dict[str, Any]:
    from docket import Docket

    from redis_sre_agent.core.docket_tasks import get_redis_url

    if in_runtime_task_execution():
        return {
            "mode": "inline",
            "task_system": "runtime",
            "cancelled": False,
            "message": "Runtime execution has no nested Docket task to cancel",
        }

    async with Docket(url=await get_redis_url(), name=docket_name) as docket:
        await docket.cancel(task_id)

    return {
        "mode": "agent_task",
        "task_system": "sre",
        "cancelled": True,
        "message": f"Cancelled Docket task {task_id}",
    }


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

    execution = await submit_background_task_call(
        processor=processor,
        processor_kwargs=payload,
        key=task_id,
    )
    if execution["mode"] == "inline":
        return _build_task_response(
            task_record=task_record,
            status="done",
            message=runtime_message,
            tool_name=tool_name,
            mode="inline",
            task_system=str(execution["task_system"]),
            final=True,
            result=execution["result"],
        )

    return _build_task_response(
        task_record=task_record,
        status=_status_value(task_record.get("status", "queued")),
        message=native_message,
        tool_name=tool_name,
        mode="agent_task",
        task_system="sre",
        final=False,
    )
