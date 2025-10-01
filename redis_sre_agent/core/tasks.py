"""Docket task definitions for SRE operations."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from docket import ConcurrencyLimit, Docket, Perpetual, Retry
from ulid import ULID

from redis_sre_agent.core.config import settings
from redis_sre_agent.core.redis import (
    get_knowledge_index,
    get_redis_client,
    get_vectorizer,
)
from redis_sre_agent.core.thread_state import ThreadStatus, get_thread_manager

logger = logging.getLogger(__name__)

# SRE-specific task registry
SRE_TASK_COLLECTION = []


def sre_task(func):
    """Decorator to register SRE tasks."""
    SRE_TASK_COLLECTION.append(func)
    return func


@sre_task
async def analyze_system_metrics(
    metric_query: str,
    time_range: str = "1h",
    threshold: Optional[float] = None,
    retry: Retry = Retry(attempts=3, delay=timedelta(seconds=5)),
) -> Dict[str, Any]:
    """
    Analyze system metrics and detect anomalies.

    Args:
        metric_query: Prometheus-style metric query
        time_range: Time range for analysis (1h, 6h, 1d, etc.)
        threshold: Alert threshold value
        retry: Retry configuration
    """
    try:
        logger.info(f"Analyzing metrics: {metric_query} over {time_range}")

        # Connect to Prometheus for real metrics
        from ..tools.prometheus_client import get_prometheus_client

        prometheus = get_prometheus_client()
        metrics_data = await prometheus.query_range(query=metric_query, time_range=time_range)

        # Analyze metrics for anomalies
        current_value = None
        anomalies_detected = False
        threshold_breached = False

        if metrics_data and "values" in metrics_data:
            values = [float(v[1]) for v in metrics_data["values"] if v[1] is not None]
            if values:
                current_value = values[-1]  # Latest value

                # Check threshold if provided
                if threshold is not None:
                    threshold_breached = current_value > threshold

                # Simple anomaly detection (check if current value is >2 std devs from mean)
                if len(values) > 5:
                    import statistics

                    mean_val = statistics.mean(values[:-1])  # Exclude current value
                    try:
                        std_dev = statistics.stdev(values[:-1])
                        if abs(current_value - mean_val) > 2 * std_dev:
                            anomalies_detected = True
                    except statistics.StatisticsError:
                        pass  # Not enough data for stdev

        result = {
            "task_id": str(ULID()),
            "metric_query": metric_query,
            "time_range": time_range,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "analyzed",
            "findings": {
                "anomalies_detected": anomalies_detected,
                "current_value": current_value,
                "threshold_breached": threshold_breached,
                "data_points": len(metrics_data.get("values", [])) if metrics_data else 0,
                "metrics_source": "prometheus",
            },
            "raw_metrics": metrics_data,
        }

        # Store result in Redis for retrieval (serialize to a single field to avoid
        # passing complex types directly to HSET)
        import json

        client = get_redis_client()
        result_key = f"sre:metrics:{result['task_id']}"
        await client.hset(result_key, mapping={"data": json.dumps(result)})
        await client.expire(result_key, 3600)  # 1 hour TTL

        logger.info(f"Metrics analysis completed: {result['task_id']}")
        return result

    except Exception as e:
        logger.error(f"Metrics analysis failed (attempt {retry.attempt}): {e}")
        raise


@sre_task
async def search_knowledge_base(
    query: str,
    category: Optional[str] = None,
    limit: int = 5,
    retry: Retry = Retry(attempts=2, delay=timedelta(seconds=2)),
) -> Dict[str, Any]:
    """
    Search SRE knowledge base and runbooks.

    Args:
        query: Search query text
        category: Optional category filter (incident, maintenance, monitoring, etc.)
        limit: Maximum number of results
        retry: Retry configuration
    """
    try:
        logger.info(f"Searching SRE knowledge: '{query}' in category '{category}'")

        # Get vector search components
        index = get_knowledge_index()
        vectorizer = get_vectorizer()

        # Create vector embedding for the query
        # TODO: This shouldn't work, embed_many is not awaitable --
        # so what's actually happening here?
        query_vector = await vectorizer.embed_many([query])

        # Build search filters
        filters = []
        if category:
            filters.append(f"@category:{category}")

        # Perform vector search
        # Note: This is a simplified version - real implementation would be more complex
        results = await index.query(
            query_vector[0], num_results=limit, filters=filters if filters else None
        )

        search_result = {
            "task_id": str(ULID()),
            "query": query,
            "category": category,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "results_count": len(results),
            "results": [
                {
                    "title": doc.get("title", ""),
                    "content": doc.get("content", "")[:500],  # Truncate for response
                    "source": doc.get("source", ""),
                    "score": doc.get("score", 0.0),
                }
                for doc in results
            ],
        }

        logger.info(
            f"Knowledge search completed: {search_result['task_id']} ({len(results)} results)"
        )
        return search_result

    except Exception as e:
        logger.error(f"Knowledge search failed (attempt {retry.attempt}): {e}")
        raise


@sre_task
async def check_service_health(
    service_name: str,
    endpoints: List[str],
    timeout: int = 30,
    retry: Retry = Retry(attempts=2, delay=timedelta(seconds=3)),
) -> Dict[str, Any]:
    """
    Check health status of a service and its endpoints.

    Args:
        service_name: Name of the service to check
        endpoints: List of health check endpoints
        timeout: Request timeout in seconds
        retry: Retry configuration
    """
    try:
        logger.info(f"Checking health for service: {service_name}")

        # Perform HTTP health checks
        # NOTE: For Redis-specific diagnostics, use get_detailed_redis_diagnostics()
        # with an explicit redis_url parameter instead of this generic health check.
        import aiohttp

        health_results = []

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
            for endpoint in endpoints:
                start_time = datetime.now()

                try:
                    async with session.get(endpoint) as response:
                        response_time = (datetime.now() - start_time).total_seconds() * 1000

                        health_check = {
                            "endpoint": endpoint,
                            "status": "healthy" if response.status < 400 else "unhealthy",
                            "response_time_ms": round(response_time, 2),
                            "status_code": response.status,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }

                except Exception as e:
                    health_check = {
                        "endpoint": endpoint,
                        "status": "unhealthy",
                        "response_time_ms": None,
                        "status_code": None,
                        "error": str(e),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }

                health_results.append(health_check)

        overall_status = (
            "healthy"
            if all(result["status"] == "healthy" for result in health_results)
            else "unhealthy"
        )

        result = {
            "task_id": str(ULID()),
            "service_name": service_name,
            "overall_status": overall_status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "endpoints_checked": len(endpoints),
            "health_checks": health_results,
        }

        # Store result in Redis (serialize complex data)
        import json

        client = get_redis_client()
        result_key = f"sre:health:{result['task_id']}"
        await client.set(result_key, json.dumps(result))
        await client.expire(result_key, 1800)  # 30 minutes TTL

        logger.info(f"Health check completed: {service_name} is {overall_status}")
        return result

    except Exception as e:
        logger.error(f"Health check failed for {service_name} (attempt {retry.attempt}): {e}")
        raise


@sre_task
async def ingest_sre_document(
    title: str,
    content: str,
    source: str,
    category: str = "general",
    severity: str = "info",
    retry: Retry = Retry(attempts=3, delay=timedelta(seconds=2)),
) -> Dict[str, Any]:
    """
    Ingest a document into the SRE knowledge base.

    Args:
        title: Document title
        content: Document content
        source: Source system or file
        category: Document category (incident, runbook, monitoring, etc.)
        severity: Severity level (info, warning, critical)
        retry: Retry configuration
    """
    try:
        logger.info(f"Ingesting SRE document: {title} from {source}")

        # Get components
        index = get_knowledge_index()
        vectorizer = get_vectorizer()

        # Create document embedding
        content_vector = await vectorizer.embed_many([content])

        # Prepare document data
        doc_id = str(ULID())
        document = {
            "title": title,
            "content": content,
            "source": source,
            "category": category,
            "severity": severity,
            "created_at": datetime.now(timezone.utc).timestamp(),
            "vector": content_vector[0],
        }

        # Store in vector index
        doc_key = f"sre_knowledge:{doc_id}"
        await index.load(data=[document], id_field="id", keys=[doc_key])

        result = {
            "task_id": str(ULID()),
            "document_id": doc_id,
            "title": title,
            "source": source,
            "category": category,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "ingested",
        }

        logger.info(f"Document ingested successfully: {doc_id}")
        return result

    except Exception as e:
        logger.error(f"Document ingestion failed (attempt {retry.attempt}): {e}")
        raise


@sre_task
async def scheduler_task(
    global_limit: str = "scheduler",
    perpetual: Perpetual = Perpetual(every=timedelta(seconds=30)),
    concurrency: ConcurrencyLimit = ConcurrencyLimit("global_limit", max_concurrent=1),
    retry: Retry = Retry(attempts=3, delay=timedelta(seconds=5)),
) -> Dict[str, Any]:
    """
    Scheduler task that runs every 30 seconds using Perpetual.

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
                    from ..core.thread_state import get_thread_manager

                    thread_manager = get_thread_manager()

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
                    from ..api.schedules import Schedule

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

        # Schedule the next run of this task (Perpetual behavior)
        try:
            next_run_time = datetime.now(timezone.utc) + timedelta(seconds=30)
            async with Docket(url=await get_redis_url(), name="sre_docket") as next_docket:
                # Use a deduplication key based on the scheduled time to prevent multiple scheduler tasks
                scheduler_key = f"scheduler_task_{next_run_time.strftime('%Y%m%d_%H%M%S')}"
                task_func = next_docket.add(scheduler_task, when=next_run_time, key=scheduler_key)
                await task_func()
                logger.debug(
                    f"Scheduled next scheduler task run at {next_run_time} with key {scheduler_key}"
                )
        except Exception as e:
            # If the task was already scheduled (duplicate key), this is expected and not an error
            if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
                logger.debug(
                    f"Scheduler task already scheduled for {next_run_time} - this is expected"
                )
            else:
                logger.error(f"Failed to schedule next scheduler task run: {e}")

        return result

    except Exception as e:
        logger.error(f"Scheduler task failed (attempt {retry.attempt}): {e}")
        raise


async def get_redis_url() -> str:
    """Get Redis URL for Docket."""
    return settings.redis_url


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


async def start_scheduler_task() -> None:
    """Start the scheduler task as a Perpetual task."""
    try:
        async with Docket(url=await get_redis_url(), name="sre_docket") as docket:
            # Submit the scheduler task with deduplication to prevent multiple instances
            logger.info("Attempting to start scheduler task...")

            # Use a fixed key to ensure only one scheduler task runs at startup
            current_time = datetime.now(timezone.utc)
            scheduler_key = f"scheduler_task_startup_{current_time.strftime('%Y%m%d_%H%M')}"

            try:
                # Submit an immediate scheduler task with deduplication key
                task_func = docket.add(scheduler_task, key=scheduler_key)
                task_id = await task_func()
                logger.info(f"Started scheduler task with ID: {task_id} and key: {scheduler_key}")
            except Exception as e:
                # If the task was already submitted (duplicate key), this is expected and not an error
                if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
                    logger.info(
                        f"Scheduler task already running with key {scheduler_key} - this is expected"
                    )
                else:
                    logger.error(f"Failed to start scheduler task: {e}")
                    raise

    except Exception as e:
        logger.error(f"Failed to start scheduler task: {e}")
        # Don't raise - let the app continue
        import traceback

        logger.error(f"Scheduler task error traceback: {traceback.format_exc()}")


@sre_task
async def process_agent_turn(
    thread_id: str,
    message: str,
    context: Optional[Dict[str, Any]] = None,
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
    thread_manager = get_thread_manager()

    try:
        logger.info(f"Processing agent turn for thread {thread_id}")

        # Update thread status to in-progress
        await thread_manager.update_thread_status(thread_id, ThreadStatus.IN_PROGRESS)
        await thread_manager.add_thread_update(
            thread_id,
            f"Processing message: {message[:100]}{'...' if len(message) > 100 else ''}",
            "turn_start",
        )

        # Get current thread state
        thread_state = await thread_manager.get_thread_state(thread_id)
        if not thread_state:
            raise ValueError(f"Thread {thread_id} not found")

        # Route to appropriate agent based on query and context
        from redis_sre_agent.agent.router import AgentType, route_to_appropriate_agent

        # Merge context for routing decision
        routing_context = thread_state.context.copy()
        if context:
            routing_context.update(context)

        agent_type = route_to_appropriate_agent(
            query=message,
            context=routing_context,
            user_preferences=None,  # Could be extended to include user preferences
        )

        logger.info(f"Routing query to {agent_type.value} agent")
        await thread_manager.add_thread_update(
            thread_id,
            f"Using {agent_type.value.replace('_', ' ')} agent for optimal results",
            "agent_routing",
        )

        # Import and initialize the appropriate agent
        if agent_type == AgentType.REDIS_FOCUSED:
            from redis_sre_agent.agent import get_sre_agent

            await thread_manager.add_thread_update(
                thread_id, "Initializing Redis-focused SRE agent and tools", "agent_init"
            )
            agent = get_sre_agent()
            use_knowledge_only = False
        else:  # AgentType.KNOWLEDGE_ONLY
            from redis_sre_agent.agent.knowledge_agent import get_knowledge_agent

            await thread_manager.add_thread_update(
                thread_id, "Initializing knowledge-only SRE agent", "agent_init"
            )
            agent = get_knowledge_agent()
            use_knowledge_only = True

        # Prepare the conversation state with thread context
        messages = thread_state.context.get("messages", [])
        logger.info(f"DEBUG: messages type: {type(messages)}, value: {messages}")

        conversation_state = {
            "messages": messages,
            "thread_id": thread_id,
        }

        logger.info(
            f"DEBUG: conversation_state messages type: {type(conversation_state['messages'])}"
        )

        # Add the new user message
        conversation_state["messages"].append(
            {
                "role": "user",
                "content": message,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

        # Update progress
        await thread_manager.add_thread_update(
            thread_id, "Running agent conversation turn", "agent_processing"
        )

        # Add initial thinking message
        await thread_manager.add_thread_update(thread_id, "Agent is thinking...", "agent_status")

        # Create a progress callback for the agent
        async def progress_callback(update_message: str, update_type: str = "progress"):
            await thread_manager.add_thread_update(thread_id, update_message, update_type)

        # Run the appropriate agent
        if use_knowledge_only:
            # Use knowledge-only agent with simpler interface
            await thread_manager.add_thread_update(
                thread_id, "Processing query with knowledge-only agent", "agent_processing"
            )

            response_text = await agent.process_query(
                query=message,
                user_id=thread_state.metadata.user_id or "unknown",
                session_id=thread_state.metadata.session_id or thread_id,
                progress_callback=progress_callback,
            )

            agent_response = {
                "response": response_text,
                "metadata": {"agent_type": "knowledge_only"},
                "action_items": [],
            }
        else:
            # Use Redis-focused agent with full conversation state
            agent_response = await run_agent_with_progress(
                agent, conversation_state, progress_callback, thread_state
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
        thread_state.context["messages"] = conversation_state["messages"]
        thread_state.context["last_updated"] = datetime.now(timezone.utc).isoformat()

        # Extract action items if present
        action_items = agent_response.get("action_items", [])
        if action_items:
            from redis_sre_agent.core.thread_state import ThreadActionItem

            action_item_objects = [
                (
                    ThreadActionItem(**item)
                    if isinstance(item, dict)
                    else ThreadActionItem(title=str(item), description="", category="general")
                )
                for item in action_items
            ]
            await thread_manager.add_action_items(thread_id, action_item_objects)

        # Set the final result
        result = {
            "response": agent_response.get("response", ""),
            "action_items": action_items,
            "metadata": agent_response.get("metadata", {}),
            "turn_completed_at": datetime.now(timezone.utc).isoformat(),
        }

        await thread_manager.set_thread_result(thread_id, result)

        # Mark thread as done
        await thread_manager.update_thread_status(thread_id, ThreadStatus.DONE)
        await thread_manager.add_thread_update(
            thread_id, "Agent turn completed successfully", "turn_complete"
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
        await progress_callback("Starting agent analysis", "agent_start")

        # Get the conversation messages
        messages = conversation_state.get("messages", [])
        if not messages:
            raise ValueError("No messages in conversation")

        # Create a new agent instance with progress callback
        from redis_sre_agent.agent.langgraph_agent import SRELangGraphAgent

        progress_agent = SRELangGraphAgent(progress_callback=progress_callback)

        # Convert conversation messages to LangChain format
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
            "max_iterations": 10,
        }

        await progress_callback("Running agent workflow", "agent_processing")

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

        # Use the process_query method to handle context properly
        response = await progress_agent.process_query(
            query=latest_user_message,
            session_id=thread_id,
            user_id=thread_state.metadata.user_id if thread_state else "system",
            max_iterations=10,
            context=agent_context,
            progress_callback=progress_callback,
        )

        # Create a mock final state for compatibility

        await progress_callback("Agent workflow completed", "agent_complete")

        # The response is already the final agent response
        agent_response = response

        # Try to extract action items from response content
        action_items = extract_action_items_from_response(agent_response)

        return {
            "response": agent_response,
            "metadata": {
                "iterations": 1,  # Since we're using process_query directly
                "tool_calls": 0,  # Placeholder - could be enhanced to track tool calls
                "session_id": thread_id,
            },
            "action_items": action_items,
        }

    except Exception as e:
        await progress_callback(f"Agent error: {str(e)}", "error")
        raise


def extract_action_items_from_response(response_content: str) -> List[Dict[str, Any]]:
    """
    Extract action items from agent response content.

    This is a simple implementation that looks for common action item patterns.
    """
    action_items = []

    # Look for common action item patterns
    import re

    # Pattern 1: "Action Items:" or "Recommendations:" sections
    action_patterns = [
        r"action items?:?\s*\n(.*?)(?:\n\n|\n[A-Z]|\Z)",
        r"recommendations?:?\s*\n(.*?)(?:\n\n|\n[A-Z]|\Z)",
        r"next steps?:?\s*\n(.*?)(?:\n\n|\n[A-Z]|\Z)",
        r"todo:?\s*\n(.*?)(?:\n\n|\n[A-Z]|\Z)",
    ]

    for pattern in action_patterns:
        matches = re.finditer(pattern, response_content, re.IGNORECASE | re.DOTALL)
        for match in matches:
            action_text = match.group(1).strip()

            # Split by lines and extract individual items
            lines = [line.strip() for line in action_text.split("\n") if line.strip()]
            for line in lines:
                # Remove bullet points and numbering
                clean_line = re.sub(r"^[\d\.\-\*\+]\s*", "", line).strip()
                if clean_line and len(clean_line) > 10:  # Ignore very short items
                    action_items.append(
                        {
                            "title": clean_line[:100],  # Truncate long titles
                            "description": clean_line,
                            "priority": "medium",
                            "category": "general",
                        }
                    )

    return action_items[:5]  # Limit to 5 action items


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
