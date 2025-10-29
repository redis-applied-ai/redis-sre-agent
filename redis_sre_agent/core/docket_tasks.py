"""Docket task definitions for SRE operations."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from docket import ConcurrencyLimit, Docket, Perpetual, Retry
from langchain_core.messages import AIMessage, HumanMessage
from ulid import ULID

from redis_sre_agent.agent import get_sre_agent
from redis_sre_agent.agent.knowledge_agent import get_knowledge_agent
from redis_sre_agent.agent.langgraph_agent import (
    _extract_instance_details_from_message,
)
from redis_sre_agent.agent.router import AgentType, route_to_appropriate_agent
from redis_sre_agent.core.config import settings
from redis_sre_agent.core.instances import create_instance
from redis_sre_agent.core.knowledge_helpers import (
    ingest_sre_document_helper,
    search_knowledge_base_helper,
)
from redis_sre_agent.core.redis import (
    get_redis_client,
)
from redis_sre_agent.core.tasks import TaskManager, TaskStatus
from redis_sre_agent.core.threads import ThreadManager

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
        if distance_threshold is not None:
            kwargs["distance_threshold"] = distance_threshold
        if category:
            kwargs["category"] = category
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
        from ..core.schedule_storage import (
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

                    # Generate and update thread subject for scheduled tasks
                    await thread_manager.update_thread_subject(thread_id, schedule["instructions"])

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
        await thread_manager.add_thread_update(thread_id, f"Started task {task_id}", "task_start")
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
            await thread_manager.add_thread_update(
                thread_id,
                f"Using Redis instance: {active_instance_id}",
                "instance_context",
            )

        elif instance_id_from_thread:
            # No instance_id from client, but we have one saved in thread
            active_instance_id = instance_id_from_thread
            logger.info(f"Using instance_id from thread context: {active_instance_id}")
            await thread_manager.add_thread_update(
                thread_id,
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
                    await thread_manager.add_thread_update(
                        thread_id,
                        f"Created Redis instance: {new_instance.name} ({active_instance_id})",
                        "instance_created",
                    )

                except Exception as e:
                    logger.warning(f"Failed to create instance from user details: {e}")
                    await thread_manager.add_thread_update(
                        thread_id,
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

        # Import and initialize the appropriate agent
        if agent_type == AgentType.REDIS_FOCUSED:
            agent = get_sre_agent()
        else:
            agent = get_knowledge_agent()

        # Prepare the conversation state with thread context
        messages = thread.context.get("messages", [])
        logger.debug(f"Loaded {len(messages)} messages from thread context")

        conversation_state = {
            "messages": messages,
            "thread_id": thread_id,
        }

        logger.debug(f"conversation_state messages type: {type(conversation_state['messages'])}")

        # Add the new user message
        conversation_state["messages"].append(
            {
                "role": "user",
                "content": message,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

        # Agent will post its own reflections as it works

        # Create a progress callback for the agent
        async def progress_callback(
            update_message: str,
            update_type: str = "progress",
            metadata: Optional[Dict[str, Any]] = None,
        ):
            # Include task_id in thread-level metadata for easier grouping
            md = dict(metadata or {})
            md.setdefault("task_id", task_id)
            await thread_manager.add_thread_update(thread_id, update_message, update_type, md)
            try:
                await task_manager.add_task_update(task_id, update_message, update_type, metadata)
            except Exception:
                # Best-effort: do not fail the turn if per-task update logging fails
                pass

        # Run the appropriate agent
        if agent_type == AgentType.KNOWLEDGE_ONLY:
            # Use knowledge-only agent with simpler interface
            await thread_manager.add_thread_update(
                thread_id, "Processing query with knowledge-only agent", "agent_processing"
            )

            # Convert conversation history to LangChain messages for knowledge agent
            lc_history = []
            for msg in conversation_state["messages"][:-1]:  # Exclude the latest message
                if msg["role"] == "user":
                    lc_history.append(HumanMessage(content=msg["content"]))
                elif msg["role"] == "assistant":
                    lc_history.append(AIMessage(content=msg["content"]))

            response_text = await agent.process_query_with_fact_check(
                query=message,
                user_id=thread.metadata.user_id or "unknown",
                session_id=thread.metadata.session_id or thread_id,
                max_iterations=settings.max_iterations,
                context=None,
                progress_callback=progress_callback,
                conversation_history=lc_history if lc_history else None,
            )

            agent_response = {
                "response": response_text,
                "metadata": {"agent_type": "knowledge_only"},
            }
        else:
            # Use Redis-focused agent with full conversation state
            agent_response = await run_agent_with_progress(
                agent, conversation_state, progress_callback, thread
            )

        # Add agent response to conversation
        conversation_state["messages"].append(
            {
                "role": "assistant",
                "content": agent_response.get("response", ""),
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
        thread.context["messages"] = clean_messages
        thread.context["last_updated"] = datetime.now(timezone.utc).isoformat()

        # Save the updated context to Redis
        await thread_manager._save_thread_state(thread)
        logger.info(
            f"Saved conversation history: {len(clean_messages)} user/assistant messages (filtered from {len(conversation_state['messages'])} total)"
        )

        # Set the final result
        result = {
            "response": agent_response.get("response", ""),
            "metadata": agent_response.get("metadata", {}),
            "thread_id": thread_id,
            "task_id": task_id,
            "turn_completed_at": datetime.now(timezone.utc).isoformat(),
        }

        await task_manager.set_task_result(task_id, result)
        await task_manager.update_task_status(task_id, TaskStatus.DONE)
        await thread_manager.set_thread_result(thread_id, result)
        await thread_manager.add_thread_update(
            thread_id, f"Task {task_id} completed successfully", "turn_complete"
        )

        logger.info(f"Agent turn completed for thread {thread_id}")
        return result

    except Exception as e:
        error_message = f"Agent turn failed: {str(e)}"
        logger.error(
            f"Turn processing failed for thread {thread_id} (attempt {retry.attempt}): {e}"
        )

        # Update thread with error
        await thread_manager.set_thread_error(thread_id, error_message)
        await thread_manager.add_thread_update(thread_id, f"Error: {error_message}", "error")
        await task_manager.set_task_error(task_id, error_message)

        raise


async def run_agent_with_progress(
    agent, conversation_state: Dict[str, Any], progress_callback, thread_state=None
):
    """
    Run the LangGraph agent with progress updates.

    This creates a new agent instance with progress callback support and runs it.

    Args:
        agent: The agent instance (currently unused, kept for compatibility)
        conversation_state: Dictionary containing messages and thread_id
        progress_callback: Async callback function for progress updates
        thread_state: Optional thread state object containing metadata and context
    """
    try:
        # Agent will post reflections as it works

        # Get the conversation messages
        messages = conversation_state.get("messages", [])
        if not messages:
            raise ValueError("No messages in conversation")

        # Create a new agent instance with progress callback
        from redis_sre_agent.agent.langgraph_agent import SRELangGraphAgent

        progress_agent = SRELangGraphAgent(progress_callback=progress_callback)

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
        response = await progress_agent.process_query_with_fact_check(
            query=latest_user_message,
            session_id=thread_id,
            user_id=thread_state.metadata.user_id if thread_state else "system",
            max_iterations=settings.max_iterations,
            context=agent_context,
            progress_callback=progress_callback,
            conversation_history=lc_messages[:-1]
            if lc_messages
            else None,  # Exclude the latest message (it's added in process_query)
        )

        # Create a mock final state for compatibility

        await progress_callback("Agent workflow completed", "agent_complete")

        # The response is already the final agent response
        agent_response = response

        return {
            "response": agent_response,
            "metadata": {
                "iterations": 1,  # Since we're using process_query directly
                "tool_calls": 0,  # Placeholder - could be enhanced to track tool calls
                "session_id": thread_id,
            },
        }

    except Exception as e:
        await progress_callback(f"Agent error: {str(e)}", "error")
        raise


async def test_task_system() -> bool:
    """Test if the task system is working."""
    try:
        # Try to connect to Docket
        async with Docket(url=await get_redis_url(), name="sre_docket"):
            # Simple connectivity test
            return True
    except Exception as e:
        logger.error(f"Task system test failed: {e}")
        return False
