"""MCP server implementation for redis-sre-agent.

This module creates an MCP server using FastMCP that exposes the agent's
capabilities to other MCP clients. The server runs in stdio mode and
proxies requests to the running Redis SRE Agent HTTP API.

This allows Claude to connect to an already-running agent via:
1. Start agent: docker compose up -d (API on port 8080)
2. Claude spawns this MCP server, which calls the HTTP API
"""

import logging
from typing import Any, Dict, List, Optional

from mcp.server.fastmcp import FastMCP

logger = logging.getLogger(__name__)

# Create the MCP server instance
mcp = FastMCP(
    name="redis-sre-agent",
    instructions="""Redis SRE Agent - An AI-powered Redis troubleshooting and operations assistant.

## Task-Based Architecture

This agent uses a **task-based workflow**. Most tools create a **Task** that runs in
the background. You MUST watch each task for:

1. **Status changes**: queued → in_progress → done/failed
2. **Notifications**: Real-time updates showing what the agent is doing
3. **Final result**: The response when status="done"

## Tools That Create Tasks (require polling)

| Tool | Purpose | Typical Duration |
|------|---------|------------------|
| `redis_sre_deep_triage()` | Deep analysis of Redis issues | 2-10 minutes |
| `redis_sre_general_chat()` | Quick Q&A with full toolset (including external MCP tools) | 10-30 seconds |
| `redis_sre_database_chat()` | Redis-focused chat (no external MCP tools) | 10-30 seconds |
| `redis_sre_knowledge_query()` | Answer questions using knowledge base | 10-30 seconds |

**Note**: Deep triage performs comprehensive analysis including metrics collection, log analysis,
knowledge base searches, and multi-topic recommendation synthesis. Complex queries or
instances with many data sources may take longer.

After calling any of these, you MUST:
1. Get the `task_id` from the response
2. Poll `redis_sre_get_task_status(task_id)` until status is "done" or "failed"
3. Read the `result` field when done

## Utility Tools (return immediately)

| Tool | Purpose |
|------|---------|
| `redis_sre_knowledge_search()` | Direct search of docs (raw results) |
| `redis_sre_list_instances()` | List available Redis instances |
| `redis_sre_get_task_status()` | Check task progress |
| `redis_sre_get_thread()` | Get conversation history |

## Standard Workflow

```
1. Call redis_sre_deep_triage(), redis_sre_general_chat(), or redis_sre_knowledge_query()
   → Returns: task_id, thread_id, status="queued"

2. Poll redis_sre_get_task_status(task_id) every 5 seconds
   → status: "queued" → "in_progress" → "done"
   → updates: Array of notifications (grows over time)
   → result: Final answer (when status="done")

3. When status="done", read result.response
```

## Example

```
# Step 1: Create task
response = redis_sre_deep_triage(query="High memory usage on prod-redis")
task_id = response.task_id

# Step 2: Poll for completion
while True:
    status = redis_sre_get_task_status(task_id)
    if status.status == "done":
        print(status.result.response)  # The answer!
        break
    elif status.status == "failed":
        print(status.error_message)
        break
    # Show progress to user
    for update in status.updates:
        print(update.message)
    sleep(5)
```

## Tips

- **Always poll redis_sre_get_task_status()** - results are on the task, not returned directly
- Use `redis_sre_knowledge_search()` for quick doc lookups (no polling needed)
- Use `redis_sre_list_instances()` to find instance IDs before calling other tools
- Check the `updates` array to show users what the agent is doing""",
)


@mcp.tool()
async def redis_sre_deep_triage(
    query: str,
    instance_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a deep triage task to analyze a Redis issue comprehensively.

    This creates a **Task** that runs in the background. You MUST watch the task
    for status changes, notifications, and the final result.

    ## What This Tool Does

    Creates a deep analysis task that:
    - Performs comprehensive multi-topic analysis (memory, connections, performance, etc.)
    - Uses knowledge base, metrics, logs, traces, and diagnostics tools
    - Synthesizes findings into actionable recommendations
    - Emits notifications as it works (visible via redis_sre_get_task_status)
    - Stores the final result on the task when complete

    ## How to Use the Task

    1. **Call this tool** → Returns `task_id` (and `thread_id`)
    2. **Watch the task** → Poll `redis_sre_get_task_status(task_id)` every 5-10 seconds
       - `status`: "queued" → "in_progress" → "done" or "failed"
       - `updates`: Array of notifications showing what the agent is doing
       - `result`: Final analysis (present when status="done")
    3. **Read the result** → When status="done", the `result` field has the response

    The task typically takes 2-10 minutes depending on complexity.

    Args:
        query: The issue to analyze (e.g., "High memory usage on production Redis")
        instance_id: Optional Redis instance ID (use redis_sre_list_instances to find IDs)
        user_id: Optional user ID for tracking

    Returns:
        task_id: Watch this task for status, notifications, and result
        thread_id: Conversation thread (for multi-turn follow-ups)
        status: Initial status (usually "queued")
    """
    from docket import Docket

    from redis_sre_agent.core.docket_tasks import get_redis_url, process_agent_turn
    from redis_sre_agent.core.redis import get_redis_client
    from redis_sre_agent.core.tasks import create_task

    logger.info(f"MCP deep_triage request: {query[:100]}...")

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

        # Submit to Docket for processing (this is what the API does).
        # Use the task_id as the Docket key so we can cancel by task_id later.
        async with Docket(url=await get_redis_url(), name="sre_docket") as docket:
            task_func = docket.add(process_agent_turn, key=result["task_id"])
            await task_func(
                thread_id=result["thread_id"],
                message=query,
                context=context,
                task_id=result["task_id"],
            )

        return {
            "thread_id": result["thread_id"],
            "task_id": result["task_id"],
            "status": (
                result["status"].value
                if hasattr(result["status"], "value")
                else str(result["status"])
            ),
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
async def redis_sre_general_chat(
    query: str,
    instance_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a chat task for Redis Q&A with full tool access.

    This creates a **Task** that runs the chat agent with access to ALL tools including:
    - Redis instance tools (INFO, SLOWLOG, CONFIG, CLIENT, etc.)
    - Knowledge base tools (search documentation, runbooks)
    - Utility tools (time conversion, formatting)
    - External MCP tools (GitHub, Slack, Prometheus, Loki, etc. if configured)

    Use this for:
    - Questions that may require external data (metrics, logs, tickets)
    - Operations that span multiple systems
    - Quick status checks with full observability context

    For Redis-only questions without external integrations, use redis_sre_database_chat().
    For complex issues requiring deep analysis, use redis_sre_deep_triage().

    ## How to Use the Task

    1. **Call this tool** → Returns `task_id` (and `thread_id`)
    2. **Watch the task** → Poll `redis_sre_get_task_status(task_id)` every 2-5 seconds
       - Chat is faster than triage (typically 10-30 seconds)
       - `status`: "queued" → "in_progress" → "done" or "failed"
       - `updates`: Notifications showing what the agent is doing
       - `result`: The answer (present when status="done")

    Args:
        query: Your question (e.g., "What's the current memory usage?")
        instance_id: Optional Redis instance ID (use redis_sre_list_instances to find IDs)
        user_id: Optional user ID for tracking

    Returns:
        task_id: Watch this task for status, notifications, and result
        thread_id: Conversation thread (for follow-up questions)
        status: Initial status (usually "queued")
    """
    from docket import Docket

    from redis_sre_agent.core.docket_tasks import get_redis_url, process_chat_turn
    from redis_sre_agent.core.redis import get_redis_client
    from redis_sre_agent.core.tasks import create_task

    logger.info(f"MCP general_chat request: {query[:100]}...")

    try:
        redis_client = get_redis_client()
        context: Dict[str, Any] = {"agent_type": "chat"}
        if instance_id:
            context["instance_id"] = instance_id
        if user_id:
            context["user_id"] = user_id

        result = await create_task(
            message=query,
            context=context,
            redis_client=redis_client,
        )

        # Submit to Docket for processing; key by task_id for later cancellation.
        async with Docket(url=await get_redis_url(), name="sre_docket") as docket:
            task_func = docket.add(process_chat_turn, key=result["task_id"])
            await task_func(
                query=query,
                task_id=result["task_id"],
                thread_id=result["thread_id"],
                instance_id=instance_id,
                user_id=user_id,
            )

        return {
            "thread_id": result["thread_id"],
            "task_id": result["task_id"],
            "status": (
                result["status"].value
                if hasattr(result["status"], "value")
                else str(result["status"])
            ),
            "message": "Chat task queued for processing",
        }

    except Exception as e:
        logger.error(f"Chat failed: {e}")
        return {
            "error": str(e),
            "status": "failed",
            "message": f"Failed to start chat: {e}",
        }


@mcp.tool()
async def redis_sre_database_chat(
    query: str,
    instance_id: Optional[str] = None,
    user_id: Optional[str] = None,
    exclude_mcp_categories: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Create a Redis-focused chat task with selective MCP tool access.

    Similar to redis_sre_general_chat(), but allows excluding specific categories of
    MCP tools. By default, excludes all external MCP tools for focused Redis diagnostics.

    The agent has access to:
    - Redis instance tools (INFO, SLOWLOG, CONFIG, CLIENT, etc.)
    - Knowledge base tools (search documentation, runbooks)
    - Utility tools (time conversion, formatting)
    - MCP tools NOT in the excluded categories

    Use this when:
    - You want focused Redis instance diagnostics without external integrations
    - You need a lighter-weight agent that won't call out to certain MCP servers
    - You want selective access to MCP tools (e.g., allow metrics but not tickets)

    ## Exclude Categories

    You can exclude specific MCP tool categories:
    - "metrics": Prometheus, Grafana, etc.
    - "logs": Loki, log aggregators, etc.
    - "tickets": Jira, GitHub Issues, etc.
    - "repos": GitHub, GitLab, etc.
    - "traces": Jaeger, distributed tracing, etc.
    - "diagnostics": External diagnostic tools
    - "knowledge": External knowledge bases
    - "utilities": External utility tools

    Pass None or empty list to include all MCP tools (same as redis_sre_general_chat).
    Pass ["all"] to exclude all MCP tools.

    ## How to Use the Task

    1. **Call this tool** → Returns `task_id` (and `thread_id`)
    2. **Watch the task** → Poll `redis_sre_get_task_status(task_id)` every 2-5 seconds
       - `status`: "queued" → "in_progress" → "done" or "failed"
       - `updates`: Notifications showing what the agent is doing
       - `result`: The answer (present when status="done")

    Args:
        query: Your question (e.g., "What's the current memory usage?")
        instance_id: Optional Redis instance ID (use redis_sre_list_instances to find IDs)
        user_id: Optional user ID for tracking
        exclude_mcp_categories: Categories to exclude. Pass ["all"] to exclude all MCP tools.
            Default: ["all"] (excludes all MCP tools for focused Redis chat)

    Returns:
        task_id: Watch this task for status, notifications, and result
        thread_id: Conversation thread (for follow-up questions)
        status: Initial status (usually "queued")
    """
    from docket import Docket

    from redis_sre_agent.core.docket_tasks import get_redis_url, process_chat_turn
    from redis_sre_agent.core.redis import get_redis_client
    from redis_sre_agent.core.tasks import create_task
    from redis_sre_agent.tools.models import ToolCapability

    logger.info(f"MCP database_chat request: {query[:100]}...")

    # Default to excluding all MCP categories for focused Redis chat
    if exclude_mcp_categories is None:
        exclude_mcp_categories = ["all"]

    # Convert "all" to list of all categories
    if "all" in exclude_mcp_categories:
        exclude_mcp_categories = [cap.value for cap in ToolCapability]

    try:
        redis_client = get_redis_client()
        context: Dict[str, Any] = {
            "agent_type": "chat",
            "exclude_mcp_categories": exclude_mcp_categories,
        }
        if instance_id:
            context["instance_id"] = instance_id
        if user_id:
            context["user_id"] = user_id

        result = await create_task(
            message=query,
            context=context,
            redis_client=redis_client,
        )

        # Submit to Docket for processing with category exclusions; key by task_id.
        async with Docket(url=await get_redis_url(), name="sre_docket") as docket:
            task_func = docket.add(process_chat_turn, key=result["task_id"])
            await task_func(
                query=query,
                task_id=result["task_id"],
                thread_id=result["thread_id"],
                instance_id=instance_id,
                user_id=user_id,
                exclude_mcp_categories=exclude_mcp_categories,
            )

        return {
            "thread_id": result["thread_id"],
            "task_id": result["task_id"],
            "status": (
                result["status"].value
                if hasattr(result["status"], "value")
                else str(result["status"])
            ),
            "message": f"Database chat task queued (excluded categories: {exclude_mcp_categories})",
        }

    except Exception as e:
        logger.error(f"Database chat failed: {e}")
        return {
            "error": str(e),
            "status": "failed",
            "message": f"Failed to start database chat: {e}",
        }


@mcp.tool()
async def redis_sre_knowledge_search(
    query: str,
    limit: int = 10,
    offset: int = 0,
    category: Optional[str] = None,
    version: Optional[str] = "latest",
) -> Dict[str, Any]:
    """Search the Redis SRE knowledge base (returns raw results).

    This is a **direct search** that returns raw knowledge base results immediately.
    Use this when you want to browse documentation or get specific content.

    For questions that need interpretation/reasoning, use `redis_sre_knowledge_query()`
    instead, which creates a task that uses the Knowledge Agent to analyze and answer.

    Args:
        query: Search query (e.g., "redis memory eviction policies")
        limit: Maximum number of results (1-50, default 10)
        offset: Number of results to skip for pagination (default 0)
        category: Optional filter by category ('incident', 'maintenance', 'monitoring', etc.)
        version: Redis documentation version filter. Defaults to "latest".

    Returns:
        results: Array of matching documents with title, content, source, etc.
        (Returns immediately - no task polling needed)
    """
    from redis_sre_agent.core.knowledge_helpers import search_knowledge_base_helper

    logger.info(f"MCP knowledge_search: {query[:100]}... (version={version}, offset={offset})")

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
            results.append(
                {
                    "title": item.get("title", "Untitled"),
                    "content": item.get("content", ""),
                    "source": item.get("source"),
                    "category": item.get("category"),
                    "version": item.get("version", "latest"),
                    "score": item.get("score"),
                }
            )

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
async def redis_sre_knowledge_query(
    query: str,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a task to answer a question using the Knowledge Agent.

    This creates a **Task** that uses the Knowledge Agent to answer questions
    about SRE practices, Redis best practices, and troubleshooting guidance.
    The agent searches the knowledge base and synthesizes an answer.

    Use this for questions that need reasoning/interpretation.
    Use `redis_sre_knowledge_search()` for direct document search.

    ## How to Use the Task

    1. **Call this tool** → Returns `task_id` (and `thread_id`)
    2. **Watch the task** → Poll `redis_sre_get_task_status(task_id)` every 2-5 seconds
       - `status`: "queued" → "in_progress" → "done" or "failed"
       - `updates`: Notifications showing knowledge sources being searched
       - `result`: The synthesized answer (present when status="done")

    Args:
        query: Your question (e.g., "What are Redis memory eviction policies?")
        user_id: Optional user ID for tracking

    Returns:
        task_id: Watch this task for status, notifications, and result
        thread_id: Conversation thread (for follow-up questions)
        status: Initial status (usually "queued")
    """
    from docket import Docket

    from redis_sre_agent.core.docket_tasks import get_redis_url, process_knowledge_query
    from redis_sre_agent.core.redis import get_redis_client
    from redis_sre_agent.core.tasks import create_task

    logger.info(f"MCP knowledge_query: {query[:100]}...")

    try:
        redis_client = get_redis_client()
        context: Dict[str, Any] = {"agent_type": "knowledge"}
        if user_id:
            context["user_id"] = user_id

        result = await create_task(
            message=query,
            context=context,
            redis_client=redis_client,
        )

        # Submit to Docket for processing; key by task_id for later cancellation.
        async with Docket(url=await get_redis_url(), name="sre_docket") as docket:
            task_func = docket.add(process_knowledge_query, key=result["task_id"])
            await task_func(
                query=query,
                task_id=result["task_id"],
                thread_id=result["thread_id"],
                user_id=user_id,
            )

        return {
            "thread_id": result["thread_id"],
            "task_id": result["task_id"],
            "status": (
                result["status"].value
                if hasattr(result["status"], "value")
                else str(result["status"])
            ),
            "message": "Knowledge query task queued for processing",
        }

    except Exception as e:
        logger.error(f"Knowledge query failed: {e}")
        return {
            "error": str(e),
            "status": "failed",
            "message": f"Failed to start knowledge query: {e}",
        }


@mcp.tool()
async def redis_sre_get_thread(thread_id: str) -> Dict[str, Any]:
    """Get the full conversation and results from a triage or chat thread.

    Call this AFTER redis_sre_get_task_status() shows status="done" to retrieve the
    complete analysis. The thread contains:

    - All messages exchanged (user query, assistant responses)
    - Tool calls made by the agent (metrics queries, log searches, etc.)
    - The final result with findings and recommendations

    Workflow:
    1. redis_sre_deep_triage() or redis_sre_*_chat() → get thread_id and task_id
    2. redis_sre_get_task_status(task_id) → poll until status="done"
    3. redis_sre_get_thread(thread_id) → get full results (this tool)

    Args:
        thread_id: The thread_id returned from the triage or chat tool

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

        # Format messages from thread.messages
        formatted_messages = []
        for msg in thread.messages:
            formatted_msg = {
                "role": msg.role,
                "content": msg.content,
            }
            # Include metadata if present
            if msg.metadata:
                formatted_msg["metadata"] = msg.metadata
            formatted_messages.append(formatted_msg)

        # Get the latest task for updates/result/error
        from redis_sre_agent.core.keys import RedisKeys
        from redis_sre_agent.core.tasks import TaskManager

        task_manager = TaskManager(redis_client=redis_client)
        latest_task_ids = await redis_client.zrevrange(
            RedisKeys.thread_tasks_index(thread_id), 0, 0
        )

        result = None
        error_message = None
        updates = []

        if latest_task_ids:
            latest_task_id = latest_task_ids[0]
            if isinstance(latest_task_id, bytes):
                latest_task_id = latest_task_id.decode()
            task_state = await task_manager.get_task_state(latest_task_id)
            if task_state:
                result = task_state.result
                error_message = task_state.error_message
                updates = [u.model_dump() for u in task_state.updates] if task_state.updates else []

        return {
            "thread_id": thread_id,
            "messages": formatted_messages,
            "message_count": len(formatted_messages),
            "result": result,
            "error_message": error_message,
            "updates": updates,
        }

    except Exception as e:
        logger.error(f"Get thread failed: {e}")
        return {
            "error": str(e),
            "thread_id": thread_id,
        }


@mcp.tool()
async def redis_sre_get_task_status(task_id: str) -> Dict[str, Any]:
    """Watch a task for status, notifications, and result.

    After calling any task-based tool (redis_sre_deep_triage, redis_sre_*_chat, etc.),
    poll this tool to watch your task. Check THREE things:

    ## 1. Status (is it done?)

    - "queued": Waiting to start
    - "in_progress": Agent is working
    - "done": Complete! Check the `result` field
    - "failed": Error occurred - check `error_message`

    ## 2. Updates/Notifications (what is the agent doing?)

    The `updates` array shows real-time notifications:
    ```
    updates: [
      {"timestamp": "...", "message": "Querying Redis INFO...", "type": "tool_call"},
      {"timestamp": "...", "message": "Memory usage is 85%...", "type": "agent_reflection"},
      {"timestamp": "...", "message": "Checking slow log...", "type": "tool_call"},
    ]
    ```

    This array grows as the agent works. Each entry shows what the agent
    is doing or thinking. Use this to provide feedback to users.

    ## 3. Result (the final answer)

    When status="done", the `result` field contains:
    ```
    result: {
      "response": "Based on my analysis, the high memory...",
      "metadata": {...}
    }
    ```

    ## Polling Pattern

    Poll every 5-10 seconds until status is "done" or "failed":
    - Show updates to user as they arrive
    - When done, extract the result

    Args:
        task_id: The task_id returned from triage or chat tools

    Returns:
        status: Current status (queued/in_progress/done/failed)
        updates: Array of notifications from the agent (grows over time)
        result: Final response (only present when status="done")
        error_message: Error details (only present when status="failed")
        thread_id: For multi-turn follow-ups via redis_sre_get_thread()
    """
    from redis_sre_agent.core.tasks import get_task_by_id

    logger.info(f"MCP get_task_status: {task_id}")

    try:
        task = await get_task_by_id(task_id=task_id)
        metadata = task.get("metadata", {}) or {}

        return {
            "task_id": task_id,
            "thread_id": task.get("thread_id"),
            "status": task.get("status"),
            "subject": metadata.get("subject"),
            "created_at": metadata.get("created_at"),
            "updated_at": metadata.get("updated_at"),
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
async def redis_sre_delete_task(task_id: str) -> Dict[str, Any]:
    """Best-effort cancel and delete a task by task_id.

    This tool mirrors the REST/CLI behavior:

    1. Try to cancel the corresponding Docket task using task_id as the key.
    2. Run core Redis cleanup via core.tasks.delete_task.
    """

    from docket import Docket

    from redis_sre_agent.core.docket_tasks import get_redis_url
    from redis_sre_agent.core.redis import get_redis_client
    from redis_sre_agent.core.tasks import delete_task as delete_task_core

    logger.info(f"MCP delete_task: {task_id}")

    client = get_redis_client()

    # Best-effort Docket cancellation
    try:
        async with Docket(url=await get_redis_url(), name="sre_docket") as docket:
            try:
                await docket.cancel(task_id)
            except Exception as e:  # pragma: no cover - defensive
                logger.warning("Failed to cancel Docket task %s: %s", task_id, e)
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("Failed to initialize Docket for cancel of %s: %s", task_id, e)

    try:
        await delete_task_core(task_id=task_id, redis_client=client)
    except Exception as e:
        logger.error("Failed to delete task %s via MCP: %s", task_id, e)
        return {
            "task_id": task_id,
            "status": "error",
            "error": str(e),
        }

    return {
        "task_id": task_id,
        "status": "deleted",
    }


@mcp.tool()
async def redis_sre_list_instances(
    environment: Optional[str] = None,
    usage: Optional[str] = None,
    status: Optional[str] = None,
    instance_type: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 100,
) -> Dict[str, Any]:
    """List configured Redis instances with optional filtering.

    Returns a list of Redis instances that have been configured in the SRE agent.
    All filter parameters are optional - when not provided, returns all instances.

    Use this to find instance IDs before calling other tools like
    redis_sre_deep_triage() or redis_sre_general_chat().

    Args:
        environment: Filter by environment (development, staging, production)
        usage: Filter by usage type (cache, analytics, session, queue, custom)
        status: Filter by status (healthy, unhealthy, unknown)
        instance_type: Filter by type (oss_single, oss_cluster, redis_enterprise, redis_cloud)
        search: Search by instance name (partial match supported)
        limit: Maximum number of results (default 100)

    Returns:
        Dictionary with filtered list of instance information and total count
    """
    from redis_sre_agent.core.instances import query_instances

    logger.info(
        f"MCP list_instances request: env={environment}, usage={usage}, "
        f"status={status}, type={instance_type}, search={search}, limit={limit}"
    )

    try:
        result = await query_instances(
            environment=environment,
            usage=usage,
            status=status,
            instance_type=instance_type,
            search=search,
            limit=limit,
            offset=0,
        )

        instance_list = []
        for inst in result.instances:
            instance_list.append(
                {
                    "id": inst.id,
                    "name": inst.name,
                    "environment": inst.environment,
                    "usage": inst.usage,
                    "description": inst.description,
                    "instance_type": inst.instance_type,
                    "repo_url": inst.repo_url,
                    "status": getattr(inst, "status", None),
                }
            )

        return {
            "instances": instance_list,
            "total": result.total,
            "limit": result.limit,
        }

    except Exception as e:
        logger.error(f"List instances failed: {e}")
        return {
            "error": str(e),
            "instances": [],
            "total": 0,
        }


@mcp.tool()
async def redis_sre_create_instance(
    name: str,
    connection_url: str,
    environment: str,
    usage: str,
    description: str,
    repo_url: Optional[str] = None,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a new Redis instance configuration.

    Registers a new Redis instance with the SRE agent. The instance can
    then be used for triage, monitoring, and diagnostics via tools like
    redis_sre_deep_triage() and redis_sre_general_chat().

    Args:
        name: Unique name for the instance
        connection_url: Redis connection URL (redis://host:port or rediss://...)
        environment: Environment type (development, staging, production, test)
        usage: Usage type (cache, analytics, session, queue, custom)
        description: Description of what this Redis instance is used for
        repo_url: Optional GitHub repository URL associated with this instance
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

    logger.info(f"MCP create_instance: {name}")

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
            repo_url=repo_url,
            instance_type="unknown",  # Will be auto-detected on first connection
        )

        instances.append(new_instance)
        if not await save_instances(instances):
            return {"error": "Failed to save instance", "status": "failed"}

        logger.info(f"Created Redis instance: {name} ({instance_id})")
        return {
            "id": instance_id,
            "name": name,
            "repo_url": repo_url,
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


# ASGI app for uvicorn deployment
# Usage: uvicorn redis_sre_agent.mcp_server.server:app --host 0.0.0.0 --port 8081
app = mcp.streamable_http_app()
