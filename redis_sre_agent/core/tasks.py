"""Docket task definitions for SRE operations."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from docket import Docket, Retry
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
async def search_runbook_knowledge(
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

        # Check if this is Redis service - use direct diagnostics
        if service_name.lower() in ["redis", "redis-server", "redis-cluster"]:
            from ..tools.redis_diagnostics import get_redis_diagnostics

            redis_diag = get_redis_diagnostics()
            diagnostic_results = await redis_diag.run_diagnostic_suite()

            # Convert diagnostics to health check format
            health_results = [
                {
                    "endpoint": "redis_diagnostics",
                    "status": (
                        "healthy"
                        if diagnostic_results["overall_status"] in ["healthy", "warning"]
                        else "unhealthy"
                    ),
                    "response_time_ms": None,
                    "diagnostic_data": diagnostic_results,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            ]

            await redis_diag.close()
        else:
            # For other services, perform HTTP health checks
            import aiohttp

            health_results = []

            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=timeout)
            ) as session:
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


async def get_redis_url() -> str:
    """Get Redis URL for Docket."""
    return settings.redis_url


async def register_sre_tasks() -> None:
    """Register all SRE tasks with Docket."""
    try:
        async with Docket(url=await get_redis_url()) as docket:
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

        # Import agent here to avoid circular imports
        from redis_sre_agent.agent import get_sre_agent

        # Update progress
        await thread_manager.add_thread_update(
            thread_id, "Initializing SRE agent and tools", "agent_init"
        )

        # Get the agent
        agent = get_sre_agent()

        # Prepare the conversation state with thread context
        conversation_state = {
            "messages": thread_state.context.get("messages", []),
            "thread_id": thread_id,
        }

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

        # Create a progress callback for the agent
        async def progress_callback(update_message: str, update_type: str = "progress"):
            await thread_manager.add_thread_update(thread_id, update_message, update_type)

        # Run the agent (this will be a modified version that accepts progress callback)
        agent_response = await run_agent_with_progress(agent, conversation_state, progress_callback)

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


async def run_agent_with_progress(agent, conversation_state: Dict[str, Any], progress_callback):
    """
    Run the LangGraph agent with progress updates.

    This creates a new agent instance with progress callback support and runs it.
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

        # Run the agent workflow
        final_state = await progress_agent.ainvoke(agent_state)

        await progress_callback("Agent workflow completed", "agent_complete")

        # Extract the final response
        final_messages = final_state.get("messages", [])
        if final_messages:
            last_message = final_messages[-1]
            response_content = (
                last_message.content if hasattr(last_message, "content") else str(last_message)
            )

            # Try to extract action items from response content
            action_items = extract_action_items_from_response(response_content)

            return {
                "response": response_content,
                "metadata": {
                    "iterations": final_state.get("iteration_count", 0),
                    "tool_calls": len(final_state.get("current_tool_calls", [])),
                    "session_id": final_state.get("session_id"),
                },
                "action_items": action_items,
            }
        else:
            return {"response": "No response from agent", "metadata": {}, "action_items": []}

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
        async with Docket(url=await get_redis_url()):
            # Simple connectivity test
            return True
    except Exception as e:
        logger.error(f"Task system test failed: {e}")
        return False
