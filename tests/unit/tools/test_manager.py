"""Tests for ToolManager."""

from contextlib import AsyncExitStack
from unittest.mock import AsyncMock, patch

import pytest
from langgraph.errors import GraphInterrupt
from langgraph.types import Interrupt

from redis_sre_agent.core.approvals import (
    ActionExecutionLedger,
    ActionExecutionStatus,
    ApprovalRecord,
    ApprovalRequiredError,
    ApprovalStatus,
    GraphResumeState,
    build_action_hash,
)
from redis_sre_agent.core.clusters import RedisCluster, RedisClusterType
from redis_sre_agent.core.config import MCPServerConfig
from redis_sre_agent.core.instances import RedisInstance
from redis_sre_agent.core.targets import TargetBinding
from redis_sre_agent.targets.contracts import (
    BindingResult,
    ProviderLoadRequest,
    TargetHandleRecord,
)
from redis_sre_agent.targets.fake_integration import (
    FakeAuthenticatedClientFactory,
    FakeTargetBindingStrategy,
)
from redis_sre_agent.targets.registry import TargetIntegrationRegistry
from redis_sre_agent.tools.manager import (
    ToolManager,
    _command_is_available,
    _missing_local_mcp_arg_path,
)
from redis_sre_agent.tools.manager import settings as manager_settings
from redis_sre_agent.tools.models import (
    Tool,
    ToolActionKind,
    ToolCapability,
    ToolDefinition,
    ToolMetadata,
)
from redis_sre_agent.tools.protocols import ToolProvider


class FakeTargetToolProvider(ToolProvider):
    """Minimal provider used to verify alternate binding strategies can attach tools."""

    @property
    def provider_name(self) -> str:
        return "fake_target"

    def create_tool_schemas(self):
        return [
            ToolDefinition(
                name=self._make_tool_name("inspect"),
                description="Inspect a mock target",
                capability=ToolCapability.UTILITIES,
                parameters={"type": "object", "properties": {}},
            )
        ]

    async def inspect(self):
        return {"status": "ok"}


class MockBindingStrategy:
    strategy_name = "mock_strategy"

    async def bind(self, request):
        return BindingResult(
            public_summary=request.handle_record.public_summary,
            provider_loads=[
                ProviderLoadRequest(
                    provider_path="tests.unit.tools.test_manager.FakeTargetToolProvider",
                    provider_key=f"target:{request.handle_record.target_handle}:fake_target",
                    target_handle=request.handle_record.target_handle,
                    provider_context={"always_on": True},
                )
            ],
        )


def _register_tool(
    mgr: ToolManager,
    *,
    name: str,
    action_kind: ToolActionKind,
    invoke: AsyncMock,
    description: str,
    capability: ToolCapability = ToolCapability.UTILITIES,
    provider_name: str = "stub_default",
) -> None:
    tool = Tool(
        metadata=ToolMetadata(
            name=name,
            description=description,
            capability=capability,
            provider_name=provider_name,
            action_kind=action_kind,
        ),
        definition=ToolDefinition(
            name=name,
            description=description,
            capability=capability,
            parameters={"type": "object", "properties": {}},
        ),
        invoke=invoke,
    )

    class _Provider:
        def __init__(self, provider_name: str, operation_name: str):
            self.provider_name = provider_name
            self._operation_name = operation_name

        def resolve_operation(self, tool_name, args):
            return self._operation_name

    provider = _Provider(provider_name, name)
    mgr._tools.append(tool)
    mgr._tool_by_name[name] = tool
    mgr._routing_table[name] = provider


@pytest.mark.asyncio
async def test_tool_manager_initialization():
    """Test that ToolManager initializes and loads knowledge provider."""
    async with ToolManager() as mgr:
        tools = mgr.get_tools()

        # Should have at least knowledge tools
        assert len(tools) >= 2

        # All tools should be ToolDefinition objects
        for tool in tools:
            assert isinstance(tool, ToolDefinition)
            assert tool.name
            assert tool.description
            assert tool.parameters

        # Should have routing table entries
        assert len(mgr._routing_table) == len(tools)


@pytest.mark.asyncio
async def test_tool_manager_knowledge_tools():
    """Test that knowledge tools are loaded without instance."""
    async with ToolManager() as mgr:
        tools = mgr.get_tools()
        tool_names = [t.name for t in tools]

        # Without an instance, only knowledge tools should be loaded
        knowledge_tools = [n for n in tool_names if "knowledge_" in n]
        prometheus_tools = [n for n in tool_names if "prometheus_" in n]
        redis_command_tools = [n for n in tool_names if "redis_command_" in n]

        # Knowledge tools (always loaded)
        assert len(knowledge_tools) == 9
        assert any("target_discovery_" in n and "resolve_redis_targets" in n for n in tool_names)
        assert any("target_discovery_" in n and "list_known_redis_targets" in n for n in tool_names)
        assert any("search" in n for n in knowledge_tools)
        assert any("ingest" in n for n in knowledge_tools)
        assert any("get_all_fragments" in n for n in knowledge_tools)
        assert any("get_related_fragments" in n for n in knowledge_tools)
        assert any("skills_check" in n for n in knowledge_tools)
        assert any("get_skill" in n for n in knowledge_tools)
        assert any("get_skill_resource" in n for n in knowledge_tools)
        assert any("search_support_tickets" in n for n in knowledge_tools)
        assert any("get_support_ticket" in n for n in knowledge_tools)

        tickets_tools = mgr.get_tools_for_capability(ToolCapability.TICKETS)
        ticket_tool_names = [t.name for t in tickets_tools]
        assert any("search_support_tickets" in n for n in ticket_tool_names)
        assert any("get_support_ticket" in n for n in ticket_tool_names)

        # Instance-specific tools should NOT be loaded without an instance
        assert len(prometheus_tools) == 0
        assert len(redis_command_tools) == 0


def test_get_tools_for_llm_prioritizes_target_discovery_and_redis_diagnostics():
    mgr = ToolManager()

    _register_tool(
        mgr,
        name="mcp_github_deadbe_search_repositories",
        action_kind=ToolActionKind.READ,
        invoke=AsyncMock(return_value={"status": "ok"}),
        description="Search repositories",
        capability=ToolCapability.REPOS,
        provider_name="mcp_github",
    )
    _register_tool(
        mgr,
        name="knowledge_deadbe_search",
        action_kind=ToolActionKind.READ,
        invoke=AsyncMock(return_value={"status": "ok"}),
        description="Search knowledge",
        capability=ToolCapability.KNOWLEDGE,
        provider_name="knowledge",
    )
    _register_tool(
        mgr,
        name="target_discovery_deadbe_resolve_redis_targets",
        action_kind=ToolActionKind.READ,
        invoke=AsyncMock(return_value={"status": "ok"}),
        description="Resolve Redis targets",
        capability=ToolCapability.UTILITIES,
        provider_name="target_discovery",
    )
    _register_tool(
        mgr,
        name="redis_command_deadbe_info",
        action_kind=ToolActionKind.READ,
        invoke=AsyncMock(return_value={"status": "ok"}),
        description="Get Redis INFO",
        capability=ToolCapability.DIAGNOSTICS,
        provider_name="redis_command",
    )

    tool_names = [tool.name for tool in mgr.get_tools_for_llm(max_tools=2)]

    assert tool_names == [
        "target_discovery_deadbe_resolve_redis_targets",
        "redis_command_deadbe_info",
    ]


@pytest.mark.asyncio
async def test_attach_bound_targets_scopes_instance_tools_to_opaque_handle():
    """Attached targets should re-scope providers to the opaque target handle."""
    binding = TargetBinding(
        target_handle="tgt_opaque_1",
        target_kind="instance",
        resource_id="inst-1",
        display_name="checkout-cache-prod",
        capabilities=["redis", "diagnostics"],
    )
    instance = RedisInstance(
        id="inst-1",
        name="checkout-cache-prod",
        connection_url="redis://localhost:6379",
        environment="production",
        usage="cache",
        description="test",
        instance_type="oss_single",
    )

    mgr = ToolManager()
    mgr._toolset_generation = 1
    with (
        patch(
            "redis_sre_agent.core.instances.get_instance_by_id",
            new=AsyncMock(return_value=instance),
        ),
        patch.object(mgr, "_load_instance_scoped_providers", new=AsyncMock()) as mock_load,
    ):
        attached = await mgr.attach_bound_targets([binding])

    assert attached == [binding]
    scoped_instance = mock_load.await_args.args[0]
    assert scoped_instance.id == "tgt_opaque_1"
    assert scoped_instance.name == "checkout-cache-prod"
    assert mgr.get_toolset_generation() == 2


@pytest.mark.asyncio
async def test_attach_bound_targets_uses_registered_strategy_and_private_handle_record():
    """Alternate binding strategies should attach tools without target_kind branching."""
    binding = TargetBinding(
        target_handle="tgt_alt_1",
        target_kind="custom",
        display_name="alternate target",
        capabilities=["custom"],
        public_metadata={"environment": "test"},
    )
    record = TargetHandleRecord(
        target_handle="tgt_alt_1",
        discovery_backend="mock_backend",
        binding_strategy="mock_strategy",
        binding_subject="private-subject-1",
        public_summary=binding,
    )
    registry = TargetIntegrationRegistry(
        default_discovery_backend="mock_backend",
        default_binding_strategy="mock_strategy",
    )
    registry.register_binding_strategy(MockBindingStrategy())
    mock_store = AsyncMock()
    mock_store.get_records.return_value = {"tgt_alt_1": record}

    async with ToolManager() as mgr:
        with (
            patch("redis_sre_agent.tools.manager.get_target_handle_store", return_value=mock_store),
            patch(
                "redis_sre_agent.tools.manager.get_target_integration_registry",
                return_value=registry,
            ),
        ):
            attached = await mgr.attach_bound_targets([binding])

        assert attached == [binding]
        assert any("fake_target_" in tool.name for tool in mgr.get_tools())
        assert mgr.get_attached_target_bindings() == [binding]


@pytest.mark.asyncio
async def test_attach_bound_targets_supports_repo_fake_authenticated_integration():
    """The repo-backed fake integration should load a live provider through ToolManager."""

    binding = TargetBinding(
        target_handle="tgt_fake_auth_1",
        target_kind="instance",
        display_name="demo fake cache",
        capabilities=["fake", "auth"],
        public_metadata={"environment": "test"},
    )
    record = TargetHandleRecord(
        target_handle="tgt_fake_auth_1",
        discovery_backend="fake_demo",
        binding_strategy="fake_authenticated",
        binding_subject="fake-demo-cache",
        private_binding_ref={
            "username": "demo-user",
            "token": "demo-token",
            "audience": "fake-control-plane",
        },
        public_summary=binding,
    )
    registry = TargetIntegrationRegistry(
        default_discovery_backend="fake_demo",
        default_binding_strategy="fake_authenticated",
    )
    registry.register_binding_strategy(FakeTargetBindingStrategy())
    registry.register_client_factory(FakeAuthenticatedClientFactory())
    mock_store = AsyncMock()
    mock_store.get_records.return_value = {"tgt_fake_auth_1": record}

    mgr = ToolManager()
    mgr._stack = AsyncExitStack()
    await mgr._stack.__aenter__()
    try:
        with (
            patch("redis_sre_agent.tools.manager.get_target_handle_store", return_value=mock_store),
            patch(
                "redis_sre_agent.tools.manager.get_target_integration_registry",
                return_value=registry,
            ),
            patch(
                "redis_sre_agent.targets.registry.get_target_integration_registry",
                return_value=registry,
            ),
        ):
            attached = await mgr.attach_bound_targets([binding])

            assert attached == [binding]

            auth_tools = [
                tool.name
                for tool in mgr.get_tools()
                if "fake_target_" in tool.name and tool.name.endswith("_auth_status")
            ]
            assert len(auth_tools) == 1

            auth_result = await mgr.resolve_tool_call(auth_tools[0], {})
    finally:
        await mgr._stack.__aexit__(None, None, None)

    assert auth_result["status"] == "success"
    assert auth_result["authenticated"] is True
    assert auth_result["target_handle"] == "tgt_fake_auth_1"
    assert auth_result["username"] == "demo-user"
    assert auth_result["audience"] == "fake-control-plane"
    assert auth_result["token_suffix"] == "oken"


@pytest.mark.asyncio
async def test_tool_manager_executes_read_tool_without_interrupt(monkeypatch):
    """Read tools should execute directly through the shared manager boundary."""
    mgr = ToolManager(thread_id="thread-1", task_id="task-1")
    invoke = AsyncMock(return_value={"status": "ok", "value": 42})
    _register_tool(
        mgr,
        name="stub_default_fetch_status",
        action_kind=ToolActionKind.READ,
        invoke=invoke,
        description="Fetch status",
    )
    monkeypatch.setattr(manager_settings, "agent_permission_mode", "read_write")

    result = await mgr.resolve_tool_call("stub_default_fetch_status", {"scope": "demo"})

    assert result == {"status": "ok", "value": 42}
    invoke.assert_awaited_once_with({"scope": "demo"})


@pytest.mark.asyncio
async def test_tool_manager_blocks_unknown_tool_kind(monkeypatch):
    """Unclassified tools should fail closed without invoking the provider."""
    mgr = ToolManager(thread_id="thread-1", task_id="task-1")
    invoke = AsyncMock(return_value={"status": "should_not_run"})
    _register_tool(
        mgr,
        name="stub_default_dynamic_tool",
        action_kind=ToolActionKind.UNKNOWN,
        invoke=invoke,
        description="Dynamic tool",
    )
    monkeypatch.setattr(manager_settings, "agent_permission_mode", "read_write")

    result = await mgr.resolve_tool_call("stub_default_dynamic_tool", {"scope": "demo"})

    assert result["status"] == "blocked"
    assert result["reason"] == "unclassified_tool"
    invoke.assert_not_awaited()


@pytest.mark.asyncio
async def test_tool_manager_interrupts_for_write_tool(monkeypatch):
    """Write tools should interrupt before execution in runnable contexts."""
    mgr = ToolManager(thread_id="thread-1", task_id="task-1")
    invoke = AsyncMock(return_value={"status": "should_not_run"})
    _register_tool(
        mgr,
        name="stub_default_update_password",
        action_kind=ToolActionKind.WRITE,
        invoke=invoke,
        description="Update password",
    )
    monkeypatch.setattr(manager_settings, "agent_permission_mode", "read_write")
    monkeypatch.setattr(manager_settings, "agent_approval_ttl_seconds", 900)

    approval_manager = AsyncMock()
    approval_manager.get_resume_state.return_value = None
    approval_manager.create_approval.side_effect = lambda record: record

    seen_payload = {}

    def raise_graph_interrupt(payload):
        seen_payload["payload"] = payload
        raise GraphInterrupt((Interrupt(value=payload, id=payload["interrupt_id"]),))

    with (
        patch("redis_sre_agent.tools.manager.ApprovalManager", return_value=approval_manager),
        patch("redis_sre_agent.tools.manager.interrupt", side_effect=raise_graph_interrupt),
        pytest.raises(GraphInterrupt),
    ):
        await mgr.resolve_tool_call(
            "stub_default_update_password",
            {"password": "top-secret", "username": "demo"},
        )

    invoke.assert_not_awaited()
    approval_manager.create_approval.assert_awaited_once()
    approval_record = approval_manager.create_approval.await_args.args[0]
    payload = seen_payload["payload"]
    assert approval_record.task_id == "task-1"
    assert approval_record.thread_id == "thread-1"
    assert approval_record.action_kind == ToolActionKind.WRITE.value
    assert approval_record.tool_args_preview["password"] == "[redacted]"
    assert payload["kind"] == "approval_required"
    assert payload["tool_name"] == "stub_default_update_password"
    assert payload["pending_approval"]["tool_name"] == "stub_default_update_password"
    assert payload["approval_id"] == approval_record.approval_id
    assert payload["interrupt_id"] == approval_record.interrupt_id


@pytest.mark.asyncio
async def test_execute_tool_calls_propagates_approval_required(monkeypatch):
    """Batch execution should surface approval pauses outside runnable contexts."""
    mgr = ToolManager(thread_id="thread-1", task_id="task-1")
    first_invoke = AsyncMock(return_value={"status": "should_not_run"})
    second_invoke = AsyncMock(return_value={"status": "should_not_run"})
    _register_tool(
        mgr,
        name="stub_default_delete_user",
        action_kind=ToolActionKind.WRITE,
        invoke=first_invoke,
        description="Delete user",
    )
    _register_tool(
        mgr,
        name="stub_default_rotate_password",
        action_kind=ToolActionKind.WRITE,
        invoke=second_invoke,
        description="Rotate password",
    )
    monkeypatch.setattr(manager_settings, "agent_permission_mode", "read_write")
    monkeypatch.setattr(manager_settings, "agent_approval_ttl_seconds", 900)

    approval_manager = AsyncMock()
    approval_manager.get_resume_state.return_value = None
    approval_manager.create_approval.side_effect = lambda record: record

    with (
        patch("redis_sre_agent.tools.manager.ApprovalManager", return_value=approval_manager),
        patch(
            "redis_sre_agent.tools.manager.interrupt",
            side_effect=RuntimeError("called outside of a runnable context"),
        ),
        pytest.raises(ApprovalRequiredError),
    ):
        await mgr.execute_tool_calls(
            [
                {"name": "stub_default_delete_user", "args": {"username": "demo"}},
                {"name": "stub_default_rotate_password", "args": {"username": "demo"}},
            ]
        )

    first_invoke.assert_not_awaited()
    second_invoke.assert_not_awaited()
    approval_manager.create_approval.assert_awaited_once()


@pytest.mark.asyncio
async def test_tool_manager_allows_approved_resume_without_creating_new_approval(monkeypatch):
    """Approved resume state should let the original write execute."""
    mgr = ToolManager(thread_id="thread-1", task_id="task-1", graph_type="chat")
    invoke = AsyncMock(return_value={"status": "ok"})
    _register_tool(
        mgr,
        name="stub_default_update_password",
        action_kind=ToolActionKind.WRITE,
        invoke=invoke,
        description="Update password",
    )
    monkeypatch.setattr(manager_settings, "agent_permission_mode", "read_write")

    approval_record = ApprovalRecord(
        approval_id="approval-1",
        task_id="task-1",
        thread_id="thread-1",
        graph_thread_id="task-1",
        interrupt_id="interrupt-1",
        graph_type="chat",
        graph_version="v1",
        tool_name="stub_default_update_password",
        tool_args={"username": "demo"},
        tool_args_preview={"username": "demo"},
        action_kind=ToolActionKind.WRITE.value,
        action_hash=build_action_hash(
            tool_name="stub_default_update_password",
            tool_args={"username": "demo"},
            target_handles=[],
        ),
        target_handles=[],
        status=ApprovalStatus.APPROVED,
    )
    resume_state = GraphResumeState(
        task_id="task-1",
        thread_id="thread-1",
        graph_thread_id="task-1",
        graph_type="chat",
        graph_version="v1",
        checkpoint_ns="agent_turn",
        checkpoint_id="checkpoint-1",
        waiting_reason="resuming",
        pending_approval_id="approval-1",
        pending_interrupt_id="interrupt-1",
    )

    approval_manager = AsyncMock()
    approval_manager.get_resume_state.return_value = resume_state
    approval_manager.get_approval.return_value = approval_record
    approval_manager.get_execution_ledger.return_value = None
    approval_manager.save_execution_ledger = AsyncMock()

    with patch("redis_sre_agent.tools.manager.ApprovalManager", return_value=approval_manager):
        result = await mgr.resolve_tool_call("stub_default_update_password", {"username": "demo"})

    assert result == {"status": "ok"}
    invoke.assert_awaited_once_with({"username": "demo"})
    approval_manager.create_approval.assert_not_awaited()
    approval_manager.save_execution_ledger.assert_awaited()


@pytest.mark.asyncio
async def test_tool_manager_blocks_rejected_resume_without_invoking(monkeypatch):
    """Rejected approvals should fail closed when the graph resumes."""
    mgr = ToolManager(thread_id="thread-1", task_id="task-1", graph_type="chat")
    invoke = AsyncMock(return_value={"status": "should_not_run"})
    _register_tool(
        mgr,
        name="stub_default_delete_user",
        action_kind=ToolActionKind.WRITE,
        invoke=invoke,
        description="Delete user",
    )
    monkeypatch.setattr(manager_settings, "agent_permission_mode", "read_write")

    approval_record = ApprovalRecord(
        approval_id="approval-1",
        task_id="task-1",
        thread_id="thread-1",
        graph_thread_id="task-1",
        interrupt_id="interrupt-1",
        graph_type="chat",
        graph_version="v1",
        tool_name="stub_default_delete_user",
        tool_args={"username": "demo"},
        tool_args_preview={"username": "demo"},
        action_kind=ToolActionKind.WRITE.value,
        action_hash=build_action_hash(
            tool_name="stub_default_delete_user",
            tool_args={"username": "demo"},
            target_handles=[],
        ),
        target_handles=[],
        status=ApprovalStatus.REJECTED,
    )
    resume_state = GraphResumeState(
        task_id="task-1",
        thread_id="thread-1",
        graph_thread_id="task-1",
        graph_type="chat",
        graph_version="v1",
        checkpoint_ns="agent_turn",
        checkpoint_id="checkpoint-1",
        waiting_reason="resuming",
        pending_approval_id="approval-1",
        pending_interrupt_id="interrupt-1",
    )

    approval_manager = AsyncMock()
    approval_manager.get_resume_state.return_value = resume_state
    approval_manager.get_approval.return_value = approval_record

    with patch("redis_sre_agent.tools.manager.ApprovalManager", return_value=approval_manager):
        result = await mgr.resolve_tool_call("stub_default_delete_user", {"username": "demo"})

    assert result["status"] == "blocked"
    assert result["reason"] == "approval_rejected"
    invoke.assert_not_awaited()
    approval_manager.create_approval.assert_not_awaited()


@pytest.mark.asyncio
async def test_tool_manager_returns_already_executed_for_duplicate_approved_resume(monkeypatch):
    """Approved writes should not replay once the execution ledger is complete."""
    mgr = ToolManager(thread_id="thread-1", task_id="task-1", graph_type="chat")
    invoke = AsyncMock(return_value={"status": "should_not_run"})
    _register_tool(
        mgr,
        name="stub_default_rotate_password",
        action_kind=ToolActionKind.WRITE,
        invoke=invoke,
        description="Rotate password",
    )
    monkeypatch.setattr(manager_settings, "agent_permission_mode", "read_write")

    approval_record = ApprovalRecord(
        approval_id="approval-1",
        task_id="task-1",
        thread_id="thread-1",
        graph_thread_id="task-1",
        interrupt_id="interrupt-1",
        graph_type="chat",
        graph_version="v1",
        tool_name="stub_default_rotate_password",
        tool_args={"username": "demo"},
        tool_args_preview={"username": "demo"},
        action_kind=ToolActionKind.WRITE.value,
        action_hash=build_action_hash(
            tool_name="stub_default_rotate_password",
            tool_args={"username": "demo"},
            target_handles=[],
        ),
        target_handles=[],
        status=ApprovalStatus.APPROVED,
    )
    resume_state = GraphResumeState(
        task_id="task-1",
        thread_id="thread-1",
        graph_thread_id="task-1",
        graph_type="chat",
        graph_version="v1",
        checkpoint_ns="agent_turn",
        checkpoint_id="checkpoint-1",
        waiting_reason="resuming",
        pending_approval_id="approval-1",
        pending_interrupt_id="interrupt-1",
    )
    executed_ledger = ActionExecutionLedger(
        approval_id="approval-1",
        task_id="task-1",
        tool_name="stub_default_rotate_password",
        action_hash=approval_record.action_hash,
        status=ActionExecutionStatus.EXECUTED,
        result_summary="already rotated",
    )

    approval_manager = AsyncMock()
    approval_manager.get_resume_state.return_value = resume_state
    approval_manager.get_approval.return_value = approval_record
    approval_manager.get_execution_ledger.return_value = executed_ledger

    with patch("redis_sre_agent.tools.manager.ApprovalManager", return_value=approval_manager):
        result = await mgr.resolve_tool_call("stub_default_rotate_password", {"username": "demo"})

    assert result["status"] == "already_executed"
    assert result["result_summary"] == "already rotated"
    invoke.assert_not_awaited()


@pytest.mark.asyncio
async def test_tool_manager_prefers_initial_target_bindings_before_thread_reload():
    """Explicit initial bindings should be attached without depending on thread state."""
    binding = TargetBinding(
        target_handle="tgt_opaque_1",
        target_kind="instance",
        resource_id="inst-1",
        display_name="checkout-cache-prod",
        capabilities=["redis", "diagnostics"],
    )

    mgr = ToolManager(
        initial_target_bindings=[binding],
        initial_toolset_generation=7,
        thread_id="thread-123",
    )

    with (
        patch.object(mgr, "_load_provider", new=AsyncMock()),
        patch.object(mgr, "_load_mcp_providers", new=AsyncMock()),
        patch.object(mgr, "_load_support_package_provider", new=AsyncMock()),
        patch.object(
            mgr, "attach_bound_targets", new=AsyncMock(return_value=[binding])
        ) as mock_attach,
        patch.object(mgr, "_load_thread_attached_targets", new=AsyncMock()) as mock_thread_reload,
    ):
        await mgr.__aenter__()
        await mgr.__aexit__(None, None, None)

    mock_attach.assert_awaited_once_with([binding], generation=7)
    mock_thread_reload.assert_not_awaited()


@pytest.mark.asyncio
async def test_tool_manager_with_instance():
    """Test that instance-specific tools are loaded when instance is provided."""
    from redis_sre_agent.core.instances import RedisInstance

    # Create a test instance
    test_instance = RedisInstance(
        id="test-instance",
        name="Test Redis",
        connection_url="redis://localhost:6379",
        environment="test",
        usage="cache",
        description="Test instance",
        instance_type="oss_single",
    )

    async with ToolManager(redis_instance=test_instance) as mgr:
        tools = mgr.get_tools()
        tool_names = [t.name for t in tools]

        # Should have knowledge, prometheus, and redis_command tools
        knowledge_tools = [n for n in tool_names if "knowledge_" in n]
        prometheus_tools = [n for n in tool_names if "prometheus_" in n]
        redis_command_tools = [n for n in tool_names if "redis_command_" in n]

        # Knowledge tools (always loaded)
        assert len(knowledge_tools) == 9

        # Instance-specific tools should be loaded
        assert len(prometheus_tools) == 3  # query, query_range, search_metrics
        assert len(redis_command_tools) == 11  # All diagnostic tools


@pytest.mark.asyncio
async def test_tool_manager_routing():
    """Test that ToolManager can route tool calls."""
    async with ToolManager() as mgr:
        tools = mgr.get_tools()

        # Get a tool name
        tool_name = tools[0].name

        # Should be able to find provider in routing table
        provider = mgr._routing_table.get(tool_name)
        assert provider is not None
        assert provider.provider_name == "knowledge"


@pytest.mark.asyncio
async def test_tool_manager_unknown_tool():
    """Test that ToolManager raises error for unknown tools."""
    async with ToolManager() as mgr:
        with pytest.raises(ValueError, match="Unknown tool"):
            await mgr.resolve_tool_call("nonexistent_tool", {})


@pytest.mark.asyncio
async def test_tool_manager_context_cleanup():
    """Test that ToolManager cleans up properly."""
    mgr = ToolManager()

    # Before entering context
    assert mgr._stack is None
    assert len(mgr._tools) == 0

    # Enter context
    await mgr.__aenter__()
    assert mgr._stack is not None
    assert len(mgr._tools) > 0

    # Exit context
    await mgr.__aexit__(None, None, None)

    # Stack should still exist but be closed
    assert mgr._stack is not None


def test_mask_redis_url_credentials():
    """Test that Redis URL credentials are properly masked."""
    from redis_sre_agent.agent.langgraph_agent import _mask_redis_url_credentials

    # Test with username and password
    url_with_creds = "redis://user:password@localhost:6379/0"
    masked = _mask_redis_url_credentials(url_with_creds)
    assert masked == "redis://***:***@localhost:6379/0"
    assert "user" not in masked
    assert "password" not in masked

    # Test with URL-encoded credentials (common in Redis Enterprise)
    url_encoded = "redis://admin%40redis.com:admin@redis-enterprise:12000/0"
    masked = _mask_redis_url_credentials(url_encoded)
    assert masked == "redis://***:***@redis-enterprise:12000/0"
    assert "admin" not in masked

    # Test without credentials
    url_no_creds = "redis://localhost:6379"
    masked = _mask_redis_url_credentials(url_no_creds)
    assert masked == "redis://localhost:6379"

    # Test with only password (edge case)
    url_only_pass = "redis://:password@localhost:6379"
    masked = _mask_redis_url_credentials(url_only_pass)
    assert masked == "redis://***:***@localhost:6379"
    assert "password" not in masked

    # Test with special characters in password
    url_special_chars = "redis://user:p@ssw0rd!@localhost:6379"
    masked = _mask_redis_url_credentials(url_special_chars)
    assert masked == "redis://***:***@localhost:6379"
    assert "p@ssw0rd!" not in masked
    assert "user" not in masked

    # Test with database number
    url_with_db = "redis://user:pass@localhost:6379/5"
    masked = _mask_redis_url_credentials(url_with_db)
    assert masked == "redis://***:***@localhost:6379/5"
    assert "user" not in masked
    assert "pass" not in masked

    # Test with query parameters
    url_with_query = "redis://user:pass@localhost:6379/0?timeout=5"
    masked = _mask_redis_url_credentials(url_with_query)
    assert masked == "redis://***:***@localhost:6379/0?timeout=5"
    assert "user" not in masked
    assert "pass" not in masked

    # Test with non-standard port
    url_enterprise_port = "redis://admin:secret@redis-enterprise:12000/0"
    masked = _mask_redis_url_credentials(url_enterprise_port)
    assert masked == "redis://***:***@redis-enterprise:12000/0"
    assert "admin" not in masked
    assert "secret" not in masked
    # Verify hostname and port are preserved
    assert "redis-enterprise" in masked
    assert "12000" in masked

    # Test with rediss:// (SSL)
    url_ssl = "rediss://user:pass@secure-redis:6380/0"
    masked = _mask_redis_url_credentials(url_ssl)
    assert masked == "rediss://***:***@secure-redis:6380/0"
    assert "user" not in masked
    assert "pass" not in masked

    # Test with complex username (email-like)
    url_email_user = "redis://admin@company.com:password123@redis-host:6379"
    masked = _mask_redis_url_credentials(url_email_user)
    assert masked == "redis://***:***@redis-host:6379"
    assert "admin@company.com" not in masked
    assert "password123" not in masked
    assert "redis-host" in masked


class TestToolManagerProviders:
    """Test ToolManager provider management."""

    @pytest.mark.asyncio
    async def test_get_tools_returns_tool_definitions(self):
        """Test get_tools returns ToolDefinition objects."""
        async with ToolManager() as mgr:
            tools = mgr.get_tools()

            assert isinstance(tools, list)
            for tool in tools:
                assert isinstance(tool, ToolDefinition)

    @pytest.mark.asyncio
    async def test_tool_manager_has_routing_table(self):
        """Test ToolManager builds routing table."""
        async with ToolManager() as mgr:
            assert hasattr(mgr, "_routing_table")
            assert isinstance(mgr._routing_table, dict)

    @pytest.mark.asyncio
    async def test_tool_manager_multiple_context_entries(self):
        """Test ToolManager handles multiple context entries."""
        mgr = ToolManager()

        await mgr.__aenter__()
        tools1 = mgr.get_tools()

        await mgr.__aexit__(None, None, None)

        # Re-enter context
        await mgr.__aenter__()
        tools2 = mgr.get_tools()

        # Should have same tools available
        assert len(tools1) == len(tools2)

        await mgr.__aexit__(None, None, None)


class TestToolManagerGetStatusUpdate:
    """Test ToolManager get_status_update method."""

    @pytest.mark.asyncio
    async def test_get_status_update_returns_none_for_unknown_tool(self):
        """Test get_status_update returns None for unknown tool."""
        async with ToolManager() as mgr:
            result = mgr.get_status_update("unknown_tool_name", {})
            assert result is None

    @pytest.mark.asyncio
    async def test_get_status_update_for_known_tool(self):
        """Test get_status_update for a known tool."""
        async with ToolManager() as mgr:
            tools = mgr.get_tools()
            if tools:
                tool_name = tools[0].name
                # May return None or a string depending on tool
                result = mgr.get_status_update(tool_name, {})
                assert result is None or isinstance(result, str)


class TestToolManagerMcpConfigValidation:
    """Test MCP provider loading guardrails."""

    def test_command_is_available_handles_missing_path(self):
        """Absolute/relative command paths should return False when missing."""
        assert _command_is_available("/definitely/not/a/real/command") is False

    def test_missing_local_mcp_arg_path_detects_direct_script_paths(self):
        """Direct script entrypoints should be validated before provider startup."""
        missing = _missing_local_mcp_arg_path(["/definitely/not/a/real/index.js"])
        assert missing == "/definitely/not/a/real/index.js"

    def test_missing_local_mcp_arg_path_ignores_shell_command_strings(self):
        """Shell command payloads should not be mistaken for direct file args."""
        assert (
            _missing_local_mcp_arg_path(
                ["-lc", "cd /work/re-analyzer && exec node /work/re-analyzer/dist/index.js"]
            )
            is None
        )

    def test_missing_local_mcp_arg_path_ignores_docker_images_and_packages(self):
        """Docker image refs and npm packages are not direct local entrypoints."""
        assert (
            _missing_local_mcp_arg_path(["run", "-i", "--rm", "ghcr.io/github/github-mcp-server"])
            is None
        )
        assert _missing_local_mcp_arg_path(["-y", "@modelcontextprotocol/server-memory"]) is None

    def test_missing_local_mcp_arg_path_detects_relative_script_entrypoints(self):
        """Relative script paths with file extensions should still be validated."""
        missing = _missing_local_mcp_arg_path(["vendor/re-analyzer-mcp/dist/src/index.js"])
        assert missing == "vendor/re-analyzer-mcp/dist/src/index.js"

    def test_missing_local_mcp_arg_path_ignores_script_urls(self):
        """Remote script URLs should not be mistaken for missing local files."""
        assert _missing_local_mcp_arg_path(["https://example.com/server.ts"]) is None

    @pytest.mark.asyncio
    async def test_load_mcp_providers_skips_missing_command(self, caplog):
        """Missing MCP command should be skipped without raising or stack traces."""
        mgr = ToolManager()
        mgr._stack = AsyncExitStack()
        await mgr._stack.__aenter__()
        try:
            with patch("redis_sre_agent.core.config.settings") as mock_settings:
                mock_settings.mcp_servers = {
                    "github": MCPServerConfig(command="definitely-missing-mcp-command-xyz")
                }
                await mgr._load_mcp_providers()

            assert "mcp:github" not in mgr._loaded_provider_keys
            assert "Skipping MCP provider 'github'" in caplog.text
        finally:
            await mgr._stack.__aexit__(None, None, None)

    @pytest.mark.asyncio
    async def test_load_mcp_providers_skips_missing_local_entrypoint(self, caplog):
        """Missing direct script entrypoints should be skipped before subprocess launch."""
        mgr = ToolManager()
        mgr._stack = AsyncExitStack()
        await mgr._stack.__aenter__()
        try:
            with (
                patch("redis_sre_agent.core.config.settings") as mock_settings,
                patch("redis_sre_agent.tools.manager._command_is_available", return_value=True),
            ):
                mock_settings.mcp_servers = {
                    "re_analyzer": MCPServerConfig(
                        command="node",
                        args=["/definitely/not/a/real/index.js"],
                    )
                }
                await mgr._load_mcp_providers()

            assert "mcp:re_analyzer" not in mgr._loaded_provider_keys
            assert "Skipping MCP provider 're_analyzer'" in caplog.text
            assert "/definitely/not/a/real/index.js" in caplog.text
        finally:
            await mgr._stack.__aexit__(None, None, None)


class TestToolDefinitionRepresentation:
    """Tests for ToolDefinition __str__ and __repr__ methods."""

    def test_tool_definition_str(self):
        """Test that __str__ returns expected format."""
        tool = ToolDefinition(
            name="test_tool",
            description="A test tool",
            parameters={"type": "object", "properties": {"arg1": {"type": "string"}}},
            capability=ToolCapability.DIAGNOSTICS,
        )
        assert str(tool) == "ToolDefinition(name=test_tool)"

    def test_tool_definition_repr(self):
        """Test that __repr__ returns expected format with parameter names."""
        tool = ToolDefinition(
            name="test_tool",
            description="A test tool",
            parameters={
                "type": "object",
                "properties": {"arg1": {"type": "string"}, "arg2": {"type": "integer"}},
            },
            capability=ToolCapability.DIAGNOSTICS,
        )
        repr_str = repr(tool)
        assert "ToolDefinition(name=test_tool" in repr_str
        assert "arg1" in repr_str
        assert "arg2" in repr_str

    def test_tool_definition_repr_empty_parameters(self):
        """Test __repr__ with empty parameters."""
        tool = ToolDefinition(
            name="empty_params_tool",
            description="A tool with no parameters",
            parameters={"type": "object", "properties": {}},
            capability=ToolCapability.UTILITIES,
        )
        repr_str = repr(tool)
        assert "ToolDefinition(name=empty_params_tool" in repr_str
        assert "parameters=[]" in repr_str


class TestEnterpriseCredentialResolution:
    """Tests for Redis Enterprise cluster-first credential resolution in ToolManager."""

    @pytest.mark.asyncio
    async def test_loads_re_admin_tools_from_linked_cluster_credentials(self):
        """Redis Enterprise instance should load re_admin tools from linked cluster creds."""
        from redis_sre_agent.core.instances import RedisInstance

        instance = RedisInstance(
            id="re-inst-1",
            name="enterprise-db",
            connection_url="redis://localhost:12000",
            environment="test",
            usage="cache",
            description="enterprise instance",
            instance_type="redis_enterprise",
            cluster_id="cluster-1",
        )
        cluster = RedisCluster(
            id="cluster-1",
            name="enterprise-cluster",
            cluster_type=RedisClusterType.redis_enterprise,
            environment="test",
            description="cluster creds",
            admin_url="https://cluster.example.com:9443",
            admin_username="admin@redis.com",
            admin_password="secret",
        )

        with patch(
            "redis_sre_agent.core.clusters.get_cluster_by_id",
            new=AsyncMock(return_value=cluster),
        ):
            async with ToolManager(redis_instance=instance) as mgr:
                tool_names = [t.name for t in mgr.get_tools()]
                assert any(name.startswith("re_admin_") for name in tool_names)
                assert mgr.redis_instance.admin_url == "https://cluster.example.com:9443"
                assert mgr.redis_instance.admin_username == "admin@redis.com"

    @pytest.mark.asyncio
    async def test_falls_back_to_deprecated_instance_admin_fields(self):
        """If linked cluster is unavailable, fallback to deprecated instance admin fields."""
        from redis_sre_agent.core.instances import RedisInstance

        instance = RedisInstance(
            id="re-inst-2",
            name="enterprise-db-fallback",
            connection_url="redis://localhost:12001",
            environment="test",
            usage="cache",
            description="enterprise instance fallback",
            instance_type="redis_enterprise",
            cluster_id="missing-cluster",
            admin_url="https://legacy-instance.example.com:9443",
            admin_username="legacy-admin@redis.com",
            admin_password="legacy-secret",
        )

        with patch(
            "redis_sre_agent.core.clusters.get_cluster_by_id",
            new=AsyncMock(return_value=None),
        ):
            async with ToolManager(redis_instance=instance) as mgr:
                tool_names = [t.name for t in mgr.get_tools()]
                assert any(name.startswith("re_admin_") for name in tool_names)
                assert mgr.redis_instance.admin_url == "https://legacy-instance.example.com:9443"

    @pytest.mark.asyncio
    async def test_skips_re_admin_tools_when_no_cluster_or_instance_admin_credentials(self):
        """Without cluster or instance admin URL, re_admin tools should not load."""
        from redis_sre_agent.core.instances import RedisInstance

        instance = RedisInstance(
            id="re-inst-3",
            name="enterprise-db-no-admin",
            connection_url="redis://localhost:12002",
            environment="test",
            usage="cache",
            description="enterprise instance no admin creds",
            instance_type="redis_enterprise",
            cluster_id="missing-cluster",
        )

        with patch(
            "redis_sre_agent.core.clusters.get_cluster_by_id",
            new=AsyncMock(return_value=None),
        ):
            async with ToolManager(redis_instance=instance) as mgr:
                tool_names = [t.name for t in mgr.get_tools()]
                assert not any(name.startswith("re_admin_") for name in tool_names)

    @pytest.mark.asyncio
    async def test_loads_re_admin_tools_from_cluster_without_instance(self):
        """Cluster-only Redis Enterprise queries should still load admin tools."""
        cluster = RedisCluster(
            id="cluster-only-1",
            name="enterprise-cluster-only",
            cluster_type=RedisClusterType.redis_enterprise,
            environment="test",
            description="cluster-only creds",
            admin_url="https://cluster-only.example.com:9443",
            admin_username="admin@redis.com",
            admin_password="secret",
        )

        async with ToolManager(redis_cluster=cluster) as mgr:
            tool_names = [t.name for t in mgr.get_tools()]
            assert any(name.startswith("re_admin_") for name in tool_names)
            assert mgr.redis_instance is None
