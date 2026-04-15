from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import sys
import types
from pathlib import Path
from typing import Any, Mapping

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
    module._REDIS_BOOTSTRAP_COMPLETE = True

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


def test_runtime_sre_agent_builds_execution_contract_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_module()

    async def _fake_tool(*, query: str) -> dict[str, Any]:
        return {"query": query}

    monkeypatch.setattr(
        module,
        "_load_mcp_tool_registry",
        lambda: {"redis_sre_general_chat": _fake_tool, "redis_sre_knowledge_search": _fake_tool},
    )

    capabilities = module._build_mcp_capabilities()
    tools = {entry["name"]: entry for entry in capabilities["tools"]}

    assert tools["redis_sre_general_chat"]["executionContract"]["nativeMode"] == "agent_task"
    assert tools["redis_sre_general_chat"]["executionContract"]["runtimeMode"] == "inline"
    assert tools["redis_sre_general_chat"]["executionContract"]["nativeResultKind"] == "task_receipt"
    assert tools["redis_sre_general_chat"]["executionContract"]["runtimeResultKind"] == "final_result"
    assert (
        tools["redis_sre_general_chat"]["executionContract"]["statusTool"]
        == "redis_sre_get_task_status"
    )
    assert tools["redis_sre_general_chat"]["executionContract"]["taskReceipt"] == {
        "taskIdField": "task_id",
        "threadIdField": "thread_id",
        "statusField": "status",
        "messageField": "message",
    }
    assert tools["redis_sre_knowledge_search"]["executionContract"] == {
        "nativeMode": "inline",
        "runtimeMode": "inline",
        "nativeResultKind": "final_result",
        "runtimeResultKind": "final_result",
    }


def test_load_mcp_tool_registry_includes_pipeline_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_module()

    async def _fake_tool(**_: Any) -> dict[str, Any]:
        return {"ok": True}

    fake_server = type(
        "_Server",
        (),
        {
            "redis_sre_list_instances": _fake_tool,
        },
    )()
    monkeypatch.setattr(module.importlib, "import_module", lambda name: fake_server)

    registry = module._load_mcp_tool_registry()

    assert "redis_sre_get_pipeline_status" in registry
    assert "redis_sre_get_pipeline_batch" in registry
    assert "redis_sre_prepare_source_documents" in registry
    assert "redis_sre_run_pipeline_full" in registry
    assert "redis_sre_run_pipeline_ingest" in registry


def test_entrypoint_metadata_exports_pipeline_tools() -> None:
    module = _load_module()

    tools = {entry["name"] for entry in module.agent.mcp_capabilities["tools"]}

    assert "redis_sre_get_pipeline_status" in tools
    assert "redis_sre_get_pipeline_batch" in tools
    assert "redis_sre_prepare_source_documents" in tools
    assert "redis_sre_run_pipeline_full" in tools
    assert "redis_sre_run_pipeline_ingest" in tools


def test_build_mcp_capabilities_includes_configured_external_mcp_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_module()

    monkeypatch.setattr(module, "_load_mcp_tool_registry", lambda: {})
    monkeypatch.setattr(
        module,
        "_load_configured_external_mcp_tools",
        lambda: {
            "analyzer_list_accounts": {
                "server_name": "re_analyzer",
                "description": "List known Analyzer accounts.",
            }
        },
    )

    capabilities = module._build_mcp_capabilities()
    tools = {entry["name"]: entry for entry in capabilities["tools"]}

    assert tools["analyzer_list_accounts"]["description"] == "List known Analyzer accounts."
    assert tools["analyzer_list_accounts"]["executionContract"] == {
        "nativeMode": "inline",
        "runtimeMode": "inline",
        "nativeResultKind": "final_result",
        "runtimeResultKind": "final_result",
    }


@pytest.mark.asyncio
async def test_runtime_sre_agent_dispatches_configured_external_mcp_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_module()
    emitter = _FakeTaskEmitter()
    module._REDIS_BOOTSTRAP_COMPLETE = True

    monkeypatch.setattr(module, "_load_mcp_tool_registry", lambda: {})
    monkeypatch.setattr(
        module,
        "_load_configured_external_mcp_tools",
        lambda: {
            "analyzer_list_accounts": {
                "server_name": "re_analyzer",
                "description": "List known Analyzer accounts.",
            }
        },
    )

    async def _fake_external(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        assert tool_name == "analyzer_list_accounts"
        assert arguments == {}
        return {"status": "error", "error": "401 Unauthorized"}

    monkeypatch.setattr(module, "_invoke_configured_external_mcp_tool", _fake_external)

    result = await module.runtime_sre_agent(
        {
            "tool": "analyzer_list_accounts",
            "arguments": {},
        },
        emitter,
    )

    assert result == {
        "ok": True,
        "mode": "mcp",
        "tool": "analyzer_list_accounts",
        "result": {"status": "error", "error": "401 Unauthorized"},
    }


@pytest.mark.asyncio
async def test_runtime_sre_agent_chat_does_not_tunnel_mcp_commands(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _load_module()
    emitter = _FakeTaskEmitter()
    module._REDIS_BOOTSTRAP_COMPLETE = True

    monkeypatch.setenv("RAK_APP_STATE_DIR", str(tmp_path))

    class _AgentResponse:
        def __init__(self, response: str) -> None:
            self.response = response
            self.search_results = []
            self.tool_envelopes = []

    class _ChatAgent:
        async def process_query(self, query: str, **kwargs: Any) -> _AgentResponse:
            return _AgentResponse(f"chat:{query}")

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
    monkeypatch.setitem(
        sys.modules,
        "redis_sre_agent.agent.knowledge_agent",
        type("_M", (), {"get_knowledge_agent": lambda: _ChatAgent()})(),
    )
    monkeypatch.setitem(
        sys.modules,
        "redis_sre_agent.agent.langgraph_agent",
        type("_M", (), {"get_sre_agent": lambda: _ChatAgent()})(),
    )
    monkeypatch.setitem(
        sys.modules,
        "redis_sre_agent.agent.router",
        type(
            "_R",
            (),
            {
                "AgentType": type("AgentType", (_PatchedAgentType,), {}),
                "route_to_appropriate_agent": _fake_route,
            },
        )(),
    )

    result = await module.runtime_sre_agent(
        {
            "message": "/mcp redis_sre_knowledge_search",
            "contextId": "ctx-chat",
        },
        emitter,
    )

    assert result["mode"] == "a2a"
    assert result["agent"] == "chat"
    assert result["reply"] == "chat:/mcp redis_sre_knowledge_search"
    assert emitter.tool_calls == []
    history_path = tmp_path / "conversations" / "ctx-chat.json"
    saved = json.loads(history_path.read_text(encoding="utf-8"))
    assert saved[-1]["content"] == "chat:/mcp redis_sre_knowledge_search"


@pytest.mark.asyncio
async def test_runtime_sre_agent_chat_persists_context_history(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _load_module()
    emitter = _FakeTaskEmitter()
    module._REDIS_BOOTSTRAP_COMPLETE = True

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
    monkeypatch.setitem(
        sys.modules,
        "redis_sre_agent.agent.knowledge_agent",
        type("_M", (), {"get_knowledge_agent": lambda: _ChatAgent()})(),
    )
    monkeypatch.setitem(
        sys.modules,
        "redis_sre_agent.agent.langgraph_agent",
        type("_M", (), {"get_sre_agent": lambda: _ChatAgent()})(),
    )
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


async def _fake_emit_tool_envelopes(
    emitter: _FakeTaskEmitter, tool_envelopes: list[dict[str, Any]]
) -> None:
    for index, envelope in enumerate(tool_envelopes, start=1):
        await emitter.emit_tool_call_async(
            str(envelope["name"]),
            call_id=f"call-{index}",
            status="completed",
            arguments=dict(envelope.get("args", {})),
            output_summary=str(envelope.get("summary", "")),
        )


def test_bootstrap_runtime_environment_prefers_runtime_redis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_module()
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setenv("RAR_RUNTIME_REDIS_URL", "redis://runtime/0")

    module._bootstrap_runtime_environment()

    assert os.environ["REDIS_URL"] == "redis://runtime/0"


@pytest.mark.asyncio
async def test_runtime_sre_agent_bootstraps_redis_indices_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_module()
    emitter = _FakeTaskEmitter()
    module._REDIS_BOOTSTRAP_COMPLETE = False
    module._REDIS_BOOTSTRAP_LOCK = asyncio.Lock()
    monkeypatch.setenv("REDIS_URL", "redis://runtime/0")

    create_calls: list[str] = []

    async def _fake_create_indices() -> bool:
        create_calls.append("create")
        return True

    async def _fake_tool(*, query: str) -> dict[str, Any]:
        return {"query": query}

    monkeypatch.setattr(
        module,
        "_load_mcp_tool_registry",
        lambda: {"redis_sre_knowledge_search": _fake_tool},
    )
    monkeypatch.setitem(
        sys.modules,
        "redis_sre_agent.core.redis",
        types.SimpleNamespace(create_indices=_fake_create_indices),
    )

    await module.runtime_sre_agent(
        {"tool": "redis_sre_knowledge_search", "arguments": {"query": "memory"}},
        emitter,
    )
    await module.runtime_sre_agent(
        {"tool": "redis_sre_knowledge_search", "arguments": {"query": "latency"}},
        emitter,
    )

    assert create_calls == ["create"]


def _set_fake_module(monkeypatch: pytest.MonkeyPatch, name: str, **attrs: Any) -> None:
    monkeypatch.setitem(sys.modules, name, types.SimpleNamespace(**attrs))


def test_conversation_history_helpers_handle_invalid_and_mixed_payloads(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _load_module()
    monkeypatch.setenv("RAK_APP_STATE_DIR", str(tmp_path))

    path = module._conversation_path("ctx")
    path.write_text("{", encoding="utf-8")
    assert module._load_conversation_history("ctx") == []

    path.write_text(json.dumps({"bad": "shape"}), encoding="utf-8")
    assert module._load_conversation_history("ctx") == []

    path.write_text(
        json.dumps(
            [
                {"role": "assistant", "content": "first"},
                {"role": "user", "content": "second"},
                "skip-me",
                {"role": "assistant", "content": "   "},
                {"role": "other", "content": "third"},
            ]
        ),
        encoding="utf-8",
    )
    history = module._load_conversation_history("ctx")
    assert [type(item).__name__ for item in history] == [
        "AIMessage",
        "HumanMessage",
        "HumanMessage",
    ]
    assert [item.content for item in history] == ["first", "second", "third"]

    module._append_conversation_history(
        "ctx",
        {"role": "assistant", "content": " latest "},
        {"role": "", "content": "skip"},
    )
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved[-1] == {"role": "assistant", "content": "latest"}


def test_append_conversation_history_truncates_and_recovers_from_bad_json(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _load_module()
    monkeypatch.setenv("RAK_APP_STATE_DIR", str(tmp_path))

    path = module._conversation_path("ctx-truncate")
    path.write_text("{bad json", encoding="utf-8")
    module._append_conversation_history("ctx-truncate", {"role": "user", "content": "one"})
    assert json.loads(path.read_text(encoding="utf-8")) == [{"role": "user", "content": "one"}]

    many_messages = [
        {"role": "assistant", "content": f"m-{index}"}
        for index in range(module.MAX_HISTORY_MESSAGES + 5)
    ]
    module._append_conversation_history("ctx-truncate", *many_messages)
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert len(saved) == module.MAX_HISTORY_MESSAGES
    assert saved[0]["content"] == "m-5"


def test_bootstrap_runtime_environment_sets_config_and_target_redis(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _load_module()
    runtime_config = tmp_path / "config.runtime.yaml"
    runtime_config.write_text("{}", encoding="utf-8")

    monkeypatch.delenv("SRE_AGENT_CONFIG", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("RAR_RUNTIME_REDIS_URL", raising=False)
    monkeypatch.setenv("TARGET_REDIS_URL", "redis://target/0")
    monkeypatch.setattr(module, "_runtime_config_path", lambda: runtime_config)

    module._bootstrap_runtime_environment()

    assert os.environ["SRE_AGENT_CONFIG"] == str(runtime_config)
    assert os.environ["REDIS_URL"] == "redis://target/0"


@pytest.mark.asyncio
async def test_ensure_runtime_redis_ready_handles_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_module()
    module._REDIS_BOOTSTRAP_COMPLETE = False
    module._REDIS_BOOTSTRAP_LOCK = asyncio.Lock()
    monkeypatch.setenv("REDIS_URL", "redis://runtime/0")

    async def _fake_create_indices() -> bool:
        return False

    _set_fake_module(monkeypatch, "redis_sre_agent.core.redis", create_indices=_fake_create_indices)

    with pytest.raises(RuntimeError, match="Failed to initialize runtime Redis indices"):
        await module._ensure_runtime_redis_ready()


@pytest.mark.asyncio
async def test_ensure_runtime_redis_ready_returns_if_completed_inside_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_module()
    module._REDIS_BOOTSTRAP_COMPLETE = False
    monkeypatch.setenv("REDIS_URL", "redis://runtime/0")

    class _CompletingLock:
        async def __aenter__(self) -> None:
            module._REDIS_BOOTSTRAP_COMPLETE = True

        async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
            return None

    async def _unexpected_create_indices() -> bool:
        raise AssertionError(
            "create_indices should not be called when bootstrap completes inside the lock"
        )

    module._REDIS_BOOTSTRAP_LOCK = _CompletingLock()
    _set_fake_module(
        monkeypatch, "redis_sre_agent.core.redis", create_indices=_unexpected_create_indices
    )

    await module._ensure_runtime_redis_ready()


def test_parse_scraper_names() -> None:
    module = _load_module()

    assert module._parse_scraper_names(None) is None
    assert module._parse_scraper_names("  ") is None
    assert module._parse_scraper_names("docs, kb , , cloud") == ["docs", "kb", "cloud"]


@pytest.mark.asyncio
async def test_pipeline_status_and_batch_helpers(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _load_module()
    init_args: list[tuple[Any, ...]] = []

    class _FakeOrchestrator:
        def __init__(
            self,
            artifacts_path: str,
            config: dict[str, Any] | None = None,
            scrapers: list[str] | None = None,
        ) -> None:
            init_args.append((artifacts_path, config, scrapers))

        async def get_pipeline_status(self) -> dict[str, Any]:
            return {"state": "ready"}

    _set_fake_module(
        monkeypatch,
        "redis_sre_agent.pipelines.orchestrator",
        PipelineOrchestrator=_FakeOrchestrator,
    )
    status = await module.redis_sre_get_pipeline_status(str(tmp_path / "artifacts"))
    assert status == {"state": "ready"}
    assert init_args == [(str(tmp_path / "artifacts"), None, None)]

    class _MissingStorage:
        def __init__(self, artifacts_path: str) -> None:
            self.base_path = Path(artifacts_path)

        def get_batch_manifest(self, batch_date: str) -> None:
            return None

    _set_fake_module(
        monkeypatch, "redis_sre_agent.pipelines.scraper.base", ArtifactStorage=_MissingStorage
    )
    missing = await module.redis_sre_get_pipeline_batch("2026-04-10", str(tmp_path / "artifacts"))
    assert missing["error"] == "Batch 2026-04-10 not found"

    class _PresentStorage:
        def __init__(self, artifacts_path: str) -> None:
            self.base_path = Path(artifacts_path)

        def get_batch_manifest(self, batch_date: str) -> dict[str, Any]:
            return {"total_documents": 2, "categories": {"runbook": 1}, "document_types": {"md": 2}}

    batch_dir = tmp_path / "artifacts" / "2026-04-10"
    batch_dir.mkdir(parents=True)
    (batch_dir / "ingestion_manifest.json").write_text(
        json.dumps({"status": "ok"}), encoding="utf-8"
    )
    _set_fake_module(
        monkeypatch, "redis_sre_agent.pipelines.scraper.base", ArtifactStorage=_PresentStorage
    )
    present = await module.redis_sre_get_pipeline_batch("2026-04-10", str(tmp_path / "artifacts"))
    assert present["total_documents"] == 2
    assert present["ingestion"] == {"status": "ok"}


@pytest.mark.asyncio
async def test_prepare_source_documents_handles_validation_and_ingestion(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _load_module()

    _set_fake_module(
        monkeypatch, "redis_sre_agent.pipelines.ingestion.processor", IngestionPipeline=object
    )
    _set_fake_module(monkeypatch, "redis_sre_agent.pipelines.scraper.base", ArtifactStorage=object)
    with pytest.raises(RuntimeError, match="Source directory does not exist"):
        await module.redis_sre_prepare_source_documents(source_dir=str(tmp_path / "missing"))

    source_dir = tmp_path / "source_documents"
    source_dir.mkdir()

    class _FakeStorage:
        def __init__(self, artifacts_path: str) -> None:
            self.base_path = Path(artifacts_path)
            self.current_date = "2026-04-09"
            self.current_batch_path = self.base_path / self.current_date
            self._dirs_created = True

    pipeline_calls: list[tuple[str, Any]] = []

    class _FakePipeline:
        def __init__(self, storage: _FakeStorage) -> None:
            self.storage = storage

        async def prepare_source_artifacts(self, source_path: Path, batch_date: str) -> int:
            pipeline_calls.append(("prepare", str(source_path), batch_date))
            return 3

        async def ingest_prepared_batch(self, batch_date: str) -> list[dict[str, Any]]:
            pipeline_calls.append(("ingest", batch_date))
            return [{"status": "success"}, {"status": "error"}, {"status": "success"}]

    _set_fake_module(
        monkeypatch,
        "redis_sre_agent.pipelines.ingestion.processor",
        IngestionPipeline=_FakePipeline,
    )
    _set_fake_module(
        monkeypatch, "redis_sre_agent.pipelines.scraper.base", ArtifactStorage=_FakeStorage
    )

    with pytest.raises(RuntimeError, match="Invalid batch date format"):
        await module.redis_sre_prepare_source_documents(
            source_dir=str(source_dir),
            batch_date="2026/04/09",
            artifacts_path=str(tmp_path / "artifacts"),
        )

    result = await module.redis_sre_prepare_source_documents(
        source_dir=str(source_dir),
        batch_date="2026-04-10",
        artifacts_path=str(tmp_path / "artifacts"),
    )
    assert result["prepared_count"] == 3
    assert result["ingestion"]["successful_documents"] == 2
    assert result["ingestion"]["failed_documents"] == 1
    assert pipeline_calls == [
        ("prepare", str(source_dir), "2026-04-10"),
        ("ingest", "2026-04-10"),
    ]

    pipeline_calls.clear()
    prepare_only = await module.redis_sre_prepare_source_documents(
        source_dir=str(source_dir),
        prepare_only=True,
        artifacts_path=str(tmp_path / "artifacts"),
    )
    assert prepare_only["prepare_only"] is True
    assert "ingestion" not in prepare_only
    assert pipeline_calls == [("prepare", str(source_dir), "2026-04-09")]


@pytest.mark.asyncio
async def test_run_pipeline_wrappers(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _load_module()
    calls: list[tuple[str, Any]] = []

    class _FakeOrchestrator:
        def __init__(
            self, artifacts_path: str, config: dict[str, Any], scrapers: list[str] | None = None
        ) -> None:
            calls.append(("init", artifacts_path, config, scrapers))

        async def run_full_pipeline(self, scrapers: list[str] | None) -> dict[str, Any]:
            calls.append(("full", scrapers))
            return {"mode": "full"}

        async def run_ingestion_pipeline(self, batch_date: str | None) -> dict[str, Any]:
            calls.append(("ingest", batch_date))
            return {"mode": "ingest"}

    _set_fake_module(
        monkeypatch,
        "redis_sre_agent.pipelines.orchestrator",
        PipelineOrchestrator=_FakeOrchestrator,
    )

    full = await module.redis_sre_run_pipeline_full(
        artifacts_path=str(tmp_path / "artifacts"),
        docs_path=str(tmp_path / "docs"),
        latest_only=True,
        scrapers="docs,cloud",
    )
    ingest = await module.redis_sre_run_pipeline_ingest(
        artifacts_path=str(tmp_path / "artifacts"),
        batch_date="2026-04-10",
        latest_only=True,
    )

    assert full == {"mode": "full"}
    assert ingest == {"mode": "ingest"}
    assert calls[0] == (
        "init",
        str(tmp_path / "artifacts"),
        {
            "redis_docs": {"latest_only": True},
            "redis_docs_local": {"latest_only": True, "docs_repo_path": str(tmp_path / "docs")},
            "ingestion": {"latest_only": True},
        },
        ["docs", "cloud"],
    )
    assert ("full", ["docs", "cloud"]) in calls
    assert (
        "init",
        str(tmp_path / "artifacts"),
        {"ingestion": {"latest_only": True}},
        None,
    ) in calls
    assert ("ingest", "2026-04-10") in calls


@pytest.mark.asyncio
async def test_runtime_progress_and_tool_envelope_helpers() -> None:
    module = _load_module()
    emitter = _FakeTaskEmitter()
    assert module._json_safe_mapping(None) is None

    class _ExplodingMapping(Mapping[str, Any]):
        def __iter__(self):
            raise TypeError("boom")

        def __len__(self) -> int:
            return 1

        def __getitem__(self, key: str) -> Any:
            raise KeyError(key)

        def items(self):
            return [("key", object())]

    progress = module.RuntimeProgressEmitter(emitter)
    await progress.emit("working", metadata=_ExplodingMapping())
    assert emitter.messages[0]["metadata"]["key"].startswith("<object object at")

    summary_text = module._tool_output_summary({"summary": "x" * 800})
    assert len(summary_text) == 500

    rendered_text = module._tool_output_summary({"data": {1: "one", "two": 2}})
    assert rendered_text.startswith("{1: 'one', 'two': 2}")

    await module._emit_tool_envelopes(
        emitter,
        [
            {
                "name": "search",
                "tool_key": "search-1",
                "status": "success",
                "args": {"query": "redis"},
                "data": {"hits": 2},
            },
            {"status": "error", "data": {"reason": "bad"}},
        ],
    )
    assert emitter.tool_calls[0]["status"] == "completed"
    assert emitter.tool_calls[0]["arguments"] == {"query": "redis"}
    assert emitter.tool_calls[1]["name"] == "tool_2"
    assert emitter.tool_calls[1]["status"] == "failed"
    assert emitter.tool_calls[1]["error_summary"] == '{"reason": "bad"}'


@pytest.mark.asyncio
async def test_resolve_agent_context_handles_success_and_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_module()
    _set_fake_module(
        monkeypatch,
        "redis_sre_agent.core.instances",
        get_instance_by_id=lambda instance_id: asyncio.sleep(0, result={"id": instance_id})
        if instance_id == "inst-1"
        else asyncio.sleep(0, result=None),
    )
    _set_fake_module(
        monkeypatch,
        "redis_sre_agent.core.clusters",
        get_cluster_by_id=lambda cluster_id: asyncio.sleep(0, result={"id": cluster_id})
        if cluster_id == "cluster-1"
        else asyncio.sleep(0, result=None),
    )

    context, instance, cluster = await module._resolve_agent_context(
        {"instance_id": " inst-1 ", "user_id": " user-1 "}
    )
    assert context == {"instance_id": "inst-1", "user_id": "user-1"}
    assert instance == {"id": "inst-1"}
    assert cluster is None

    context, instance, cluster = await module._resolve_agent_context({})
    assert context == {}
    assert instance is None
    assert cluster is None

    with pytest.raises(RuntimeError, match="Provide only one of instance_id or cluster_id"):
        await module._resolve_agent_context({"instance_id": "inst-1", "cluster_id": "cluster-1"})

    with pytest.raises(RuntimeError, match="Unknown instance_id: missing"):
        await module._resolve_agent_context({"instance_id": "missing"})

    with pytest.raises(RuntimeError, match="Unknown cluster_id: missing"):
        await module._resolve_agent_context({"cluster_id": "missing"})


@pytest.mark.asyncio
async def test_dispatch_chat_query_validates_message(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_module()

    with pytest.raises(RuntimeError, match="chat requests require a non-empty message"):
        await module._dispatch_chat_query({}, _FakeTaskEmitter())


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("requested_agent", "selected_type", "expected_label"),
    [
        ("triage", "triage", "triage"),
        ("chat", "chat", "chat"),
        ("knowledge", "knowledge", "knowledge"),
    ],
)
async def test_dispatch_chat_query_selects_requested_agents(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    requested_agent: str,
    selected_type: str,
    expected_label: str,
) -> None:
    module = _load_module()
    monkeypatch.setenv("RAK_APP_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("RAR_TASK_RUN_ID", "task-run-2")

    class _AgentResponse:
        def __init__(self, label: str) -> None:
            self.response = f"{label}:reply"
            self.search_results = []
            self.tool_envelopes = []

    class _NamedAgent:
        def __init__(self, label: str) -> None:
            self.label = label

        async def process_query(self, query: str, **kwargs: Any) -> _AgentResponse:
            assert query == "hello"
            return _AgentResponse(self.label)

    captured_chat_args: list[tuple[Any, Any]] = []

    async def _fake_resolve_agent_context(task_input: Mapping[str, Any]):
        return {"user_id": "runtime-user"}, {"id": "instance"}, {"id": "cluster"}

    async def _fake_route(*_: Any, **__: Any):
        return selected_type

    async def _fake_emit(*_: Any, **__: Any) -> None:
        return None

    monkeypatch.setattr(module, "_resolve_agent_context", _fake_resolve_agent_context)
    monkeypatch.setattr(module, "_emit_tool_envelopes", _fake_emit)
    _set_fake_module(
        monkeypatch,
        "redis_sre_agent.agent.chat_agent",
        get_chat_agent=lambda redis_instance=None, redis_cluster=None: captured_chat_args.append(
            (redis_instance, redis_cluster)
        )
        or _NamedAgent("chat"),
    )
    _set_fake_module(
        monkeypatch,
        "redis_sre_agent.agent.knowledge_agent",
        get_knowledge_agent=lambda: _NamedAgent("knowledge"),
    )
    _set_fake_module(
        monkeypatch,
        "redis_sre_agent.agent.langgraph_agent",
        get_sre_agent=lambda: _NamedAgent("triage"),
    )
    _set_fake_module(
        monkeypatch,
        "redis_sre_agent.agent.router",
        AgentType=type(
            "AgentType",
            (),
            {"REDIS_TRIAGE": "triage", "REDIS_CHAT": "chat", "KNOWLEDGE_ONLY": "knowledge"},
        ),
        route_to_appropriate_agent=_fake_route,
    )

    result = await module._dispatch_chat_query(
        {"message": "hello", "agent": requested_agent, "contextId": "ctx-explicit"},
        _FakeTaskEmitter(),
    )

    assert result["agent"] == expected_label
    assert result["reply"] == f"{expected_label}:reply"
    if requested_agent == "chat":
        assert captured_chat_args == [({"id": "instance"}, {"id": "cluster"})]


def test_load_configured_external_mcp_tools_maps_descriptions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_module()

    class _ToolConfig:
        def __init__(self, description: str | None = None) -> None:
            self.description = description

    class _ServerConfig:
        def __init__(self, tools: dict[str, Any] | None = None) -> None:
            self.tools = tools or {}

        @classmethod
        def model_validate(cls, payload: dict[str, Any]) -> "_ServerConfig":
            return cls(tools=payload.get("tools"))

    settings = types.SimpleNamespace(
        mcp_servers={
            "re_analyzer": {"tools": {"analyzer_list_accounts": _ToolConfig()}},
            "other": _ServerConfig(tools={"custom_tool": _ToolConfig("Custom description")}),
            "empty": _ServerConfig(),
        }
    )
    _set_fake_module(
        monkeypatch, "redis_sre_agent.core.config", MCPServerConfig=_ServerConfig, settings=settings
    )

    tools = module._load_configured_external_mcp_tools()

    assert tools == {
        "analyzer_list_accounts": {
            "server_name": "re_analyzer",
            "description": "Configured external MCP tool 'analyzer_list_accounts' from 're_analyzer'.",
        },
        "custom_tool": {
            "server_name": "other",
            "description": "Custom description",
        },
    }


@pytest.mark.asyncio
async def test_invoke_configured_external_mcp_tool_handles_errors_and_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_module()

    with pytest.raises(RuntimeError, match="Unsupported configured external MCP tool 'missing'"):
        await module._invoke_configured_external_mcp_tool("missing", {})

    class _ServerConfig:
        def __init__(self, tools: dict[str, Any] | None = None) -> None:
            self.tools = tools or {}

        @classmethod
        def model_validate(cls, payload: dict[str, Any]) -> "_ServerConfig":
            return cls(tools=payload.get("tools"))

    settings = types.SimpleNamespace(mcp_servers={})
    _set_fake_module(
        monkeypatch, "redis_sre_agent.core.config", MCPServerConfig=_ServerConfig, settings=settings
    )
    monkeypatch.setattr(
        module,
        "_load_configured_external_mcp_tools",
        lambda: {
            "analyzer_list_accounts": {"server_name": "re_analyzer", "description": "Analyzer"}
        },
    )

    with pytest.raises(RuntimeError, match="references unknown server 're_analyzer'"):
        await module._invoke_configured_external_mcp_tool("analyzer_list_accounts", {})

    provider_calls: list[tuple[str, Any, bool]] = []

    class _FakeProvider:
        def __init__(self, server_name: str, server_config: Any, use_pool: bool) -> None:
            provider_calls.append((server_name, server_config, use_pool))

        async def __aenter__(self) -> "_FakeProvider":
            return self

        async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
            return None

        async def _call_mcp_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
            return {"tool": tool_name, "arguments": arguments}

    settings.mcp_servers["re_analyzer"] = {"tools": {"analyzer_list_accounts": object()}}
    _set_fake_module(
        monkeypatch, "redis_sre_agent.tools.mcp.provider", MCPToolProvider=_FakeProvider
    )

    result = await module._invoke_configured_external_mcp_tool(
        "analyzer_list_accounts", {"limit": 1}
    )
    assert result == {"tool": "analyzer_list_accounts", "arguments": {"limit": 1}}
    assert provider_calls[0][0] == "re_analyzer"
    assert provider_calls[0][2] is False


@pytest.mark.asyncio
async def test_dispatch_mcp_tool_validation_and_supported_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_module()

    with pytest.raises(RuntimeError, match="mcp requests require a non-empty tool name"):
        await module._dispatch_mcp_tool({})

    with pytest.raises(RuntimeError, match="mcp arguments must be an object"):
        await module._dispatch_mcp_tool({"tool": "redis_sre_knowledge_search", "arguments": "bad"})

    monkeypatch.setattr(
        module,
        "_load_mcp_tool_registry",
        lambda: {"redis_sre_knowledge_search": lambda **kwargs: kwargs},
    )
    monkeypatch.setattr(
        module,
        "_load_configured_external_mcp_tools",
        lambda: {
            "analyzer_list_accounts": {"server_name": "re_analyzer", "description": "Analyzer"}
        },
    )
    with pytest.raises(
        RuntimeError, match="Supported tools: analyzer_list_accounts, redis_sre_knowledge_search"
    ):
        await module._dispatch_mcp_tool({"tool": "missing", "arguments": {}})


@pytest.mark.asyncio
async def test_dispatch_mcp_tool_executes_sync_builtin_with_runtime_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_module()
    seen_contexts: list[dict[str, Any]] = []

    class _ContextManager:
        def __init__(self, payload: dict[str, Any]) -> None:
            seen_contexts.append(payload)

        def __enter__(self) -> None:
            return None

        def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
            return None

    monkeypatch.setenv("RAR_TASK_RUN_ID", "task-123")
    monkeypatch.setattr(
        module, "_load_mcp_tool_registry", lambda: {"sync_tool": lambda **kwargs: {"echo": kwargs}}
    )
    monkeypatch.setattr(module, "_load_configured_external_mcp_tools", lambda: {})
    _set_fake_module(
        monkeypatch,
        "redis_sre_agent.mcp_server.task_contract",
        runtime_task_execution_context=lambda payload: _ContextManager(payload),
        tool_execution_contract=lambda name: {"nativeMode": "inline", "runtimeMode": name},
    )

    result = await module._dispatch_mcp_tool({"tool": "sync_tool", "arguments": {"query": "redis"}})

    assert result == {
        "ok": True,
        "mode": "mcp",
        "tool": "sync_tool",
        "result": {"echo": {"query": "redis"}},
    }
    assert seen_contexts == [{"outerTaskId": "task-123"}]


def test_build_mcp_capabilities_skips_duplicate_external_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_module()

    async def _fake_tool() -> dict[str, Any]:
        return {"ok": True}

    monkeypatch.setattr(module, "_load_mcp_tool_registry", lambda: {"dup_tool": _fake_tool})
    monkeypatch.setattr(
        module,
        "_load_configured_external_mcp_tools",
        lambda: {
            "dup_tool": {"server_name": "re_analyzer", "description": "duplicate"},
            "extra_tool": {"server_name": "re_analyzer", "description": "extra"},
        },
    )
    _set_fake_module(
        monkeypatch,
        "redis_sre_agent.mcp_server.task_contract",
        tool_execution_contract=lambda name: {"nativeMode": "inline", "runtimeMode": name},
    )

    capabilities = module._build_mcp_capabilities()
    names = [entry["name"] for entry in capabilities["tools"]]

    assert names.count("dup_tool") == 1
    assert "extra_tool" in names
