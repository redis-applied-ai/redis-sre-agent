"""MCP server implementation for redis-sre-agent.

This module creates an MCP server using FastMCP that exposes the agent's
capabilities to other MCP clients. The server runs in stdio mode and
proxies requests to the running Redis SRE Agent HTTP API.

This allows Claude to connect to an already-running agent via:
1. Start agent: docker compose up -d (API on port 8080)
2. Claude spawns this MCP server, which calls the HTTP API
"""

import logging
import os
from typing import Any, Dict, Optional

import httpx
from mcp.server.fastmcp import FastMCP

logger = logging.getLogger(__name__)

# API URL - can be overridden via environment variable
API_BASE_URL = os.environ.get("REDIS_SRE_API_URL", "http://localhost:8080")

# Create the MCP server instance
mcp = FastMCP(
    name="redis-sre-agent",
    instructions="""Redis SRE Agent - An AI-powered Redis troubleshooting and operations assistant.

## Triage Workflow (Most Common)

To analyze a Redis issue:

1. Call `triage(query="describe the issue", instance_id="optional-instance-id")`
   - Returns: thread_id and task_id
   - The analysis runs in the background (30-120 seconds typically)

2. Poll `get_task_status(task_id)` every 5-10 seconds
   - Wait until status is "done" or "failed"
   - The "updates" field shows progress messages

3. Call `get_thread(thread_id)` to get results
   - Contains full conversation, tool calls, and findings
   - The "result" field has the final analysis

## Other Tools

- `knowledge_search`: Search Redis docs and runbooks for quick answers
- `list_instances`: See available Redis instances (use IDs with triage)
- `create_instance`: Register a new Redis instance to monitor

## Tips

- Use list_instances first to find the correct instance_id for triage
- For simple questions, try knowledge_search before full triage
- Check get_task_status updates to see what the agent is analyzing""",
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

    IMPORTANT: This runs as a background task and returns immediately.
    Follow these steps to get results:

    1. Call this tool - returns thread_id and task_id
    2. Poll get_task_status(task_id) until status is "done" or "failed"
    3. Call get_thread(thread_id) to retrieve the full analysis and results

    The task typically takes 30-120 seconds depending on complexity.

    Args:
        query: The issue or question to triage (e.g., "High memory usage on production Redis")
        instance_id: Optional Redis instance ID to focus the analysis on (use list_instances to find IDs)
        user_id: Optional user ID for tracking

    Returns:
        thread_id: Use with get_thread() to retrieve conversation and results
        task_id: Use with get_task_status() to check if processing is complete
        status: Initial status (usually "queued")
    """
    from docket import Docket

    from redis_sre_agent.core.docket_tasks import get_redis_url, process_agent_turn
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

        # Submit to Docket for processing (this is what the API does)
        async with Docket(url=await get_redis_url(), name="sre_docket") as docket:
            task_func = docket.add(process_agent_turn)
            await task_func(
                thread_id=result["thread_id"],
                message=query,
                context=context,
                task_id=result["task_id"],
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
    limit: int = 10,
    offset: int = 0,
    category: Optional[str] = None,
    version: Optional[str] = "latest",
) -> Dict[str, Any]:
    """Search the Redis SRE knowledge base.

    Searches through Redis documentation, runbooks, troubleshooting guides,
    and SRE best practices. Use this to find information about Redis
    configuration, operations, and problem resolution.

    Args:
        query: Search query (e.g., "redis memory eviction policies")
        limit: Maximum number of results (1-50, default 10)
        offset: Number of results to skip for pagination (default 0)
        category: Optional filter by category ('incident', 'maintenance', 'monitoring', etc.)
        version: Redis documentation version filter. Defaults to "latest" which returns
                 only the most current documentation. Available versions:
                 - "latest": Current/unversioned docs (default, recommended)
                 - "7.8": Redis Enterprise 7.8 docs
                 - "7.4": Redis Enterprise 7.4 docs
                 - "7.2": Redis Enterprise 7.2 docs
                 - null/None: Return all versions (may include duplicates)

    Returns:
        Dictionary with search results including title, content, source, version, and relevance
    """
    from redis_sre_agent.core.knowledge_helpers import search_knowledge_base_helper

    logger.info(f"MCP knowledge search: {query[:100]}... (version={version}, offset={offset})")

    try:
        limit = max(1, min(50, limit))
        offset = max(0, offset)
        kwargs: Dict[str, Any] = {
            "query": query,
            "limit": limit,
            "offset": offset,
            "version": version,
        }
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
                "version": item.get("version", "latest"),
                "score": item.get("score"),
            })

        return {
            "query": query,
            "version": version,
            "offset": offset,
            "limit": limit,
            "results": results,
            "total_results": len(results),
            "has_more": len(results) == limit,  # Hint for pagination
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
    """Get the full conversation and results from a triage thread.

    Call this AFTER get_task_status() shows status="done" to retrieve the
    complete triage analysis. The thread contains:

    - All messages exchanged (user query, assistant responses)
    - Tool calls made by the agent (metrics queries, log searches, etc.)
    - The final result with findings and recommendations

    Workflow:
    1. triage() → get thread_id and task_id
    2. get_task_status(task_id) → poll until status="done"
    3. get_thread(thread_id) → get full results (this tool)

    Args:
        thread_id: The thread_id returned from the triage tool

    Returns:
        messages: List of conversation messages with role and content
        result: Final analysis result (findings, recommendations, etc.)
        updates: Progress updates that occurred during execution
        error_message: Error details if the triage failed
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
    """Check if a triage task is complete.

    Poll this after calling triage() to check when the analysis is done.
    Once status="done", call get_thread(thread_id) to retrieve results.

    Status values:
    - "queued": Task is waiting to be processed
    - "in_progress": Agent is actively analyzing
    - "done": Complete - call get_thread() to get results
    - "failed": Error occurred - check error_message
    - "cancelled": Task was cancelled

    Typical polling: Check every 5-10 seconds until status is "done" or "failed".

    Workflow:
    1. triage() → get thread_id and task_id
    2. get_task_status(task_id) → poll until status="done" (this tool)
    3. get_thread(thread_id) → get full results

    Args:
        task_id: The task_id returned from the triage tool

    Returns:
        status: Current task status (queued/in_progress/done/failed/cancelled)
        thread_id: Use with get_thread() once status is "done"
        updates: Progress messages from the agent during execution
        error_message: Error details if status is "failed"
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
    mcp.run(transport="stdio")


def run_sse(host: str = "127.0.0.1", port: int = 8080):
    """Run the MCP server in SSE mode (legacy, use HTTP instead)."""
    mcp.run(transport="sse", host=host, port=port)


def run_http(host: str = "0.0.0.0", port: int = 8081):
    """Run the MCP server in HTTP mode (Streamable HTTP).

    This is the recommended transport for remote access. Claude can connect
    to this server via Settings > Connectors > Add Custom Connector with
    the URL: http://<host>:<port>/mcp

    Args:
        host: Host to bind to (default 0.0.0.0 for external access)
        port: Port to listen on (default 8081)
    """
    import asyncio

    mcp.settings.host = host
    mcp.settings.port = port
    asyncio.run(mcp.run_streamable_http_async())


def get_http_app():
    """Get the ASGI app for the MCP server.

    Use this when deploying with uvicorn or other ASGI servers:
        uvicorn redis_sre_agent.mcp_server.server:app --host 0.0.0.0 --port 8081

    The MCP endpoint will be available at /mcp
    """
    return mcp.streamable_http_app()


# ASGI app for uvicorn deployment - lazy initialization to avoid import-time errors
def _get_app():
    return get_http_app()


# For uvicorn: uvicorn redis_sre_agent.mcp_server.server:app
app = None  # Will be initialized on first request
