import json
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml
from langchain_core.messages import AIMessage

from redis_sre_agent.agent.chat_agent import ChatAgent
from redis_sre_agent.agent.models import AgentResponse
from redis_sre_agent.agent.router import AgentType
from redis_sre_agent.core.agent_memory import PreparedAgentTurnMemory, TurnMemoryContext
from redis_sre_agent.core.config import MCPServerConfig
from redis_sre_agent.core.instances import RedisInstance
from redis_sre_agent.core.tasks import TaskMetadata, TaskState, TaskStatus, TaskUpdate
from redis_sre_agent.core.threads import Message, Thread, ThreadMetadata
from redis_sre_agent.evaluation.injection import EvalInjectionOverrides
from redis_sre_agent.evaluation.runner import EvalRunner
from redis_sre_agent.evaluation.runtime import (
    EvalRuntime,
    _build_catalog_matches,
    _default_turn_processor,
    build_full_turn_context,
    run_full_turn_scenario,
)
from redis_sre_agent.evaluation.scenarios import EvalScenario, LLMMode
from redis_sre_agent.targets.contracts import (
    BindingResult,
    ProviderLoadRequest,
    PublicTargetBinding,
    TargetHandleRecord,
)
from redis_sre_agent.targets.registry import TargetIntegrationRegistry
from redis_sre_agent.tools.manager import ToolManager
from redis_sre_agent.tools.models import Tool, ToolCapability, ToolDefinition, ToolMetadata
from redis_sre_agent.tools.protocols import ToolProvider


@pytest.mark.asyncio
async def test_default_turn_processor_forwards_explicit_redis_client():
    redis_client = object()
    process_agent_turn = AsyncMock(return_value={"response": "ok"})

    with patch(
        "redis_sre_agent.core.docket_tasks._process_agent_turn_impl",
        process_agent_turn,
    ):
        result = await _default_turn_processor(
            thread_id="thread-1",
            message="hello",
            context={},
            task_id="task-1",
            redis_client=redis_client,
        )

    assert result == {"response": "ok"}
    process_agent_turn.assert_awaited_once_with(
        thread_id="thread-1",
        message="hello",
        context={},
        task_id="task-1",
        redis_client=redis_client,
    )


def _build_scenario(*, route_via_router: bool = True, agent: str | None = None) -> EvalScenario:
    return EvalScenario.model_validate(
        {
            "id": "enterprise-node-maintenance",
            "name": "Redis Enterprise node maintenance incident",
            "provenance": {
                "source_kind": "redis_docs",
                "source_pack": "redis-docs-curated",
                "source_pack_version": "2026-04-13",
                "golden": {
                    "expectation_basis": "human_from_docs",
                },
            },
            "execution": {
                "lane": "full_turn",
                "query": "Investigate failovers on the prod enterprise cluster.",
                "route_via_router": route_via_router,
                **({"agent": agent} if agent else {}),
            },
            "scope": {
                "turn_scope": {
                    "resolution_policy": "require_target",
                    "automation_mode": "automated",
                },
                "target_catalog": [
                    {
                        "handle": "tgt_cluster_prod_east",
                        "kind": "cluster",
                        "resource_id": "cluster-prod-east",
                        "display_name": "prod-east cluster",
                        "cluster_type": "redis_enterprise",
                        "capabilities": ["admin", "diagnostics", "metrics"],
                        "public_metadata": {"environment": "production"},
                    }
                ],
                "bound_targets": ["tgt_cluster_prod_east"],
            },
        }
    )


def _build_binding(
    *, thread_id: str = "thread-123", task_id: str = "task-123"
) -> PublicTargetBinding:
    return PublicTargetBinding(
        target_handle="tgt_cluster_prod_east",
        target_kind="cluster",
        display_name="prod-east cluster",
        capabilities=["admin", "diagnostics", "metrics"],
        public_metadata={"environment": "production"},
        thread_id=thread_id,
        task_id=task_id,
        resource_id="cluster-prod-east",
    )


def test_build_catalog_matches_persists_eval_target_seed():
    scenario = _build_scenario(route_via_router=False, agent="redis_triage")

    matches, existing = _build_catalog_matches(
        scenario,
        thread_id="thread-123",
        task_id="task-123",
    )

    assert len(matches) == 1
    candidate = matches[0]
    assert candidate.binding_subject == "cluster-prod-east"
    assert candidate.private_binding_ref["eval_target_seed"] == {
        "seed_kind": "cluster",
        "id": "cluster-prod-east",
        "name": "prod-east cluster",
        "cluster_type": "redis_enterprise",
        "environment": "production",
        "description": "Eval target seed for prod-east cluster",
        "admin_url": "https://eval-target.invalid:9443",
        "admin_username": "eval",
        "admin_password": "eval-password",
    }
    assert existing[("cluster", "cluster-prod-east")].target_handle == "tgt_cluster_prod_east"


def _build_instance_bound_scenario(*, route_via_router: bool = True) -> EvalScenario:
    return EvalScenario.model_validate(
        {
            "id": "instance-bound-runtime",
            "name": "Instance bound runtime",
            "provenance": {
                "source_kind": "synthetic",
                "source_pack": "fixture-pack",
                "source_pack_version": "2026-04-13",
                "golden": {
                    "expectation_basis": "human_authored",
                },
            },
            "execution": {
                "lane": "full_turn",
                "query": "Check memory pressure on the checkout cache.",
                "route_via_router": route_via_router,
            },
            "scope": {
                "turn_scope": {
                    "resolution_policy": "require_target",
                    "automation_mode": "automated",
                },
                "target_catalog": [
                    {
                        "handle": "tgt_instance_checkout",
                        "kind": "instance",
                        "resource_id": "inst-checkout-cache",
                        "display_name": "checkout-cache-prod",
                        "cluster_type": "oss_single",
                        "capabilities": ["diagnostics", "metrics"],
                        "public_metadata": {"environment": "production"},
                    }
                ],
                "bound_targets": ["tgt_instance_checkout"],
            },
        }
    )


def _build_instance_binding(
    *,
    thread_id: str = "thread-1",
    task_id: str = "task-1",
) -> PublicTargetBinding:
    return PublicTargetBinding(
        target_handle="tgt_instance_checkout",
        target_kind="instance",
        display_name="checkout-cache-prod",
        capabilities=["diagnostics", "metrics"],
        public_metadata={"environment": "production"},
        thread_id=thread_id,
        task_id=task_id,
        resource_id="inst-checkout-cache",
    )


@pytest.mark.asyncio
async def test_run_full_turn_scenario_rejects_live_llm_without_opt_in():
    base = _build_scenario()
    scenario = base.model_copy(
        update={"execution": base.execution.model_copy(update={"llm_mode": LLMMode.LIVE})}
    )

    with pytest.raises(PermissionError, match="allow_live_llm=True"):
        await run_full_turn_scenario(scenario)


def _write_fixture_full_turn_scenario(tmp_path: Path) -> EvalScenario:
    fixtures_dir = tmp_path / "fixtures"
    docs_dir = fixtures_dir / "docs"
    skills_dir = fixtures_dir / "skills"
    tickets_dir = fixtures_dir / "tickets"
    docs_dir.mkdir(parents=True)
    skills_dir.mkdir(parents=True)
    tickets_dir.mkdir(parents=True)

    (docs_dir / "maintenance-runbook.md").write_text(
        "\n".join(
            [
                "---",
                "name: maintenance-runbook",
                "title: Maintenance Runbook",
                "doc_type: runbook",
                "priority: critical",
                "pinned: true",
                "summary: Check maintenance mode before failover triage.",
                "source: fixture://docs/maintenance-runbook.md",
                "---",
                "Check maintenance mode before failover triage.",
            ]
        ),
        encoding="utf-8",
    )
    (docs_dir / "failover-guide.md").write_text(
        "\n".join(
            [
                "---",
                "document_hash: failover-guide",
                "name: failover-guide",
                "title: Failover Guide",
                "doc_type: knowledge",
                "category: incident",
                "priority: high",
                "summary: Investigate maintenance mode before any failover.",
                "source: fixture://docs/failover-guide.md",
                "---",
                "Investigate maintenance mode before any failover on enterprise clusters.",
            ]
        ),
        encoding="utf-8",
    )
    (skills_dir / "maintenance-mode-skill.md").write_text(
        "\n".join(
            [
                "---",
                "document_hash: maintenance-mode-skill",
                "name: maintenance-mode-skill",
                "title: Maintenance Mode Skill",
                "doc_type: skill",
                "priority: high",
                "summary: Check maintenance mode before using admin tooling.",
                "source: fixture://skills/maintenance-mode-skill.md",
                "---",
                "Before using admin tooling, check whether maintenance mode is enabled.",
            ]
        ),
        encoding="utf-8",
    )
    (tickets_dir / "RET-4421.yaml").write_text(
        yaml.safe_dump(
            {
                "document_hash": "RET-4421",
                "name": "RET-4421",
                "title": "Checkout cache failover",
                "doc_type": "support_ticket",
                "priority": "high",
                "summary": "Prior incident caused by maintenance mode on a node.",
                "source": "fixture://tickets/RET-4421.yaml",
                "content": "Prior incident caused by maintenance mode on a checkout cache node.",
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    scenario_path = tmp_path / "runtime-scenario.yaml"
    scenario_path.write_text(
        yaml.safe_dump(
            {
                "id": "runtime-fixture-backed-full-turn",
                "name": "Runtime fixture backed full turn",
                "provenance": {
                    "source_kind": "synthetic",
                    "source_pack": "fixture-pack",
                    "source_pack_version": "2026-04-13",
                    "golden": {
                        "expectation_basis": "human_authored",
                    },
                },
                "execution": {
                    "lane": "full_turn",
                    "query": "Investigate maintenance mode on the checkout cache.",
                    "route_via_router": False,
                    "agent": "chat",
                },
                "scope": {
                    "turn_scope": {
                        "resolution_policy": "require_target",
                        "automation_mode": "automated",
                    },
                    "target_catalog": [
                        {
                            "handle": "tgt_cluster_prod_east",
                            "kind": "cluster",
                            "resource_id": "cluster-prod-east",
                            "display_name": "prod-east cluster",
                            "cluster_type": "redis_enterprise",
                            "capabilities": ["admin", "diagnostics", "metrics"],
                            "public_metadata": {"environment": "production"},
                        }
                    ],
                    "bound_targets": ["tgt_cluster_prod_east"],
                },
                "knowledge": {
                    "mode": "full",
                    "version": "latest",
                    "pinned_documents": ["fixtures/docs/maintenance-runbook.md"],
                    "corpus": [
                        "fixtures/docs/failover-guide.md",
                        "fixtures/skills/maintenance-mode-skill.md",
                        "fixtures/tickets/RET-4421.yaml",
                    ],
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return EvalScenario.from_file(scenario_path)


class _FakeMCPProvider:
    def __init__(self, server_name, server_config, redis_instance=None, use_pool=True):
        self.provider_name = f"mcp_{server_name}"
        self.server_name = server_name
        self.server_config = server_config
        self.redis_instance = redis_instance
        self.use_pool = use_pool

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    def tools(self):
        tool_name = f"mcp_{self.server_name}_query_metrics"
        return [
            Tool(
                metadata=ToolMetadata(
                    name=tool_name,
                    description="query metrics",
                    capability=ToolCapability.METRICS,
                    provider_name=self.provider_name,
                ),
                definition=ToolDefinition(
                    name=tool_name,
                    description="query metrics",
                    capability=ToolCapability.METRICS,
                    parameters={"type": "object", "properties": {}},
                ),
                invoke=AsyncMock(return_value={"ok": True}),
            )
        ]


class _EvalRedisCommandProvider(ToolProvider):
    actual_call_count = 0

    @classmethod
    def reset(cls) -> None:
        cls.actual_call_count = 0

    @property
    def provider_name(self) -> str:
        return "redis_command"

    def create_tool_schemas(self):
        return [
            ToolDefinition(
                name=self._make_tool_name("info"),
                description="inspect Redis INFO",
                capability=ToolCapability.DIAGNOSTICS,
                parameters={
                    "type": "object",
                    "properties": {
                        "section": {"type": "string"},
                    },
                },
            )
        ]

    async def info(self, section=None):
        type(self).actual_call_count += 1
        return {
            "live": True,
            "section": section,
            "target_handle": getattr(self.redis_instance, "id", None),
        }


class _EvalRedisCommandBindingStrategy:
    strategy_name = "eval_runtime_strategy"

    async def bind(self, request):
        target_handle = request.handle_record.target_handle
        instance = RedisInstance(
            id=target_handle,
            name=request.handle_record.public_summary.display_name,
            connection_url="redis://fixture.invalid:6379/0",
            environment="production",
            usage="cache",
            description="fixture runtime target",
            instance_type="oss_single",
        )
        return BindingResult(
            public_summary=request.handle_record.public_summary,
            provider_loads=[
                ProviderLoadRequest(
                    provider_path="tests.unit.evaluation.test_runtime._EvalRedisCommandProvider",
                    provider_key=f"target:{target_handle}:redis_command",
                    target_handle=target_handle,
                    provider_context={"redis_instance_override": instance},
                )
            ],
        )


class _MemoryThreadManager:
    threads: dict[str, Thread] = {}
    traces: dict[str, dict[str, object]] = {}
    counter = 0

    @classmethod
    def reset(cls) -> None:
        cls.threads = {}
        cls.traces = {}
        cls.counter = 0

    def __init__(self, *, redis_client=None):
        self.redis_client = redis_client

    async def create_thread(
        self, *, user_id=None, session_id=None, initial_context=None, tags=None
    ):
        type(self).counter += 1
        thread_id = f"thread-{type(self).counter}"
        type(self).threads[thread_id] = Thread(
            thread_id=thread_id,
            context=dict(initial_context or {}),
            metadata=ThreadMetadata(user_id=user_id, session_id=session_id),
        )
        return thread_id

    async def set_thread_subject(self, thread_id, subject):
        type(self).threads[thread_id].metadata.subject = subject
        return True

    async def update_thread_context(self, thread_id, context_updates, merge=True):
        thread = type(self).threads[thread_id]
        if merge:
            thread.context.update(context_updates)
        else:
            thread.context = dict(context_updates)
        return True

    async def get_thread(self, thread_id):
        return type(self).threads[thread_id]

    async def append_messages(self, thread_id, messages):
        thread = type(self).threads[thread_id]
        for payload in messages:
            thread.messages.append(
                Message(
                    role=payload["role"],
                    content=payload["content"],
                    metadata=payload.get("metadata"),
                )
            )
        return True

    async def set_message_trace(self, **kwargs):
        message_id = kwargs["message_id"]
        type(self).traces[message_id] = kwargs
        return kwargs

    async def get_message_trace(self, message_id):
        return type(self).traces.get(message_id)

    async def _save_thread_state(self, thread):
        type(self).threads[thread.thread_id] = thread
        return True


class _MemoryTaskManager:
    tasks: dict[str, TaskState] = {}
    counter = 0

    @classmethod
    def reset(cls) -> None:
        cls.tasks = {}
        cls.counter = 0

    def __init__(self, *, redis_client=None):
        self.redis_client = redis_client

    async def create_task(self, *, thread_id, user_id=None, subject=None):
        type(self).counter += 1
        task_id = f"task-{type(self).counter}"
        type(self).tasks[task_id] = TaskState(
            task_id=task_id,
            thread_id=thread_id,
            metadata=TaskMetadata(user_id=user_id, subject=subject),
        )
        return task_id

    async def update_task_status(self, task_id, status):
        type(self).tasks[task_id].status = status
        return True

    async def add_task_update(self, task_id, message, update_type="progress", metadata=None):
        type(self).tasks[task_id].updates.append(
            TaskUpdate(message=message, update_type=update_type, metadata=metadata)
        )
        return True

    async def set_task_result(self, task_id, result):
        type(self).tasks[task_id].result = result
        return True

    async def set_task_error(self, task_id, error_message):
        task = type(self).tasks[task_id]
        task.error_message = error_message
        task.status = TaskStatus.FAILED
        return True

    async def get_task_state(self, task_id):
        return type(self).tasks.get(task_id)

    async def _publish_stream_update(self, *args, **kwargs):
        return True


@pytest.mark.asyncio
async def test_build_full_turn_context_compiles_bound_targets_and_agent_override():
    scenario = _build_scenario(route_via_router=False, agent="redis_triage")
    binding_service = AsyncMock()
    binding_service.build_and_persist_records.return_value = [_build_binding()]

    context, turn_scope = await build_full_turn_context(
        scenario,
        thread_id="thread-123",
        task_id="task-123",
        session_id="session-123",
        target_binding_service=binding_service,
    )

    assert context["requested_agent_type"] == "triage"
    assert context["attached_target_handles"] == ["tgt_cluster_prod_east"]
    assert context["target_bindings"][0]["resource_id"] == "cluster-prod-east"
    assert context["automated"] is True
    assert context["turn_scope"]["scope_kind"] == "target_bindings"
    assert turn_scope.scope_kind == "target_bindings"
    binding_service.build_and_persist_records.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_full_turn_scenario_creates_thread_task_and_calls_turn_processor(monkeypatch):
    scenario = _build_scenario()
    redis_client = object()
    turn_processor = AsyncMock(return_value={"response": "triage complete", "task_id": "task-123"})
    binding_service = AsyncMock()
    binding_service.build_and_persist_records.return_value = [_build_binding()]
    captured: dict[str, object] = {}

    class FakeThreadManager:
        def __init__(self, *, redis_client=None):
            captured["thread_manager_redis_client"] = redis_client

        async def create_thread(self, **kwargs):
            captured["create_thread_kwargs"] = kwargs
            return "thread-123"

        async def set_thread_subject(self, thread_id, subject):
            captured["set_thread_subject"] = (thread_id, subject)
            return True

        async def update_thread_context(self, thread_id, context_updates, merge=True):
            captured["update_thread_context"] = {
                "thread_id": thread_id,
                "context_updates": context_updates,
                "merge": merge,
            }
            return True

        async def get_thread(self, thread_id):
            context = captured["update_thread_context"]["context_updates"]  # type: ignore[index]
            return SimpleNamespace(context=context, messages=[{"role": "user"}])

    class FakeTaskManager:
        def __init__(self, *, redis_client=None):
            captured["task_manager_redis_client"] = redis_client

        async def create_task(self, **kwargs):
            captured["create_task_kwargs"] = kwargs
            return "task-123"

        async def get_task_state(self, task_id):
            return SimpleNamespace(status=SimpleNamespace(value="done"))

    monkeypatch.setattr("redis_sre_agent.evaluation.runtime.ThreadManager", FakeThreadManager)
    monkeypatch.setattr("redis_sre_agent.evaluation.runtime.TaskManager", FakeTaskManager)

    result = await run_full_turn_scenario(
        scenario,
        user_id="user-123",
        session_id="session-123",
        redis_client=redis_client,
        target_binding_service=binding_service,
        turn_processor=turn_processor,
    )

    assert captured["create_thread_kwargs"]["session_id"] == "session-123"  # type: ignore[index]
    assert captured["create_task_kwargs"] == {  # type: ignore[comparison-overlap]
        "thread_id": "thread-123",
        "user_id": "user-123",
        "subject": "Investigate failovers on the prod enterprise cluster.",
    }
    assert captured["update_thread_context"]["merge"] is False  # type: ignore[index]
    turn_kwargs = turn_processor.await_args.kwargs
    assert turn_kwargs["thread_id"] == "thread-123"
    assert turn_kwargs["task_id"] == "task-123"
    assert turn_kwargs["redis_client"] is redis_client
    assert turn_kwargs["context"]["original_query"] == scenario.execution.query
    assert turn_kwargs["context"]["eval_scenario_id"] == scenario.id
    assert (
        turn_kwargs["context"]["eval_scenario_provenance"]["source_pack"]
        == scenario.provenance.source_pack
    )
    assert turn_kwargs["context"]["turn_scope"]["scope_kind"] == "target_bindings"
    assert result.thread_id == "thread-123"
    assert result.task_id == "task-123"
    assert result.scenario_provenance["source_pack_version"] == "2026-04-13"
    assert result.turn_result["response"] == "triage complete"
    assert result.task_status == "done"


@pytest.mark.asyncio
async def test_run_full_turn_scenario_uses_production_turn_path_for_attached_scope(monkeypatch):
    scenario = _build_scenario(route_via_router=False, agent="chat")
    redis_client = object()
    binding_service = AsyncMock()
    binding_service.build_and_persist_records.return_value = [_build_binding()]
    stored_threads: dict[str, SimpleNamespace] = {}
    stored_tasks: dict[str, SimpleNamespace] = {}

    class FakeThreadManager:
        def __init__(self, *, redis_client=None):
            self.redis_client = redis_client

        async def create_thread(
            self, *, user_id=None, session_id=None, initial_context=None, tags=None
        ):
            stored_threads["thread-123"] = SimpleNamespace(
                thread_id="thread-123",
                context=dict(initial_context or {}),
                metadata=SimpleNamespace(
                    user_id=user_id,
                    session_id=session_id,
                    subject=None,
                ),
                messages=[],
            )
            return "thread-123"

        async def set_thread_subject(self, thread_id, subject):
            stored_threads[thread_id].metadata.subject = subject
            return True

        async def update_thread_context(self, thread_id, context_updates, merge=True):
            if merge:
                stored_threads[thread_id].context.update(context_updates)
            else:
                stored_threads[thread_id].context = dict(context_updates)
            return True

        async def get_thread(self, thread_id):
            return stored_threads[thread_id]

        async def append_messages(self, thread_id, messages):
            thread = stored_threads[thread_id]
            for message in messages:
                thread.messages.append(
                    SimpleNamespace(
                        role=message.get("role", "user"),
                        content=message.get("content", ""),
                        metadata=message.get("metadata"),
                        message_id=message.get("message_id"),
                    )
                )
            return True

        async def set_message_trace(self, **kwargs):
            stored_threads.setdefault("_traces", {})[kwargs["message_id"]] = kwargs
            return kwargs

        async def get_message_trace(self, message_id):
            return stored_threads.get("_traces", {}).get(message_id)

        async def _save_thread_state(self, thread):
            stored_threads[thread.thread_id] = thread
            return True

    class FakeTaskManager:
        def __init__(self, *, redis_client=None):
            self.redis_client = redis_client

        async def create_task(self, **kwargs):
            stored_tasks["task-123"] = SimpleNamespace(
                status=SimpleNamespace(value="created"),
                updates=[],
                result=None,
                error_message=None,
            )
            return "task-123"

        async def update_task_status(self, task_id, status):
            stored_tasks[task_id].status = status
            return True

        async def add_task_update(self, task_id, message, update_type, metadata=None):
            stored_tasks[task_id].updates.append(
                SimpleNamespace(
                    message=message,
                    update_type=update_type,
                    metadata=metadata,
                    timestamp="2026-04-13T00:00:00+00:00",
                )
            )
            return True

        async def set_task_result(self, task_id, result):
            stored_tasks[task_id].result = result
            return True

        async def set_task_error(self, task_id, error_message):
            stored_tasks[task_id].error_message = error_message
            return True

        async def get_task_state(self, task_id):
            return stored_tasks[task_id]

        async def _publish_stream_update(self, *args, **kwargs):
            return True

    prepared_memory = PreparedAgentTurnMemory(
        memory_service=MagicMock(),
        memory_context=TurnMemoryContext(
            system_prompt=None,
            user_working_memory=None,
            asset_working_memory=None,
        ),
        session_id="session-123",
        user_id="user-123",
        query=scenario.execution.query,
        instance_id=None,
        cluster_id=None,
        emitter=None,
    )
    prepared_memory.persist_response_fail_open = AsyncMock()

    mock_tool = MagicMock()
    mock_tool.name = "knowledge_test_skills_check"
    mock_tool_manager = MagicMock()
    mock_tool_manager.__aenter__.return_value = mock_tool_manager
    mock_tool_manager.__aexit__.return_value = None
    mock_tool_manager.get_tools.return_value = [mock_tool]
    mock_tool_manager.get_toolset_generation.return_value = 1

    fake_app = AsyncMock()
    fake_app.ainvoke.return_value = {
        "messages": [AIMessage(content="attached target answer")],
        "signals_envelopes": [],
    }
    fake_workflow = MagicMock()
    fake_workflow.compile.return_value = fake_app
    fake_handle_store = MagicMock()
    fake_handle_store.get_records = AsyncMock(return_value={"tgt_cluster_prod_east": object()})
    fake_checkpointer = MagicMock()
    fake_checkpointer.get_tuple.return_value = None

    @contextmanager
    def fake_open_graph_checkpointer():
        yield fake_checkpointer

    with (
        patch("redis_sre_agent.agent.chat_agent.create_llm") as mock_create_llm,
        patch("redis_sre_agent.agent.chat_agent.create_mini_llm") as mock_create_mini_llm,
    ):
        mock_llm = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm
        mock_create_llm.return_value = mock_llm
        mock_create_mini_llm.return_value = mock_llm
        agent = ChatAgent()

    monkeypatch.setattr("redis_sre_agent.evaluation.runtime.ThreadManager", FakeThreadManager)
    monkeypatch.setattr("redis_sre_agent.evaluation.runtime.TaskManager", FakeTaskManager)
    monkeypatch.setattr("redis_sre_agent.core.docket_tasks.ThreadManager", FakeThreadManager)
    monkeypatch.setattr("redis_sre_agent.core.docket_tasks.TaskManager", FakeTaskManager)

    with (
        patch("redis_sre_agent.core.docket_tasks.get_chat_agent", return_value=agent),
        patch(
            "redis_sre_agent.core.docket_tasks.route_to_appropriate_agent",
            new_callable=AsyncMock,
        ) as mock_router,
        patch(
            "redis_sre_agent.core.docket_tasks._extract_instance_details_from_message",
            return_value=None,
        ),
        patch(
            "redis_sre_agent.agent.chat_agent.prepare_agent_turn_memory",
            AsyncMock(return_value=prepared_memory),
        ) as mock_prepare_memory,
        patch(
            "redis_sre_agent.agent.chat_agent.ToolManager",
            return_value=mock_tool_manager,
        ) as mock_tool_manager_class,
        patch(
            "redis_sre_agent.agent.chat_agent.build_startup_knowledge_context",
            new=AsyncMock(return_value=""),
        ),
        patch(
            "redis_sre_agent.agent.chat_agent.open_graph_checkpointer",
            side_effect=fake_open_graph_checkpointer,
        ),
        patch(
            "redis_sre_agent.targets.get_target_handle_store",
            return_value=fake_handle_store,
        ),
        patch.object(agent, "_build_workflow", return_value=fake_workflow),
        patch("opentelemetry.trace.get_tracer") as mock_tracer,
    ):
        mock_span = MagicMock()
        mock_span.end = MagicMock()
        mock_span.set_attribute = MagicMock()
        mock_tracer.return_value.start_span.return_value = mock_span

        result = await run_full_turn_scenario(
            scenario,
            user_id="user-123",
            session_id="session-123",
            redis_client=redis_client,
            target_binding_service=binding_service,
        )

    mock_router.assert_not_called()
    assert mock_tool_manager_class.call_args.kwargs["thread_id"] == "thread-123"
    assert mock_tool_manager_class.call_args.kwargs["task_id"] == "task-123"
    assert mock_tool_manager_class.call_args.kwargs["redis_instance"] is None
    assert mock_tool_manager_class.call_args.kwargs["redis_cluster"] is None
    assert mock_tool_manager_class.call_args.kwargs["initial_toolset_generation"] == 1
    bindings = mock_tool_manager_class.call_args.kwargs["initial_target_bindings"]
    assert [binding.target_handle for binding in bindings] == ["tgt_cluster_prod_east"]
    prepared_context = mock_prepare_memory.await_args.kwargs["context"]
    assert prepared_context["original_query"] == scenario.execution.query
    assert prepared_context["requested_agent_type"] == "chat"
    assert prepared_context["turn_scope"]["scope_kind"] == "target_bindings"
    assert prepared_context["turn_scope"]["thread_id"] == "thread-123"
    assert result.thread_id == "thread-123"
    assert result.task_id == "task-123"
    assert result.task_status == "done"
    assert result.turn_result["response"] == "attached target answer"
    assert stored_tasks["task-123"].result["response"] == "attached target answer"


@pytest.mark.asyncio
async def test_run_full_turn_scenario_applies_runtime_overrides_to_real_provider_loading(
    monkeypatch,
):
    scenario = EvalScenario.model_validate(
        {
            "id": "runtime-override-provider-loading",
            "name": "Runtime override provider loading",
            "provenance": {
                "source_kind": "synthetic",
                "source_pack": "fixture-pack",
                "source_pack_version": "2026-04-13",
                "golden": {
                    "expectation_basis": "human_authored",
                },
            },
            "execution": {
                "lane": "full_turn",
                "query": "Check memory pressure on the checkout cache.",
                "route_via_router": True,
            },
        }
    )
    runtime_overrides = EvalInjectionOverrides(
        mcp_servers={
            "metrics_eval": MCPServerConfig(url="http://fixture-mcp.invalid"),
        }
    )
    seen: dict[str, object] = {}

    class FakeChatAgent:
        async def process_query(
            self,
            query,
            session_id,
            user_id,
            max_iterations=10,
            context=None,
            progress_emitter=None,
            conversation_history=None,
        ):
            seen["query"] = query
            seen["session_id"] = session_id
            seen["user_id"] = user_id
            seen["context"] = context
            seen["history_length"] = len(conversation_history or [])

            async with ToolManager(
                thread_id=session_id,
                task_id=context["task_id"],
                user_id=user_id,
            ) as tool_mgr:
                seen["tool_names"] = [tool.name for tool in tool_mgr.get_tools()]
                seen["toolset_generation"] = tool_mgr.get_toolset_generation()

            return AgentResponse(response="runtime path complete")

    _MemoryThreadManager.reset()
    _MemoryTaskManager.reset()
    monkeypatch.setattr("redis_sre_agent.evaluation.runtime.ThreadManager", _MemoryThreadManager)
    monkeypatch.setattr("redis_sre_agent.evaluation.runtime.TaskManager", _MemoryTaskManager)
    monkeypatch.setattr("redis_sre_agent.core.docket_tasks.ThreadManager", _MemoryThreadManager)
    monkeypatch.setattr("redis_sre_agent.core.docket_tasks.TaskManager", _MemoryTaskManager)
    monkeypatch.setattr(
        "redis_sre_agent.core.docket_tasks.route_to_appropriate_agent",
        AsyncMock(return_value=AgentType.REDIS_CHAT),
    )
    monkeypatch.setattr(
        "redis_sre_agent.core.docket_tasks.get_chat_agent",
        lambda redis_instance=None, redis_cluster=None: FakeChatAgent(),
    )
    monkeypatch.setattr(ToolManager, "_always_on_providers", [])
    monkeypatch.setattr(ToolManager, "_load_support_package_provider", AsyncMock())

    with (
        patch("redis_sre_agent.core.config.settings") as mock_settings,
        patch("redis_sre_agent.tools.mcp.provider.MCPToolProvider", new=_FakeMCPProvider),
        patch("opentelemetry.trace.get_tracer") as mock_tracer,
    ):
        mock_settings.mcp_servers = {}
        mock_span = MagicMock()
        mock_span.end = MagicMock()
        mock_span.set_attribute = MagicMock()
        mock_tracer.return_value.start_span.return_value = mock_span

        result = await run_full_turn_scenario(
            scenario,
            user_id="user-123",
            session_id="session-123",
            redis_client=object(),
            runtime_overrides=runtime_overrides,
        )

    assert result.thread_id == "thread-1"
    assert result.task_id == "task-1"
    assert result.task_status == "done"
    assert result.turn_context["turn_scope"]["scope_kind"] == "zero_scope"
    assert result.turn_result["response"] == "runtime path complete"
    assert seen["query"] == "Check memory pressure on the checkout cache."
    assert seen["session_id"] == "session-123"
    assert seen["user_id"] == "user-123"
    assert seen["history_length"] == 0
    assert seen["toolset_generation"] == 1
    assert "mcp_metrics_eval_query_metrics" in seen["tool_names"]


@pytest.mark.asyncio
async def test_run_full_turn_scenario_mounts_fake_mcp_catalog_and_invokes_real_provider(
    monkeypatch,
):
    scenario = EvalScenario.model_validate(
        {
            "id": "full-turn-fake-mcp",
            "name": "Full-turn fake MCP",
            "provenance": {
                "source_kind": "synthetic",
                "source_pack": "fixture-pack",
                "source_pack_version": "2026-04-14",
                "golden": {
                    "expectation_basis": "human_authored",
                },
            },
            "execution": {
                "lane": "full_turn",
                "query": "Check memory pressure on the checkout cache.",
                "route_via_router": True,
            },
            "tools": {
                "mcp_servers": {
                    "metrics_eval": {
                        "capability": "metrics",
                        "tools": {
                            "query_metrics": {
                                "description": "Query fixture memory pressure metrics.",
                                "input_schema": {
                                    "properties": {
                                        "query": {"type": "string"},
                                    },
                                    "required": ["query"],
                                },
                                "responders": [
                                    {
                                        "when": {
                                            "args_contains": {"query": "memory pressure"},
                                            "call_count": 1,
                                        },
                                        "result": {
                                            "series": "memory_pressure",
                                            "value": 91,
                                        },
                                        "state_updates": {"phase": "followup"},
                                    },
                                    {
                                        "when": {
                                            "state_contains": {"phase": "followup"},
                                        },
                                        "result": {
                                            "series": "memory_pressure",
                                            "value": 87,
                                        },
                                    },
                                ],
                            }
                        },
                    }
                }
            },
        }
    )
    seen: dict[str, object] = {}

    class FakeChatAgent:
        async def process_query(
            self,
            query,
            session_id,
            user_id,
            max_iterations=10,
            context=None,
            progress_emitter=None,
            conversation_history=None,
        ):
            seen["query"] = query
            seen["session_id"] = session_id
            seen["user_id"] = user_id

            async with ToolManager(
                thread_id=session_id,
                task_id=context["task_id"],
                user_id=user_id,
            ) as tool_mgr:
                tools = tool_mgr.get_tools()
                tool_name = tools[0].name
                seen["tool_names"] = [tool.name for tool in tools]
                seen["tool_capabilities"] = [tool.capability.value for tool in tools]
                seen["first_result"] = await tool_mgr.resolve_tool_call(
                    tool_name,
                    {"query": "memory pressure"},
                )
                seen["second_result"] = await tool_mgr.resolve_tool_call(
                    tool_name,
                    {"query": "memory pressure followup"},
                )

            return AgentResponse(response="fake MCP runtime complete")

    _MemoryThreadManager.reset()
    _MemoryTaskManager.reset()
    monkeypatch.setattr("redis_sre_agent.evaluation.runtime.ThreadManager", _MemoryThreadManager)
    monkeypatch.setattr("redis_sre_agent.evaluation.runtime.TaskManager", _MemoryTaskManager)
    monkeypatch.setattr("redis_sre_agent.core.docket_tasks.ThreadManager", _MemoryThreadManager)
    monkeypatch.setattr("redis_sre_agent.core.docket_tasks.TaskManager", _MemoryTaskManager)
    monkeypatch.setattr(
        "redis_sre_agent.core.docket_tasks.route_to_appropriate_agent",
        AsyncMock(return_value=AgentType.REDIS_CHAT),
    )
    monkeypatch.setattr(
        "redis_sre_agent.core.docket_tasks.get_chat_agent",
        lambda redis_instance=None, redis_cluster=None: FakeChatAgent(),
    )
    monkeypatch.setattr(ToolManager, "_always_on_providers", [])
    monkeypatch.setattr(ToolManager, "_load_support_package_provider", AsyncMock())

    with (
        patch("redis_sre_agent.core.config.settings") as mock_settings,
        patch("opentelemetry.trace.get_tracer") as mock_tracer,
        patch(
            "redis_sre_agent.tools.mcp.provider.streamablehttp_client",
            side_effect=AssertionError("network transport should not run"),
        ),
        patch(
            "redis_sre_agent.tools.mcp.provider.sse_client",
            side_effect=AssertionError("network transport should not run"),
        ),
        patch(
            "redis_sre_agent.tools.mcp.provider.stdio_client",
            side_effect=AssertionError("stdio transport should not run"),
        ),
    ):
        mock_settings.mcp_servers = {}
        mock_span = MagicMock()
        mock_span.end = MagicMock()
        mock_span.set_attribute = MagicMock()
        mock_tracer.return_value.start_span.return_value = mock_span

        result = await run_full_turn_scenario(
            scenario,
            user_id="user-123",
            session_id="session-123",
            redis_client=object(),
        )

    assert result.thread_id == "thread-1"
    assert result.task_id == "task-1"
    assert result.task_status == "done"
    assert result.turn_result["response"] == "fake MCP runtime complete"
    assert seen["query"] == "Check memory pressure on the checkout cache."
    assert seen["session_id"] == "session-123"
    assert seen["user_id"] == "user-123"
    assert len(seen["tool_names"]) == 1
    assert seen["tool_names"][0].endswith("_query_metrics")
    assert seen["tool_capabilities"] == ["metrics"]
    assert seen["first_result"]["status"] == "success"
    assert seen["first_result"]["data"]["value"] == 91
    assert seen["second_result"]["status"] == "success"
    assert seen["second_result"]["data"]["value"] == 87


@pytest.mark.asyncio
async def test_run_full_turn_scenario_installs_fixture_knowledge_backend_for_turn_processor(
    monkeypatch,
    tmp_path: Path,
):
    scenario = _write_fixture_full_turn_scenario(tmp_path)
    binding_service = AsyncMock()
    binding_service.build_and_persist_records.return_value = [
        _build_binding(thread_id="thread-1", task_id="task-1")
    ]

    async def turn_processor(**kwargs):
        from redis_sre_agent.agent.knowledge_context import build_startup_knowledge_context
        from redis_sre_agent.core.knowledge_helpers import (
            get_skill_helper,
            get_support_ticket_helper,
            search_knowledge_base_helper,
            search_support_tickets_helper,
        )

        startup_context = await build_startup_knowledge_context(
            query=kwargs["message"],
            version="latest",
            available_tools=[],
        )
        knowledge_search = await search_knowledge_base_helper(
            query='"maintenance mode"',
            version="latest",
        )
        ticket_search = await search_support_tickets_helper(
            query="RET-4421",
            version="latest",
        )
        skill = await get_skill_helper(
            skill_name="maintenance-mode-skill",
            version="latest",
        )
        ticket = await get_support_ticket_helper(ticket_id="RET-4421")
        return {
            "response": "fixture backend active",
            "startup_context": str(startup_context),
            "knowledge_document_hash": knowledge_search["results"][0]["document_hash"],
            "ticket_search_id": ticket_search["tickets"][0]["ticket_id"],
            "skill_content": skill["full_content"],
            "ticket_content": ticket["full_content"],
            "turn_scope_kind": kwargs["context"]["turn_scope"]["scope_kind"],
        }

    _MemoryThreadManager.reset()
    _MemoryTaskManager.reset()
    monkeypatch.setattr("redis_sre_agent.evaluation.runtime.ThreadManager", _MemoryThreadManager)
    monkeypatch.setattr("redis_sre_agent.evaluation.runtime.TaskManager", _MemoryTaskManager)

    with (
        patch(
            "redis_sre_agent.core.knowledge_helpers.get_vectorizer",
            side_effect=AssertionError("live vectorizer should not run"),
        ),
        patch(
            "redis_sre_agent.core.knowledge_helpers.get_knowledge_index",
            side_effect=AssertionError("live knowledge index should not run"),
        ),
        patch(
            "redis_sre_agent.core.knowledge_helpers.get_skills_index",
            side_effect=AssertionError("live skills index should not run"),
        ),
        patch(
            "redis_sre_agent.core.knowledge_helpers.get_support_tickets_index",
            side_effect=AssertionError("live support-ticket index should not run"),
        ),
    ):
        result = await run_full_turn_scenario(
            scenario,
            user_id="user-123",
            session_id="session-123",
            redis_client=object(),
            target_binding_service=binding_service,
            turn_processor=turn_processor,
        )

    assert result.thread_id == "thread-1"
    assert result.task_id == "task-1"
    assert result.task_status == "queued"
    assert result.turn_context["eval_source_pack"] == "fixture-pack"
    assert result.turn_context["eval_source_pack_version"] == "2026-04-13"
    assert result.scenario_provenance["source_pack"] == "fixture-pack"
    assert result.turn_context["requested_agent_type"] == "chat"
    assert result.turn_context["turn_scope"]["scope_kind"] == "target_bindings"
    assert "Pinned documents:" in result.turn_result["startup_context"]
    assert "maintenance-runbook" in result.turn_result["startup_context"]
    assert "maintenance-mode-skill" in result.turn_result["startup_context"]
    assert result.turn_result["knowledge_document_hash"] == "failover-guide"
    assert result.turn_result["ticket_search_id"] == "RET-4421"
    assert "maintenance mode is enabled" in result.turn_result["skill_content"]
    assert "checkout cache node" in result.turn_result["ticket_content"]
    assert result.turn_result["turn_scope_kind"] == "target_bindings"


@pytest.mark.asyncio
async def test_run_full_turn_scenario_virtualizes_target_bound_provider_execution(
    monkeypatch,
    tmp_path: Path,
):
    fixtures_dir = tmp_path / "fixtures" / "tools"
    fixtures_dir.mkdir(parents=True)
    (fixtures_dir / "info.json").write_text(
        json.dumps(
            {
                "mocked": True,
                "source": "scenario-fixture",
                "section": "memory",
            }
        ),
        encoding="utf-8",
    )
    scenario_path = tmp_path / "runtime-tool-virtualization.yaml"
    scenario_path.write_text(
        yaml.safe_dump(
            {
                "id": "runtime-tool-virtualization",
                "name": "Runtime tool virtualization",
                "provenance": {
                    "source_kind": "synthetic",
                    "source_pack": "fixture-pack",
                    "source_pack_version": "2026-04-13",
                    "golden": {
                        "expectation_basis": "human_authored",
                    },
                },
                "execution": {
                    "lane": "full_turn",
                    "query": "Inspect the checkout cache memory state.",
                    "route_via_router": False,
                    "agent": "chat",
                },
                "scope": {
                    "turn_scope": {
                        "resolution_policy": "require_target",
                        "automation_mode": "automated",
                    },
                    "target_catalog": [
                        {
                            "handle": "tgt_instance_checkout",
                            "kind": "instance",
                            "resource_id": "inst-checkout-cache",
                            "display_name": "checkout-cache-prod",
                            "cluster_type": "oss_single",
                            "capabilities": ["diagnostics"],
                            "public_metadata": {"environment": "production"},
                        }
                    ],
                    "bound_targets": ["tgt_instance_checkout"],
                },
                "tools": {
                    "redis_command": {
                        "info": {
                            "result": "fixtures/tools/info.json",
                        }
                    }
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    scenario = EvalScenario.from_file(scenario_path)
    binding = _build_instance_binding(thread_id="thread-1", task_id="task-1")
    binding_service = AsyncMock()
    binding_service.build_and_persist_records.return_value = [binding]

    record = TargetHandleRecord(
        target_handle="tgt_instance_checkout",
        discovery_backend="eval_runtime",
        binding_strategy="eval_runtime_strategy",
        binding_subject="inst-checkout-cache",
        public_summary=binding,
    )
    registry = TargetIntegrationRegistry(
        default_discovery_backend="eval_runtime",
        default_binding_strategy="eval_runtime_strategy",
    )
    registry.register_binding_strategy(_EvalRedisCommandBindingStrategy())
    handle_store = AsyncMock()
    handle_store.get_records.return_value = {"tgt_instance_checkout": record}

    async def turn_processor(**kwargs):
        turn_scope = kwargs["context"]["turn_scope"]
        bindings = [PublicTargetBinding.model_validate(item) for item in turn_scope["bindings"]]
        async with ToolManager(
            thread_id=kwargs["thread_id"],
            task_id=kwargs["task_id"],
            user_id="user-123",
            initial_target_bindings=bindings,
            initial_toolset_generation=turn_scope["toolset_generation"],
        ) as tool_mgr:
            tool_name = next(
                tool.name
                for tool in tool_mgr.get_tools()
                if tool.name.startswith("redis_command_") and tool.name.endswith("_info")
            )
            tool_result = await tool_mgr.resolve_tool_call(tool_name, {"section": "memory"})
            return {
                "tool_name": tool_name,
                "tool_result": tool_result,
                "toolset_generation": tool_mgr.get_toolset_generation(),
                "turn_scope_kind": turn_scope["scope_kind"],
            }

    _EvalRedisCommandProvider.reset()
    _MemoryThreadManager.reset()
    _MemoryTaskManager.reset()
    monkeypatch.setattr("redis_sre_agent.evaluation.runtime.ThreadManager", _MemoryThreadManager)
    monkeypatch.setattr("redis_sre_agent.evaluation.runtime.TaskManager", _MemoryTaskManager)
    monkeypatch.setattr(ToolManager, "_always_on_providers", [])
    monkeypatch.setattr(ToolManager, "_load_mcp_providers", AsyncMock())
    monkeypatch.setattr(ToolManager, "_load_support_package_provider", AsyncMock())

    with (
        patch("redis_sre_agent.tools.manager.get_target_handle_store", return_value=handle_store),
        patch(
            "redis_sre_agent.tools.manager.get_target_integration_registry",
            return_value=registry,
        ),
    ):
        result = await run_full_turn_scenario(
            scenario,
            user_id="user-123",
            session_id="session-123",
            redis_client=object(),
            target_binding_service=binding_service,
            turn_processor=turn_processor,
        )

    assert result.thread_id == "thread-1"
    assert result.task_id == "task-1"
    assert result.task_status == "queued"
    assert result.turn_context["requested_agent_type"] == "chat"
    assert result.turn_context["turn_scope"]["scope_kind"] == "target_bindings"
    assert result.turn_result["turn_scope_kind"] == "target_bindings"
    assert result.turn_result["toolset_generation"] == 1
    assert result.turn_result["tool_name"].startswith("redis_command_")
    assert result.turn_result["tool_result"] == {
        "mocked": True,
        "source": "scenario-fixture",
        "section": "memory",
    }
    assert _EvalRedisCommandProvider.actual_call_count == 0


@pytest.mark.asyncio
async def test_run_full_turn_scenario_supports_stateful_responder_sequences(
    monkeypatch,
):
    scenario = EvalScenario.model_validate(
        {
            "id": "runtime-stateful-tool-sequence",
            "name": "Runtime stateful tool sequence",
            "provenance": {
                "source_kind": "synthetic",
                "source_pack": "fixture-pack",
                "source_pack_version": "2026-04-13",
                "golden": {"expectation_basis": "human_authored"},
            },
            "execution": {
                "lane": "full_turn",
                "query": "Inspect the checkout cache memory state.",
                "route_via_router": False,
                "agent": "chat",
            },
            "scope": {
                "turn_scope": {
                    "resolution_policy": "require_target",
                    "automation_mode": "automated",
                },
                "target_catalog": [
                    {
                        "handle": "tgt_instance_checkout",
                        "kind": "instance",
                        "resource_id": "inst-checkout-cache",
                        "display_name": "checkout-cache-prod",
                        "cluster_type": "oss_single",
                        "capabilities": ["diagnostics"],
                        "public_metadata": {"environment": "production"},
                    }
                ],
                "bound_targets": ["tgt_instance_checkout"],
            },
            "tools": {
                "redis_command": {
                    "info": {
                        "responders": [
                            {
                                "when": {"call_count": 1},
                                "result": {"phase": "initial"},
                                "state_updates": {"step": "followup"},
                            },
                            {
                                "when": {"state_contains": {"step": "followup"}},
                                "result": {"phase": "followup"},
                            },
                        ]
                    }
                }
            },
        }
    )
    binding = _build_instance_binding(thread_id="thread-1", task_id="task-1")
    binding_service = AsyncMock()
    binding_service.build_and_persist_records.return_value = [binding]

    record = TargetHandleRecord(
        target_handle="tgt_instance_checkout",
        discovery_backend="eval_runtime",
        binding_strategy="eval_runtime_strategy",
        binding_subject="inst-checkout-cache",
        public_summary=binding,
    )
    registry = TargetIntegrationRegistry(
        default_discovery_backend="eval_runtime",
        default_binding_strategy="eval_runtime_strategy",
    )
    registry.register_binding_strategy(_EvalRedisCommandBindingStrategy())
    handle_store = AsyncMock()
    handle_store.get_records.return_value = {"tgt_instance_checkout": record}

    async def turn_processor(**kwargs):
        turn_scope = kwargs["context"]["turn_scope"]
        bindings = [PublicTargetBinding.model_validate(item) for item in turn_scope["bindings"]]
        async with ToolManager(
            thread_id=kwargs["thread_id"],
            task_id=kwargs["task_id"],
            user_id="user-123",
            initial_target_bindings=bindings,
            initial_toolset_generation=turn_scope["toolset_generation"],
        ) as tool_mgr:
            tool_name = next(
                tool.name
                for tool in tool_mgr.get_tools()
                if tool.name.startswith("redis_command_") and tool.name.endswith("_info")
            )
            first = await tool_mgr.resolve_tool_call(tool_name, {"section": "memory"})
            second = await tool_mgr.resolve_tool_call(tool_name, {"section": "memory"})
            return {
                "tool_name": tool_name,
                "first": first,
                "second": second,
            }

    _EvalRedisCommandProvider.reset()
    _MemoryThreadManager.reset()
    _MemoryTaskManager.reset()
    monkeypatch.setattr("redis_sre_agent.evaluation.runtime.ThreadManager", _MemoryThreadManager)
    monkeypatch.setattr("redis_sre_agent.evaluation.runtime.TaskManager", _MemoryTaskManager)
    monkeypatch.setattr(ToolManager, "_always_on_providers", [])
    monkeypatch.setattr(ToolManager, "_load_mcp_providers", AsyncMock())
    monkeypatch.setattr(ToolManager, "_load_support_package_provider", AsyncMock())

    with (
        patch("redis_sre_agent.tools.manager.get_target_handle_store", return_value=handle_store),
        patch(
            "redis_sre_agent.tools.manager.get_target_integration_registry",
            return_value=registry,
        ),
    ):
        result = await run_full_turn_scenario(
            scenario,
            user_id="user-123",
            session_id="session-123",
            redis_client=object(),
            target_binding_service=binding_service,
            turn_processor=turn_processor,
        )

    assert result.turn_result["first"] == {"phase": "initial"}
    assert result.turn_result["second"] == {"phase": "followup"}


@pytest.mark.asyncio
async def test_run_full_turn_scenario_enriches_turn_result_from_message_trace(monkeypatch):
    scenario = EvalScenario.model_validate(
        {
            "id": "runtime-message-trace-enrichment",
            "name": "Runtime message trace enrichment",
            "provenance": {
                "source_kind": "synthetic",
                "source_pack": "fixture-pack",
                "source_pack_version": "2026-04-13",
                "golden": {"expectation_basis": "human_authored"},
            },
            "execution": {
                "lane": "full_turn",
                "query": "Inspect the checkout cache memory state.",
                "route_via_router": False,
                "agent": "chat",
            },
        }
    )

    _MemoryThreadManager.reset()
    _MemoryTaskManager.reset()
    monkeypatch.setattr("redis_sre_agent.evaluation.runtime.ThreadManager", _MemoryThreadManager)
    monkeypatch.setattr("redis_sre_agent.evaluation.runtime.TaskManager", _MemoryTaskManager)

    async def turn_processor(**kwargs):
        thread_manager = _MemoryThreadManager(redis_client=kwargs["redis_client"])
        await thread_manager.set_message_trace(
            message_id="msg-1",
            tool_envelopes=[
                {
                    "tool_key": "knowledge_search",
                    "status": "success",
                    "args": {"query": "checkout cache memory"},
                    "data": {
                        "results": [
                            {
                                "document_hash": "memory-runbook",
                                "title": "Memory Runbook",
                                "source_kind": "runbook",
                            }
                        ]
                    },
                }
            ],
        )
        return {"response": "ok", "message_id": "msg-1"}

    result = await run_full_turn_scenario(
        scenario,
        user_id="user-123",
        session_id="session-123",
        redis_client=object(),
        turn_processor=turn_processor,
    )

    assert result.turn_result["tool_envelopes"][0]["tool_key"] == "knowledge_search"
    assert result.turn_result["search_results"][0]["document_hash"] == "memory-runbook"


@pytest.mark.asyncio
async def test_run_full_turn_scenario_supports_injected_tool_failures(
    monkeypatch,
):
    scenario = EvalScenario.model_validate(
        {
            "id": "runtime-injected-timeout",
            "name": "Runtime injected timeout",
            "provenance": {
                "source_kind": "synthetic",
                "source_pack": "fixture-pack",
                "source_pack_version": "2026-04-13",
                "golden": {"expectation_basis": "human_authored"},
            },
            "execution": {
                "lane": "full_turn",
                "query": "Inspect the checkout cache memory state.",
                "route_via_router": False,
                "agent": "chat",
            },
            "scope": {
                "turn_scope": {
                    "resolution_policy": "require_target",
                    "automation_mode": "automated",
                },
                "target_catalog": [
                    {
                        "handle": "tgt_instance_checkout",
                        "kind": "instance",
                        "resource_id": "inst-checkout-cache",
                        "display_name": "checkout-cache-prod",
                        "cluster_type": "oss_single",
                        "capabilities": ["diagnostics"],
                        "public_metadata": {"environment": "production"},
                    }
                ],
                "bound_targets": ["tgt_instance_checkout"],
            },
            "tools": {
                "redis_command": {
                    "info": {
                        "failure": {
                            "kind": "timeout",
                            "message": "simulated timeout",
                        }
                    }
                }
            },
        }
    )
    binding = _build_instance_binding(thread_id="thread-1", task_id="task-1")
    binding_service = AsyncMock()
    binding_service.build_and_persist_records.return_value = [binding]

    record = TargetHandleRecord(
        target_handle="tgt_instance_checkout",
        discovery_backend="eval_runtime",
        binding_strategy="eval_runtime_strategy",
        binding_subject="inst-checkout-cache",
        public_summary=binding,
    )
    registry = TargetIntegrationRegistry(
        default_discovery_backend="eval_runtime",
        default_binding_strategy="eval_runtime_strategy",
    )
    registry.register_binding_strategy(_EvalRedisCommandBindingStrategy())
    handle_store = AsyncMock()
    handle_store.get_records.return_value = {"tgt_instance_checkout": record}

    async def turn_processor(**kwargs):
        turn_scope = kwargs["context"]["turn_scope"]
        bindings = [PublicTargetBinding.model_validate(item) for item in turn_scope["bindings"]]
        async with ToolManager(
            thread_id=kwargs["thread_id"],
            task_id=kwargs["task_id"],
            user_id="user-123",
            initial_target_bindings=bindings,
            initial_toolset_generation=turn_scope["toolset_generation"],
        ) as tool_mgr:
            tool_name = next(
                tool.name
                for tool in tool_mgr.get_tools()
                if tool.name.startswith("redis_command_") and tool.name.endswith("_info")
            )
            await tool_mgr.resolve_tool_call(tool_name, {"section": "memory"})
            return {"unexpected": True}

    _EvalRedisCommandProvider.reset()
    _MemoryThreadManager.reset()
    _MemoryTaskManager.reset()
    monkeypatch.setattr("redis_sre_agent.evaluation.runtime.ThreadManager", _MemoryThreadManager)
    monkeypatch.setattr("redis_sre_agent.evaluation.runtime.TaskManager", _MemoryTaskManager)
    monkeypatch.setattr(ToolManager, "_always_on_providers", [])
    monkeypatch.setattr(ToolManager, "_load_mcp_providers", AsyncMock())
    monkeypatch.setattr(ToolManager, "_load_support_package_provider", AsyncMock())

    with (
        patch("redis_sre_agent.tools.manager.get_target_handle_store", return_value=handle_store),
        patch(
            "redis_sre_agent.tools.manager.get_target_integration_registry",
            return_value=registry,
        ),
    ):
        with pytest.raises(TimeoutError, match="simulated timeout"):
            await run_full_turn_scenario(
                scenario,
                user_id="user-123",
                session_id="session-123",
                redis_client=object(),
                target_binding_service=binding_service,
                turn_processor=turn_processor,
            )
    assert _EvalRedisCommandProvider.actual_call_count == 0


@pytest.mark.asyncio
async def test_eval_runtime_runs_full_turn_scenarios(monkeypatch):
    scenario = _build_scenario()
    run_full_turn = AsyncMock(return_value=SimpleNamespace(thread_id="thread-123"))
    monkeypatch.setattr("redis_sre_agent.evaluation.runtime.run_full_turn_scenario", run_full_turn)

    runtime = EvalRuntime(
        redis_client="redis-client",
        target_binding_service="binding-service",
        session_id="session-123",
    )
    result = await runtime.run(scenario, user_id="user-123", extra_context={"seed": "abc"})

    assert result.thread_id == "thread-123"
    run_full_turn.assert_awaited_once_with(
        scenario,
        user_id="user-123",
        session_id="session-123",
        redis_client="redis-client",
        target_binding_service="binding-service",
        context_overrides={"seed": "abc"},
        runtime_overrides=None,
    )


@pytest.mark.asyncio
async def test_eval_runner_dispatches_full_turn(monkeypatch):
    scenario = _build_scenario()
    run_full_turn = AsyncMock(return_value=SimpleNamespace(thread_id="thread-123"))
    monkeypatch.setattr("redis_sre_agent.evaluation.runner.run_full_turn_scenario", run_full_turn)

    runner = EvalRunner(redis_client="redis-client")
    result = await runner.run_scenario(scenario, user_id="user-123")

    assert result.thread_id == "thread-123"
    run_full_turn.assert_awaited_once_with(
        scenario,
        user_id="user-123",
        session_id=None,
        redis_client="redis-client",
        target_binding_service=None,
        context_overrides=None,
    )
