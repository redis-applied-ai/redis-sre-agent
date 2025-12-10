"""MCP server implementation for redis-sre-agent.

This module creates an MCP server using FastMCP that exposes the agent's
capabilities to other MCP clients. The server can be run in stdio mode
for integration with other AI agents.
"""

import logging
from typing import Any, Dict, Optional

from mcp.server.fastmcp import FastMCP

logger = logging.getLogger(__name__)

# Create the MCP server instance
mcp = FastMCP(
    name="redis-sre-agent",
    instructions="""Redis SRE Agent - An AI-powered Redis troubleshooting and operations assistant.

This agent provides tools for:
- Triaging Redis issues and getting expert analysis
- Searching Redis documentation, runbooks, and best practices
- Managing Redis instance configurations

Use the triage tool when you need help troubleshooting Redis issues or want
expert analysis of a Redis deployment. Use knowledge_search to find specific
documentation or runbook information.""",
)


@mcp.tool()
async def triage(
    query: str,
    instance_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Start a Redis triage session.

    Submits a triage request to the Redis SRE Agent, which will analyze
    the issue using its knowledge base, metrics, logs, and diagnostic tools.

    The triage runs as a background task. Use the returned thread_id to
    check on progress or get results.

    Args:
        query: The issue or question to triage (e.g., "High memory usage on production Redis")
        instance_id: Optional Redis instance ID to focus the analysis on
        user_id: Optional user ID for tracking

    Returns:
        Dictionary with thread_id, task_id, and status information
    """
    from redis_sre_agent.core.redis import get_redis_client
    from redis_sre_agent.core.tasks import create_task

    logger.info(f"MCP triage request: {query[:100]}...")

    try:
        redis_client = get_redis_client()
        context: Dict[str, Any] = {}
        if instance_id:
            context["instance_id"] = instance_id
        if user_id:
            context["user_id"] = user_id

        result = await create_task(
            message=query,
            context=context,
            redis_client=redis_client,
        )

        return {
            "thread_id": result["thread_id"],
            "task_id": result["task_id"],
            "status": result["status"].value if hasattr(result["status"], "value") else str(result["status"]),
            "message": result.get("message", "Triage queued for processing"),
        }

    except Exception as e:
        logger.error(f"Triage failed: {e}")
        return {
            "error": str(e),
            "status": "failed",
            "message": f"Failed to start triage: {e}",
        }


@mcp.tool()
async def knowledge_search(
    query: str,
    limit: int = 5,
    category: Optional[str] = None,
) -> Dict[str, Any]:
    """Search the Redis SRE knowledge base.

    Searches through Redis documentation, runbooks, troubleshooting guides,
    and SRE best practices. Use this to find information about Redis
    configuration, operations, and problem resolution.

    Args:
        query: Search query (e.g., "redis memory eviction policies")
        limit: Maximum number of results (1-20, default 5)
        category: Optional filter by category ('incident', 'maintenance', 'monitoring', etc.)

    Returns:
        Dictionary with search results including title, content, source, and relevance
    """
    from redis_sre_agent.core.knowledge_helpers import search_knowledge_base_helper

    logger.info(f"MCP knowledge search: {query[:100]}...")

    try:
        limit = max(1, min(20, limit))
        kwargs: Dict[str, Any] = {"query": query, "limit": limit}
        if category:
            kwargs["category"] = category

        result = await search_knowledge_base_helper(**kwargs)

        results = []
        for item in result.get("results", []):
            results.append({
                "title": item.get("title", "Untitled"),
                "content": item.get("content", ""),
                "source": item.get("source"),
                "category": item.get("category"),
                "score": item.get("score"),
            })

        return {
            "query": query,
            "results": results,
            "total_results": len(results),
        }

    except Exception as e:
        logger.error(f"Knowledge search failed: {e}")
        return {
            "error": str(e),
            "query": query,
            "results": [],
            "total_results": 0,
        }


@mcp.tool()
async def get_thread(thread_id: str) -> Dict[str, Any]:
    """Get the contents of a triage thread.

    Retrieves the full conversation history, messages, tool calls, and results
    from a triage thread. Use this to check on the progress or get the final
    results of a triage session.

    Args:
        thread_id: The thread ID returned from the triage tool

    Returns:
        Dictionary with thread messages, status, and results
    """
    from redis_sre_agent.core.redis import get_redis_client
    from redis_sre_agent.core.threads import ThreadManager

    logger.info(f"MCP get_thread: {thread_id}")

    try:
        redis_client = get_redis_client()
        tm = ThreadManager(redis_client=redis_client)
        thread = await tm.get_thread(thread_id)

        if not thread:
            return {
                "error": f"Thread {thread_id} not found",
                "thread_id": thread_id,
            }

        # Extract messages from context
        messages = thread.context.get("messages", [])

        # Format messages for readability
        formatted_messages = []
        for msg in messages:
            formatted_msg = {
                "role": msg.get("role", "unknown"),
                "content": msg.get("content", ""),
            }
            # Include tool calls if present
            if "tool_calls" in msg:
                formatted_msg["tool_calls"] = msg["tool_calls"]
            formatted_messages.append(formatted_msg)

        return {
            "thread_id": thread_id,
            "messages": formatted_messages,
            "message_count": len(formatted_messages),
            "result": thread.result,
            "error_message": thread.error_message,
            "updates": [u.model_dump() for u in thread.updates] if thread.updates else [],
        }

    except Exception as e:
        logger.error(f"Get thread failed: {e}")
        return {
            "error": str(e),
            "thread_id": thread_id,
        }


@mcp.tool()
async def get_task_status(task_id: str) -> Dict[str, Any]:
    """Get the status of a background task.

    Check if a triage task is still running, completed, or failed.
    Use this to poll for task completion before retrieving thread results.

    Args:
        task_id: The task ID returned from the triage tool

    Returns:
        Dictionary with task status, progress updates, and result if complete
    """
    from redis_sre_agent.core.tasks import get_task_by_id

    logger.info(f"MCP get_task_status: {task_id}")

    try:
        task = await get_task_by_id(task_id=task_id)

        return {
            "task_id": task_id,
            "thread_id": task.get("thread_id"),
            "status": task.get("status"),
            "subject": task.get("subject"),
            "created_at": task.get("created_at"),
            "updated_at": task.get("updated_at"),
            "updates": task.get("updates", []),
            "result": task.get("result"),
            "error_message": task.get("error_message"),
        }

    except ValueError as e:
        return {
            "error": str(e),
            "task_id": task_id,
            "status": "not_found",
        }
    except Exception as e:
        logger.error(f"Get task status failed: {e}")
        return {
            "error": str(e),
            "task_id": task_id,
        }


@mcp.tool()
async def list_instances() -> Dict[str, Any]:
    """List all configured Redis instances.

    Returns a list of all Redis instances that have been configured
    in the SRE agent. Sensitive information like connection URLs and
    passwords are masked.

    Returns:
        Dictionary with list of instance information
    """
    from redis_sre_agent.core.instances import get_instances

    logger.info("MCP list instances request")

    try:
        instances = await get_instances()

        instance_list = []
        for inst in instances:
            instance_list.append({
                "id": inst.id,
                "name": inst.name,
                "environment": inst.environment,
                "usage": inst.usage,
                "description": inst.description,
                "instance_type": inst.instance_type,
                "status": getattr(inst, "status", None),
            })

        return {
            "instances": instance_list,
            "total": len(instance_list),
        }

    except Exception as e:
        logger.error(f"List instances failed: {e}")
        return {
            "error": str(e),
            "instances": [],
            "total": 0,
        }


@mcp.tool()
async def create_instance(
    name: str,
    connection_url: str,
    environment: str,
    usage: str,
    description: str,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a new Redis instance configuration.

    Registers a new Redis instance with the SRE agent. The instance can
    then be used for triage, monitoring, and diagnostics.

    Args:
        name: Unique name for the instance
        connection_url: Redis connection URL (redis://host:port or rediss://...)
        environment: Environment type (development, staging, production, test)
        usage: Usage type (cache, analytics, session, queue, custom)
        description: Description of what this Redis instance is used for
        user_id: Optional user ID of who is creating this instance

    Returns:
        Dictionary with the created instance ID and status
    """
    from datetime import datetime

    from redis_sre_agent.core.instances import (
        RedisInstance,
        get_instances,
        save_instances,
    )

    logger.info(f"MCP create instance: {name}")

    valid_envs = ["development", "staging", "production", "test"]
    if environment.lower() not in valid_envs:
        return {
            "error": f"Invalid environment. Must be one of: {', '.join(valid_envs)}",
            "status": "failed",
        }

    valid_usages = ["cache", "analytics", "session", "queue", "custom"]
    if usage.lower() not in valid_usages:
        return {
            "error": f"Invalid usage. Must be one of: {', '.join(valid_usages)}",
            "status": "failed",
        }

    try:
        instances = await get_instances()

        if any(inst.name == name for inst in instances):
            return {
                "error": f"Instance with name '{name}' already exists",
                "status": "failed",
            }

        instance_id = f"redis-{environment.lower()}-{int(datetime.now().timestamp())}"
        new_instance = RedisInstance(
            id=instance_id,
            name=name,
            connection_url=connection_url,
            environment=environment.lower(),
            usage=usage.lower(),
            description=description,
            instance_type="unknown",  # Will be auto-detected on first connection
        )

        instances.append(new_instance)
        if not await save_instances(instances):
            return {"error": "Failed to save instance", "status": "failed"}

        logger.info(f"Created Redis instance: {name} ({instance_id})")
        return {
            "id": instance_id,
            "name": name,
            "status": "created",
            "message": f"Successfully created instance '{name}'",
        }

    except Exception as e:
        logger.error(f"Create instance failed: {e}")
        return {"error": str(e), "status": "failed"}


# ============================================================================
# Server runners
# ============================================================================


def run_stdio():
    """Run the MCP server in stdio mode."""
    import asyncio
    asyncio.run(mcp.run_stdio_async())


def run_sse(host: str = "127.0.0.1", port: int = 8080):
    """Run the MCP server in SSE mode."""
    import asyncio
    mcp.settings.host = host
    mcp.settings.port = port
    asyncio.run(mcp.run_sse_async())
