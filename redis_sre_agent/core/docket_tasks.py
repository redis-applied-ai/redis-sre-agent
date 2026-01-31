"""Docket task definitions for SRE operations."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from docket import ConcurrencyLimit, Docket, Perpetual, Retry
from langchain_core.messages import AIMessage, HumanMessage
from ulid import ULID

from redis_sre_agent.agent import get_sre_agent
from redis_sre_agent.agent.chat_agent import get_chat_agent
from redis_sre_agent.agent.knowledge_agent import get_knowledge_agent
from redis_sre_agent.agent.langgraph_agent import (
    _extract_instance_details_from_message,
)
from redis_sre_agent.agent.router import AgentType, route_to_appropriate_agent
from redis_sre_agent.core.config import Settings, settings
from redis_sre_agent.core.instances import create_instance, get_instance_by_id
from redis_sre_agent.core.knowledge_helpers import (
    ingest_sre_document_helper,
    search_knowledge_base_helper,
)
from redis_sre_agent.core.progress import TaskEmitter
from redis_sre_agent.core.qa import QAManager
from redis_sre_agent.core.redis import (
    get_redis_client,
)
from redis_sre_agent.core.tasks import TaskManager, TaskStatus
from redis_sre_agent.core.threads import Message, ThreadManager

logger = logging.getLogger(__name__)

# SRE-specific task registry
SRE_TASK_COLLECTION = []


def sre_task(func):
    """Decorator to register SRE tasks."""
    SRE_TASK_COLLECTION.append(func)
    return func


# NOTE: analyze_system_metrics was removed as it was never actually provided
# as a tool to the LLM. Metrics/diagnostics will be implemented via the
# ToolProvider system in a future PR.


@sre_task
async def search_knowledge_base(
    query: str,
    category: Optional[str] = None,
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

        # Get Redis instance if specified
        redis_instance = None
        if instance_id:
            redis_instance = await get_instance_by_id(instance_id)
            if not redis_instance:
                raise ValueError(f"Instance not found: {instance_id}")

        # Run chat agent
        agent = ChatAgent(
            redis_instance=redis_instance,
            progress_emitter=emitter,
            exclude_mcp_categories=mcp_categories,
        )
        response = await agent.process_query(
            query=query,
            session_id=thread_id,
            user_id=user_id or "mcp-user",
            progress_emitter=emitter,
        )

        # Store result on task
        result = {
            "response": response,
            "instance_id": instance_id,
        }
        await task_manager.set_task_result(task_id, result)
        await task_manager.update_task_status(task_id, TaskStatus.DONE)

        # Add response to thread as assistant message
        await thread_manager.append_messages(
            thread_id,
            [
                {
                    "role": "assistant",
                    "content": response,
                    "metadata": {"task_id": task_id, "agent": "chat"},
                }
            ],
        )

        return result

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
    Process a knowledge query using the KnowledgeOnlyAgent (background task).

    This runs the KnowledgeOnlyAgent for general SRE knowledge questions.
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
    from redis_sre_agent.agent.knowledge_agent import KnowledgeOnlyAgent

    logger.info(f"Processing knowledge query for task {task_id}")

    redis_client = get_redis_client()
    task_manager = TaskManager(redis_client=redis_client)
    thread_manager = ThreadManager(redis_client=redis_client)

    # Mark task as in progress
    await task_manager.update_task_status(task_id, TaskStatus.IN_PROGRESS)

    try:
        # Create task emitter for notifications
        emitter = TaskEmitter(task_manager=task_manager, task_id=task_id)

        # Run knowledge agent
        agent = KnowledgeOnlyAgent(progress_emitter=emitter)
        response = await agent.process_query(
            query=query,
            session_id=thread_id,
            user_id=user_id or "mcp-user",
            progress_emitter=emitter,
        )

        # Store result on task
        result = {
            "response": response,
        }
        await task_manager.set_task_result(task_id, result)
        await task_manager.update_task_status(task_id, TaskStatus.DONE)

        # Add response to thread as assistant message
        await thread_manager.append_messages(
            thread_id,
            [
                {
                    "role": "assistant",
                    "content": response,
                    "metadata": {"task_id": task_id, "agent": "knowledge"},
                }
            ],
        )

        return result

    except Exception as e:
        logger.error(f"Knowledge query failed: {e}")
        await task_manager.set_task_error(task_id, str(e))
        raise


@sre_task
async def scheduler_task(
    global_limit="scheduler",  # Need a sentinel value for concurrency limit argument
    perpetual: Perpetual = Perpetual(every=timedelta(seconds=30), automatic=True),
    concurrency: ConcurrencyLimit = ConcurrencyLimit("sentinel", max_concurrent=1),
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
    """
    Process a single agent conversation turn.

    This is the main task that runs the LangGraph agent for one conversation turn,
    updating thread state throughout the execution.

    Args:
        thread_id: Thread/conversation identifier
        message: User message for this turn
        context: Additional context for the turn
        retry: Retry configuration
    """
    redis_client = get_redis_client()
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
        # Instance ID Management Logic
        # ============================================================================
        # Determine the instance_id to use for this turn:
        # 1. If client provides instance_id in context, use it and update thread
        # 2. If no instance_id from client, check thread context for saved instance_id
        # 3. If no instance_id anywhere, attempt to create one from user message
        # 4. If still no instance_id, route to knowledge agent
        # ============================================================================

        instance_id_from_client = context.get("instance_id") if context else None
        instance_id_from_thread = thread.context.get("instance_id")

        # Determine which instance_id to use
        active_instance_id = None

        if instance_id_from_client:
            # Client provided instance_id - use it and update thread
            active_instance_id = instance_id_from_client
            logger.info(
                f"Using instance_id from client: {active_instance_id} (will update thread context)"
            )

            # Update thread context with new instance_id
            await thread_manager.update_thread_context(
                thread_id, {"instance_id": active_instance_id}, merge=True
            )
            await task_manager.add_task_update(
                task_id,
                f"Using Redis instance: {active_instance_id}",
                "instance_context",
            )

        elif instance_id_from_thread:
            # No instance_id from client, but we have one saved in thread
            active_instance_id = instance_id_from_thread
            logger.info(f"Using instance_id from thread context: {active_instance_id}")
            await task_manager.add_task_update(
                task_id,
                f"Continuing with Redis instance: {active_instance_id}",
                "instance_context",
            )

        else:
            # No instance_id from client or thread - attempt to create one from message
            logger.info("No instance_id found, attempting to extract from user message")

            # Try to extract connection details from the message
            instance_details = _extract_instance_details_from_message(message)

            if instance_details:
                # User provided connection details - create instance
                try:
                    logger.info("Creating instance from user-provided connection details")
                    new_instance = await create_instance(
                        name=instance_details["name"],
                        connection_url=instance_details["connection_url"],
                        environment=instance_details["environment"],
                        usage=instance_details["usage"],
                        description=instance_details.get(
                            "description", "Created by agent from user-provided details"
                        ),
                        created_by="agent",
                        user_id=thread.metadata.user_id or "unknown",
                    )

                    active_instance_id = new_instance.id
                    logger.info(f"Created new instance: {new_instance.name} ({active_instance_id})")

                    # Save instance_id to thread context
                    await thread_manager.update_thread_context(
                        thread_id, {"instance_id": active_instance_id}, merge=True
                    )
                    await task_manager.add_task_update(
                        task_id,
                        f"Created Redis instance: {new_instance.name} ({active_instance_id})",
                        "instance_created",
                    )

                except Exception as e:
                    logger.warning(f"Failed to create instance from user details: {e}")
                    await task_manager.add_task_update(
                        task_id,
                        f"Could not create instance from provided details: {str(e)}",
                        "instance_error",
                    )
                    # Continue without instance_id - will route to knowledge agent

        # Merge context for routing decision
        routing_context = thread.context.copy()
        if context:
            routing_context.update(context)

        # Ensure active_instance_id is in routing context
        if active_instance_id:
            routing_context["instance_id"] = active_instance_id

        agent_type = await route_to_appropriate_agent(
            query=message,
            context=routing_context,
            user_preferences=None,  # Could be extended to include user preferences
        )

        logger.info(f"Routing query to {agent_type.value} agent")

        # Import and initialize the appropriate agent based on routing decision
        # REDIS_TRIAGE = full triage agent (heavy, comprehensive)
        # REDIS_CHAT = lightweight chat agent (fast, targeted)
        # KNOWLEDGE_ONLY = knowledge agent (no instance needed)
        if agent_type == AgentType.REDIS_TRIAGE:
            agent = get_sre_agent()
        elif agent_type == AgentType.REDIS_CHAT:
            # Get the target instance for the chat agent
            target_instance = (
                await get_instance_by_id(active_instance_id) if active_instance_id else None
            )
            agent = get_chat_agent(redis_instance=target_instance)
        else:
            agent = get_knowledge_agent()

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
        if agent_type == AgentType.KNOWLEDGE_ONLY:
            # Use knowledge-only agent with simpler interface
            await task_manager.add_task_update(
                task_id, "Processing query with knowledge-only agent", "agent_processing"
            )

            # Convert conversation history to LangChain messages for knowledge agent
            lc_history = []
            for msg in conversation_state["messages"][:-1]:  # Exclude the latest message
                if msg["role"] == "user":
                    lc_history.append(HumanMessage(content=msg["content"]))
                elif msg["role"] == "assistant":
                    lc_history.append(AIMessage(content=msg["content"]))

            # Use a smaller iteration cap for the knowledge agent to avoid long loops
            _k_max_iters = settings.knowledge_max_iterations
            if not isinstance(_k_max_iters, int) or _k_max_iters <= 0:
                _k_max_iters = min(int(settings.max_iterations or 10), 8)

            knowledge_agent_response = await agent.process_query(
                query=message,
                user_id=thread.metadata.user_id or "unknown",
                session_id=thread.metadata.session_id or thread_id,
                max_iterations=_k_max_iters,
                context=None,
                progress_emitter=progress_emitter,
                conversation_history=lc_history if lc_history else None,
            )

            # knowledge_agent_response is an AgentResponse with .response and .search_results
            agent_response = {
                "response": knowledge_agent_response.response,
                "search_results": knowledge_agent_response.search_results,
                "metadata": {"agent_type": "knowledge_only"},
            }
        elif agent_type == AgentType.REDIS_CHAT:
            # Use lightweight chat agent with process_query interface
            await task_manager.add_task_update(
                task_id, "Processing query with chat agent", "agent_processing"
            )

            # Convert conversation history to LangChain messages
            lc_history = []
            for msg in conversation_state["messages"][:-1]:  # Exclude the latest message
                if msg["role"] == "user":
                    lc_history.append(HumanMessage(content=msg["content"]))
                elif msg["role"] == "assistant":
                    lc_history.append(AIMessage(content=msg["content"]))

            # Chat agent uses a reasonable iteration cap for quick responses
            _chat_max_iters = min(int(settings.max_iterations or 15), 10)

            chat_agent_response = await agent.process_query(
                query=message,
                user_id=thread.metadata.user_id or "unknown",
                session_id=thread.metadata.session_id or thread_id,
                max_iterations=_chat_max_iters,
                context=routing_context,
                progress_emitter=progress_emitter,
                conversation_history=lc_history if lc_history else None,
            )

            # chat_agent_response is an AgentResponse with .response and .search_results
            agent_response = {
                "response": chat_agent_response.response,
                "search_results": chat_agent_response.search_results,
                "metadata": {"agent_type": "redis_chat"},
            }
        else:
            # Use full Redis triage agent with full conversation state
            agent_response = await run_agent_with_progress(
                agent, conversation_state, progress_emitter, thread
            )

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
        conversation_state["messages"].append(
            {
                "role": "assistant",
                "content": response_text,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "metadata": agent_response.get("metadata", {}),
            }
        )

        # Update thread context with new conversation state
        # Only save user/assistant messages - tool messages are internal to LangGraph
        # and shouldn't be persisted across turns
        clean_messages = [
            msg
            for msg in conversation_state["messages"]
            if isinstance(msg, dict) and msg.get("role") in ["user", "assistant"]
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
            "turn_completed_at": datetime.now(timezone.utc).isoformat(),
        }

        await task_manager.set_task_result(task_id, result)
        await task_manager.update_task_status(task_id, TaskStatus.DONE)

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

    except Exception as e:
        error_message = f"Agent turn failed: {str(e)}"
        logger.error(
            f"Turn processing failed for thread {thread_id} (attempt {retry.attempt}): {e}"
        )
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


async def run_agent_with_progress(
    agent, conversation_state: Dict[str, Any], progress_emitter, thread_state=None
):
    """
    Run the LangGraph agent with progress updates.

    This creates a new agent instance with progress emitter support and runs it.

    Args:
        agent: The agent instance (currently unused, kept for compatibility)
        conversation_state: Dictionary containing messages and thread_id
        progress_emitter: ProgressEmitter instance for progress updates
        thread_state: Optional thread state object containing metadata and context
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
        from langchain_core.messages import AIMessage, HumanMessage

        lc_messages = []
        for msg in messages:
            if msg["role"] == "user":
                lc_messages.append(HumanMessage(content=msg["content"]))
            elif msg["role"] == "assistant":
                lc_messages.append(AIMessage(content=msg["content"]))

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

        # Pass thread context to the agent if available
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

        # agent_response is an AgentResponse with .response and .search_results
        return {
            "response": agent_response.response,
            "search_results": agent_response.search_results,
            "metadata": {
                "iterations": 1,  # Since we're using process_query directly
                "tool_calls": 0,  # Placeholder - could be enhanced to track tool calls
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
