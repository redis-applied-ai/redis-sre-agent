from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from redis_sre_agent.agent.models import AgentResponse
from redis_sre_agent.core.approvals import (
    ApprovalDecision,
    ApprovalDecisionType,
    ApprovalRecord,
    ApprovalStatus,
    GraphResumeState,
    PendingApprovalSummary,
)
from redis_sre_agent.core.docket_tasks import resume_task_after_approval
from redis_sre_agent.core.tasks import TaskMetadata, TaskState, TaskStatus


def _build_task_state(*, status: TaskStatus, pending: PendingApprovalSummary | None) -> TaskState:
    return TaskState(
        task_id="task-1",
        thread_id="thread-1",
        status=status,
        pending_approval=pending,
        resume_supported=True,
        metadata=TaskMetadata(user_id="user-1"),
    )


def _build_approval(status: ApprovalStatus = ApprovalStatus.PENDING) -> ApprovalRecord:
    return ApprovalRecord(
        approval_id="approval-1",
        task_id="task-1",
        thread_id="thread-1",
        graph_thread_id="task-1",
        interrupt_id="interrupt-1",
        graph_type="chat",
        graph_version="v1",
        tool_name="redis_cloud_deadbeef_update_tags",
        tool_args={"tag": "prod"},
        tool_args_preview={"tag": "prod"},
        action_hash="hash-1",
        target_handles=["inst-1"],
        status=status,
    )


def _build_thread() -> MagicMock:
    thread = MagicMock()
    thread.context = {"instance_id": "inst-1", "exclude_mcp_categories": []}
    thread.metadata = MagicMock()
    thread.metadata.user_id = "user-1"
    thread.metadata.session_id = "session-1"
    thread.messages = []
    return thread


@pytest.mark.asyncio
async def test_resume_task_after_approval_completes_chat_turn():
    approval_record = _build_approval()
    pending = PendingApprovalSummary.from_record(approval_record)
    task_state = _build_task_state(status=TaskStatus.AWAITING_APPROVAL, pending=pending)
    post_resume_state = _build_task_state(status=TaskStatus.IN_PROGRESS, pending=None)
    thread = _build_thread()
    resume_state = GraphResumeState(
        task_id="task-1",
        thread_id="thread-1",
        graph_thread_id="task-1",
        graph_type="chat",
        graph_version="v1",
        checkpoint_ns="agent_turn",
        checkpoint_id="ckpt-1",
        waiting_reason="approval_required",
        pending_approval_id="approval-1",
        pending_interrupt_id="interrupt-1",
    )
    decided_record = approval_record.model_copy(
        update={
            "status": ApprovalStatus.APPROVED,
            "decision": ApprovalDecision(decision=ApprovalDecisionType.APPROVED),
        }
    )

    mock_task_manager = AsyncMock()
    mock_task_manager.get_task_state = AsyncMock(side_effect=[task_state, post_resume_state])
    mock_task_manager.set_pending_approval = AsyncMock()
    mock_task_manager.set_resume_supported = AsyncMock()
    mock_task_manager.update_task_status = AsyncMock()
    mock_task_manager.add_task_update = AsyncMock()
    mock_task_manager.set_task_result = AsyncMock()

    mock_thread_manager = AsyncMock()
    mock_thread_manager.get_thread = AsyncMock(return_value=thread)
    mock_thread_manager.set_message_trace = AsyncMock()
    mock_thread_manager.append_messages = AsyncMock()

    mock_approval_manager = AsyncMock()
    mock_approval_manager.get_resume_state = AsyncMock(return_value=resume_state)
    mock_approval_manager.get_approval = AsyncMock(return_value=approval_record)
    mock_approval_manager.record_decision = AsyncMock(return_value=decided_record)
    mock_approval_manager.save_resume_state = AsyncMock()
    mock_approval_manager.delete_resume_state = AsyncMock()

    mock_chat_agent = AsyncMock()
    mock_chat_agent.resume_query = AsyncMock(
        return_value=AgentResponse(response="Applied the change.", tool_envelopes=[])
    )

    with (
        patch("redis_sre_agent.core.docket_tasks.TaskManager", return_value=mock_task_manager),
        patch("redis_sre_agent.core.docket_tasks.ThreadManager", return_value=mock_thread_manager),
        patch(
            "redis_sre_agent.core.docket_tasks.ApprovalManager",
            return_value=mock_approval_manager,
        ),
        patch("redis_sre_agent.core.docket_tasks.get_instance_by_id", new=AsyncMock()),
        patch("redis_sre_agent.core.docket_tasks.get_cluster_by_id", new=AsyncMock()),
        patch("redis_sre_agent.agent.chat_agent.ChatAgent", return_value=mock_chat_agent),
    ):
        result = await resume_task_after_approval(
            task_id="task-1",
            approval_id="approval-1",
            decision="approved",
            decision_by="reviewer@example.com",
        )

    assert result["response"]["response"] == "Applied the change."
    mock_approval_manager.record_decision.assert_awaited_once()
    mock_approval_manager.delete_resume_state.assert_awaited_once_with("task-1")
    mock_task_manager.update_task_status.assert_any_call("task-1", TaskStatus.IN_PROGRESS)
    mock_task_manager.update_task_status.assert_any_call("task-1", TaskStatus.DONE)
    mock_thread_manager.append_messages.assert_awaited_once()


@pytest.mark.asyncio
async def test_resume_task_after_approval_accepts_pretransitioned_in_progress_state():
    approval_record = _build_approval()
    thread = _build_thread()
    resume_state = GraphResumeState(
        task_id="task-1",
        thread_id="thread-1",
        graph_thread_id="task-1",
        graph_type="chat",
        graph_version="v1",
        checkpoint_ns="agent_turn",
        checkpoint_id="ckpt-1",
        waiting_reason="approval_required",
        pending_approval_id="approval-1",
        pending_interrupt_id="interrupt-1",
    )
    decided_record = approval_record.model_copy(
        update={
            "status": ApprovalStatus.APPROVED,
            "decision": ApprovalDecision(decision=ApprovalDecisionType.APPROVED),
        }
    )
    in_progress_state = _build_task_state(status=TaskStatus.IN_PROGRESS, pending=None)
    post_resume_state = _build_task_state(status=TaskStatus.IN_PROGRESS, pending=None)

    mock_task_manager = AsyncMock()
    mock_task_manager.get_task_state = AsyncMock(side_effect=[in_progress_state, post_resume_state])
    mock_task_manager.set_pending_approval = AsyncMock()
    mock_task_manager.set_resume_supported = AsyncMock()
    mock_task_manager.update_task_status = AsyncMock()
    mock_task_manager.add_task_update = AsyncMock()
    mock_task_manager.set_task_result = AsyncMock()

    mock_thread_manager = AsyncMock()
    mock_thread_manager.get_thread = AsyncMock(return_value=thread)
    mock_thread_manager.set_message_trace = AsyncMock()
    mock_thread_manager.append_messages = AsyncMock()

    mock_approval_manager = AsyncMock()
    mock_approval_manager.get_resume_state = AsyncMock(return_value=resume_state)
    mock_approval_manager.get_approval = AsyncMock(return_value=approval_record)
    mock_approval_manager.record_decision = AsyncMock(return_value=decided_record)
    mock_approval_manager.save_resume_state = AsyncMock()
    mock_approval_manager.delete_resume_state = AsyncMock()

    mock_chat_agent = AsyncMock()
    mock_chat_agent.resume_query = AsyncMock(
        return_value=AgentResponse(response="Applied the change.", tool_envelopes=[])
    )

    with (
        patch("redis_sre_agent.core.docket_tasks.TaskManager", return_value=mock_task_manager),
        patch("redis_sre_agent.core.docket_tasks.ThreadManager", return_value=mock_thread_manager),
        patch(
            "redis_sre_agent.core.docket_tasks.ApprovalManager",
            return_value=mock_approval_manager,
        ),
        patch("redis_sre_agent.core.docket_tasks.get_instance_by_id", new=AsyncMock()),
        patch("redis_sre_agent.core.docket_tasks.get_cluster_by_id", new=AsyncMock()),
        patch("redis_sre_agent.agent.chat_agent.ChatAgent", return_value=mock_chat_agent),
    ):
        result = await resume_task_after_approval(
            task_id="task-1",
            approval_id="approval-1",
            decision="approved",
        )

    assert result["response"]["response"] == "Applied the change."
    mock_chat_agent.resume_query.assert_awaited_once()


@pytest.mark.asyncio
async def test_resume_task_after_approval_returns_next_pending_approval():
    approval_record = _build_approval()
    pending = PendingApprovalSummary.from_record(approval_record)
    task_state = _build_task_state(status=TaskStatus.AWAITING_APPROVAL, pending=pending)
    next_pending = PendingApprovalSummary(
        approval_id="approval-2",
        interrupt_id="interrupt-2",
        tool_name="redis_cloud_deadbeef_delete_user",
        summary="redis_cloud_deadbeef_delete_user on inst-1",
        requested_at="2026-04-15T00:00:00+00:00",
        status=ApprovalStatus.PENDING,
    )
    post_resume_state = _build_task_state(status=TaskStatus.AWAITING_APPROVAL, pending=next_pending)
    thread = _build_thread()
    resume_state = GraphResumeState(
        task_id="task-1",
        thread_id="thread-1",
        graph_thread_id="task-1",
        graph_type="chat",
        graph_version="v1",
        checkpoint_ns="agent_turn",
        checkpoint_id="ckpt-1",
        waiting_reason="approval_required",
        pending_approval_id="approval-1",
        pending_interrupt_id="interrupt-1",
    )
    decided_record = approval_record.model_copy(
        update={
            "status": ApprovalStatus.APPROVED,
            "decision": ApprovalDecision(decision=ApprovalDecisionType.APPROVED),
        }
    )

    mock_task_manager = AsyncMock()
    mock_task_manager.get_task_state = AsyncMock(side_effect=[task_state, post_resume_state])
    mock_task_manager.set_pending_approval = AsyncMock()
    mock_task_manager.set_resume_supported = AsyncMock()
    mock_task_manager.update_task_status = AsyncMock()
    mock_task_manager.add_task_update = AsyncMock()
    mock_task_manager.set_task_result = AsyncMock()

    mock_thread_manager = AsyncMock()
    mock_thread_manager.get_thread = AsyncMock(return_value=thread)

    mock_approval_manager = AsyncMock()
    mock_approval_manager.get_resume_state = AsyncMock(return_value=resume_state)
    mock_approval_manager.get_approval = AsyncMock(return_value=approval_record)
    mock_approval_manager.record_decision = AsyncMock(return_value=decided_record)
    mock_approval_manager.save_resume_state = AsyncMock()
    mock_approval_manager.delete_resume_state = AsyncMock()

    mock_chat_agent = AsyncMock()
    mock_chat_agent.resume_query = AsyncMock(
        return_value=AgentResponse(response="Need another approval.", tool_envelopes=[])
    )

    with (
        patch("redis_sre_agent.core.docket_tasks.TaskManager", return_value=mock_task_manager),
        patch("redis_sre_agent.core.docket_tasks.ThreadManager", return_value=mock_thread_manager),
        patch(
            "redis_sre_agent.core.docket_tasks.ApprovalManager",
            return_value=mock_approval_manager,
        ),
        patch("redis_sre_agent.core.docket_tasks.get_instance_by_id", new=AsyncMock()),
        patch("redis_sre_agent.core.docket_tasks.get_cluster_by_id", new=AsyncMock()),
        patch("redis_sre_agent.agent.chat_agent.ChatAgent", return_value=mock_chat_agent),
    ):
        result = await resume_task_after_approval(
            task_id="task-1",
            approval_id="approval-1",
            decision="approved",
        )

    assert result["status"] == TaskStatus.AWAITING_APPROVAL.value
    assert result["pending_approval"]["approval_id"] == "approval-2"
    mock_task_manager.set_task_result.assert_awaited_once_with("task-1", result)
    mock_approval_manager.delete_resume_state.assert_not_awaited()


@pytest.mark.asyncio
async def test_resume_task_after_approval_returns_existing_done_result_without_replaying():
    completed_result = {"response": {"response": "Already done."}}
    task_state = _build_task_state(status=TaskStatus.DONE, pending=None)
    task_state.result = completed_result

    mock_task_manager = AsyncMock()
    mock_task_manager.get_task_state = AsyncMock(return_value=task_state)

    mock_approval_manager = AsyncMock()
    mock_approval_manager.delete_resume_state = AsyncMock()

    with (
        patch("redis_sre_agent.core.docket_tasks.TaskManager", return_value=mock_task_manager),
        patch("redis_sre_agent.core.docket_tasks.ThreadManager", return_value=AsyncMock()),
        patch(
            "redis_sre_agent.core.docket_tasks.ApprovalManager",
            return_value=mock_approval_manager,
        ),
    ):
        result = await resume_task_after_approval(
            task_id="task-1",
            approval_id="approval-1",
            decision="approved",
        )

    assert result == {
        "task_id": "task-1",
        "thread_id": "thread-1",
        "status": TaskStatus.DONE.value,
        "result": completed_result,
    }
    mock_approval_manager.delete_resume_state.assert_awaited_once_with("task-1")


@pytest.mark.asyncio
async def test_resume_task_after_rejection_resumes_with_rejected_decision():
    approval_record = _build_approval()
    pending = PendingApprovalSummary.from_record(approval_record)
    task_state = _build_task_state(status=TaskStatus.AWAITING_APPROVAL, pending=pending)
    post_resume_state = _build_task_state(status=TaskStatus.IN_PROGRESS, pending=None)
    thread = _build_thread()
    resume_state = GraphResumeState(
        task_id="task-1",
        thread_id="thread-1",
        graph_thread_id="task-1",
        graph_type="chat",
        graph_version="v1",
        checkpoint_ns="agent_turn",
        checkpoint_id="ckpt-1",
        waiting_reason="approval_required",
        pending_approval_id="approval-1",
        pending_interrupt_id="interrupt-1",
    )
    decided_record = approval_record.model_copy(
        update={
            "status": ApprovalStatus.REJECTED,
            "decision": ApprovalDecision(decision=ApprovalDecisionType.REJECTED),
        }
    )

    mock_task_manager = AsyncMock()
    mock_task_manager.get_task_state = AsyncMock(side_effect=[task_state, post_resume_state])
    mock_task_manager.set_pending_approval = AsyncMock()
    mock_task_manager.set_resume_supported = AsyncMock()
    mock_task_manager.update_task_status = AsyncMock()
    mock_task_manager.add_task_update = AsyncMock()
    mock_task_manager.set_task_result = AsyncMock()

    mock_thread_manager = AsyncMock()
    mock_thread_manager.get_thread = AsyncMock(return_value=thread)
    mock_thread_manager.set_message_trace = AsyncMock()
    mock_thread_manager.append_messages = AsyncMock()

    mock_approval_manager = AsyncMock()
    mock_approval_manager.get_resume_state = AsyncMock(return_value=resume_state)
    mock_approval_manager.get_approval = AsyncMock(return_value=approval_record)
    mock_approval_manager.record_decision = AsyncMock(return_value=decided_record)
    mock_approval_manager.save_resume_state = AsyncMock()
    mock_approval_manager.delete_resume_state = AsyncMock()

    mock_chat_agent = AsyncMock()
    mock_chat_agent.resume_query = AsyncMock(
        return_value=AgentResponse(response="Okay, I will not make that change.", tool_envelopes=[])
    )

    with (
        patch("redis_sre_agent.core.docket_tasks.TaskManager", return_value=mock_task_manager),
        patch("redis_sre_agent.core.docket_tasks.ThreadManager", return_value=mock_thread_manager),
        patch(
            "redis_sre_agent.core.docket_tasks.ApprovalManager",
            return_value=mock_approval_manager,
        ),
        patch("redis_sre_agent.core.docket_tasks.get_instance_by_id", new=AsyncMock()),
        patch("redis_sre_agent.core.docket_tasks.get_cluster_by_id", new=AsyncMock()),
        patch("redis_sre_agent.agent.chat_agent.ChatAgent", return_value=mock_chat_agent),
    ):
        result = await resume_task_after_approval(
            task_id="task-1",
            approval_id="approval-1",
            decision="rejected",
            decision_comment="Not approved",
        )

    assert result["response"]["response"] == "Okay, I will not make that change."
    mock_approval_manager.record_decision.assert_awaited_once()
    resume_payload = mock_chat_agent.resume_query.await_args.kwargs["resume_payload"]
    assert resume_payload["decision"] == ApprovalDecisionType.REJECTED.value
    mock_approval_manager.delete_resume_state.assert_awaited_once_with("task-1")


@pytest.mark.asyncio
async def test_resume_task_after_approval_rejects_expired_approval():
    expired_record = _build_approval().model_copy(
        update={
            "expires_at": (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(),
        }
    )
    pending = PendingApprovalSummary.from_record(expired_record)
    task_state = _build_task_state(status=TaskStatus.AWAITING_APPROVAL, pending=pending)
    thread = _build_thread()
    resume_state = GraphResumeState(
        task_id="task-1",
        thread_id="thread-1",
        graph_thread_id="task-1",
        graph_type="chat",
        graph_version="v1",
        checkpoint_ns="agent_turn",
        checkpoint_id="ckpt-1",
        waiting_reason="approval_required",
        pending_approval_id="approval-1",
        pending_interrupt_id="interrupt-1",
    )
    expired_state = expired_record.model_copy(update={"status": ApprovalStatus.EXPIRED})

    mock_task_manager = AsyncMock()
    mock_task_manager.get_task_state = AsyncMock(return_value=task_state)

    mock_thread_manager = AsyncMock()
    mock_thread_manager.get_thread = AsyncMock(return_value=thread)

    mock_approval_manager = AsyncMock()
    mock_approval_manager.get_resume_state = AsyncMock(return_value=resume_state)
    mock_approval_manager.get_approval = AsyncMock(return_value=expired_record)
    mock_approval_manager.expire_approval = AsyncMock(return_value=expired_state)

    with (
        patch("redis_sre_agent.core.docket_tasks.TaskManager", return_value=mock_task_manager),
        patch("redis_sre_agent.core.docket_tasks.ThreadManager", return_value=mock_thread_manager),
        patch(
            "redis_sre_agent.core.docket_tasks.ApprovalManager",
            return_value=mock_approval_manager,
        ),
        pytest.raises(ValueError, match="Approval approval-1 has expired"),
    ):
        await resume_task_after_approval(
            task_id="task-1",
            approval_id="approval-1",
            decision="approved",
        )

    mock_approval_manager.expire_approval.assert_awaited_once_with("approval-1")


@pytest.mark.asyncio
async def test_resume_task_after_approval_rejects_interrupt_mismatch():
    approval_record = _build_approval()
    pending = PendingApprovalSummary.from_record(approval_record).model_copy(
        update={"interrupt_id": "interrupt-2"}
    )
    task_state = _build_task_state(status=TaskStatus.AWAITING_APPROVAL, pending=pending)
    thread = _build_thread()
    resume_state = GraphResumeState(
        task_id="task-1",
        thread_id="thread-1",
        graph_thread_id="task-1",
        graph_type="chat",
        graph_version="v1",
        checkpoint_ns="agent_turn",
        checkpoint_id="ckpt-1",
        waiting_reason="approval_required",
        pending_approval_id="approval-1",
        pending_interrupt_id="interrupt-1",
    )

    mock_task_manager = AsyncMock()
    mock_task_manager.get_task_state = AsyncMock(return_value=task_state)

    mock_thread_manager = AsyncMock()
    mock_thread_manager.get_thread = AsyncMock(return_value=thread)

    mock_approval_manager = AsyncMock()
    mock_approval_manager.get_resume_state = AsyncMock(return_value=resume_state)
    mock_approval_manager.get_approval = AsyncMock(return_value=approval_record)

    with (
        patch("redis_sre_agent.core.docket_tasks.TaskManager", return_value=mock_task_manager),
        patch("redis_sre_agent.core.docket_tasks.ThreadManager", return_value=mock_thread_manager),
        patch(
            "redis_sre_agent.core.docket_tasks.ApprovalManager",
            return_value=mock_approval_manager,
        ),
        pytest.raises(
            ValueError,
            match="Approval interrupt does not match the current pending approval",
        ),
    ):
        await resume_task_after_approval(
            task_id="task-1",
            approval_id="approval-1",
            decision="approved",
        )
