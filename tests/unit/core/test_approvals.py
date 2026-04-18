"""Unit tests for approval domain models and storage helpers."""

import json
from unittest.mock import AsyncMock

import pytest

from redis_sre_agent.core.approvals import (
    ActionExecutionLedger,
    ActionExecutionStatus,
    ApprovalDecision,
    ApprovalDecisionType,
    ApprovalManager,
    ApprovalRecord,
    ApprovalStatus,
    GraphResumeState,
    PendingApprovalSummary,
)
from redis_sre_agent.core.keys import RedisKeys


class TestApprovalModels:
    def test_approval_record_defaults(self):
        record = ApprovalRecord(
            task_id="task-1",
            thread_id="thread-1",
            graph_thread_id="task-1",
            interrupt_id="interrupt-1",
            graph_type="chat",
            graph_version="v1",
            tool_name="dangerous_tool",
            action_hash="abc123",
        )

        assert record.approval_id
        assert record.status == ApprovalStatus.PENDING
        assert record.requested_at is not None
        assert record.tool_args == {}
        assert record.tool_args_preview == {}
        assert record.target_handles == []

    def test_pending_approval_summary_from_record(self):
        record = ApprovalRecord(
            approval_id="approval-1",
            task_id="task-1",
            thread_id="thread-1",
            graph_thread_id="task-1",
            interrupt_id="interrupt-1",
            graph_type="chat",
            graph_version="v1",
            tool_name="redis_scale",
            action_hash="abc123",
            target_handles=["tgt-1", "tgt-2"],
        )

        summary = PendingApprovalSummary.from_record(record)

        assert summary.approval_id == "approval-1"
        assert summary.summary == "redis_scale on tgt-1, tgt-2"
        assert summary.status == ApprovalStatus.PENDING

    def test_action_execution_ledger_key(self):
        ledger = ActionExecutionLedger(
            approval_id="approval-1",
            task_id="task-1",
            tool_name="redis_scale",
            action_hash="abc123",
        )

        assert ledger.ledger_key == "approval-1:abc123"


class TestApprovalManager:
    @pytest.fixture
    def redis_client(self):
        client = AsyncMock()
        client.set = AsyncMock(return_value=True)
        client.get = AsyncMock(return_value=None)
        client.zadd = AsyncMock(return_value=1)
        client.zrange = AsyncMock(return_value=[])
        client.zrevrange = AsyncMock(return_value=[])
        client.zrem = AsyncMock(return_value=1)
        client.delete = AsyncMock(return_value=1)
        return client

    @pytest.fixture
    def manager(self, redis_client):
        return ApprovalManager(redis_client=redis_client)

    @pytest.fixture
    def approval_record(self):
        return ApprovalRecord(
            approval_id="approval-1",
            task_id="task-1",
            thread_id="thread-1",
            graph_thread_id="task-1",
            interrupt_id="interrupt-1",
            graph_type="chat",
            graph_version="v1",
            tool_name="redis_scale",
            tool_args={"memory_size_gb": 4},
            tool_args_preview={"memory_size_gb": 4},
            action_hash="abc123",
            target_handles=["tgt-1"],
        )

    @pytest.mark.asyncio
    async def test_create_approval_stores_record_and_indexes(
        self, manager, redis_client, approval_record
    ):
        record = await manager.create_approval(approval_record)

        assert record == approval_record
        redis_client.set.assert_called_once()
        redis_client.zadd.assert_any_call(
            RedisKeys.task_approvals("task-1"),
            {
                "approval-1": pytest.approx(
                    redis_client.zadd.call_args_list[0].args[1]["approval-1"]
                )
            },
        )
        redis_client.zadd.assert_any_call(
            RedisKeys.approvals_pending(),
            {
                "approval-1": pytest.approx(
                    redis_client.zadd.call_args_list[1].args[1]["approval-1"]
                )
            },
        )

    @pytest.mark.asyncio
    async def test_get_approval_decodes_bytes(self, manager, redis_client, approval_record):
        redis_client.get.return_value = json.dumps(approval_record.model_dump(mode="json")).encode()

        record = await manager.get_approval("approval-1")

        assert record is not None
        assert record.approval_id == "approval-1"
        assert record.tool_args["memory_size_gb"] == 4

    @pytest.mark.asyncio
    async def test_list_task_approvals_uses_ordered_index(
        self, manager, redis_client, approval_record
    ):
        second = approval_record.model_copy(
            update={"approval_id": "approval-2", "action_hash": "def456"}
        )
        redis_client.zrevrange.return_value = [b"approval-2", b"approval-1"]

        async def get_side_effect(key):
            if key == RedisKeys.approval("approval-1"):
                return json.dumps(approval_record.model_dump(mode="json")).encode()
            if key == RedisKeys.approval("approval-2"):
                return json.dumps(second.model_dump(mode="json")).encode()
            return None

        redis_client.get.side_effect = get_side_effect

        records = await manager.list_task_approvals("task-1")

        assert [record.approval_id for record in records] == ["approval-2", "approval-1"]

    @pytest.mark.asyncio
    async def test_record_decision_updates_status_and_removes_pending(
        self,
        manager,
        redis_client,
        approval_record,
    ):
        redis_client.get.return_value = json.dumps(approval_record.model_dump(mode="json")).encode()
        decision = ApprovalDecision(
            decision=ApprovalDecisionType.APPROVED,
            decision_by="user-1",
            decision_comment="Proceed",
        )

        updated = await manager.record_decision("approval-1", decision)

        assert updated is not None
        assert updated.status == ApprovalStatus.APPROVED
        assert updated.decision is not None
        redis_client.zrem.assert_called_once_with(RedisKeys.approvals_pending(), "approval-1")

    @pytest.mark.asyncio
    async def test_save_and_get_resume_state(self, manager, redis_client):
        state = GraphResumeState(
            task_id="task-1",
            thread_id="thread-1",
            graph_thread_id="task-1",
            graph_type="chat",
            graph_version="v1",
            checkpoint_ns="agent_turn",
            checkpoint_id="checkpoint-1",
            waiting_reason="approval_required",
            pending_approval_id="approval-1",
            pending_interrupt_id="interrupt-1",
        )

        await manager.save_resume_state(state)
        redis_client.get.return_value = state.model_dump_json().encode()

        loaded = await manager.get_resume_state("task-1")

        assert loaded == state

    @pytest.mark.asyncio
    async def test_save_and_get_execution_ledger(self, manager, redis_client):
        ledger = ActionExecutionLedger(
            approval_id="approval-1",
            task_id="task-1",
            tool_name="redis_scale",
            action_hash="abc123",
            status=ActionExecutionStatus.EXECUTED,
            executed_at="2026-04-15T12:00:00+00:00",
            result_summary="scaled successfully",
        )

        await manager.save_execution_ledger(ledger)
        redis_client.get.return_value = ledger.model_dump_json().encode()

        loaded = await manager.get_execution_ledger("approval-1", "abc123")

        assert loaded == ledger

    @pytest.mark.asyncio
    async def test_list_pending_approvals_filters_non_pending(
        self, manager, redis_client, approval_record
    ):
        approved = approval_record.model_copy(
            update={
                "approval_id": "approval-2",
                "action_hash": "def456",
                "status": ApprovalStatus.APPROVED,
            }
        )
        redis_client.zrange.return_value = [b"approval-1", b"approval-2"]

        async def get_side_effect(key):
            if key == RedisKeys.approval("approval-1"):
                return json.dumps(approval_record.model_dump(mode="json")).encode()
            if key == RedisKeys.approval("approval-2"):
                return json.dumps(approved.model_dump(mode="json")).encode()
            return None

        redis_client.get.side_effect = get_side_effect

        records = await manager.list_pending_approvals()

        assert [record.approval_id for record in records] == ["approval-1"]


class TestApprovalKeys:
    def test_approval_related_keys(self):
        assert RedisKeys.approval("approval-1") == "sre:approval:approval-1"
        assert RedisKeys.task_approvals("task-1") == "sre:task:task-1:approvals"
        assert RedisKeys.task_resume_state("task-1") == "sre:task:task-1:resume_state"
        assert RedisKeys.approvals_pending() == "sre:approvals:pending"
        assert (
            RedisKeys.approval_execution("approval-1", "abc123")
            == "sre:approval_execution:approval-1:abc123"
        )
