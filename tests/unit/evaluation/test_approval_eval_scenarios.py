from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
import yaml

from redis_sre_agent.agent.models import AgentResponse
from redis_sre_agent.core.approvals import (
    ApprovalDecision,
    ApprovalDecisionType,
    ApprovalRecord,
    ApprovalStatus,
    GraphResumeState,
)
from redis_sre_agent.core.docket_tasks import resume_task_after_approval
from redis_sre_agent.core.tasks import TaskMetadata, TaskState, TaskStatus, TaskUpdate
from redis_sre_agent.evaluation.fixture_layout import (
    golden_assertions_path,
    golden_expected_response_path,
    golden_metadata_path,
    scenario_manifest_path,
)
from redis_sre_agent.evaluation.runtime import load_eval_scenario, run_full_turn_scenario
from redis_sre_agent.tools.manager import ToolManager
from redis_sre_agent.tools.manager import settings as tool_manager_settings
from redis_sre_agent.tools.models import (
    Tool,
    ToolActionKind,
    ToolCapability,
    ToolDefinition,
    ToolMetadata,
)
from redis_sre_agent.tools.protocols import ToolProvider

REPO_ROOT = Path(__file__).resolve().parents[3]


def _load_contract(scenario_name: str) -> tuple[object, dict, str, dict]:
    scenario = load_eval_scenario(REPO_ROOT / scenario_manifest_path("prompt", scenario_name))
    metadata = yaml.safe_load(
        (REPO_ROOT / golden_metadata_path("prompt", scenario_name)).read_text(encoding="utf-8")
    )
    expected = (
        REPO_ROOT / golden_expected_response_path("prompt", scenario_name)
    ).read_text(encoding="utf-8")
    assertions = json.loads(
        (REPO_ROOT / golden_assertions_path("prompt", scenario_name)).read_text(encoding="utf-8")
    )
    return scenario, metadata, expected, assertions


class _EvalApprovalProvider(ToolProvider):
    actual_call_count = 0

    @classmethod
    def reset(cls) -> None:
        cls.actual_call_count = 0

    @property
    def provider_name(self) -> str:
        return "change_control"

    def create_tool_schemas(self):
        return [
            ToolDefinition(
                name=self._make_tool_name("enable_maintenance_mode"),
                description="Enable maintenance mode for a target.",
                capability=ToolCapability.UTILITIES,
                parameters={
                    "type": "object",
                    "properties": {
                        "reason": {"type": "string"},
                    },
                },
            )
        ]

    def tools(self) -> list[Tool]:
        schema = self.create_tool_schemas()[0]

        async def _invoke(args):
            type(self).actual_call_count += 1
            return {
                "status": "ok",
                "reason": args.get("reason"),
                "target_handle": getattr(self.redis_instance, "id", None),
            }

        return [
            Tool(
                metadata=ToolMetadata(
                    name=schema.name,
                    description=schema.description,
                    capability=schema.capability,
                    provider_name=self.provider_name,
                    requires_instance=self.requires_redis_instance,
                    action_kind=ToolActionKind.WRITE,
                ),
                definition=schema,
                invoke=_invoke,
            )
        ]


class _MemoryThreadManager:
    threads: dict[str, object] = {}
    traces: dict[str, dict[str, object]] = {}
    counter = 0

    @classmethod
    def reset(cls) -> None:
        cls.threads = {}
        cls.traces = {}
        cls.counter = 0

    def __init__(self, *, redis_client=None):
        self.redis_client = redis_client

    async def create_thread(self, *, user_id=None, session_id=None, initial_context=None, tags=None):
        type(self).counter += 1
        thread_id = f"thread-{type(self).counter}"
        type(self).threads[thread_id] = SimpleNamespace(
            thread_id=thread_id,
            context=dict(initial_context or {}),
            metadata=SimpleNamespace(user_id=user_id, session_id=session_id, subject=None),
            messages=[],
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
        type(self).threads[thread_id].messages.extend(messages)
        return True

    async def set_message_trace(self, **kwargs):
        type(self).traces[kwargs["message_id"]] = kwargs
        return kwargs

    async def get_message_trace(self, message_id):
        return type(self).traces.get(message_id)


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

    async def set_pending_approval(self, task_id, pending_approval):
        type(self).tasks[task_id].pending_approval = pending_approval
        return True

    async def set_resume_supported(self, task_id, resume_supported):
        type(self).tasks[task_id].resume_supported = resume_supported
        return True

    async def get_task_state(self, task_id):
        return type(self).tasks.get(task_id)

    async def _publish_stream_update(self, *args, **kwargs):
        return True


class _MemoryApprovalManager:
    approvals: dict[str, ApprovalRecord] = {}
    resume_states: dict[str, GraphResumeState] = {}

    @classmethod
    def reset(cls) -> None:
        cls.approvals = {}
        cls.resume_states = {}

    def __init__(self, *, redis_client=None):
        self.redis_client = redis_client

    async def create_approval(self, record):
        type(self).approvals[record.approval_id] = record
        return record

    async def get_approval(self, approval_id):
        return type(self).approvals.get(approval_id)

    async def get_resume_state(self, task_id):
        return type(self).resume_states.get(task_id)

    async def save_resume_state(self, state):
        type(self).resume_states[state.task_id] = state
        return state

    async def delete_resume_state(self, task_id):
        type(self).resume_states.pop(task_id, None)
        return True

    async def record_decision(self, approval_id, decision):
        record = type(self).approvals[approval_id]
        status = (
            ApprovalStatus.APPROVED
            if decision.decision is ApprovalDecisionType.APPROVED
            else ApprovalStatus.REJECTED
        )
        updated = record.model_copy(update={"status": status, "decision": decision})
        type(self).approvals[approval_id] = updated
        return updated


class _PauseForApprovalChatAgent:
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
        async with ToolManager(
            thread_id=context["turn_scope"]["thread_id"],
            task_id=context["task_id"],
            user_id=user_id,
        ) as tool_mgr:
            tool_name = next(
                tool.name
                for tool in tool_mgr.get_tools()
                if tool.name.startswith("change_control_")
                and tool.name.endswith("enable_maintenance_mode")
            )
            await tool_mgr.resolve_tool_call(
                tool_name,
                {"reason": "planned maintenance"},
            )
        raise AssertionError("approval gate should interrupt before the tool executes")


def _reset_runtime_state() -> None:
    _EvalApprovalProvider.reset()
    _MemoryApprovalManager.reset()
    _MemoryThreadManager.reset()
    _MemoryTaskManager.reset()


@pytest.mark.parametrize(
    ("scenario_name", "required_assertion_keys"),
    [
        (
            "approval-write-awaits-approval",
            {
                "expected_task_status",
                "expected_resume_supported",
                "expected_pending_approval_status",
                "expected_pending_tool_name_suffix",
            },
        ),
        (
            "approval-write-resume-approved",
            {
                "expected_initial_task_status",
                "resume_decision",
                "expected_final_task_status",
                "expected_final_response_contains",
            },
        ),
    ],
)
def test_approval_eval_contract_files_are_committed(
    scenario_name: str,
    required_assertion_keys: set[str],
):
    scenario, metadata, expected, assertions = _load_contract(scenario_name)

    assert scenario.id == f"prompt/{scenario_name}"
    assert metadata["scenario_id"] == scenario.id
    assert metadata["source_pack"] == "prompt-approvals"
    assert metadata["source_pack_version"] == "2026-04-23"
    assert expected.strip()
    assert required_assertion_keys.issubset(assertions)


@pytest.mark.asyncio
async def test_approval_pause_eval_fixture_runs_end_to_end(monkeypatch):
    scenario, metadata, expected, assertions = _load_contract("approval-write-awaits-approval")

    _reset_runtime_state()
    monkeypatch.setattr(tool_manager_settings, "agent_permission_mode", "read_write")
    monkeypatch.setattr(tool_manager_settings, "agent_approval_ttl_seconds", 900)
    monkeypatch.setattr("redis_sre_agent.evaluation.runtime.ThreadManager", _MemoryThreadManager)
    monkeypatch.setattr("redis_sre_agent.evaluation.runtime.TaskManager", _MemoryTaskManager)
    monkeypatch.setattr("redis_sre_agent.core.docket_tasks.ThreadManager", _MemoryThreadManager)
    monkeypatch.setattr("redis_sre_agent.core.docket_tasks.TaskManager", _MemoryTaskManager)
    monkeypatch.setattr(
        ToolManager,
        "_always_on_providers",
        ["tests.unit.evaluation.test_approval_eval_scenarios._EvalApprovalProvider"],
    )
    monkeypatch.setattr(ToolManager, "_load_mcp_providers", AsyncMock())
    monkeypatch.setattr(ToolManager, "_load_support_package_provider", AsyncMock())

    with (
        patch(
            "redis_sre_agent.core.docket_tasks.get_chat_agent",
            return_value=_PauseForApprovalChatAgent(),
        ),
        patch("redis_sre_agent.tools.manager.ApprovalManager", _MemoryApprovalManager),
    ):
        result = await run_full_turn_scenario(
            scenario,
            user_id="user-123",
            session_id="session-123",
            redis_client=object(),
        )

    pending = result.turn_result["pending_approval"]

    assert metadata["review_status"] == "reviewed"
    assert "awaiting_approval" in expected
    assert result.task_status == assertions["expected_task_status"]
    assert result.turn_result["status"] == assertions["expected_task_status"]
    assert result.turn_result["resume_supported"] is assertions["expected_resume_supported"]
    assert pending["status"] == assertions["expected_pending_approval_status"]
    assert pending["tool_name"].endswith(assertions["expected_pending_tool_name_suffix"])
    assert _EvalApprovalProvider.actual_call_count == assertions["expected_provider_call_count"]


@pytest.mark.asyncio
async def test_approval_resume_eval_fixture_runs_end_to_end(monkeypatch):
    scenario, metadata, expected, assertions = _load_contract("approval-write-resume-approved")

    _reset_runtime_state()
    monkeypatch.setattr(tool_manager_settings, "agent_permission_mode", "read_write")
    monkeypatch.setattr(tool_manager_settings, "agent_approval_ttl_seconds", 900)
    monkeypatch.setattr("redis_sre_agent.evaluation.runtime.ThreadManager", _MemoryThreadManager)
    monkeypatch.setattr("redis_sre_agent.evaluation.runtime.TaskManager", _MemoryTaskManager)
    monkeypatch.setattr("redis_sre_agent.core.docket_tasks.ThreadManager", _MemoryThreadManager)
    monkeypatch.setattr("redis_sre_agent.core.docket_tasks.TaskManager", _MemoryTaskManager)
    monkeypatch.setattr(
        ToolManager,
        "_always_on_providers",
        ["tests.unit.evaluation.test_approval_eval_scenarios._EvalApprovalProvider"],
    )
    monkeypatch.setattr(ToolManager, "_load_mcp_providers", AsyncMock())
    monkeypatch.setattr(ToolManager, "_load_support_package_provider", AsyncMock())

    with (
        patch(
            "redis_sre_agent.core.docket_tasks.get_chat_agent",
            return_value=_PauseForApprovalChatAgent(),
        ),
        patch("redis_sre_agent.tools.manager.ApprovalManager", _MemoryApprovalManager),
    ):
        pause_result = await run_full_turn_scenario(
            scenario,
            user_id="user-123",
            session_id="session-123",
            redis_client=object(),
        )

    pending = pause_result.turn_result["pending_approval"]
    approval_record = _MemoryApprovalManager.approvals[pending["approval_id"]].model_copy(
        update={"graph_type": "chat"}
    )
    _MemoryApprovalManager.approvals[approval_record.approval_id] = approval_record
    _MemoryApprovalManager.resume_states[pause_result.task_id] = GraphResumeState(
        task_id=pause_result.task_id,
        thread_id=pause_result.thread_id,
        graph_thread_id=approval_record.graph_thread_id,
        graph_type=approval_record.graph_type,
        graph_version=approval_record.graph_version,
        checkpoint_ns="agent_turn",
        checkpoint_id="ckpt-1",
        waiting_reason="approval_required",
        pending_approval_id=approval_record.approval_id,
        pending_interrupt_id=approval_record.interrupt_id,
    )

    resume_agent = AsyncMock()
    resume_agent.resume_query = AsyncMock(
        return_value=AgentResponse(response="Applied the change.", tool_envelopes=[])
    )

    with (
        patch(
            "redis_sre_agent.core.docket_tasks.TaskManager",
            return_value=_MemoryTaskManager(redis_client=object()),
        ),
        patch(
            "redis_sre_agent.core.docket_tasks.ThreadManager",
            return_value=_MemoryThreadManager(redis_client=object()),
        ),
        patch(
            "redis_sre_agent.core.docket_tasks.ApprovalManager",
            return_value=_MemoryApprovalManager(redis_client=object()),
        ),
        patch("redis_sre_agent.core.docket_tasks.get_instance_by_id", new=AsyncMock()),
        patch("redis_sre_agent.core.docket_tasks.get_cluster_by_id", new=AsyncMock()),
        patch("redis_sre_agent.agent.chat_agent.ChatAgent", return_value=resume_agent),
    ):
        resume_result = await resume_task_after_approval(
            task_id=pause_result.task_id,
            approval_id=approval_record.approval_id,
            decision=assertions["resume_decision"],
        )

    final_task = _MemoryTaskManager.tasks[pause_result.task_id]

    assert metadata["review_status"] == "reviewed"
    assert "pause in `awaiting_approval`" in expected
    assert pause_result.task_status == assertions["expected_initial_task_status"]
    assert _EvalApprovalProvider.actual_call_count == assertions["expected_provider_call_count_before_resume"]
    assert final_task.status == TaskStatus(assertions["expected_final_task_status"])
    assert assertions["expected_final_response_contains"] in resume_result["response"]["response"]
    assert final_task.result == resume_result
