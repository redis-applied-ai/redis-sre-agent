"""Docket task definitions for SRE operations."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from docket import ConcurrencyLimit, Docket, Perpetual, Retry
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.errors import GraphInterrupt
from ulid import ULID

from redis_sre_agent.agent import get_sre_agent
from redis_sre_agent.agent.chat_agent import get_chat_agent
from redis_sre_agent.agent.langgraph_agent import (
    _extract_instance_details_from_message,
)
from redis_sre_agent.agent.router import AgentType, route_to_appropriate_agent
from redis_sre_agent.core.approvals import (
    ApprovalDecision,
    ApprovalDecisionType,
    ApprovalManager,
    ApprovalRecord,
    ApprovalRequiredError,
    ApprovalStatus,
)
from redis_sre_agent.core.citation_message import (
    build_citation_message_payloads,
    should_include_citations,
)
from redis_sre_agent.core.clusters import get_cluster_by_id
from redis_sre_agent.core.config import Settings, settings
from redis_sre_agent.core.instances import (
    RedisInstance,
    RedisInstanceType,
    add_session_instance,
    get_instance_by_id,
    get_session_instances,
)
from redis_sre_agent.core.knowledge_helpers import (
    ingest_sre_document_helper,
    search_knowledge_base_helper,
)
from redis_sre_agent.core.progress import TaskEmitter
from redis_sre_agent.core.qa import QAManager
from redis_sre_agent.core.redis import (
    get_redis_client,
)
from redis_sre_agent.core.targets import get_attached_target_handles_from_context
from redis_sre_agent.core.tasks import TaskManager, TaskStatus
from redis_sre_agent.core.threads import Message, ThreadManager
from redis_sre_agent.core.turn_scope import TurnScope

logger = logging.getLogger(__name__)

# SRE-specific task registry
SRE_TASK_COLLECTION = []


def sre_task(func):
    """Decorator to register SRE tasks."""
    SRE_TASK_COLLECTION.append(func)
    return func


def _thread_messages_to_conversation_history(thread_messages: List[Message]) -> List[Any]:
    """Convert persisted thread messages into LangChain conversation history."""
    history: List[Any] = []
    for msg in thread_messages:
        if msg.role == "user":
            history.append(HumanMessage(content=msg.content))
        elif msg.role == "assistant":
            history.append(AIMessage(content=msg.content))
    return history


def _extract_pending_approval_from_response(response: Any) -> Optional[Dict[str, Any]]:
    """Return pending approval metadata from an agent response, if present."""

    tool_envelopes = (
        response.get("tool_envelopes", [])
        if isinstance(response, dict)
        else getattr(response, "tool_envelopes", None) or []
    )
    for envelope in tool_envelopes:
        if not isinstance(envelope, dict):
            continue
        data = envelope.get("data")
        if not isinstance(data, dict):
            continue
        if data.get("status") != "approval_required":
            continue
        pending_approval = data.get("pending_approval")
        if isinstance(pending_approval, dict):
            return pending_approval
    return None


def _extract_pending_approval_from_interrupt(error: GraphInterrupt) -> Optional[Dict[str, Any]]:
    """Return the approval payload embedded in a LangGraph interrupt."""
    if not error.args:
        return None

    interrupts = error.args[0]
    if not isinstance(interrupts, (list, tuple)):
        interrupts = [interrupts]

    for item in interrupts:
        payload = getattr(item, "value", None)
        if isinstance(payload, dict) and payload.get("kind") == "approval_required":
            return payload
    return None


async def _resolve_instance_for_thread(
    instance_id: Optional[str], thread_id: Optional[str]
) -> Optional[RedisInstance]:
    """Resolve an instance ID against persistent storage, then thread-scoped session instances."""
    if not instance_id:
        return None

    instance = await get_instance_by_id(instance_id)
    if instance or not thread_id:
        return instance

    for session_instance in await get_session_instances(thread_id):
        if session_instance.id == instance_id:
            return session_instance
    return None


async def _stage_session_instance_from_message(
    *,
    thread_id: str,
    thread_user_id: Optional[str],
    instance_details: Dict[str, str],
) -> RedisInstance:
    """Stage extracted connection details as a thread-scoped instance without mutating global config."""
    connection_url = instance_details["connection_url"]
    name = instance_details["name"]

    for session_instance in await get_session_instances(thread_id):
        if (
            session_instance.name == name
            or session_instance.connection_url.get_secret_value() == connection_url
        ):
            return session_instance

    session_instance = RedisInstance(
        id=f"redis-{instance_details['environment']}-{ULID()}",
        name=name,
        connection_url=connection_url,
        environment=instance_details["environment"],
        usage=instance_details["usage"],
        description=instance_details.get(
            "description", "Staged by agent from user-provided connection details"
        ),
        created_by="agent",
        user_id=thread_user_id,
        instance_type=RedisInstanceType.unknown,
    )
    if not await add_session_instance(thread_id, session_instance):
        raise ValueError("Failed to stage session instance from provided details")
    return session_instance


async def _transition_task_to_awaiting_approval(
    *,
    task_manager: TaskManager,
    task_id: str,
    thread_id: str,
    error: ApprovalRequiredError,
) -> Dict[str, Any]:
    """Persist task state for a paused turn waiting on human approval."""
    pending_approval = error.pending_approval
    approval_record = error.approval_record

    await task_manager.update_task_status(task_id, TaskStatus.AWAITING_APPROVAL)
    await task_manager.set_pending_approval(task_id, pending_approval)
    await task_manager.set_resume_supported(task_id, True)
    await task_manager.add_task_update(
        task_id,
        error.decision.message or "Approval required before continuing task execution.",
        "pending_approval",
        metadata={
            "approval_id": approval_record.approval_id if approval_record else None,
            "interrupt_id": approval_record.interrupt_id if approval_record else None,
            "tool_name": error.decision.tool_name,
            "tool_args_preview": (
                approval_record.tool_args_preview if approval_record is not None else {}
            ),
            "target_handles": approval_record.target_handles if approval_record is not None else [],
            "expires_at": approval_record.expires_at if approval_record is not None else None,
        },
    )

    result = {
        "status": TaskStatus.AWAITING_APPROVAL.value,
        "thread_id": thread_id,
        "task_id": task_id,
        "resume_supported": True,
        "pending_approval": (
            pending_approval.model_dump(mode="json") if pending_approval is not None else None
        ),
        "approval_id": approval_record.approval_id if approval_record is not None else None,
        "interrupt_id": approval_record.interrupt_id if approval_record is not None else None,
        "tool_name": error.decision.tool_name,
    }
    await task_manager.set_task_result(task_id, result)
    try:
        await task_manager._publish_stream_update(
            thread_id,
            "awaiting_approval",
            {
                "task_id": task_id,
                "message": "Task is awaiting approval",
                "pending_approval": result["pending_approval"] or {},
            },
        )
    except Exception:
        logger.debug("Failed to publish awaiting_approval update for task %s", task_id)
    return result


def _approval_is_expired(record: ApprovalRecord) -> bool:
    """Return True when an approval has passed its expiry timestamp."""

    if not record.expires_at:
        return False
    try:
        expires_at = datetime.fromisoformat(record.expires_at.replace("Z", "+00:00"))
    except Exception:
        return False
    return expires_at <= datetime.now(timezone.utc)


def _normalize_approval_decision(
    decision: ApprovalDecisionType | str,
) -> ApprovalDecisionType:
    """Normalize caller input into an approval decision enum."""

    if isinstance(decision, ApprovalDecisionType):
        return decision

    normalized = str(decision or "").strip().lower()
    if normalized == ApprovalDecisionType.APPROVED.value:
        return ApprovalDecisionType.APPROVED
    if normalized == ApprovalDecisionType.REJECTED.value:
        return ApprovalDecisionType.REJECTED
    raise ValueError(f"Unsupported approval decision: {decision}")


def _build_resume_payload(
    *,
    approval_record: ApprovalRecord,
    decision: ApprovalDecision,
) -> Dict[str, Any]:
    """Build the resume payload passed back into LangGraph."""

    return {
        "approval_id": approval_record.approval_id,
        "interrupt_id": approval_record.interrupt_id,
        "decision": decision.decision.value,
        "decision_at": decision.decision_at,
        "decision_by": decision.decision_by,
        "decision_comment": decision.decision_comment,
        "action_hash": approval_record.action_hash,
        "tool_name": approval_record.tool_name,
    }


async def _load_resume_context(
    *,
    task_id: str,
    approval_id: str,
    decision: ApprovalDecisionType | str,
    decision_by: Optional[str],
    decision_comment: Optional[str],
    task_state: Optional[Any] = None,
    task_manager: TaskManager,
    thread_manager: ThreadManager,
    approval_manager: ApprovalManager,
) -> tuple[Any, Any, Any, ApprovalRecord, ApprovalDecision]:
    """Load and validate the persisted state needed to resume an approval pause."""

    task_state = task_state or await task_manager.get_task_state(task_id)
    if not task_state:
        raise ValueError(f"Task {task_id} not found")
    if task_state.status not in {TaskStatus.AWAITING_APPROVAL, TaskStatus.IN_PROGRESS}:
        raise ValueError(f"Task {task_id} is not awaiting approval")

    thread_id = task_state.thread_id
    thread = await thread_manager.get_thread(thread_id)
    if not thread:
        raise ValueError(f"Thread {thread_id} not found for task {task_id}")

    resume_state = await approval_manager.get_resume_state(task_id)
    if not resume_state:
        raise ValueError(f"Task {task_id} is missing resume state")

    approval_record = await approval_manager.get_approval(approval_id)
    if not approval_record:
        raise ValueError(f"Approval {approval_id} not found")
    if approval_record.task_id != task_id:
        raise ValueError(f"Approval {approval_id} does not belong to task {task_id}")

    pending_summary = getattr(task_state, "pending_approval", None)
    if pending_summary is not None:
        if pending_summary.approval_id != approval_id:
            raise ValueError(
                f"Task {task_id} is waiting on approval {pending_summary.approval_id}, not {approval_id}"
            )
        if pending_summary.interrupt_id != approval_record.interrupt_id:
            raise ValueError(
                "Approval interrupt does not match the current pending approval for this task"
            )

    if resume_state.pending_approval_id and resume_state.pending_approval_id != approval_id:
        raise ValueError(
            f"Task {task_id} is waiting on approval {resume_state.pending_approval_id}, not {approval_id}"
        )
    if (
        resume_state.pending_interrupt_id
        and resume_state.pending_interrupt_id != approval_record.interrupt_id
    ):
        raise ValueError("Approval interrupt does not match the current resume checkpoint")
    if (
        approval_record.graph_thread_id
        and resume_state.graph_thread_id
        and approval_record.graph_thread_id != resume_state.graph_thread_id
    ):
        raise ValueError("Approval graph thread does not match the current resume checkpoint")
    if (
        approval_record.graph_type
        and resume_state.graph_type
        and approval_record.graph_type != resume_state.graph_type
    ):
        raise ValueError("Approval graph type does not match the current resume checkpoint")

    if _approval_is_expired(approval_record) and approval_record.status is ApprovalStatus.PENDING:
        approval_record = await approval_manager.expire_approval(approval_id) or approval_record
    if approval_record.status is ApprovalStatus.EXPIRED:
        raise ValueError(f"Approval {approval_id} has expired")

    normalized_decision = _normalize_approval_decision(decision)
    decision_model = ApprovalDecision(
        decision=normalized_decision,
        decision_by=decision_by,
        decision_comment=decision_comment,
    )
    return task_state, thread, resume_state, approval_record, decision_model


async def validate_task_resume_request(
    *,
    task_id: str,
    approval_id: str,
    decision: ApprovalDecisionType | str,
    decision_by: Optional[str] = None,
    decision_comment: Optional[str] = None,
    redis_client=None,
) -> None:
    """Validate that a task can be resumed for the requested approval decision."""

    redis_client = redis_client or get_redis_client()
    task_manager = TaskManager(redis_client=redis_client)
    task_state = await task_manager.get_task_state(task_id)
    if not task_state:
        raise ValueError(f"Task {task_id} not found")
    if task_state.status != TaskStatus.AWAITING_APPROVAL:
        return

    await _load_resume_context(
        task_id=task_id,
        approval_id=approval_id,
        decision=decision,
        decision_by=decision_by,
        decision_comment=decision_comment,
        task_state=task_state,
        task_manager=task_manager,
        thread_manager=ThreadManager(redis_client=redis_client),
        approval_manager=ApprovalManager(redis_client=redis_client),
    )


def _build_awaiting_approval_result(
    *,
    task_id: str,
    thread_id: str,
    task_state: Any,
) -> Dict[str, Any]:
    """Build a serialized awaiting-approval result payload from TaskState."""

    pending_approval = (
        task_state.pending_approval.model_dump(mode="json")
        if task_state and task_state.pending_approval
        else None
    )
    return {
        "status": TaskStatus.AWAITING_APPROVAL.value,
        "thread_id": thread_id,
        "task_id": task_id,
        "pending_approval": pending_approval,
        "resume_supported": bool(task_state.resume_supported) if task_state else True,
    }


async def _transition_task_to_awaiting_approval_from_interrupt(
    *,
    task_manager: TaskManager,
    task_id: str,
    thread_id: str,
    error: GraphInterrupt,
) -> Dict[str, Any]:
    """Persist task state when LangGraph returns an approval interrupt."""
    task_state = await task_manager.get_task_state(task_id)
    pending_approval = task_state.pending_approval if task_state is not None else None
    payload = _extract_pending_approval_from_interrupt(error) or {}
    payload_pending = payload.get("pending_approval")
    if pending_approval is None and isinstance(payload_pending, dict):
        try:
            from redis_sre_agent.core.approvals import PendingApprovalSummary

            pending_approval = PendingApprovalSummary(**payload_pending)
        except Exception:
            pending_approval = None

    await task_manager.set_pending_approval(task_id, pending_approval)
    await task_manager.set_resume_supported(task_id, True)
    await task_manager.add_task_update(
        task_id,
        str(payload.get("message") or "Approval required before continuing task execution."),
        "pending_approval",
        metadata={"pending_approval": payload_pending or {}},
    )

    result = {
        "status": TaskStatus.AWAITING_APPROVAL.value,
        "thread_id": thread_id,
        "task_id": task_id,
        "resume_supported": True,
        "pending_approval": (
            pending_approval.model_dump(mode="json") if pending_approval is not None else None
        ),
        "approval_id": payload.get("approval_id")
        or (pending_approval.approval_id if pending_approval is not None else None),
        "interrupt_id": payload.get("interrupt_id")
        or (pending_approval.interrupt_id if pending_approval is not None else None),
        "tool_name": payload.get("tool_name")
        or (pending_approval.tool_name if pending_approval is not None else None),
    }
    await task_manager.set_task_result(task_id, result)
    await task_manager.update_task_status(task_id, TaskStatus.AWAITING_APPROVAL)
    try:
        await task_manager._publish_stream_update(
            thread_id,
            "awaiting_approval",
            {
                "task_id": task_id,
                "message": "Task is awaiting approval",
                "pending_approval": result["pending_approval"] or {},
            },
        )
    except Exception:
        logger.debug("Failed to publish awaiting_approval update for task %s", task_id)
    return result


async def _ensure_handle_backed_turn_scope(
    *,
    turn_scope: TurnScope,
    routing_context: Dict[str, Any],
    thread_context: Dict[str, Any],
    thread_id: str,
    task_id: str,
    legacy_instance_id: Optional[str] = None,
    legacy_cluster_id: Optional[str] = None,
) -> TurnScope:
    """Materialize legacy seed-hint scope through private handle records when needed."""
    from redis_sre_agent.core.targets import (
        build_seed_hint_candidates,
        materialize_bound_target_scope,
    )
    from redis_sre_agent.targets import get_target_handle_store

    normalized_instance_id = str(legacy_instance_id or "").strip() or None
    normalized_cluster_id = str(legacy_cluster_id or "").strip() or None

    if normalized_instance_id and normalized_cluster_id:
        routing_instance_id = str(routing_context.get("instance_id") or "").strip() or None
        routing_cluster_id = str(routing_context.get("cluster_id") or "").strip() or None

        if turn_scope.bindings:
            # Attached bindings already define the target set. Ignore conflicting
            # legacy single-target hints so the seed-hint resolver does not raise.
            normalized_instance_id = None
            normalized_cluster_id = None
        elif routing_instance_id and not routing_cluster_id:
            normalized_cluster_id = None
        elif routing_cluster_id and not routing_instance_id:
            normalized_instance_id = None
        else:
            # Conflicting legacy single-target hints are ambiguous. Drop both
            # rather than raising while rebuilding handle-backed scope.
            normalized_instance_id = None
            normalized_cluster_id = None

    needs_materialization = False
    if turn_scope.scope_kind != "target_bindings":
        needs_materialization = bool(normalized_instance_id or normalized_cluster_id)
    elif turn_scope.bindings:
        bound_handles = [binding.target_handle for binding in turn_scope.bindings]
        handle_records = await get_target_handle_store().get_records(bound_handles)
        needs_materialization = any(
            binding.target_handle not in handle_records for binding in turn_scope.bindings
        )

    if not needs_materialization:
        return turn_scope

    candidates = await build_seed_hint_candidates(
        bindings=turn_scope.bindings,
        instance_id=normalized_instance_id,
        cluster_id=normalized_cluster_id,
    )
    if not candidates:
        return turn_scope

    materialized_scope = await materialize_bound_target_scope(
        matches=candidates,
        thread_id=thread_id,
        task_id=task_id,
        replace_existing=bool(turn_scope.bindings),
    )
    scope_updates = dict(materialized_scope.context_updates)
    if normalized_instance_id:
        scope_updates["instance_id"] = normalized_instance_id
        scope_updates["cluster_id"] = ""
    elif normalized_cluster_id:
        scope_updates["cluster_id"] = normalized_cluster_id
        scope_updates["instance_id"] = ""

    routing_context.update(scope_updates)
    thread_context.update(scope_updates)

    return TurnScope.from_context(
        routing_context,
        thread_id=thread_id,
        session_id=turn_scope.session_id,
        seed_hints={
            key: routing_context[key]
            for key in ("instance_id", "cluster_id")
            if routing_context.get(key)
        },
    )


# NOTE: analyze_system_metrics was removed as it was never actually provided
# as a tool to the LLM. Metrics/diagnostics will be implemented via the
# ToolProvider system in a future PR.


@sre_task
async def search_knowledge_base(
    query: str,
    category: Optional[str] = None,
    doc_type: Optional[str] = None,
    limit: int = 5,
    distance_threshold: Optional[float] = None,
    retry: Retry = Retry(attempts=2, delay=timedelta(seconds=2)),
) -> Dict[str, Any]:
    """
    Search SRE knowledge base and runbooks (background task wrapper).

    This is a Docket task wrapper around the core helper function.
    It adds retry logic and task tracking for background execution.

    Args:
        query: Search query text
        category: Optional category filter (incident, maintenance, monitoring, etc.)
        doc_type: Optional document type filter
        limit: Maximum number of results
        distance_threshold: Optional cosine distance threshold. If provided, overrides backend default.
        retry: Retry configuration

    Returns:
        Dictionary with search results
    """
    try:
        kwargs = {"query": query, "limit": limit}
        if category is not None:
            kwargs["category"] = category
        if doc_type is not None:
            kwargs["doc_type"] = doc_type
        if distance_threshold is not None:
            kwargs["distance_threshold"] = distance_threshold
        result = await search_knowledge_base_helper(**kwargs)
        # Ensure a task_id is present for callers/tests expecting it
        try:
            from ulid import ULID

            result.setdefault("task_id", str(ULID()))
        except Exception:
            # Best-effort; absence shouldn't break callers
            result.setdefault("task_id", "task")
        return result
    except Exception as e:
        logger.error(f"Knowledge search failed (attempt {retry.attempt}): {e}")
        raise


@sre_task
async def ingest_sre_document(
    title: str,
    content: str,
    source: str,
    category: str = "general",
    severity: str = "info",
    doc_type: Optional[str] = None,
    product_labels: Optional[List[str]] = None,
    retry: Retry = Retry(attempts=3, delay=timedelta(seconds=2)),
) -> Dict[str, Any]:
    """
    Ingest a document into the SRE knowledge base (background task wrapper).

    This is a Docket task wrapper around the core helper function.
    It adds retry logic and task tracking for background execution.

    Args:
        title: Document title
        content: Document content
        source: Source system or file
        category: Document category (incident, runbook, monitoring, etc.)
        severity: Severity level (info, warning, critical)
        doc_type: Optional document type
        product_labels: Optional list of product labels
        retry: Retry configuration

    Returns:
        Dictionary with ingestion result
    """
    try:
        return await ingest_sre_document_helper(
            title=title,
            content=content,
            source=source,
            category=category,
            severity=severity,
            doc_type=doc_type,
            product_labels=product_labels,
        )
    except Exception as e:
        logger.error(f"Document ingestion failed (attempt {retry.attempt}): {e}")
        raise


@sre_task
async def embed_qa_record(
    qa_id: str,
    retry: Retry = Retry(attempts=3, delay=timedelta(seconds=2)),
) -> Dict[str, Any]:
    """
    Generate embeddings for a Q&A record out-of-band.

    This Docket task fetches the Q&A record, generates embeddings for the
    question and answer using the configured vectorizer, and updates the
    record with the vectors. This allows Q&A recording to remain fast
    while embeddings are computed asynchronously.

    Args:
        qa_id: The ID of the QuestionAnswer record to embed
        retry: Retry configuration

    Returns:
        Dictionary with status and qa_id
    """
    from redis_sre_agent.core.qa import QAManager
    from redis_sre_agent.core.redis import get_vectorizer

    try:
        # Get the Q&A record
        qa_manager = QAManager()
        qa = await qa_manager.get_qa(qa_id)

        if qa is None:
            logger.warning(f"Q&A record {qa_id} not found for embedding")
            return {"status": "error", "error": f"Q&A record {qa_id} not found", "qa_id": qa_id}

        # Generate embeddings
        vectorizer = get_vectorizer()
        question_vector = await vectorizer.aembed(qa.question, as_buffer=True)
        answer_vector = await vectorizer.aembed(qa.answer, as_buffer=True)

        # Update the record with vectors
        await qa_manager.update_vectors(
            qa_id=qa_id,
            question_vector=question_vector,
            answer_vector=answer_vector,
        )

        logger.info(f"Embedded Q&A record {qa_id}")
        return {"status": "success", "qa_id": qa_id}

    except Exception as e:
        logger.error(f"Q&A embedding failed for {qa_id} (attempt {retry.attempt}): {e}")
        raise


@sre_task
async def process_chat_turn(
    query: str,
    task_id: str,
    thread_id: str,
    instance_id: Optional[str] = None,
    cluster_id: Optional[str] = None,
    user_id: Optional[str] = None,
    exclude_mcp_categories: Optional[List[str]] = None,
    retry: Retry = Retry(attempts=2, delay=timedelta(seconds=2)),
) -> Dict[str, Any]:
    """
    Process a chat query using the ChatAgent (background task).

    This runs the lightweight ChatAgent for quick Q&A about Redis instances.
    Notifications are emitted to the task, and the result is stored on both
    the task and the thread.

    Args:
        query: User's question
        task_id: Task ID for notifications and result storage
        thread_id: Thread ID for conversation context and result storage
        instance_id: Optional Redis instance ID
        cluster_id: Optional Redis cluster ID
        user_id: Optional user ID for tracking
        exclude_mcp_categories: Optional list of MCP tool category names to exclude.
            Valid values: "metrics", "logs", "tickets", "repos", "traces",
            "diagnostics", "knowledge", "utilities".
        retry: Retry configuration

    Returns:
        Dictionary with the chat response
    """
    from redis_sre_agent.agent.chat_agent import ChatAgent
    from redis_sre_agent.tools.models import ToolCapability

    logger.info(f"Processing chat turn for task {task_id}")

    redis_client = get_redis_client()
    task_manager = TaskManager(redis_client=redis_client)
    thread_manager = ThreadManager(redis_client=redis_client)

    # Mark task as in progress
    await task_manager.update_task_status(task_id, TaskStatus.IN_PROGRESS)

    # Convert string category names to ToolCapability enums
    mcp_categories: Optional[List[ToolCapability]] = None
    if exclude_mcp_categories:
        mcp_categories = []
        for cat_name in exclude_mcp_categories:
            try:
                mcp_categories.append(ToolCapability(cat_name.lower()))
            except ValueError:
                logger.warning(f"Unknown MCP category to exclude: {cat_name}")

    try:
        # Create task emitter for notifications
        emitter = TaskEmitter(task_manager=task_manager, task_id=task_id)

        if instance_id and cluster_id:
            raise ValueError("Please provide only one of instance_id or cluster_id")

        # Get Redis instance if specified
        redis_instance = None
        if instance_id:
            redis_instance = await get_instance_by_id(instance_id)
            if not redis_instance:
                raise ValueError(f"Instance not found: {instance_id}")

        redis_cluster = None
        if cluster_id:
            redis_cluster = await get_cluster_by_id(cluster_id)
            if not redis_cluster:
                raise ValueError(f"Cluster not found: {cluster_id}")

        # Run chat agent
        agent = ChatAgent(
            redis_instance=redis_instance,
            redis_cluster=redis_cluster,
            progress_emitter=emitter,
            exclude_mcp_categories=mcp_categories,
        )
        agent_context = {"task_id": task_id}
        if instance_id:
            agent_context["instance_id"] = instance_id
        if cluster_id:
            agent_context["cluster_id"] = cluster_id
        response = await agent.process_query(
            query=query,
            session_id=thread_id,
            user_id=user_id,
            context=agent_context,
            progress_emitter=emitter,
        )

        pending_approval = _extract_pending_approval_from_response(response)
        current_task_state = await task_manager.get_task_state(task_id)
        if pending_approval or (
            current_task_state and current_task_state.status == TaskStatus.AWAITING_APPROVAL
        ):
            result = {
                "status": TaskStatus.AWAITING_APPROVAL.value,
                "task_id": task_id,
                "thread_id": thread_id,
                "pending_approval": pending_approval
                or (
                    current_task_state.pending_approval.model_dump(mode="json")
                    if current_task_state and current_task_state.pending_approval
                    else None
                ),
                "resume_supported": current_task_state.resume_supported
                if current_task_state
                else True,
            }
            return result

        # Store result on task (convert AgentResponse to dict for JSON serialization)
        result = {
            "response": response.model_dump() if hasattr(response, "model_dump") else response,
            "instance_id": instance_id,
            "cluster_id": cluster_id,
        }
        await task_manager.set_task_result(task_id, result)
        await task_manager.update_task_status(task_id, TaskStatus.DONE)

        # Generate message_id for the assistant response
        from ulid import ULID

        message_id = str(ULID())

        # Store decision trace for this message (tool calls + citations)
        tool_envelopes = response.tool_envelopes if hasattr(response, "tool_envelopes") else []
        if tool_envelopes:
            try:
                from opentelemetry import trace as otel_trace

                current_span = otel_trace.get_current_span()
                span_context = current_span.get_span_context() if current_span else None
                otel_trace_id = (
                    format(span_context.trace_id, "032x")
                    if span_context and span_context.is_valid
                    else None
                )
            except Exception:
                otel_trace_id = None

            await thread_manager.set_message_trace(
                message_id=message_id,
                tool_envelopes=tool_envelopes,
                otel_trace_id=otel_trace_id,
            )

        # Add response to thread as assistant message
        # response is an AgentResponse; extract the text for thread content
        response_text = response.response if hasattr(response, "response") else str(response)
        await thread_manager.append_messages(
            thread_id,
            [
                {
                    "role": "assistant",
                    "content": response_text,
                    "metadata": {"task_id": task_id, "message_id": message_id, "agent": "chat"},
                }
            ],
        )
        return result

    except GraphInterrupt as exc:
        logger.info("Chat turn paused awaiting approval for task %s", task_id)
        return await _transition_task_to_awaiting_approval_from_interrupt(
            task_manager=task_manager,
            task_id=task_id,
            thread_id=thread_id,
            error=exc,
        )

    except ApprovalRequiredError as exc:
        logger.info("Chat turn paused awaiting approval for task %s", task_id)
        return await _transition_task_to_awaiting_approval(
            task_manager=task_manager,
            task_id=task_id,
            thread_id=thread_id,
            error=exc,
        )

    except Exception as e:
        logger.error(f"Chat turn failed: {e}")
        await task_manager.set_task_error(task_id, str(e))
        raise


@sre_task
async def process_knowledge_query(
    query: str,
    task_id: str,
    thread_id: str,
    user_id: Optional[str] = None,
    retry: Retry = Retry(attempts=2, delay=timedelta(seconds=2)),
) -> Dict[str, Any]:
    """
    Process a knowledge query using the chat agent compatibility path.

    This routes onto the default chat agent with no explicit Redis scope.
    Notifications are emitted to the task, and the result is stored on both
    the task and the thread.

    Args:
        query: User's question about SRE practices or Redis
        task_id: Task ID for notifications and result storage
        thread_id: Thread ID for conversation context and result storage
        user_id: Optional user ID for tracking
        retry: Retry configuration

    Returns:
        Dictionary with the knowledge agent response
    """
    logger.info(f"Processing knowledge query for task {task_id}")

    redis_client = get_redis_client()
    task_manager = TaskManager(redis_client=redis_client)
    thread_manager = ThreadManager(redis_client=redis_client)

    # Mark task as in progress
    await task_manager.update_task_status(task_id, TaskStatus.IN_PROGRESS)

    try:
        # Create task emitter for notifications
        emitter = TaskEmitter(task_manager=task_manager, task_id=task_id)

        conversation_history = None
        thread = await thread_manager.get_thread(thread_id)
        if thread and thread.messages:
            history_messages = list(thread.messages)
            if (
                history_messages
                and history_messages[-1].role == "user"
                and history_messages[-1].content == query
            ):
                history_messages = history_messages[:-1]
            conversation_history = _thread_messages_to_conversation_history(history_messages)

        # Run chat agent without explicit target scope. This preserves the
        # legacy entrypoint while keeping runtime behavior on the two-agent model.
        agent = get_chat_agent()
        chat_max_iterations = min(int(settings.max_iterations or 15), 10)
        response = await agent.process_query(
            query=query,
            session_id=thread_id,
            user_id=user_id,
            max_iterations=chat_max_iterations,
            context={"task_id": task_id},
            progress_emitter=emitter,
            conversation_history=conversation_history,
        )

        pending_approval = _extract_pending_approval_from_response(response)
        current_task_state = await task_manager.get_task_state(task_id)
        if pending_approval or (
            current_task_state and current_task_state.status == TaskStatus.AWAITING_APPROVAL
        ):
            return {
                "status": TaskStatus.AWAITING_APPROVAL.value,
                "task_id": task_id,
                "thread_id": thread_id,
                "pending_approval": pending_approval
                or (
                    current_task_state.pending_approval.model_dump(mode="json")
                    if current_task_state and current_task_state.pending_approval
                    else None
                ),
                "resume_supported": current_task_state.resume_supported
                if current_task_state
                else True,
            }

        # Store result on task (convert AgentResponse to dict for JSON serialization)
        result = {
            "response": response.model_dump() if hasattr(response, "model_dump") else response,
        }
        await task_manager.set_task_result(task_id, result)
        await task_manager.update_task_status(task_id, TaskStatus.DONE)

        # Generate message_id for the assistant response
        from ulid import ULID

        message_id = str(ULID())

        # Store decision trace for this message (tool calls + citations)
        tool_envelopes = response.tool_envelopes if hasattr(response, "tool_envelopes") else []
        if tool_envelopes:
            try:
                from opentelemetry import trace as otel_trace

                current_span = otel_trace.get_current_span()
                span_context = current_span.get_span_context() if current_span else None
                otel_trace_id = (
                    format(span_context.trace_id, "032x")
                    if span_context and span_context.is_valid
                    else None
                )
            except Exception:
                otel_trace_id = None

            await thread_manager.set_message_trace(
                message_id=message_id,
                tool_envelopes=tool_envelopes,
                otel_trace_id=otel_trace_id,
            )

        # Add response to thread as assistant message
        # response is an AgentResponse; extract the text for thread content
        response_text = response.response if hasattr(response, "response") else str(response)
        await thread_manager.append_messages(
            thread_id,
            [
                {
                    "role": "assistant",
                    "content": response_text,
                    "metadata": {
                        "task_id": task_id,
                        "message_id": message_id,
                        "agent": "chat",
                    },
                }
            ],
        )

        return result

    except GraphInterrupt as exc:
        logger.info("Knowledge query paused awaiting approval for task %s", task_id)
        return await _transition_task_to_awaiting_approval_from_interrupt(
            task_manager=task_manager,
            task_id=task_id,
            thread_id=thread_id,
            error=exc,
        )
    except ApprovalRequiredError as exc:
        logger.info("Knowledge query paused awaiting approval for task %s", task_id)
        return await _transition_task_to_awaiting_approval(
            task_manager=task_manager,
            task_id=task_id,
            thread_id=thread_id,
            error=exc,
        )
    except Exception as e:
        logger.error(f"Knowledge query failed: {e}")
        await task_manager.set_task_error(task_id, str(e))
        raise


@sre_task
async def process_pipeline_operation(
    operation: str,
    task_id: str,
    thread_id: str,
    batch_date: Optional[str] = None,
    artifacts_path: str = "./artifacts",
    scrapers: Optional[List[str]] = None,
    latest_only: bool = False,
    docs_path: str = "./redis-docs",
    source_dir: str = "source_documents",
    prepare_only: bool = False,
    keep_days: int = 30,
    url: Optional[str] = None,
    test_url: Optional[str] = None,
    list_urls: bool = False,
    retry: Retry = Retry(attempts=2, delay=timedelta(seconds=2)),
) -> Dict[str, Any]:
    """Run a task-backed pipeline operation and persist its result."""
    from redis_sre_agent.core.pipeline_execution_helpers import run_pipeline_operation_helper

    logger.info("Processing pipeline operation %s for task %s", operation, task_id)

    redis_client = get_redis_client()
    task_manager = TaskManager(redis_client=redis_client)

    await task_manager.update_task_status(task_id, TaskStatus.IN_PROGRESS)

    try:
        emitter = TaskEmitter(task_manager=task_manager, task_id=task_id)
        result = await run_pipeline_operation_helper(
            operation=operation,
            batch_date=batch_date,
            artifacts_path=artifacts_path,
            scrapers=scrapers,
            latest_only=latest_only,
            docs_path=docs_path,
            source_dir=source_dir,
            prepare_only=prepare_only,
            keep_days=keep_days,
            url=url,
            test_url=test_url,
            list_urls=list_urls,
            progress_emitter=emitter,
        )
        await task_manager.set_task_result(task_id, result)
        await task_manager.update_task_status(task_id, TaskStatus.DONE)
        return result
    except Exception as e:
        logger.error(
            "Pipeline operation %s failed for task %s (attempt %s): %s",
            operation,
            task_id,
            retry.attempt,
            e,
        )
        await task_manager.set_task_error(task_id, str(e))
        raise


@sre_task
async def process_runbook_operation(
    operation: str,
    task_id: str,
    thread_id: str,
    topic: Optional[str] = None,
    scenario_description: Optional[str] = None,
    severity: str = "warning",
    category: str = "operational_runbook",
    output_file: Optional[str] = None,
    requirements: Optional[List[str]] = None,
    max_iterations: int = 2,
    auto_save: bool = True,
    ingest: bool = False,
    input_dir: str = "source_documents/runbooks",
    retry: Retry = Retry(attempts=2, delay=timedelta(seconds=2)),
) -> Dict[str, Any]:
    """Run a task-backed runbook operation and persist its result."""
    from redis_sre_agent.core.runbook_execution_helpers import run_runbook_operation_helper

    logger.info("Processing runbook operation %s for task %s", operation, task_id)

    redis_client = get_redis_client()
    task_manager = TaskManager(redis_client=redis_client)

    await task_manager.update_task_status(task_id, TaskStatus.IN_PROGRESS)

    try:
        emitter = TaskEmitter(task_manager=task_manager, task_id=task_id)
        result = await run_runbook_operation_helper(
            operation=operation,
            topic=topic,
            scenario_description=scenario_description,
            severity=severity,
            category=category,
            output_file=output_file,
            requirements=requirements,
            max_iterations=max_iterations,
            auto_save=auto_save,
            ingest=ingest,
            input_dir=input_dir,
            progress_emitter=emitter,
        )
        await task_manager.set_task_result(task_id, result)
        await task_manager.update_task_status(task_id, TaskStatus.DONE)
        return result
    except Exception as e:
        logger.error(
            "Runbook operation %s failed for task %s (attempt %s): %s",
            operation,
            task_id,
            retry.attempt,
            e,
        )
        await task_manager.set_task_error(task_id, str(e))
        raise


@sre_task
async def scheduler_task(
    global_limit="scheduler",  # Need a sentinel value for concurrency limit argument
    perpetual: Perpetual = Perpetual(every=timedelta(seconds=30), automatic=True),
    concurrency: ConcurrencyLimit = ConcurrencyLimit("global_limit", max_concurrent=1),
    retry: Retry = Retry(attempts=3, delay=timedelta(seconds=5)),
) -> Dict[str, Any]:
    """
    Scheduler task that runs every 30 seconds using Perpetual with automatic=True.

    With automatic=True, Docket automatically starts and reschedules this task when
    a worker is running. No manual startup or rescheduling is needed.

    The ConcurrencyLimit ensures only ONE instance of this task runs at a time,
    preventing multiple workers or rapid rescheduling from creating duplicates.

    This task:
    1. Queries Redis for schedules that need to run based on current time
    2. Submits tasks to Docket with deduplication keys
    3. Updates schedule next_run_at times
    """
    try:
        logger.info("Running scheduler task")
        current_time = datetime.now(timezone.utc)

        # Import schedule storage functions
        from ..core.schedules import (
            find_schedules_needing_runs,
            update_schedule_last_run,
            update_schedule_next_run,
        )

        # Find schedules that need runs
        schedules_needing_runs = await find_schedules_needing_runs(current_time)
        logger.info(f"Found {len(schedules_needing_runs)} schedules needing runs")

        if not schedules_needing_runs:
            logger.debug("No schedules need runs at this time")
            return {
                "task_id": str(ULID()),
                "submitted_tasks": 0,
                "timestamp": current_time.isoformat(),
                "status": "completed",
            }

        submitted_tasks = 0

        # Get Docket instance
        async with Docket(url=await get_redis_url(), name="sre_docket") as docket:
            for schedule in schedules_needing_runs:
                try:
                    schedule_id = schedule["id"]

                    # Calculate when this task should actually run
                    # Use the next_run_at time from the schedule
                    if schedule.get("next_run_at"):
                        scheduled_time = datetime.fromisoformat(
                            schedule["next_run_at"].replace("Z", "+00:00")
                        )
                    else:
                        # Fallback to current time if no next_run_at
                        scheduled_time = current_time

                    # Create a thread for this scheduled task
                    redis_client = get_redis_client()
                    thread_manager = ThreadManager(redis_client=redis_client)

                    # Prepare context for the scheduled run
                    run_context = {
                        "schedule_id": schedule_id,
                        "schedule_name": schedule["name"],
                        "automated": True,
                        "original_query": schedule["instructions"],
                        "scheduled_at": scheduled_time.isoformat(),
                    }

                    if schedule.get("redis_instance_id"):
                        run_context["instance_id"] = schedule["redis_instance_id"]

                    # Create thread for the scheduled run
                    thread_id = await thread_manager.create_thread(
                        user_id="scheduler",
                        session_id=f"schedule_{schedule_id}_{scheduled_time.strftime('%Y%m%d_%H%M')}",
                        initial_context=run_context,
                        tags=["automated", "scheduled"],
                    )

                    # Set subject for scheduled tasks to the schedule name for clarity
                    await thread_manager.set_thread_subject(thread_id, schedule["name"])

                    # Create a unique deduplication key for this schedule + time slot
                    # This ensures we don't create duplicate tasks for the same schedule at the same time
                    time_slot = scheduled_time.strftime("%Y%m%d_%H%M")  # Round to minute precision
                    task_key = f"schedule_{schedule_id}_{time_slot}"

                    # Use Redis-based deduplication to prevent race conditions
                    redis_client = await get_redis_client()
                    dedup_key = f"sre_task_dedup:{task_key}"

                    # Try to set the deduplication key with expiration (5 minutes)
                    # This will only succeed if the key doesn't already exist
                    task_submitted = await redis_client.set(dedup_key, "submitted", ex=300, nx=True)

                    if task_submitted:
                        # We successfully claimed this task slot, submit to Docket
                        task_func = docket.add(
                            process_agent_turn, when=scheduled_time, key=task_key
                        )
                        agent_task_id = await task_func(
                            thread_id=thread_id,
                            message=schedule["instructions"],
                            context=run_context,
                        )
                        logger.info(
                            f"Submitted agent task {agent_task_id} for schedule {schedule_id} at {scheduled_time} with key {task_key}"
                        )
                        submitted_tasks += 1
                    else:
                        # Another scheduler task already submitted this task
                        logger.debug(
                            f"Agent task for schedule {schedule_id} at {scheduled_time} already submitted by another scheduler (key: {task_key})"
                        )

                    # Update last run time for both successful and skipped tasks
                    await update_schedule_last_run(schedule_id, scheduled_time)

                except Exception as e:
                    logger.error(f"Failed to process schedule {schedule_id}: {e}")

                # Calculate and update next run time regardless of success/failure
                try:
                    from ..core.schedules import Schedule

                    schedule_obj = Schedule(**schedule)
                    next_run = schedule_obj.calculate_next_run()
                    await update_schedule_next_run(schedule_id, next_run)
                    logger.debug(f"Updated next run time for schedule {schedule_id} to {next_run}")
                except Exception as e:
                    logger.error(f"Failed to update next run time for schedule {schedule_id}: {e}")

        result = {
            "task_id": str(ULID()),
            "processed_schedules": len(schedules_needing_runs),
            "submitted_tasks": submitted_tasks,
            "timestamp": current_time.isoformat(),
            "status": "completed",
        }

        logger.info(
            f"Scheduler task completed: processed {len(schedules_needing_runs)} schedules, submitted {submitted_tasks} tasks"
        )

        # Note: With automatic=True, Docket will automatically reschedule this task
        # No manual rescheduling needed

        return result

    except Exception as e:
        logger.error(f"Scheduler task failed (attempt {retry.attempt}): {e}")
        raise


async def get_redis_url() -> str:
    """Get Redis URL for Docket."""
    return settings.redis_url.get_secret_value()


async def register_sre_tasks() -> None:
    """Register all SRE tasks with Docket."""
    try:
        async with Docket(url=await get_redis_url(), name="sre_docket") as docket:
            # Register all SRE tasks
            for task in SRE_TASK_COLLECTION:
                docket.register(task)

            logger.info(f"Registered {len(SRE_TASK_COLLECTION)} SRE tasks with Docket")
    except Exception as e:
        logger.error(f"Failed to register SRE tasks: {e}")
        raise


async def _process_agent_turn_impl(
    thread_id: str,
    message: str,
    context: Optional[Dict[str, Any]] = None,
    task_id: Optional[str] = None,
    redis_client=None,
) -> Dict[str, Any]:
    """
    Process a single agent conversation turn.

    This is the main task that runs the LangGraph agent for one conversation turn,
    updating thread state throughout the execution.

    Args:
        thread_id: Thread/conversation identifier
        message: User message for this turn
        context: Additional context for the turn
    """
    redis_client = redis_client or get_redis_client()
    thread_manager = ThreadManager(redis_client=redis_client)

    # OTel: root span for the entire agent turn so Redis commands nest under it
    from opentelemetry import trace
    from opentelemetry.context import attach as _attach
    from opentelemetry.trace import set_span_in_context as _set_span_in_context

    _root_span = trace.get_tracer(__name__).start_span(
        "agent.turn",
        attributes={
            "thread.id": thread_id,
            "message.len": len(message or ""),
            "agent": "sre_agent",
        },
    )
    _root_ctx_token = _attach(_set_span_in_context(_root_span))

    try:
        logger.info(f"Processing agent turn for thread {thread_id}")

        # Get current thread
        thread = await thread_manager.get_thread(thread_id)

        # Create or use a per-turn task record associated with this thread
        task_manager = TaskManager(redis_client=redis_client)
        if task_id is None:
            task_id = await task_manager.create_task(
                thread_id=thread_id, user_id=thread.metadata.user_id if thread else None
            )
        await task_manager.update_task_status(task_id, TaskStatus.IN_PROGRESS)
        await task_manager.add_task_update(task_id, f"Started task {task_id}", "task_start")
        if not thread:
            raise ValueError(f"Thread {thread_id} not found")

        # ============================================================================
        # Target scope management logic
        # ============================================================================
        # Determine the target for this turn:
        # 1. If client provides instance_id, use it and clear cluster_id on thread
        # 2. Else if client provides cluster_id, use it and clear instance_id on thread
        # 3. Else fall back to existing thread instance_id/cluster_id
        # 4. If no target exists, attempt to create an instance from user message
        # 5. If still no target, route to the default zero-scope chat flow
        # ============================================================================

        instance_id_from_client = context.get("instance_id") if context else None
        cluster_id_from_client = context.get("cluster_id") if context else None
        instance_id_from_thread = thread.context.get("instance_id")
        cluster_id_from_thread = thread.context.get("cluster_id")
        attached_target_handles_from_thread = get_attached_target_handles_from_context(
            thread.context
        )

        if instance_id_from_client and cluster_id_from_client:
            raise ValueError("Please provide only one of instance_id or cluster_id")

        def _clear_attached_scope(target_context: Dict[str, Any]) -> None:
            target_context["attached_target_handles"] = []
            target_context["target_bindings"] = []
            target_context["target_toolset_generation"] = 0
            target_context.pop("turn_scope", None)

        # Determine active targets
        active_instance_id = None
        active_cluster_id = None
        staged_thread_instance: Optional[RedisInstance] = None

        if instance_id_from_client:
            # Client provided instance_id - use it and update thread
            active_instance_id = instance_id_from_client
            logger.info(
                f"Using instance_id from client: {active_instance_id} (will update thread context)"
            )

            # Update thread context with new instance_id and clear cluster scope
            await thread_manager.update_thread_context(
                thread_id,
                {
                    "instance_id": active_instance_id,
                    "cluster_id": "",
                    "attached_target_handles": [],
                    "target_bindings": [],
                    "target_toolset_generation": 0,
                    "turn_scope": "",
                },
                merge=True,
            )
            _clear_attached_scope(thread.context)
            await task_manager.add_task_update(
                task_id,
                f"Using Redis instance: {active_instance_id}",
                "instance_context",
            )

        elif cluster_id_from_client:
            # Client provided cluster_id - use it and update thread
            active_cluster_id = cluster_id_from_client
            logger.info(
                f"Using cluster_id from client: {active_cluster_id} (will update thread context)"
            )
            await thread_manager.update_thread_context(
                thread_id,
                {
                    "cluster_id": active_cluster_id,
                    "instance_id": "",
                    "attached_target_handles": [],
                    "target_bindings": [],
                    "target_toolset_generation": 0,
                    "turn_scope": "",
                },
                merge=True,
            )
            _clear_attached_scope(thread.context)
            await task_manager.add_task_update(
                task_id,
                f"Using Redis cluster: {active_cluster_id}",
                "cluster_context",
            )

        elif instance_id_from_thread and not attached_target_handles_from_thread:
            # No instance_id from client, but we have one saved in thread
            active_instance_id = instance_id_from_thread
            logger.info(f"Using instance_id from thread context: {active_instance_id}")
            await task_manager.add_task_update(
                task_id,
                f"Continuing with Redis instance: {active_instance_id}",
                "instance_context",
            )

        elif cluster_id_from_thread and not attached_target_handles_from_thread:
            # No explicit target from client, but cluster is saved on thread
            active_cluster_id = cluster_id_from_thread
            logger.info(f"Using cluster_id from thread context: {active_cluster_id}")
            await task_manager.add_task_update(
                task_id,
                f"Continuing with Redis cluster: {active_cluster_id}",
                "cluster_context",
            )

        else:
            # No instance_id from client or thread - attempt to create one from message
            logger.info("No instance_id found, attempting to extract from user message")

            # Try to extract connection details from the message
            instance_details = _extract_instance_details_from_message(message)

            if instance_details:
                # User provided connection details - stage a thread-scoped instance
                try:
                    logger.info("Staging session instance from user-provided connection details")
                    new_instance = await _stage_session_instance_from_message(
                        thread_id=thread_id,
                        thread_user_id=thread.metadata.user_id,
                        instance_details=instance_details,
                    )

                    active_instance_id = new_instance.id
                    staged_thread_instance = new_instance
                    logger.info(
                        "Staged session instance: %s (%s)",
                        new_instance.name,
                        active_instance_id,
                    )

                    # Save instance_id to thread context
                    await thread_manager.update_thread_context(
                        thread_id,
                        {
                            "instance_id": active_instance_id,
                            "cluster_id": "",
                            "attached_target_handles": [],
                            "target_bindings": [],
                            "target_toolset_generation": 0,
                            "turn_scope": "",
                        },
                        merge=True,
                    )
                    _clear_attached_scope(thread.context)
                    await task_manager.add_task_update(
                        task_id,
                        (
                            "Using provided Redis connection details for this thread: "
                            f"{new_instance.name} ({active_instance_id})"
                        ),
                        "instance_context",
                    )

                except Exception as e:
                    logger.warning(f"Failed to stage session instance from user details: {e}")
                    await task_manager.add_task_update(
                        task_id,
                        f"Could not stage provided Redis details for this thread: {str(e)}",
                        "instance_error",
                    )
                    # Continue without instance_id - will route to knowledge agent

        def _materialize_turn_scope(routing_payload: Dict[str, Any]) -> TurnScope:
            scope = TurnScope.from_context(
                routing_payload,
                thread_id=thread_id,
                session_id=thread.metadata.session_id or thread_id,
                seed_hints={
                    key: routing_payload[key]
                    for key in ("instance_id", "cluster_id")
                    if routing_payload.get(key)
                },
            )
            routing_payload.update(scope.to_thread_context())
            if scope.scope_kind == "target_bindings":
                routing_payload.pop("instance_id", None)
                routing_payload.pop("cluster_id", None)
            routing_payload["turn_scope"] = scope.model_dump(mode="json")
            return scope

        # Merge context for routing decision
        routing_context = thread.context.copy()
        if context:
            routing_context.update(context)
        routing_context["task_id"] = task_id
        routing_context["thread_id"] = thread_id
        routing_context["session_id"] = thread.metadata.session_id or thread_id
        attached_target_handles = get_attached_target_handles_from_context(routing_context)

        # Ensure active_instance_id is in routing context
        if active_instance_id:
            routing_context["instance_id"] = active_instance_id
            routing_context.pop("cluster_id", None)
        elif active_cluster_id:
            routing_context["cluster_id"] = active_cluster_id
            routing_context.pop("instance_id", None)

        current_scope = _materialize_turn_scope(routing_context)
        if staged_thread_instance is None:
            current_scope = await _ensure_handle_backed_turn_scope(
                turn_scope=current_scope,
                routing_context=routing_context,
                thread_context=thread.context,
                thread_id=thread_id,
                task_id=task_id,
                legacy_instance_id=(
                    routing_context.get("instance_id")
                    or current_scope.seed_hints.get("instance_id")
                ),
                legacy_cluster_id=(
                    routing_context.get("cluster_id") or current_scope.seed_hints.get("cluster_id")
                ),
            )
        routing_context["turn_scope"] = current_scope.model_dump(mode="json")

        requested_agent_type = (context or {}).get("requested_agent_type")
        if requested_agent_type == "triage":
            agent_type = AgentType.REDIS_TRIAGE
        elif requested_agent_type == "chat":
            agent_type = AgentType.REDIS_CHAT
        elif requested_agent_type == "knowledge":
            agent_type = AgentType.KNOWLEDGE_ONLY
        else:
            agent_type = await route_to_appropriate_agent(
                query=message,
                context=routing_context,
                user_preferences=None,  # Could be extended to include user preferences
            )

        if (
            agent_type == AgentType.REDIS_TRIAGE
            and current_scope.scope_kind == "zero_scope"
            and not (active_instance_id or active_cluster_id or attached_target_handles)
        ):
            try:
                from redis_sre_agent.core.targets import (
                    materialize_bound_target_scope,
                    resolve_target_query,
                )

                resolution = await resolve_target_query(
                    query=message,
                    user_id=thread.metadata.user_id,
                    allow_multiple=True,
                    max_results=5,
                    preferred_capabilities=["diagnostics", "admin", "cloud"],
                )
                if resolution.selected_matches:
                    bound_scope = await materialize_bound_target_scope(
                        matches=resolution.selected_matches,
                        thread_id=thread_id,
                        task_id=task_id,
                        replace_existing=False,
                    )
                    if bound_scope.attached_bindings:
                        routing_context.update(bound_scope.context_updates)
                        await task_manager.add_task_update(
                            task_id,
                            "Resolved target scope from natural language before deep triage",
                            "target_resolution",
                            metadata={
                                "attached_target_handles": routing_context[
                                    "attached_target_handles"
                                ],
                                "match_count": len(bound_scope.selected_bindings),
                            },
                        )
                        current_scope = _materialize_turn_scope(routing_context)
            except Exception:
                logger.exception("Failed to pre-resolve target scope for deep triage")

        logger.info(f"Routing query to {agent_type.value} agent")

        # Import and initialize the appropriate agent based on routing decision
        # REDIS_TRIAGE = full triage agent (heavy, comprehensive)
        # REDIS_CHAT / KNOWLEDGE_ONLY = lightweight/default chat agent
        explicit_client_scope = bool(instance_id_from_client or cluster_id_from_client)

        if agent_type == AgentType.REDIS_TRIAGE:
            agent = get_sre_agent()
        else:
            if (
                explicit_client_scope
                or current_scope.scope_kind == "target_bindings"
                or len(get_attached_target_handles_from_context(routing_context)) > 1
            ):
                # Explicit client-selected scope should flow through routing context so
                # stale direct bindings never survive handle-backed scope rebuilds.
                target_instance = None
                target_cluster = None
            else:
                # Get the target instance for the chat agent
                target_instance = None
                if active_instance_id:
                    if (
                        staged_thread_instance is not None
                        and staged_thread_instance.id == active_instance_id
                    ):
                        target_instance = staged_thread_instance
                    else:
                        target_instance = await _resolve_instance_for_thread(
                            active_instance_id, thread_id
                        )
                target_cluster = (
                    await get_cluster_by_id(active_cluster_id) if active_cluster_id else None
                )
            agent = get_chat_agent(
                redis_instance=target_instance,
                redis_cluster=target_cluster,
            )

        # Prepare the conversation state with thread messages
        # Convert Message objects to dicts for agent processing
        messages = [
            {
                "role": m.role,
                "content": m.content,
                **({"metadata": m.metadata} if m.metadata else {}),
            }
            for m in thread.messages
        ]
        logger.debug(f"Loaded {len(messages)} messages from thread")

        conversation_state = {
            "messages": messages,
            "thread_id": thread_id,
        }

        logger.debug(f"conversation_state messages type: {type(conversation_state['messages'])}")

        # Add the new user message
        user_msg_timestamp = datetime.now(timezone.utc).isoformat()
        conversation_state["messages"].append(
            {
                "role": "user",
                "content": message,
                "timestamp": user_msg_timestamp,
            }
        )

        # Persist the new user message early so UI transcript reflects it during processing
        try:
            await thread_manager.append_messages(
                thread_id,
                [
                    {
                        "role": "user",
                        "content": message,
                        "metadata": {"timestamp": user_msg_timestamp},
                    }
                ],
            )
        except Exception as e:
            logger.warning(f"Failed to persist user message early for thread {thread_id}: {e}")

        # Agent will post its own reflections as it works

        # Create a task emitter for agent notifications
        # Notifications go to the task only; the final result goes to both task and thread
        progress_emitter = TaskEmitter(
            task_manager=task_manager,
            task_id=task_id,
        )

        # Run the appropriate agent
        if agent_type != AgentType.REDIS_TRIAGE:
            # Use lightweight chat agent with process_query interface
            is_knowledge_only = agent_type == AgentType.KNOWLEDGE_ONLY
            await task_manager.add_task_update(
                task_id,
                "Processing query with knowledge-only agent"
                if is_knowledge_only
                else "Processing query with chat agent",
                "agent_processing",
            )

            # Convert conversation history to LangChain messages
            lc_history = []
            for msg in conversation_state["messages"][:-1]:  # Exclude the latest message
                if msg["role"] == "user":
                    lc_history.append(HumanMessage(content=msg["content"]))
                elif msg["role"] == "assistant":
                    lc_history.append(AIMessage(content=msg["content"]))

            if is_knowledge_only:
                max_iterations = settings.knowledge_max_iterations
                if not isinstance(max_iterations, int) or max_iterations <= 0:
                    max_iterations = min(int(settings.max_iterations or 10), 8)
            else:
                max_iterations = min(int(settings.max_iterations or 15), 10)

            chat_agent_response = await agent.process_query(
                query=message,
                user_id=thread.metadata.user_id,
                session_id=thread.metadata.session_id or thread_id,
                max_iterations=max_iterations,
                context=routing_context,
                progress_emitter=progress_emitter,
                conversation_history=lc_history if lc_history else None,
            )

            # chat_agent_response is an AgentResponse with .response, .search_results, .tool_envelopes
            agent_response = {
                "response": chat_agent_response.response,
                "search_results": chat_agent_response.search_results,
                "tool_envelopes": chat_agent_response.tool_envelopes,
                "metadata": {"agent_type": "knowledge_only" if is_knowledge_only else "redis_chat"},
            }
        else:
            # Use full Redis triage agent with full conversation state
            agent_response = await run_agent_with_progress(
                agent,
                conversation_state,
                progress_emitter,
                thread,
                agent_context=routing_context,
            )

        pending_approval = _extract_pending_approval_from_response(agent_response)
        try:
            current_task_state = await task_manager.get_task_state(task_id)
        except Exception:
            logger.debug("Unable to read task state for %s after agent execution", task_id)
            current_task_state = None
        if pending_approval or (
            current_task_state and current_task_state.status == TaskStatus.AWAITING_APPROVAL
        ):
            pending_approval = pending_approval or (
                current_task_state.pending_approval.model_dump(mode="json")
                if current_task_state and current_task_state.pending_approval
                else None
            )
            result = {
                "status": TaskStatus.AWAITING_APPROVAL.value,
                "thread_id": thread_id,
                "task_id": task_id,
                "pending_approval": pending_approval,
                "resume_supported": current_task_state.resume_supported
                if current_task_state
                else True,
            }
            logger.info("Task %s is awaiting approval", task_id)
            return result

        # Record Q&A with citation tracking (non-blocking, best effort)
        response_text = agent_response.get("response", "")
        search_results = agent_response.get("search_results", [])
        if response_text and search_results:
            try:
                qa_manager = QAManager()
                await qa_manager.record_qa_from_search(
                    question=message,
                    answer=response_text,
                    search_results=search_results,
                    thread_id=thread_id,
                    task_id=task_id,
                    user_id=thread.metadata.user_id,
                )
                logger.info(f"Recorded Q&A with {len(search_results)} citations for task {task_id}")
            except Exception as e:
                logger.warning(f"Failed to record Q&A with citations: {e}")

        # Add agent response to conversation
        assistant_message_id = str(ULID())
        assistant_metadata = dict(agent_response.get("metadata", {}) or {})
        assistant_metadata["task_id"] = task_id
        assistant_metadata["message_id"] = assistant_message_id
        conversation_state["messages"].append(
            {
                "message_id": assistant_message_id,
                "role": "assistant",
                "content": response_text,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "metadata": assistant_metadata,
            }
        )

        # Add citation system message if there are search results
        # This allows the LLM to see which sources were used and retrieve more info
        if should_include_citations(search_results):
            citation_timestamp = datetime.now(timezone.utc).isoformat()
            for citation_msg in build_citation_message_payloads(search_results):
                conversation_state["messages"].append(
                    {
                        "role": "system",
                        "content": citation_msg["content"],
                        "timestamp": citation_timestamp,
                        "metadata": citation_msg["metadata"],
                    }
                )

        # Update thread context with new conversation state
        # Only save user/assistant/system messages - tool messages are internal to LangGraph
        # and shouldn't be persisted across turns
        clean_messages = [
            msg
            for msg in conversation_state["messages"]
            if isinstance(msg, dict) and msg.get("role") in ["user", "assistant", "system"]
        ]

        # Persist agent reflections/status updates for this turn as chat messages
        # Note: Updates are now stored on TaskState, not Thread
        try:
            task_state = await task_manager.get_task_state(task_id)
            if task_state and task_state.updates:
                # Keep only relevant types of updates
                relevant_types = {"agent_reflection", "agent_processing", "agent_start"}
                turn_updates = [
                    u for u in task_state.updates if u.update_type in relevant_types and u.message
                ]
                # Order chronologically
                turn_updates.sort(key=lambda u: u.timestamp)
                reflection_messages = [
                    {
                        "role": "assistant",
                        "content": u.message,
                        "timestamp": u.timestamp,
                        "metadata": {"update_type": u.update_type, **(u.metadata or {})},
                    }
                    for u in turn_updates
                ]
                if reflection_messages:
                    # Insert reflections before the final assistant message for this turn
                    if clean_messages:
                        final_msg = clean_messages[-1]
                        base_msgs = clean_messages[:-1]
                        # Deduplicate by content
                        seen = set(m.get("content") for m in base_msgs)
                        merged = (
                            base_msgs
                            + [m for m in reflection_messages if m["content"] not in seen]
                            + [final_msg]
                        )
                        clean_messages = merged
                    else:
                        clean_messages = reflection_messages
        except Exception as e:
            logger.warning(f"Failed to merge reflection updates into transcript: {e}")

        # Convert clean_messages dicts to Message objects for thread storage
        thread.messages = [
            Message(
                message_id=m.get("message_id"),
                role=m.get("role", "user"),
                content=m.get("content", ""),
                metadata={k: v for k, v in m.items() if k not in ("role", "content")} or None,
            )
            for m in clean_messages
            if m.get("content")
        ]
        thread.context["last_updated"] = datetime.now(timezone.utc).isoformat()

        # If the subject is empty/placeholder, set an optimistic subject from original_query or first user message
        try:
            subj = (thread.metadata.subject or "").strip()
            if not subj or subj.lower() in {"untitled", "unknown"}:
                candidate = None
                oq = (
                    thread.context.get("original_query")
                    if isinstance(thread.context, dict)
                    else None
                )
                if isinstance(oq, str) and oq.strip():
                    candidate = oq.strip()
                else:
                    # Find the first user message content
                    for m in thread.messages:
                        if m.role == "user" and m.content.strip():
                            candidate = m.content.strip()
                            break
                if candidate:
                    # Normalize to a single line and cap length
                    line = candidate.splitlines()[0].strip()
                    if len(line) > 80:
                        line = line[:77].rstrip() + "…"
                    await thread_manager.set_thread_subject(thread_id, line)
        except Exception as e:
            logger.warning(f"Failed to set optimistic subject for thread {thread_id}: {e}")

        # Save the updated thread state to Redis
        await thread_manager._save_thread_state(thread)
        logger.info(
            f"Saved conversation history: {len(thread.messages)} user/assistant messages (filtered from {len(conversation_state['messages'])} total)"
        )

        # Set the final result on the task (not the thread - results belong on tasks)
        result = {
            "response": agent_response.get("response", ""),
            "metadata": agent_response.get("metadata", {}),
            "thread_id": thread_id,
            "task_id": task_id,
            "message_id": assistant_message_id,
            "turn_completed_at": datetime.now(timezone.utc).isoformat(),
        }

        await task_manager.set_task_result(task_id, result)
        await task_manager.update_task_status(task_id, TaskStatus.DONE)

        # Store decision trace for this message (tool calls + citations)
        tool_envelopes = agent_response.get("tool_envelopes", [])
        if tool_envelopes and assistant_message_id:
            try:
                otel_trace_id = (
                    format(_root_span.get_span_context().trace_id, "032x")
                    if _root_span and _root_span.get_span_context().is_valid
                    else None
                )
            except Exception:
                otel_trace_id = None

            await thread_manager.set_message_trace(
                message_id=assistant_message_id,
                tool_envelopes=tool_envelopes,
                otel_trace_id=otel_trace_id,
            )

        # Publish completion to stream for WebSocket updates
        await task_manager._publish_stream_update(
            thread_id,
            "turn_complete",
            {"task_id": task_id, "message": "Task completed successfully"},
        )

        # End root span if present
        try:
            if _root_span is not None:
                _root_span.end()
        except Exception:
            pass

        logger.info(f"Agent turn completed for thread {thread_id}")
        return result

    except GraphInterrupt as exc:
        logger.info("Task %s is awaiting approval", task_id)
        result = await _transition_task_to_awaiting_approval_from_interrupt(
            task_manager=task_manager,
            task_id=task_id,
            thread_id=thread_id,
            error=exc,
        )
        try:
            if _root_span is not None:
                _root_span.end()
        except Exception:
            pass
        return result

    except ApprovalRequiredError as exc:
        logger.info("Task %s is awaiting approval", task_id)
        result = await _transition_task_to_awaiting_approval(
            task_manager=task_manager,
            task_id=task_id,
            thread_id=thread_id,
            error=exc,
        )
        try:
            if _root_span is not None:
                _root_span.end()
        except Exception:
            pass
        return result

    except Exception as e:
        error_message = f"Agent turn failed: {str(e)}"
        logger.error(f"Turn processing failed for thread {thread_id}: {e}")
        # Record exception on root span if available
        try:
            if _root_span is not None:
                _root_span.record_exception(e)
        except Exception:
            pass

        # Update task with error (also publishes to stream for WebSocket updates)
        await task_manager.set_task_error(task_id, error_message)
        await task_manager.add_task_update(task_id, f"Error: {error_message}", "error")

        # Add an assistant message to the thread so the error is visible in the conversation
        await thread_manager.append_messages(
            thread_id,
            [
                {
                    "role": "assistant",
                    "content": f"I encountered an error while processing your request: {str(e)}",
                }
            ],
        )

        # End root span on error
        try:
            if _root_span is not None:
                _root_span.end()
        except Exception:
            pass

        raise


@sre_task
async def resume_task_after_approval(
    task_id: str,
    approval_id: str,
    decision: ApprovalDecisionType | str,
    decision_by: Optional[str] = None,
    decision_comment: Optional[str] = None,
    redis_client=None,
    concurrency: ConcurrencyLimit = ConcurrencyLimit(
        "task_id", max_concurrent=1, scope="task_approval_resume"
    ),
    retry: Retry = Retry(attempts=2, delay=timedelta(seconds=2)),
) -> Dict[str, Any]:
    """Resume a paused task after recording a human approval decision."""

    redis_client = redis_client or get_redis_client()
    task_manager = TaskManager(redis_client=redis_client)
    thread_manager = ThreadManager(redis_client=redis_client)
    approval_manager = ApprovalManager(redis_client=redis_client)

    task_state = await task_manager.get_task_state(task_id)
    if not task_state:
        raise ValueError(f"Task {task_id} not found")
    if task_state.status not in {TaskStatus.AWAITING_APPROVAL, TaskStatus.IN_PROGRESS}:
        if task_state.status in {TaskStatus.DONE, TaskStatus.FAILED, TaskStatus.CANCELLED}:
            await approval_manager.delete_resume_state(task_id)
        return {
            "task_id": task_id,
            "thread_id": task_state.thread_id,
            "status": task_state.status.value,
            "result": task_state.result,
        }

    (
        task_state,
        thread,
        resume_state,
        approval_record,
        decision_model,
    ) = await _load_resume_context(
        task_id=task_id,
        approval_id=approval_id,
        decision=decision,
        decision_by=decision_by,
        decision_comment=decision_comment,
        task_state=task_state,
        task_manager=task_manager,
        thread_manager=thread_manager,
        approval_manager=approval_manager,
    )
    thread_id = task_state.thread_id
    normalized_decision = decision_model.decision

    if approval_record.decision is None:
        approval_record = (
            await approval_manager.record_decision(
                approval_id,
                decision_model,
            )
            or approval_record
        )
    elif approval_record.decision.decision != normalized_decision:
        raise ValueError(
            f"Approval {approval_id} was already decided as {approval_record.decision.decision.value}"
        )

    await task_manager.set_pending_approval(task_id, None)
    await task_manager.set_resume_supported(task_id, True)
    await task_manager.update_task_status(task_id, TaskStatus.IN_PROGRESS)
    await task_manager.add_task_update(
        task_id,
        f"Approval {normalized_decision.value} for {approval_record.tool_name}",
        "approval_decision",
        metadata={
            "approval_id": approval_record.approval_id,
            "interrupt_id": approval_record.interrupt_id,
            "tool_name": approval_record.tool_name,
            "decision": normalized_decision.value,
            "decision_by": decision_by,
            "decision_comment": decision_comment,
        },
    )
    await approval_manager.save_resume_state(
        resume_state.model_copy(
            update={
                "waiting_reason": "resuming",
                "resume_count": resume_state.resume_count + 1,
                "pending_approval_id": approval_record.approval_id,
                "pending_interrupt_id": approval_record.interrupt_id,
            }
        )
    )

    resume_payload = _build_resume_payload(
        approval_record=approval_record,
        decision=decision_model,
    )
    from redis_sre_agent.agent.checkpointing import persist_approval_wait_state

    progress_emitter = TaskEmitter(task_manager=task_manager, task_id=task_id)
    resume_context = dict(thread.context or {})
    resume_context["task_id"] = task_id
    resume_context["thread_id"] = thread_id

    if resume_state.graph_type == "chat":
        from redis_sre_agent.agent.chat_agent import ChatAgent
        from redis_sre_agent.tools.models import ToolCapability

        instance_id = str(resume_context.get("instance_id") or "").strip() or None
        cluster_id = str(resume_context.get("cluster_id") or "").strip() or None
        redis_instance = await _resolve_instance_for_thread(instance_id, thread_id)
        redis_cluster = await get_cluster_by_id(cluster_id) if cluster_id else None

        excluded_categories = resume_context.get("exclude_mcp_categories") or []
        mcp_categories = []
        for cat_name in excluded_categories if isinstance(excluded_categories, list) else []:
            try:
                mcp_categories.append(ToolCapability(str(cat_name).lower()))
            except ValueError:
                logger.warning("Unknown MCP category to exclude during resume: %s", cat_name)

        chat_agent = ChatAgent(
            redis_instance=redis_instance,
            redis_cluster=redis_cluster,
            progress_emitter=progress_emitter,
            exclude_mcp_categories=mcp_categories or None,
        )
        try:
            response = await chat_agent.resume_query(
                session_id=thread.metadata.session_id or thread_id,
                user_id=thread.metadata.user_id,
                context=resume_context,
                progress_emitter=progress_emitter,
                resume_payload=resume_payload,
            )
        except GraphInterrupt as exc:
            result = await _transition_task_to_awaiting_approval_from_interrupt(
                task_manager=task_manager,
                task_id=task_id,
                thread_id=thread_id,
                error=exc,
            )
            current_task_state = await task_manager.get_task_state(task_id)
            await persist_approval_wait_state(
                task_id=task_id,
                pending_approval=current_task_state.pending_approval
                if current_task_state
                else None,
            )
            return result
        except ApprovalRequiredError as exc:
            result = await _transition_task_to_awaiting_approval(
                task_manager=task_manager,
                task_id=task_id,
                thread_id=thread_id,
                error=exc,
            )
            await persist_approval_wait_state(
                task_id=task_id,
                pending_approval=exc.pending_approval,
            )
            return result

        current_task_state = await task_manager.get_task_state(task_id)
        if current_task_state and current_task_state.status == TaskStatus.AWAITING_APPROVAL:
            result = _build_awaiting_approval_result(
                task_id=task_id,
                thread_id=thread_id,
                task_state=current_task_state,
            )
            await task_manager.set_task_result(task_id, result)
            await persist_approval_wait_state(
                task_id=task_id,
                pending_approval=current_task_state.pending_approval,
            )
            return result

        result = {
            "response": response.model_dump() if hasattr(response, "model_dump") else response,
            "instance_id": instance_id,
            "cluster_id": cluster_id,
        }
        await task_manager.set_task_result(task_id, result)
        await task_manager.update_task_status(task_id, TaskStatus.DONE)
        await approval_manager.delete_resume_state(task_id)

        message_id = str(ULID())
        tool_envelopes = response.tool_envelopes if hasattr(response, "tool_envelopes") else []
        if tool_envelopes:
            await thread_manager.set_message_trace(
                message_id=message_id,
                tool_envelopes=tool_envelopes,
                otel_trace_id=None,
            )

        response_text = response.response if hasattr(response, "response") else str(response)
        await thread_manager.append_messages(
            thread_id,
            [
                {
                    "role": "assistant",
                    "content": response_text,
                    "metadata": {
                        "task_id": task_id,
                        "message_id": message_id,
                        "agent": "chat",
                    },
                }
            ],
        )
        return result

    if resume_state.graph_type != "redis_triage":
        raise ValueError(f"Unsupported resume graph type: {resume_state.graph_type}")

    instance_id = str(resume_context.get("instance_id") or "").strip() or None
    cluster_id = str(resume_context.get("cluster_id") or "").strip() or None
    target_instance = await _resolve_instance_for_thread(instance_id, thread_id)
    target_cluster = await get_cluster_by_id(cluster_id) if cluster_id else None

    agent = get_sre_agent(
        redis_instance=target_instance,
        redis_cluster=target_cluster,
    )
    try:
        agent_response_obj = await agent.resume_query(
            session_id=thread.metadata.session_id or thread_id,
            user_id=thread.metadata.user_id,
            context=resume_context,
            progress_emitter=progress_emitter,
            resume_payload=resume_payload,
        )
    except GraphInterrupt as exc:
        result = await _transition_task_to_awaiting_approval_from_interrupt(
            task_manager=task_manager,
            task_id=task_id,
            thread_id=thread_id,
            error=exc,
        )
        current_task_state = await task_manager.get_task_state(task_id)
        await persist_approval_wait_state(
            task_id=task_id,
            pending_approval=current_task_state.pending_approval if current_task_state else None,
        )
        return result
    except ApprovalRequiredError as exc:
        result = await _transition_task_to_awaiting_approval(
            task_manager=task_manager,
            task_id=task_id,
            thread_id=thread_id,
            error=exc,
        )
        await persist_approval_wait_state(
            task_id=task_id,
            pending_approval=exc.pending_approval,
        )
        return result
    agent_response = {
        "response": agent_response_obj.response,
        "search_results": agent_response_obj.search_results,
        "tool_envelopes": agent_response_obj.tool_envelopes,
        "metadata": {"agent_type": "redis_triage"},
    }

    current_task_state = await task_manager.get_task_state(task_id)
    if current_task_state and current_task_state.status == TaskStatus.AWAITING_APPROVAL:
        result = _build_awaiting_approval_result(
            task_id=task_id,
            thread_id=thread_id,
            task_state=current_task_state,
        )
        await task_manager.set_task_result(task_id, result)
        await persist_approval_wait_state(
            task_id=task_id,
            pending_approval=current_task_state.pending_approval,
        )
        return result

    conversation_state = {
        "messages": [
            {
                "role": m.role,
                "content": m.content,
                **({"metadata": m.metadata} if m.metadata else {}),
            }
            for m in thread.messages
        ],
        "thread_id": thread_id,
    }
    response_text = agent_response.get("response", "")
    assistant_message_id = str(ULID())
    assistant_metadata = dict(agent_response.get("metadata", {}) or {})
    assistant_metadata["task_id"] = task_id
    assistant_metadata["message_id"] = assistant_message_id
    conversation_state["messages"].append(
        {
            "message_id": assistant_message_id,
            "role": "assistant",
            "content": response_text,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metadata": assistant_metadata,
        }
    )

    clean_messages = [
        msg
        for msg in conversation_state["messages"]
        if isinstance(msg, dict) and msg.get("role") in ["user", "assistant", "system"]
    ]
    try:
        latest_task_state = await task_manager.get_task_state(task_id)
        if latest_task_state and latest_task_state.updates:
            relevant_types = {"agent_reflection", "agent_processing", "agent_start"}
            turn_updates = [
                u
                for u in latest_task_state.updates
                if u.update_type in relevant_types and u.message
            ]
            turn_updates.sort(key=lambda u: u.timestamp)
            reflection_messages = [
                {
                    "role": "assistant",
                    "content": u.message,
                    "timestamp": u.timestamp,
                    "metadata": {"update_type": u.update_type, **(u.metadata or {})},
                }
                for u in turn_updates
            ]
            if reflection_messages:
                final_msg = clean_messages[-1] if clean_messages else None
                base_msgs = clean_messages[:-1] if final_msg else clean_messages
                seen = set(m.get("content") for m in base_msgs)
                merged = base_msgs + [m for m in reflection_messages if m["content"] not in seen]
                if final_msg:
                    merged.append(final_msg)
                clean_messages = merged
    except Exception as e:
        logger.warning("Failed to merge reflection updates into resumed transcript: %s", e)

    thread.messages = [
        Message(
            message_id=m.get("message_id"),
            role=m.get("role", "user"),
            content=m.get("content", ""),
            metadata={k: v for k, v in m.items() if k not in ("role", "content")} or None,
        )
        for m in clean_messages
        if m.get("content")
    ]
    thread.context["last_updated"] = datetime.now(timezone.utc).isoformat()
    await thread_manager._save_thread_state(thread)

    result = {
        "response": response_text,
        "metadata": agent_response.get("metadata", {}),
        "thread_id": thread_id,
        "task_id": task_id,
        "message_id": assistant_message_id,
        "turn_completed_at": datetime.now(timezone.utc).isoformat(),
    }
    await task_manager.set_task_result(task_id, result)
    await task_manager.update_task_status(task_id, TaskStatus.DONE)
    await approval_manager.delete_resume_state(task_id)

    tool_envelopes = agent_response.get("tool_envelopes", [])
    if tool_envelopes and assistant_message_id:
        await thread_manager.set_message_trace(
            message_id=assistant_message_id,
            tool_envelopes=tool_envelopes,
            otel_trace_id=None,
        )
    await task_manager._publish_stream_update(
        thread_id,
        "turn_complete",
        {"task_id": task_id, "message": "Task completed successfully"},
    )
    return result


@sre_task
async def process_agent_turn(
    thread_id: str,
    message: str,
    context: Optional[Dict[str, Any]] = None,
    task_id: Optional[str] = None,
    concurrency: ConcurrencyLimit = ConcurrencyLimit(
        "thread_id", max_concurrent=1, scope="thread_turns"
    ),
    retry: Retry = Retry(attempts=3, delay=timedelta(seconds=5)),
) -> Dict[str, Any]:
    """Docket-managed wrapper around the in-process agent turn implementation."""

    return await _process_agent_turn_impl(
        thread_id=thread_id,
        message=message,
        context=context,
        task_id=task_id,
    )


async def run_agent_with_progress(
    agent,
    conversation_state: Dict[str, Any],
    progress_emitter,
    thread_state=None,
    agent_context: Optional[Dict[str, Any]] = None,
):
    """
    Run the LangGraph agent with progress updates.

    This creates a new agent instance with progress emitter support and runs it.

    Args:
        agent: The agent instance (currently unused, kept for compatibility)
        conversation_state: Dictionary containing messages and thread_id
        progress_emitter: ProgressEmitter instance for progress updates
        thread_state: Optional thread state object containing metadata and context
        agent_context: Optional per-turn context to pass directly to the agent.
            When provided, this takes precedence over thread_state.context.
    """
    try:
        # Agent will post reflections as it works

        # Get the conversation messages
        messages = conversation_state.get("messages", [])
        if not messages:
            raise ValueError("No messages in conversation")

        # Create a new agent instance with progress emitter
        from redis_sre_agent.agent.langgraph_agent import SRELangGraphAgent

        progress_agent = SRELangGraphAgent(progress_emitter=progress_emitter)

        # Convert conversation messages to LangChain format
        # We only store user/assistant messages, tool messages are internal to LangGraph
        from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

        lc_messages = []
        for msg in messages:
            if msg["role"] == "user":
                lc_messages.append(HumanMessage(content=msg["content"]))
            elif msg["role"] == "assistant":
                lc_messages.append(AIMessage(content=msg["content"]))
            elif msg["role"] == "system":
                lc_messages.append(SystemMessage(content=msg["content"]))

        # Prepare the state
        thread_id = conversation_state.get("thread_id", "default")
        agent_state = {
            "messages": lc_messages,
            "session_id": thread_id,
            "user_id": "system",  # Will be updated with actual user_id later
            "current_tool_calls": [],
            "iteration_count": 0,
            "max_iterations": settings.max_iterations,
        }

        # Agent will post reflections as it executes tools

        # Run the agent workflow using the compiled app
        {"configurable": {"thread_id": agent_state["session_id"]}}

        # Pass explicit per-turn context to the agent when available.
        if agent_context is None:
            agent_context = thread_state.context if thread_state else None

        # Get the latest user message for the query
        latest_user_message = None
        for msg in reversed(messages):
            if msg["role"] == "user":
                latest_user_message = msg["content"]
                break

        if not latest_user_message:
            raise ValueError("No user message found in conversation")

        # Pass conversation history to the agent
        # MemorySaver is created fresh each time, so we need to provide history
        agent_response = await progress_agent.process_query(
            query=latest_user_message,
            session_id=thread_id,
            user_id=thread_state.metadata.user_id if thread_state else "system",
            max_iterations=settings.max_iterations,
            context=agent_context,
            progress_emitter=progress_emitter,
            conversation_history=lc_messages[:-1]
            if lc_messages
            else None,  # Exclude the latest message (it's added in process_query)
        )

        await progress_emitter.emit("Agent workflow completed", "agent_complete")

        # agent_response is an AgentResponse with .response, .search_results, .tool_envelopes
        return {
            "response": agent_response.response,
            "search_results": agent_response.search_results,
            "tool_envelopes": agent_response.tool_envelopes,
            "metadata": {
                "iterations": 1,  # Since we're using process_query directly
                "tool_calls": len(agent_response.tool_envelopes),
                "session_id": thread_id,
            },
        }

    except Exception as e:
        await progress_emitter.emit(f"Agent error: {str(e)}", "error")
        raise


async def test_task_system(config: Optional[Settings] = None) -> bool:
    """Test if the task system is working.

    Args:
        config: Optional Settings instance for dependency injection.
                If not provided, uses get_redis_url() for backwards compatibility
                with unit tests that patch that function.

    Returns:
        True if the task system is working, False otherwise.
    """
    try:
        # Use injected config if provided, otherwise call get_redis_url()
        # for backwards compatibility with unit tests that patch it
        if config is not None:
            redis_url = config.redis_url.get_secret_value()
        else:
            redis_url = await get_redis_url()

        # Try to connect to Docket
        async with Docket(url=redis_url, name="sre_docket"):
            # Simple connectivity test
            return True
    except Exception as e:
        logger.error(f"Task system test failed: {e}")
        return False
