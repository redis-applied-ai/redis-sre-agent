from __future__ import annotations

import json
import os
import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest


def _load_module():
    module_path = Path(__file__).resolve().parents[1] / "runtime_agent.py"
    spec = importlib.util.spec_from_file_location("runtime_agent_module", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _FakeTaskEmitter:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []
        self.tool_calls: list[dict[str, Any]] = []

    async def emit_async(
        self,
        message: str,
        *,
        update_type: str = "info",
        stage: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.messages.append(
            {
                "message": message,
                "update_type": update_type,
                "stage": stage,
                "metadata": metadata,
            }
        )

    async def emit_tool_call_async(
        self,
        name: str,
        *,
        call_id: str,
        status: str,
        arguments: dict[str, Any] | None = None,
        output_summary: str | None = None,
        error_summary: str | None = None,
    ) -> None:
        self.tool_calls.append(
            {
                "name": name,
                "call_id": call_id,
                "status": status,
                "arguments": arguments,
                "output_summary": output_summary,
                "error_summary": error_summary,
            }
        )


@pytest.mark.asyncio
async def test_runtime_sre_agent_dispatches_mcp_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_module()
    emitter = _FakeTaskEmitter()

    async def _fake_tool(*, query: str) -> dict[str, Any]:
        return {"query": query, "hits": 1}

    monkeypatch.setattr(
        module,
        "_load_mcp_tool_registry",
        lambda: {"redis_sre_knowledge_search": _fake_tool},
    )

    result = await module.runtime_sre_agent(
        {
            "tool": "redis_sre_knowledge_search",
            "arguments": {"query": "memory pressure"},
        },
        emitter,
    )

    assert result == {
        "ok": True,
        "mode": "mcp",
        "tool": "redis_sre_knowledge_search",
        "result": {"query": "memory pressure", "hits": 1},
    }


@pytest.mark.asyncio
async def test_runtime_sre_agent_chat_dispatches_mcp_command(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _load_module()
    emitter = _FakeTaskEmitter()

    monkeypatch.setenv("RAK_APP_STATE_DIR", str(tmp_path))
    monkeypatch.setattr(
        module,
        "_load_mcp_tool_registry",
        lambda: {"redis_sre_knowledge_search": _fake_search_tool},
    )

    result = await module.runtime_sre_agent(
        {
            "message": '/mcp redis_sre_knowledge_search {"query":"memory pressure"}',
            "contextId": "ctx-mcp",
        },
        emitter,
    )

    assert result["mode"] == "a2a"
    assert result["agent"] == "mcp"
    assert result["mcpResult"] == {"query": "memory pressure", "hits": 1}
    assert "memory pressure" in result["reply"]
    assert emitter.tool_calls[-1]["name"] == "redis_sre_knowledge_search"
    history_path = tmp_path / "conversations" / "ctx-mcp.json"
    saved = json.loads(history_path.read_text(encoding="utf-8"))
    assert saved[-1]["content"].startswith("MCP tool `redis_sre_knowledge_search` result:")


async def _fake_search_tool(*, query: str) -> dict[str, Any]:
    return {"query": query, "hits": 1}


@pytest.mark.asyncio
async def test_runtime_sre_agent_chat_persists_context_history(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _load_module()
    emitter = _FakeTaskEmitter()

    monkeypatch.setenv("RAK_APP_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("RAR_TASK_RUN_ID", "task-run-1")

    class _AgentResponse:
        def __init__(self, response: str) -> None:
            self.response = response
            self.search_results = [{"source": "doc"}]
            self.tool_envelopes = [
                {
                    "tool_key": "knowledge.search",
                    "name": "knowledge_search",
                    "args": {"query": "redis replication"},
                    "status": "success",
                    "data": {"hits": 3},
                    "summary": "3 hits",
                }
            ]

    class _ChatAgent:
        async def process_query(self, query: str, **kwargs: Any) -> _AgentResponse:
            history = kwargs.get("conversation_history") or []
            return _AgentResponse(f"reply:{query}:history={len(history)}")

    class _PatchedAgentType:
        REDIS_TRIAGE = "triage"
        REDIS_CHAT = "chat"
        KNOWLEDGE_ONLY = "knowledge"

    async def _fake_route(*_: Any, **__: Any):
        return _PatchedAgentType.REDIS_CHAT

    monkeypatch.setattr(module, "_resolve_agent_context", _fake_resolve_agent_context)
    monkeypatch.setattr(module, "_emit_tool_envelopes", _fake_emit_tool_envelopes)

    monkeypatch.setitem(
        sys.modules,
        "redis_sre_agent.agent.chat_agent",
        type("_M", (), {"get_chat_agent": lambda *_, **__: _ChatAgent()})(),
    )
    monkeypatch.setitem(sys.modules, "redis_sre_agent.agent.knowledge_agent", type("_M", (), {"get_knowledge_agent": lambda: _ChatAgent()})())
    monkeypatch.setitem(sys.modules, "redis_sre_agent.agent.langgraph_agent", type("_M", (), {"get_sre_agent": lambda: _ChatAgent()})())
    monkeypatch.setitem(
        sys.modules,
        "redis_sre_agent.agent.router",
        type(
            "_R",
            (),
            {
                "AgentType": type(
                    "AgentType",
                    (_PatchedAgentType,),
                    {},
                ),
                "route_to_appropriate_agent": _fake_route,
            },
        )(),
    )

    first = await module.runtime_sre_agent({"message": "hello"}, emitter)
    second = await module.runtime_sre_agent({"message": "follow up", "contextId": "ctx-1"}, emitter)

    assert first["mode"] == "a2a"
    assert first["reply"].startswith("reply:hello")
    assert second["contextId"] == "ctx-1"
    history_path = tmp_path / "conversations" / "ctx-1.json"
    assert history_path.exists()
    saved = json.loads(history_path.read_text(encoding="utf-8"))
    assert saved[-1]["content"].startswith("reply:follow up")


async def _fake_resolve_agent_context(task_input: dict[str, Any]):
    return {}, None, None


async def _fake_emit_tool_envelopes(emitter: _FakeTaskEmitter, tool_envelopes: list[dict[str, Any]]) -> None:
    for index, envelope in enumerate(tool_envelopes, start=1):
        await emitter.emit_tool_call_async(
            str(envelope["name"]),
            call_id=f"call-{index}",
            status="completed",
            arguments=dict(envelope.get("args", {})),
            output_summary=str(envelope.get("summary", "")),
        )


def test_bootstrap_runtime_environment_prefers_runtime_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_module()
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setenv("RAR_RUNTIME_REDIS_URL", "redis://runtime/0")

    module._bootstrap_runtime_environment()

    assert os.environ["REDIS_URL"] == "redis://runtime/0"
