from __future__ import annotations

import asyncio
import importlib
import inspect
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Mapping

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

try:
    from redis_agent_kit import Agent, TaskEmitter
except ImportError:  # pragma: no cover - local monorepo fallback for tests
    _repo_runner_src = Path(__file__).resolve().parents[1].parent / "apps" / "runner" / "src"
    if _repo_runner_src.is_dir():
        sys.path.insert(0, str(_repo_runner_src))
        from redis_agent_kit import Agent, TaskEmitter
    else:  # pragma: no cover - defensive
        raise


MAX_HISTORY_MESSAGES = 20
DEFAULT_USER_ID = "runtime-user"
_REDIS_BOOTSTRAP_LOCK = asyncio.Lock()
_REDIS_BOOTSTRAP_COMPLETE = False


def _runtime_state_dir() -> Path:
    state_dir = Path(os.environ.get("RAK_APP_STATE_DIR", "/tmp/rar-app-state/redis-sre-agent"))
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir


def _runtime_config_path() -> Path:
    return Path(__file__).resolve().with_name("config.runtime.yaml")


def _conversation_dir() -> Path:
    path = _runtime_state_dir() / "conversations"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _safe_context_id(raw_value: object, *, fallback: str) -> str:
    if isinstance(raw_value, str) and raw_value.strip():
        candidate = raw_value.strip()
    else:
        candidate = fallback
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "_", candidate).strip("._")
    return normalized or fallback


def _conversation_path(context_id: str) -> Path:
    return _conversation_dir() / f"{context_id}.json"


def _load_conversation_history(context_id: str) -> list[BaseMessage]:
    path = _conversation_path(context_id)
    if not path.is_file():
        return []
    try:
        decoded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    if not isinstance(decoded, list):
        return []

    messages: list[BaseMessage] = []
    for item in decoded[-MAX_HISTORY_MESSAGES:]:
        if not isinstance(item, Mapping):
            continue
        role = str(item.get("role", "")).strip().lower()
        content = str(item.get("content", "")).strip()
        if not content:
            continue
        if role == "assistant":
            messages.append(AIMessage(content=content))
        else:
            messages.append(HumanMessage(content=content))
    return messages


def _append_conversation_history(context_id: str, *messages: Mapping[str, str]) -> None:
    path = _conversation_path(context_id)
    history: list[dict[str, str]] = []
    if path.is_file():
        try:
            decoded = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            decoded = []
        if isinstance(decoded, list):
            for item in decoded:
                if isinstance(item, Mapping):
                    role = str(item.get("role", "")).strip()
                    content = str(item.get("content", "")).strip()
                    if role and content:
                        history.append({"role": role, "content": content})

    for item in messages:
        role = str(item.get("role", "")).strip()
        content = str(item.get("content", "")).strip()
        if role and content:
            history.append({"role": role, "content": content})

    path.write_text(
        json.dumps(history[-MAX_HISTORY_MESSAGES:], indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _bootstrap_runtime_environment() -> None:
    if not os.environ.get("SRE_AGENT_CONFIG"):
        runtime_config = _runtime_config_path()
        if runtime_config.is_file():
            os.environ["SRE_AGENT_CONFIG"] = str(runtime_config)

    if not os.environ.get("REDIS_URL"):
        for key in ("RAR_RUNTIME_REDIS_URL", "TARGET_REDIS_URL"):
            candidate = os.environ.get(key, "").strip()
            if candidate:
                os.environ["REDIS_URL"] = candidate
                break


_bootstrap_runtime_environment()


async def _ensure_runtime_redis_ready() -> None:
    global _REDIS_BOOTSTRAP_COMPLETE

    if _REDIS_BOOTSTRAP_COMPLETE or not os.environ.get("REDIS_URL"):
        return

    async with _REDIS_BOOTSTRAP_LOCK:
        if _REDIS_BOOTSTRAP_COMPLETE:
            return

        from redis_sre_agent.core.redis import create_indices

        if not await create_indices():
            raise RuntimeError("Failed to initialize runtime Redis indices")
        _REDIS_BOOTSTRAP_COMPLETE = True


class RuntimeProgressEmitter:
    def __init__(self, emitter: TaskEmitter) -> None:
        self._emitter = emitter

    async def emit(
        self,
        message: str,
        update_type: str = "progress",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        await self._emitter.emit_async(
            str(message),
            update_type=update_type or "progress",
            metadata=_json_safe_mapping(metadata),
        )


def _json_safe_mapping(payload: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if payload is None:
        return None
    try:
        return json.loads(json.dumps(dict(payload), default=str))
    except TypeError:
        return {str(key): str(value) for key, value in payload.items()}


def _tool_output_summary(envelope: Mapping[str, Any]) -> str:
    summary = envelope.get("summary")
    if isinstance(summary, str) and summary.strip():
        return summary.strip()[:500]
    data = envelope.get("data", {})
    try:
        rendered = json.dumps(data, default=str, sort_keys=True)
    except TypeError:
        rendered = str(data)
    return rendered[:500]


async def _emit_tool_envelopes(
    emitter: TaskEmitter, tool_envelopes: list[Mapping[str, Any]]
) -> None:
    for index, envelope in enumerate(tool_envelopes, start=1):
        tool_name_raw = envelope.get("name") or envelope.get("tool_key") or f"tool_{index}"
        tool_name = str(tool_name_raw).strip() or f"tool_{index}"
        call_id = str(envelope.get("tool_key") or f"{tool_name}-{index}").strip()
        status = (
            "failed" if str(envelope.get("status", "")).strip().lower() == "error" else "completed"
        )
        arguments = envelope.get("args")
        await emitter.emit_tool_call_async(
            tool_name,
            call_id=call_id,
            status=status,
            arguments=dict(arguments) if isinstance(arguments, Mapping) else None,
            output_summary=_tool_output_summary(envelope),
            error_summary=None if status == "completed" else _tool_output_summary(envelope),
        )


def _normalize_context(task_input: Mapping[str, Any]) -> dict[str, Any]:
    context: dict[str, Any] = {}
    for key in ("instance_id", "cluster_id", "user_id"):
        value = task_input.get(key)
        if isinstance(value, str) and value.strip():
            context[key] = value.strip()
    return context


async def _resolve_agent_context(task_input: Mapping[str, Any]) -> tuple[dict[str, Any], Any, Any]:
    from redis_sre_agent.core.clusters import get_cluster_by_id
    from redis_sre_agent.core.instances import get_instance_by_id

    context = _normalize_context(task_input)
    instance = None
    cluster = None

    instance_id = context.get("instance_id")
    cluster_id = context.get("cluster_id")
    if instance_id and cluster_id:
        raise RuntimeError("Provide only one of instance_id or cluster_id")
    if instance_id:
        instance = await get_instance_by_id(instance_id)
        if instance is None:
            raise RuntimeError(f"Unknown instance_id: {instance_id}")
    if cluster_id:
        cluster = await get_cluster_by_id(cluster_id)
        if cluster is None:
            raise RuntimeError(f"Unknown cluster_id: {cluster_id}")

    return context, instance, cluster


async def _dispatch_chat_query(
    task_input: Mapping[str, Any],
    emitter: TaskEmitter,
) -> dict[str, Any]:
    message_raw = task_input.get("message")
    if not isinstance(message_raw, str) or not message_raw.strip():
        raise RuntimeError("chat requests require a non-empty message")
    message = message_raw.strip()

    explicit_context_id = task_input.get("contextId")
    task_run_id = os.environ.get("RAR_TASK_RUN_ID", "context")
    context_id = _safe_context_id(explicit_context_id, fallback=task_run_id)
    user_id = str(task_input.get("user_id") or DEFAULT_USER_ID)
    runtime_progress = RuntimeProgressEmitter(emitter)

    from redis_sre_agent.agent.chat_agent import get_chat_agent
    from redis_sre_agent.agent.knowledge_agent import get_knowledge_agent
    from redis_sre_agent.agent.langgraph_agent import get_sre_agent
    from redis_sre_agent.agent.router import AgentType, route_to_appropriate_agent

    context, instance, cluster = await _resolve_agent_context(task_input)
    conversation_history = _load_conversation_history(context_id)

    requested_agent = str(task_input.get("agent", "auto")).strip().lower()
    if requested_agent == "triage":
        selected_type = AgentType.REDIS_TRIAGE
    elif requested_agent == "chat":
        selected_type = AgentType.REDIS_CHAT
    elif requested_agent == "knowledge":
        selected_type = AgentType.KNOWLEDGE_ONLY
    else:
        selected_type = await route_to_appropriate_agent(
            query=message,
            context=context or None,
            conversation_history=conversation_history or None,
        )

    if selected_type == AgentType.REDIS_TRIAGE:
        selected_agent = get_sre_agent()
        agent_label = "triage"
    elif selected_type == AgentType.REDIS_CHAT:
        selected_agent = get_chat_agent(redis_instance=instance, redis_cluster=cluster)
        agent_label = "chat"
    else:
        selected_agent = get_knowledge_agent()
        agent_label = "knowledge"

    response = await selected_agent.process_query(
        message,
        session_id=context_id,
        user_id=user_id,
        context=context or None,
        progress_emitter=runtime_progress,
        conversation_history=conversation_history or None,
    )
    await _emit_tool_envelopes(emitter, response.tool_envelopes)
    _append_conversation_history(
        context_id,
        {"role": "user", "content": message},
        {"role": "assistant", "content": response.response},
    )
    return {
        "ok": True,
        "mode": "a2a",
        "agent": agent_label,
        "reply": response.response,
        "response": response.response,
        "contextId": context_id,
        "citations": response.search_results,
        "toolCalls": len(response.tool_envelopes),
    }


def _load_mcp_tool_registry() -> dict[str, Any]:
    module = importlib.import_module("redis_sre_agent.mcp_server.server")
    mcp_server = getattr(module, "mcp", None)
    tool_manager = getattr(mcp_server, "_tool_manager", None)
    registered_tools = getattr(tool_manager, "_tools", {})

    registry: dict[str, Any] = {}
    for name, tool in registered_tools.items():
        tool_fn = getattr(tool, "fn", None)
        if not callable(tool_fn):
            continue
        if getattr(tool, "context_kwarg", None):
            continue
        registry[str(name)] = tool_fn
    return registry


def _load_configured_external_mcp_tools() -> dict[str, dict[str, str]]:
    from redis_sre_agent.core.config import MCPServerConfig, settings

    tools: dict[str, dict[str, str]] = {}
    for server_name, server_config in settings.mcp_servers.items():
        if isinstance(server_config, dict):
            server_config = MCPServerConfig.model_validate(server_config)
        if not server_config.tools:
            continue
        for tool_name, tool_config in server_config.tools.items():
            description = getattr(tool_config, "description", None) or (
                f"Configured external MCP tool '{tool_name}' from '{server_name}'."
            )
            tools.setdefault(
                tool_name,
                {
                    "server_name": server_name,
                    "description": description,
                },
            )
    return tools


async def _invoke_configured_external_mcp_tool(
    tool_name: str,
    arguments: Mapping[str, Any],
) -> dict[str, Any]:
    from redis_sre_agent.core.config import MCPServerConfig, settings
    from redis_sre_agent.tools.mcp.provider import MCPToolProvider

    external_tools = _load_configured_external_mcp_tools()
    tool_spec = external_tools.get(tool_name)
    if tool_spec is None:
        raise RuntimeError(f"Unsupported configured external MCP tool '{tool_name}'")

    server_name = tool_spec["server_name"]
    server_config = settings.mcp_servers.get(server_name)
    if server_config is None:
        raise RuntimeError(
            f"Configured external MCP tool '{tool_name}' references unknown server '{server_name}'"
        )
    if isinstance(server_config, dict):
        server_config = MCPServerConfig.model_validate(server_config)

    provider = MCPToolProvider(
        server_name=server_name,
        server_config=server_config,
        use_pool=False,
    )
    async with provider:
        return await provider._call_mcp_tool(tool_name, dict(arguments))


async def _dispatch_mcp_tool(task_input: Mapping[str, Any]) -> dict[str, Any]:
    tool_name_raw = task_input.get("tool")
    if not isinstance(tool_name_raw, str) or not tool_name_raw.strip():
        raise RuntimeError("mcp requests require a non-empty tool name")
    tool_name = tool_name_raw.strip()
    arguments = task_input.get("arguments", {})
    if not isinstance(arguments, Mapping):
        raise RuntimeError("mcp arguments must be an object")

    registry = _load_mcp_tool_registry()
    tool = registry.get(tool_name)
    if tool is None and tool_name in _load_configured_external_mcp_tools():
        result = await _invoke_configured_external_mcp_tool(tool_name, arguments)
        return {
            "ok": True,
            "mode": "mcp",
            "tool": tool_name,
            "result": result,
        }

    if tool is None:
        supported = ", ".join(sorted(set(registry) | set(_load_configured_external_mcp_tools())))
        raise RuntimeError(f"Unsupported MCP tool '{tool_name}'. Supported tools: {supported}")

    from redis_sre_agent.mcp_server.task_contract import runtime_task_execution_context

    with runtime_task_execution_context({"outerTaskId": os.environ.get("RAR_TASK_RUN_ID", "")}):
        result = tool(**dict(arguments))
        if inspect.isawaitable(result):
            result = await result

    return {
        "ok": True,
        "mode": "mcp",
        "tool": tool_name,
        "result": result,
    }


def _build_mcp_capabilities() -> dict[str, list[dict[str, Any]]]:
    from redis_sre_agent.mcp_server.task_contract import tool_execution_contract

    tools: list[dict[str, Any]] = []
    for name, tool in sorted(_load_mcp_tool_registry().items()):
        description = (
            (inspect.getdoc(tool) or "").strip().splitlines()[0] if inspect.getdoc(tool) else name
        )
        tools.append(
            {
                "name": name,
                "description": description,
                "executionContract": tool_execution_contract(name),
            }
        )
    for name, tool_spec in sorted(_load_configured_external_mcp_tools().items()):
        if any(existing["name"] == name for existing in tools):
            continue
        tools.append(
            {
                "name": name,
                "description": tool_spec["description"],
                "executionContract": {
                    "nativeMode": "inline",
                    "runtimeMode": "inline",
                    "nativeResultKind": "final_result",
                    "runtimeResultKind": "final_result",
                },
            }
        )
    return {"tools": tools, "resources": [], "prompts": []}


async def runtime_sre_agent(task_input: Mapping[str, Any], emitter: TaskEmitter) -> dict[str, Any]:
    _bootstrap_runtime_environment()
    await _ensure_runtime_redis_ready()
    if isinstance(task_input.get("tool"), str) and str(task_input.get("tool")).strip():
        return await _dispatch_mcp_tool(task_input)
    return await _dispatch_chat_query(task_input, emitter)


agent = Agent(
    agent_callable=runtime_sre_agent,
    protocols=["a2a", "mcp"],
    a2a_card={
        "name": "Redis SRE Agent",
        "description": "Runtime-adapted Redis SRE agent for chat, triage, and Redis operations workflows.",
        "skills": [
            {
                "id": "redis-sre-chat",
                "name": "Redis SRE chat",
                "description": "Answer Redis operational questions and perform live triage.",
            }
        ],
    },
    mcp_capabilities=_build_mcp_capabilities(),
)


__all__ = [
    "agent",
    "runtime_sre_agent",
]
