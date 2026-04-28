"""MCP server implementation for redis-sre-agent.

This module creates an MCP server using FastMCP that exposes the agent's
capabilities to other MCP clients. The server runs in stdio mode and
proxies requests to the running Redis SRE Agent HTTP API.

This allows Claude to connect to an already-running agent via:
1. Start agent: docker compose up -d (API on port 8080)
2. Claude spawns this MCP server, which calls the HTTP API
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from docket import Docket
from mcp.server.fastmcp import FastMCP
from ulid import ULID

from redis_sre_agent.core.turn_scope import build_legacy_target_scope_adapter

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
| `redis_sre_run_pipeline_scrape()` | Run the scraping pipeline | Varies |
| `redis_sre_run_pipeline_ingest()` | Ingest a prepared batch | Varies |
| `redis_sre_run_pipeline_full()` | Run scraping and ingestion together | Varies |
| `redis_sre_prepare_source_documents()` | Prepare and optionally ingest local source docs | Varies |
| `redis_sre_generate_pipeline_runbooks()` | Run pipeline runbook operations | Varies |
| `redis_sre_cleanup_pipeline_batches()` | Remove old pipeline batches | Varies |
| `redis_sre_generate_runbook()` | Generate a Redis SRE runbook | Varies |
| `redis_sre_evaluate_runbooks()` | Evaluate runbook markdown files | Varies |

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
| `redis_sre_get_knowledge_fragments()` | Get all chunks for a document hash |
| `redis_sre_get_related_knowledge_fragments()` | Get nearby chunks around a document fragment |
| `redis_sre_get_pipeline_status()` | Show pipeline artifacts and recent ingestion state |
| `redis_sre_get_pipeline_batch()` | Show manifest and ingestion details for a batch |
| `redis_sre_list_support_packages()` | List uploaded support packages |
| `redis_sre_get_support_package_info()` | Get metadata for a support package |
| `redis_sre_upload_support_package()` | Upload a support package |
| `redis_sre_extract_support_package()` | Extract a support package |
| `redis_sre_delete_support_package()` | Delete a support package |
| `redis_sre_search_support_tickets()` | Search support-ticket docs only |
| `redis_sre_get_support_ticket()` | Get full support-ticket content by ticket id |
| `redis_sre_cache_stats()` | Show tool cache statistics |
| `redis_sre_cache_clear()` | Clear cached tool outputs |
| `redis_sre_audit_cli_mcp_parity()` | Audit in-scope CLI commands against MCP coverage |
| `redis_sre_version()` | Show Redis SRE Agent version metadata |
| `redis_sre_list_instances()` | List available Redis instances |
| `redis_sre_get_instance()` | Get a configured Redis instance by id |
| `redis_sre_create_instance()` | Create a Redis instance configuration |
| `redis_sre_update_instance()` | Update a configured Redis instance |
| `redis_sre_delete_instance()` | Delete a configured Redis instance |
| `redis_sre_test_instance()` | Test a configured Redis instance connection |
| `redis_sre_test_redis_url()` | Test a Redis URL without creating an instance |
| `redis_sre_list_threads()` | List conversation threads (find previous chats) |
| `redis_sre_get_thread_sources()` | Get recorded knowledge fragments for a thread |
| `redis_sre_get_thread_trace()` | Get tool-call trace for a message |
| `redis_sre_get_task_status()` | Check task progress |
| `redis_sre_get_task_citations()` | Get task citation/tool-call data |
| `redis_sre_get_task()` | Get a full task payload by task id |
| `redis_sre_list_tasks()` | List tasks with status filtering |
| `redis_sre_purge_tasks()` | Purge tasks in bulk with safeguards |
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
- Use `redis_sre_get_task_citations()` only when you need tool provenance or citation data
- Use `redis_sre_get_task()` and `redis_sre_list_tasks()` for direct task inspection without polling semantics
- Use `redis_sre_purge_tasks()` for bulk task cleanup with explicit confirmation
- Use `redis_sre_get_thread_sources()` and `redis_sre_get_thread_trace()` for thread provenance inspection
- Use `redis_sre_knowledge_search()` for quick doc lookups (no polling needed)
- Use fragment tools when you need the full document or nearby chunk context for a search hit
- Use task-backed pipeline and runbook tools for scrape/ingest/prepare/runbook/cleanup workflows
- Use `redis_sre_get_pipeline_status()` and `redis_sre_get_pipeline_batch()` for ingestion inspection
- Use support-package tools to upload, inspect, and extract Redis Enterprise diagnostics
- Use `redis_sre_search_support_tickets()` and `redis_sre_get_support_ticket()` for ticket-only retrieval
- Use `redis_sre_cache_stats()` to inspect cache state and `redis_sre_cache_clear()` to clear cached tool outputs
- Use `redis_sre_version()` for basic package/version inspection
- Use `redis_sre_list_instances()` and `redis_sre_get_instance()` to inspect configured instances
- Use `redis_sre_create_instance()`, `redis_sre_update_instance()`, and `redis_sre_delete_instance()` to manage instance configs
- Use `redis_sre_test_instance()` and `redis_sre_test_redis_url()` for connectivity checks
- Check the `updates` array to show users what the agent is doing""",
)


def _resolve_workspace_path(path_value: str) -> Path:
    """Resolve a user-supplied path and confine it to the server workspace."""
    workspace_root = Path.cwd().resolve()
    resolved = Path(path_value).expanduser().resolve()
    try:
        resolved.relative_to(workspace_root)
    except ValueError as exc:
        raise ValueError(
            f"Path must stay within the MCP server workspace: {workspace_root}"
        ) from exc
    return resolved


def _build_mcp_query_context(
    *,
    instance_id: Optional[str] = None,
    cluster_id: Optional[str] = None,
    user_id: Optional[str] = None,
    extra_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build MCP task context with TurnScope-compatible target metadata."""
    _, context = build_legacy_target_scope_adapter(
        instance_id=instance_id,
        cluster_id=cluster_id,
        resolution_policy="require_target" if (instance_id or cluster_id) else "allow_zero_scope",
    )
    if user_id:
        context["user_id"] = user_id
    if extra_context:
        for key, value in extra_context.items():
            context.setdefault(key, value)
    return context


@mcp.tool()
async def redis_sre_deep_triage(
    query: str,
    instance_id: Optional[str] = None,
    cluster_id: Optional[str] = None,
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
        cluster_id: Optional Redis cluster ID
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
        if instance_id and cluster_id:
            return {
                "status": "failed",
                "message": "Please provide only one of instance_id or cluster_id",
            }

        redis_client = get_redis_client()
        context = _build_mcp_query_context(
            instance_id=instance_id,
            cluster_id=cluster_id,
            user_id=user_id,
        )

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
    cluster_id: Optional[str] = None,
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
        cluster_id: Optional Redis cluster ID
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
        if instance_id and cluster_id:
            raise ValueError("Please provide only one of instance_id or cluster_id")

        redis_client = get_redis_client()
        context = _build_mcp_query_context(
            instance_id=instance_id,
            cluster_id=cluster_id,
            user_id=user_id,
            extra_context={"agent_type": "chat"},
        )

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
                cluster_id=cluster_id,
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
    cluster_id: Optional[str] = None,
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
        cluster_id: Optional Redis cluster ID
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
        if instance_id and cluster_id:
            raise ValueError("Please provide only one of instance_id or cluster_id")

        redis_client = get_redis_client()
        context = _build_mcp_query_context(
            instance_id=instance_id,
            cluster_id=cluster_id,
            user_id=user_id,
            extra_context={
                "agent_type": "chat",
                "exclude_mcp_categories": exclude_mcp_categories,
            },
        )

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
                cluster_id=cluster_id,
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
async def redis_sre_query(
    query: str,
    instance_id: Optional[str] = None,
    cluster_id: Optional[str] = None,
    support_package_id: Optional[str] = None,
    thread_id: Optional[str] = None,
    agent: str = "auto",
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a routed query task with thread continuation and support-package targeting."""
    from redis_sre_agent.core.query_helpers import queue_query_task_helper

    logger.info("MCP query request: %s...", query[:100])

    try:
        return await queue_query_task_helper(
            query=query,
            instance_id=instance_id,
            cluster_id=cluster_id,
            support_package_id=support_package_id,
            thread_id=thread_id,
            agent=agent,
            user_id=user_id,
        )
    except Exception as e:
        logger.error(f"Query failed: {e}")
        return {
            "error": str(e),
            "status": "failed",
            "message": f"Failed to start query: {e}",
        }


@mcp.tool()
async def redis_sre_list_clusters(
    environment: Optional[str] = None,
    status: Optional[str] = None,
    cluster_type: Optional[str] = None,
    user_id: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> Dict[str, Any]:
    """List configured Redis clusters with optional filtering."""
    from redis_sre_agent.core.cluster_helpers import list_clusters_helper

    return await list_clusters_helper(
        environment=environment,
        status=status,
        cluster_type=cluster_type,
        user_id=user_id,
        search=search,
        limit=limit,
        offset=offset,
    )


@mcp.tool()
async def redis_sre_get_cluster(cluster_id: str) -> Dict[str, Any]:
    """Get a configured Redis cluster by ID."""
    from redis_sre_agent.core.cluster_helpers import get_cluster_helper

    return await get_cluster_helper(cluster_id)


@mcp.tool()
async def redis_sre_create_cluster(
    name: str,
    environment: str,
    description: str,
    cluster_type: str = "unknown",
    notes: Optional[str] = None,
    admin_url: Optional[str] = None,
    admin_username: Optional[str] = None,
    admin_password: Optional[str] = None,
    status: Optional[str] = None,
    version: Optional[str] = None,
    last_checked: Optional[str] = None,
    created_by: str = "user",
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a new Redis cluster configuration."""
    from redis_sre_agent.core.cluster_helpers import create_cluster_helper

    try:
        return await create_cluster_helper(
            name=name,
            environment=environment,
            description=description,
            cluster_type=cluster_type,
            notes=notes,
            admin_url=admin_url,
            admin_username=admin_username,
            admin_password=admin_password,
            status=status,
            version=version,
            last_checked=last_checked,
            created_by=created_by,
            user_id=user_id,
        )
    except Exception as e:
        return {"error": str(e), "status": "failed"}


@mcp.tool()
async def redis_sre_update_cluster(
    cluster_id: str,
    name: Optional[str] = None,
    cluster_type: Optional[str] = None,
    environment: Optional[str] = None,
    description: Optional[str] = None,
    notes: Optional[str] = None,
    admin_url: Optional[str] = None,
    admin_username: Optional[str] = None,
    admin_password: Optional[str] = None,
    status: Optional[str] = None,
    version: Optional[str] = None,
    last_checked: Optional[str] = None,
    created_by: Optional[str] = None,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Update an existing Redis cluster configuration."""
    from redis_sre_agent.core.cluster_helpers import update_cluster_helper

    try:
        return await update_cluster_helper(
            cluster_id,
            name=name,
            cluster_type=cluster_type,
            environment=environment,
            description=description,
            notes=notes,
            admin_url=admin_url,
            admin_username=admin_username,
            admin_password=admin_password,
            status=status,
            version=version,
            last_checked=last_checked,
            created_by=created_by,
            user_id=user_id,
        )
    except Exception as e:
        return {"error": str(e), "id": cluster_id, "status": "failed"}


@mcp.tool()
async def redis_sre_delete_cluster(cluster_id: str, confirm: bool = False) -> Dict[str, Any]:
    """Delete a configured Redis cluster."""
    from redis_sre_agent.core.cluster_helpers import delete_cluster_helper

    try:
        return await delete_cluster_helper(cluster_id, confirm=confirm)
    except Exception as e:
        return {"error": str(e), "id": cluster_id, "status": "failed"}


@mcp.tool()
async def redis_sre_backfill_instance_links(
    dry_run: bool = False,
    force: bool = False,
) -> Dict[str, Any]:
    """Backfill cluster links for existing instance records."""
    from redis_sre_agent.core.cluster_helpers import backfill_instance_links_helper

    try:
        return await backfill_instance_links_helper(dry_run=dry_run, force=force)
    except Exception as e:
        return {"error": str(e), "status": "failed"}


@mcp.tool()
async def redis_sre_list_schedules(limit: int = 50) -> Dict[str, Any]:
    """List configured schedules."""
    from redis_sre_agent.core.schedule_helpers import list_schedules_helper

    try:
        return await list_schedules_helper(limit=limit)
    except Exception as e:
        return {"error": str(e), "status": "failed"}


@mcp.tool()
async def redis_sre_get_schedule(schedule_id: str) -> Dict[str, Any]:
    """Get a configured schedule by id."""
    from redis_sre_agent.core.schedule_helpers import get_schedule_helper

    try:
        return await get_schedule_helper(schedule_id)
    except Exception as e:
        return {"error": str(e), "id": schedule_id, "status": "failed"}


@mcp.tool()
async def redis_sre_create_schedule(
    name: str,
    interval_type: str,
    interval_value: int,
    instructions: str,
    redis_instance_id: Optional[str] = None,
    description: Optional[str] = None,
    enabled: bool = True,
) -> Dict[str, Any]:
    """Create a new schedule."""
    from redis_sre_agent.core.schedule_helpers import create_schedule_helper

    try:
        return await create_schedule_helper(
            name=name,
            interval_type=interval_type,
            interval_value=interval_value,
            instructions=instructions,
            redis_instance_id=redis_instance_id,
            description=description,
            enabled=enabled,
        )
    except Exception as e:
        return {"error": str(e), "status": "failed"}


@mcp.tool()
async def redis_sre_update_schedule(
    schedule_id: str,
    name: Optional[str] = None,
    description: Optional[str] = None,
    instructions: Optional[str] = None,
    redis_instance_id: Optional[str] = None,
    interval_type: Optional[str] = None,
    interval_value: Optional[int] = None,
    enabled: Optional[bool] = None,
    recalc_next_run: bool = True,
) -> Dict[str, Any]:
    """Update an existing schedule."""
    from redis_sre_agent.core.schedule_helpers import update_schedule_helper

    try:
        return await update_schedule_helper(
            schedule_id,
            name=name,
            description=description,
            instructions=instructions,
            redis_instance_id=redis_instance_id,
            interval_type=interval_type,
            interval_value=interval_value,
            enabled=enabled,
            recalc_next_run=recalc_next_run,
        )
    except Exception as e:
        return {"error": str(e), "id": schedule_id, "status": "failed"}


@mcp.tool()
async def redis_sre_enable_schedule(schedule_id: str) -> Dict[str, Any]:
    """Enable a schedule."""
    from redis_sre_agent.core.schedule_helpers import enable_schedule_helper

    try:
        return await enable_schedule_helper(schedule_id)
    except Exception as e:
        return {"error": str(e), "id": schedule_id, "status": "failed"}


@mcp.tool()
async def redis_sre_disable_schedule(schedule_id: str) -> Dict[str, Any]:
    """Disable a schedule."""
    from redis_sre_agent.core.schedule_helpers import disable_schedule_helper

    try:
        return await disable_schedule_helper(schedule_id)
    except Exception as e:
        return {"error": str(e), "id": schedule_id, "status": "failed"}


@mcp.tool()
async def redis_sre_delete_schedule(
    schedule_id: str,
    confirm: bool = False,
) -> Dict[str, Any]:
    """Delete a schedule."""
    from redis_sre_agent.core.schedule_helpers import delete_schedule_helper

    try:
        return await delete_schedule_helper(schedule_id, confirm=confirm)
    except Exception as e:
        return {"error": str(e), "id": schedule_id, "status": "failed"}


@mcp.tool()
async def redis_sre_run_schedule_now(schedule_id: str) -> Dict[str, Any]:
    """Trigger a schedule to run immediately."""
    from redis_sre_agent.core.schedule_helpers import run_schedule_now_helper

    try:
        return await run_schedule_now_helper(schedule_id)
    except Exception as e:
        return {"error": str(e), "id": schedule_id, "status": "failed"}


@mcp.tool()
async def redis_sre_list_schedule_runs(
    schedule_id: str,
    limit: int = 50,
) -> Dict[str, Any]:
    """List recent runs for a schedule."""
    from redis_sre_agent.core.schedule_helpers import list_schedule_runs_helper

    try:
        return await list_schedule_runs_helper(schedule_id, limit=limit)
    except Exception as e:
        return {"error": str(e), "id": schedule_id, "status": "failed"}


@mcp.tool()
async def redis_sre_reindex_threads(
    drop: bool = False,
    limit: int = 0,
    start: int = 0,
) -> Dict[str, Any]:
    """Recreate the threads index and backfill search documents."""
    from redis_sre_agent.core.thread_maintenance_helpers import reindex_threads_helper

    try:
        return await reindex_threads_helper(drop=drop, limit=limit, start=start)
    except Exception as e:
        return {"error": str(e), "status": "failed"}


@mcp.tool()
async def redis_sre_backfill_threads(
    limit: int = 0,
    start: int = 0,
) -> Dict[str, Any]:
    """Backfill the threads index from existing thread data."""
    from redis_sre_agent.core.thread_maintenance_helpers import backfill_threads_helper

    try:
        return await backfill_threads_helper(limit=limit, start=start)
    except Exception as e:
        return {"error": str(e), "status": "failed"}


@mcp.tool()
async def redis_sre_backfill_scheduled_thread_subjects(
    limit: int = 0,
    start: int = 0,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Backfill scheduled thread subjects and tags."""
    from redis_sre_agent.core.thread_maintenance_helpers import (
        backfill_scheduled_thread_subjects_helper,
    )

    try:
        return await backfill_scheduled_thread_subjects_helper(
            limit=limit,
            start=start,
            dry_run=dry_run,
        )
    except Exception as e:
        return {"error": str(e), "status": "failed"}


@mcp.tool()
async def redis_sre_backfill_empty_thread_subjects(
    limit: int = 0,
    start: int = 0,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Backfill empty or placeholder thread subjects."""
    from redis_sre_agent.core.thread_maintenance_helpers import (
        backfill_empty_thread_subjects_helper,
    )

    try:
        return await backfill_empty_thread_subjects_helper(
            limit=limit,
            start=start,
            dry_run=dry_run,
        )
    except Exception as e:
        return {"error": str(e), "status": "failed"}


@mcp.tool()
async def redis_sre_purge_threads(
    older_than: Optional[str] = None,
    purge_all: bool = False,
    include_tasks: bool = True,
    dry_run: bool = False,
    confirm: bool = False,
) -> Dict[str, Any]:
    """Purge threads in bulk with safeguards."""
    from redis_sre_agent.core.thread_maintenance_helpers import purge_threads_helper

    try:
        return await purge_threads_helper(
            older_than=older_than,
            purge_all=purge_all,
            include_tasks=include_tasks,
            dry_run=dry_run,
            confirm=confirm,
        )
    except Exception as e:
        return {"error": str(e), "status": "failed"}


@mcp.tool()
async def redis_sre_run_pipeline_scrape(
    artifacts_path: str = "./artifacts",
    scrapers: Optional[List[str]] = None,
    latest_only: bool = False,
    docs_path: str = "./redis-docs",
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a task to run the scraping pipeline."""
    from redis_sre_agent.core.pipeline_execution_helpers import queue_pipeline_operation_task

    logger.info("MCP pipeline scrape request")

    try:
        return await queue_pipeline_operation_task(
            operation="scrape",
            user_id=user_id,
            artifacts_path=artifacts_path,
            scrapers=scrapers,
            latest_only=latest_only,
            docs_path=docs_path,
        )
    except Exception as e:
        logger.error("Pipeline scrape failed: %s", e)
        return {
            "error": str(e),
            "status": "failed",
            "message": f"Failed to start pipeline scrape: {e}",
        }


@mcp.tool()
async def redis_sre_run_pipeline_ingest(
    batch_date: Optional[str] = None,
    artifacts_path: str = "./artifacts",
    latest_only: bool = False,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a task to run pipeline ingestion for a batch."""
    from redis_sre_agent.core.pipeline_execution_helpers import queue_pipeline_operation_task

    logger.info("MCP pipeline ingest request")

    try:
        return await queue_pipeline_operation_task(
            operation="ingest",
            user_id=user_id,
            batch_date=batch_date,
            artifacts_path=artifacts_path,
            latest_only=latest_only,
        )
    except Exception as e:
        logger.error("Pipeline ingest failed: %s", e)
        return {
            "error": str(e),
            "status": "failed",
            "message": f"Failed to start pipeline ingest: {e}",
        }


@mcp.tool()
async def redis_sre_run_pipeline_full(
    artifacts_path: str = "./artifacts",
    scrapers: Optional[List[str]] = None,
    latest_only: bool = False,
    docs_path: str = "./redis-docs",
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a task to run the full scraping plus ingestion pipeline."""
    from redis_sre_agent.core.pipeline_execution_helpers import queue_pipeline_operation_task

    logger.info("MCP pipeline full request")

    try:
        return await queue_pipeline_operation_task(
            operation="full",
            user_id=user_id,
            artifacts_path=artifacts_path,
            scrapers=scrapers,
            latest_only=latest_only,
            docs_path=docs_path,
        )
    except Exception as e:
        logger.error("Pipeline full failed: %s", e)
        return {
            "error": str(e),
            "status": "failed",
            "message": f"Failed to start full pipeline: {e}",
        }


@mcp.tool()
async def redis_sre_prepare_source_documents(
    source_dir: str = "source_documents",
    batch_date: Optional[str] = None,
    prepare_only: bool = False,
    artifacts_path: str = "./artifacts",
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a task to prepare source documents as pipeline artifacts."""
    from redis_sre_agent.core.pipeline_execution_helpers import queue_pipeline_operation_task

    logger.info("MCP prepare source documents request")

    try:
        return await queue_pipeline_operation_task(
            operation="prepare_sources",
            user_id=user_id,
            source_dir=source_dir,
            batch_date=batch_date,
            prepare_only=prepare_only,
            artifacts_path=artifacts_path,
        )
    except Exception as e:
        logger.error("Prepare source documents failed: %s", e)
        return {
            "error": str(e),
            "status": "failed",
            "message": f"Failed to start source preparation: {e}",
        }


@mcp.tool()
async def redis_sre_generate_pipeline_runbooks(
    url: Optional[str] = None,
    test_url: Optional[str] = None,
    list_urls: bool = False,
    artifacts_path: str = "./artifacts",
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a task to run pipeline runbook generation operations."""
    from redis_sre_agent.core.pipeline_execution_helpers import queue_pipeline_operation_task

    logger.info("MCP pipeline runbooks request")

    try:
        return await queue_pipeline_operation_task(
            operation="runbooks",
            user_id=user_id,
            url=url,
            test_url=test_url,
            list_urls=list_urls,
            artifacts_path=artifacts_path,
        )
    except Exception as e:
        logger.error("Pipeline runbooks failed: %s", e)
        return {
            "error": str(e),
            "status": "failed",
            "message": f"Failed to start pipeline runbooks: {e}",
        }


@mcp.tool()
async def redis_sre_cleanup_pipeline_batches(
    keep_days: int = 30,
    artifacts_path: str = "./artifacts",
    confirm: bool = False,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a task to clean up old pipeline batches."""
    from redis_sre_agent.core.pipeline_execution_helpers import queue_pipeline_operation_task

    logger.info("MCP pipeline cleanup request")

    if not confirm:
        return {
            "status": "failed",
            "message": "Cleanup is destructive. Re-run with confirm=True to continue.",
        }

    try:
        return await queue_pipeline_operation_task(
            operation="cleanup",
            user_id=user_id,
            keep_days=keep_days,
            artifacts_path=artifacts_path,
        )
    except Exception as e:
        logger.error("Pipeline cleanup failed: %s", e)
        return {
            "error": str(e),
            "status": "failed",
            "message": f"Failed to start pipeline cleanup: {e}",
        }


@mcp.tool()
async def redis_sre_generate_runbook(
    topic: str,
    scenario_description: str,
    severity: str = "warning",
    category: str = "operational_runbook",
    output_file: Optional[str] = None,
    requirements: Optional[List[str]] = None,
    max_iterations: int = 2,
    auto_save: bool = True,
    ingest: bool = False,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a task to generate a Redis SRE runbook."""
    from redis_sre_agent.core.runbook_execution_helpers import queue_runbook_operation_task

    logger.info("MCP runbook generate request")

    try:
        return await queue_runbook_operation_task(
            operation="generate",
            user_id=user_id,
            topic=topic,
            scenario_description=scenario_description,
            severity=severity,
            category=category,
            output_file=output_file,
            requirements=requirements,
            max_iterations=max_iterations,
            auto_save=auto_save,
            ingest=ingest,
        )
    except Exception as e:
        logger.error("Runbook generate failed: %s", e)
        return {
            "error": str(e),
            "status": "failed",
            "message": f"Failed to start runbook generation: {e}",
        }


@mcp.tool()
async def redis_sre_evaluate_runbooks(
    input_dir: str = "source_documents/runbooks",
    output_file: Optional[str] = None,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a task to evaluate runbook markdown files."""
    from redis_sre_agent.core.runbook_execution_helpers import queue_runbook_operation_task

    logger.info("MCP runbook evaluate request")

    try:
        return await queue_runbook_operation_task(
            operation="evaluate",
            user_id=user_id,
            input_dir=input_dir,
            output_file=output_file,
        )
    except Exception as e:
        logger.error("Runbook evaluation failed: %s", e)
        return {
            "error": str(e),
            "status": "failed",
            "message": f"Failed to start runbook evaluation: {e}",
        }


@mcp.tool()
async def redis_sre_get_knowledge_fragments(
    document_hash: str,
    include_metadata: bool = True,
    index_type: str = "knowledge",
    version: Optional[str] = None,
) -> Dict[str, Any]:
    """Get all document fragments for a document hash.

    Args:
        document_hash: Document hash to fetch.
        include_metadata: Include document metadata in the response.
        index_type: Index type to query.
        version: Optional version filter.

    Returns:
        Fragment payload for the requested document hash.
    """
    from redis_sre_agent.core.knowledge_helpers import get_all_document_fragments

    logger.info(
        "MCP get_knowledge_fragments: document_hash=%s index_type=%s version=%s",
        document_hash,
        index_type,
        version,
    )

    try:
        return await get_all_document_fragments(
            document_hash,
            include_metadata=include_metadata,
            index_type=index_type,
            version=version,
        )
    except Exception as e:
        logger.error("Get knowledge fragments failed: %s", e)
        return {
            "document_hash": document_hash,
            "error": str(e),
            "fragments": [],
        }


@mcp.tool()
async def redis_sre_get_related_knowledge_fragments(
    document_hash: str, chunk_index: int, window: int = 2
) -> Dict[str, Any]:
    """Get related fragments around a target chunk.

    Args:
        document_hash: Document hash to fetch.
        chunk_index: Target chunk index.
        window: Number of chunks before/after to include.

    Returns:
        Related fragment payload for the requested chunk.
    """
    from redis_sre_agent.core.knowledge_helpers import get_related_document_fragments

    logger.info(
        "MCP get_related_knowledge_fragments: document_hash=%s chunk_index=%s window=%s",
        document_hash,
        chunk_index,
        window,
    )

    try:
        return await get_related_document_fragments(
            document_hash,
            current_chunk_index=chunk_index,
            context_window=window,
        )
    except Exception as e:
        logger.error("Get related knowledge fragments failed: %s", e)
        return {
            "document_hash": document_hash,
            "error": str(e),
            "related_fragments": [],
        }


@mcp.tool()
async def redis_sre_list_skills(
    query: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
    version: Optional[str] = "latest",
) -> Dict[str, Any]:
    """List skills from the active skill backend.

    Args:
        query: Optional search query for relevance-ranked matching.
        limit: Maximum number of skills to return.
        offset: Number of skills to skip for pagination.
        version: Optional version filter. Defaults to "latest".

    Returns:
        Skill listing payload from the active backend.
    """
    from redis_sre_agent.core.knowledge_helpers import skills_check_helper

    logger.info(
        "MCP list_skills: query=%s limit=%s offset=%s version=%s",
        bool(query),
        limit,
        offset,
        version,
    )

    try:
        return await skills_check_helper(
            query=query,
            limit=limit,
            offset=offset,
            version=version,
        )
    except Exception as e:
        logger.error("List skills failed: %s", e)
        return {
            "error": str(e),
            "skills": [],
            "total": 0,
            "query": query,
            "limit": limit,
            "offset": offset,
            "version": version,
        }


@mcp.tool()
async def redis_sre_get_skill(
    skill_name: str,
    version: Optional[str] = "latest",
) -> Dict[str, Any]:
    """Get one skill manifest or legacy skill body.

    Args:
        skill_name: Skill name returned by list_skills or skills_check.
        version: Optional version filter. Defaults to "latest".

    Returns:
        Skill manifest or legacy markdown payload.
    """
    from redis_sre_agent.core.knowledge_helpers import get_skill_helper

    logger.info("MCP get_skill: skill_name=%s version=%s", skill_name, version)

    try:
        return await get_skill_helper(skill_name=skill_name, version=version)
    except Exception as e:
        logger.error("Get skill failed: %s", e)
        return {
            "error": str(e),
            "skill_name": skill_name,
            "version": version,
        }


@mcp.tool()
async def redis_sre_get_skill_resource(
    skill_name: str,
    resource_path: str,
    version: Optional[str] = "latest",
) -> Dict[str, Any]:
    """Get one named skill resource by relative path.

    Args:
        skill_name: Skill name returned by list_skills or get_skill.
        resource_path: Relative resource path such as `references/foo.md`.
        version: Optional version filter. Defaults to "latest".

    Returns:
        Resource payload including content and truncation metadata.
    """
    from redis_sre_agent.core.knowledge_helpers import get_skill_resource_helper

    logger.info(
        "MCP get_skill_resource: skill_name=%s resource_path=%s version=%s",
        skill_name,
        resource_path,
        version,
    )

    try:
        return await get_skill_resource_helper(
            skill_name=skill_name,
            resource_path=resource_path,
            version=version,
        )
    except Exception as e:
        logger.error("Get skill resource failed: %s", e)
        return {
            "error": str(e),
            "skill_name": skill_name,
            "resource_path": resource_path,
            "version": version,
        }


@mcp.tool()
def redis_sre_scaffold_skill_package(
    legacy_skill_path: str,
    target_dir: str,
    force: bool = False,
) -> Dict[str, Any]:
    """Scaffold an Agent Skills package from a legacy markdown skill.

    Args:
        legacy_skill_path: Path to an existing legacy markdown skill file.
        target_dir: Directory where the new package should be written.
        force: Allow writing into an existing non-empty directory.

    Returns:
        Scaffold result including created files and package directory.
    """
    from redis_sre_agent.skills.scaffold import scaffold_skill_package_from_markdown

    logger.info(
        "MCP scaffold_skill_package: legacy_skill_path=%s target_dir=%s force=%s",
        legacy_skill_path,
        target_dir,
        force,
    )

    try:
        _resolve_workspace_path(legacy_skill_path)
        _resolve_workspace_path(target_dir)
        return scaffold_skill_package_from_markdown(
            legacy_skill_path=legacy_skill_path,
            target_dir=target_dir,
            force=force,
        )
    except Exception as e:
        logger.error("Scaffold skill package failed: %s", e)
        return {
            "error": str(e),
            "legacy_skill_path": legacy_skill_path,
            "target_dir": target_dir,
            "force": force,
            "status": "failed",
        }


@mcp.tool()
async def redis_sre_list_support_packages(limit: int = 100) -> Dict[str, Any]:
    """List uploaded support packages.

    Args:
        limit: Maximum number of packages to return.

    Returns:
        packages: Serialized package metadata
        total: Number of returned packages
    """
    from redis_sre_agent.core.support_package_helpers import get_support_package_manager

    logger.info("MCP list_support_packages: limit=%s", limit)

    try:
        limit = max(1, limit)
        manager = get_support_package_manager()
        packages = await manager.list_packages()
        return {
            "packages": [pkg.model_dump(mode="json") for pkg in packages[:limit]],
            "total": min(len(packages), limit),
            "limit": limit,
        }
    except Exception as e:
        logger.error("List support packages failed: %s", e)
        return {
            "error": str(e),
            "packages": [],
            "total": 0,
            "limit": limit,
        }


@mcp.tool()
async def redis_sre_get_support_package_info(package_id: str) -> Dict[str, Any]:
    """Get information about a support package.

    Args:
        package_id: Support package id.

    Returns:
        Serialized metadata plus extraction state.
    """
    from redis_sre_agent.core.support_package_helpers import get_support_package_manager

    logger.info("MCP get_support_package_info: package_id=%s", package_id)

    try:
        manager = get_support_package_manager()
        metadata = await manager.get_metadata(package_id)
        if not metadata:
            return {
                "package_id": package_id,
                "status": "not_found",
                "error": "Package not found",
            }

        payload = metadata.model_dump(mode="json")
        payload["is_extracted"] = await manager.is_extracted(package_id)
        return payload
    except Exception as e:
        logger.error("Get support package info failed: %s", e)
        return {
            "package_id": package_id,
            "status": "failed",
            "error": str(e),
        }


@mcp.tool()
async def redis_sre_upload_support_package(
    file_path: str, package_id: Optional[str] = None
) -> Dict[str, Any]:
    """Upload a support package.

    Args:
        file_path: Local path to a `.tar.gz` support package.
        package_id: Optional custom package id.

    Returns:
        package_id: Stored package id
        filename: Original filename
        status: Upload status
    """
    from pathlib import Path

    from redis_sre_agent.core.support_package_helpers import get_support_package_manager

    logger.info("MCP upload_support_package: file_path=%s, package_id=%s", file_path, package_id)

    try:
        source_path = Path(file_path)
        if not source_path.exists():
            return {
                "file_path": file_path,
                "status": "failed",
                "error": f"File not found: {file_path}",
            }

        manager = get_support_package_manager()
        result_id = await manager.upload(source_path, package_id=package_id)
        return {
            "package_id": result_id,
            "filename": source_path.name,
            "status": "uploaded",
        }
    except Exception as e:
        logger.error("Upload support package failed: %s", e)
        return {
            "file_path": file_path,
            "status": "failed",
            "error": str(e),
        }


@mcp.tool()
async def redis_sre_extract_support_package(package_id: str) -> Dict[str, Any]:
    """Extract a support package.

    Args:
        package_id: Support package id.

    Returns:
        package_id: Support package id
        path: Extracted directory
        status: Extraction status
    """
    from redis_sre_agent.core.support_package_helpers import get_support_package_manager

    logger.info("MCP extract_support_package: package_id=%s", package_id)

    try:
        manager = get_support_package_manager()
        extract_path = await manager.extract(package_id)
        return {
            "package_id": package_id,
            "path": str(extract_path),
            "status": "extracted",
        }
    except Exception as e:
        logger.error("Extract support package failed: %s", e)
        return {
            "package_id": package_id,
            "status": "failed",
            "error": str(e),
        }


@mcp.tool()
async def redis_sre_delete_support_package(
    package_id: str, confirm: bool = False
) -> Dict[str, Any]:
    """Delete a support package.

    Args:
        package_id: Support package id.
        confirm: Explicit confirmation for deletion.

    Returns:
        package_id: Support package id
        status: Delete status
    """
    from redis_sre_agent.core.support_package_helpers import get_support_package_manager

    logger.info("MCP delete_support_package: package_id=%s confirm=%s", package_id, confirm)

    if not confirm:
        return {
            "package_id": package_id,
            "status": "failed",
            "error": "Deletion requires confirm=true",
        }

    try:
        manager = get_support_package_manager()
        await manager.delete(package_id)
        return {
            "package_id": package_id,
            "status": "deleted",
        }
    except Exception as e:
        logger.error("Delete support package failed: %s", e)
        return {
            "package_id": package_id,
            "status": "failed",
            "error": str(e),
        }


@mcp.tool()
async def redis_sre_get_pipeline_status(artifacts_path: str = "./artifacts") -> Dict[str, Any]:
    """Get pipeline status and available batches.

    Use this to inspect the current ingestion artifact state without shell access.

    Args:
        artifacts_path: Artifact root path. Defaults to './artifacts'.

    Returns:
        artifacts_path: Root artifact path
        current_batch_date: Today's batch folder name
        available_batches: Known batch directories
        scrapers: Configured scraper metadata
        ingestion: Recent ingestion summary
    """
    from redis_sre_agent.core.pipeline_helpers import get_pipeline_status_helper

    logger.info("MCP get_pipeline_status: artifacts_path=%s", artifacts_path)

    try:
        result = await get_pipeline_status_helper(artifacts_path=artifacts_path)
        result["artifacts_path"] = str(result.get("artifacts_path", artifacts_path))
        return result
    except Exception as e:
        logger.error("Get pipeline status failed: %s", e)
        return {
            "error": str(e),
            "artifacts_path": artifacts_path,
            "available_batches": [],
            "scrapers": {},
            "ingestion": {},
        }


@mcp.tool()
async def redis_sre_get_pipeline_batch(
    batch_date: str, artifacts_path: str = "./artifacts"
) -> Dict[str, Any]:
    """Get detailed information for a specific pipeline batch.

    This exposes the batch manifest and any ingestion summary for the target batch.

    Args:
        batch_date: Batch date in YYYY-MM-DD format
        artifacts_path: Artifact root path. Defaults to './artifacts'.

    Returns:
        batch_date: Requested batch date
        total_documents: Number of documents in the batch manifest
        categories: Category counts for the batch
        document_types: Document-type counts for the batch
        ingestion: Ingestion status/details if present
    """
    from redis_sre_agent.core.pipeline_helpers import get_pipeline_batch_helper

    logger.info(
        "MCP get_pipeline_batch: batch_date=%s, artifacts_path=%s",
        batch_date,
        artifacts_path,
    )

    try:
        return await get_pipeline_batch_helper(batch_date=batch_date, artifacts_path=artifacts_path)
    except Exception as e:
        logger.error("Get pipeline batch failed: %s", e)
        return {
            "error": str(e),
            "batch_date": batch_date,
            "artifacts_path": artifacts_path,
        }


@mcp.tool()
async def redis_sre_knowledge_search(
    query: str,
    limit: int = 10,
    offset: int = 0,
    category: Optional[str] = None,
    doc_type: Optional[str] = None,
    version: Optional[str] = "latest",
) -> Dict[str, Any]:
    """Search the Redis SRE knowledge base (returns raw results).

    This is a **direct search** that returns raw knowledge base results immediately.
    Use this when you want to browse documentation or get specific content.

    For questions that need interpretation/reasoning, use `redis_sre_knowledge_query()`
    instead, which creates a task that uses the Knowledge Agent to analyze and answer.

    Args:
        query: Search query (e.g., "redis memory eviction policies"). Wrap exact
            identifiers such as names, document hashes, source filenames, or literal
            phrases in quotes to trigger precise matching plus literal text search
            before semantic results are merged.
        limit: Maximum number of results (1-50, default 10)
        offset: Number of results to skip for pagination (default 0)
        category: Optional filter by category ('incident', 'maintenance', 'monitoring', etc.)
        doc_type: Optional filter by document type
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
        if doc_type:
            kwargs["doc_type"] = doc_type

        result = await search_knowledge_base_helper(**kwargs)

        results = []
        for item in result.get("results", []):
            results.append(
                {
                    "title": item.get("title", "Untitled"),
                    "content": item.get("content", ""),
                    "source": item.get("source"),
                    "category": item.get("category"),
                    "doc_type": item.get("doc_type", "knowledge"),
                    "version": item.get("version", "latest"),
                    "score": item.get("score"),
                }
            )

        return {
            "query": query,
            "version": version,
            "offset": offset,
            "limit": limit,
            "doc_type": doc_type,
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
async def redis_sre_search_support_tickets(
    query: str,
    limit: int = 10,
    offset: int = 0,
    version: Optional[str] = "latest",
    distance_threshold: Optional[float] = 0.8,
) -> Dict[str, Any]:
    """Search support-ticket documents only.

    Uses the dedicated support-ticket index and returns ticket-scoped results.

    Args:
        query: Search query text. Exact ticket IDs such as RET-4421 are matched
            directly before semantic results are merged.
        limit: Maximum results to return (1-50, default 10)
        offset: Number of results to skip for pagination (default 0)
        version: Redis documentation version filter. Defaults to "latest".
        distance_threshold: Optional cosine distance threshold (default: 0.8).
            Set to null to disable threshold and use pure KNN.

    Returns:
        Ticket search results and pagination metadata.
    """
    from redis_sre_agent.core.knowledge_helpers import search_support_tickets_helper

    logger.info(
        "MCP support_ticket_search: %s... (version=%s, offset=%s)",
        query[:100],
        version,
        offset,
    )

    try:
        limit = max(1, min(50, limit))
        offset = max(0, offset)

        result = await search_support_tickets_helper(
            query=query,
            limit=limit,
            offset=offset,
            version=version,
            distance_threshold=distance_threshold,
        )

        return {
            "query": query,
            "version": version,
            "offset": offset,
            "limit": limit,
            "tickets": result.get("tickets", []),
            "results": result.get("results", []),
            "ticket_count": result.get("ticket_count", 0),
            "total_results": result.get("results_count", 0),
            "has_more": len(result.get("results", [])) == limit,
        }

    except Exception as e:
        logger.error(f"Support ticket search failed: {e}")
        return {
            "error": str(e),
            "query": query,
            "tickets": [],
            "results": [],
            "ticket_count": 0,
            "total_results": 0,
        }


@mcp.tool()
async def redis_sre_cache_stats(instance_id: Optional[str] = None) -> Dict[str, Any]:
    """Show tool cache statistics for one instance or all instances."""
    from redis_sre_agent.core.cache_helpers import cache_stats_helper

    logger.info("MCP cache_stats: instance_id=%s", instance_id)

    try:
        return await cache_stats_helper(instance_id=instance_id)
    except Exception as e:
        logger.error("Cache stats failed: %s", e)
        return {
            "error": str(e),
            "status": "failed",
            "instance_id": instance_id,
        }


@mcp.tool()
async def redis_sre_cache_clear(
    instance_id: Optional[str] = None,
    clear_all: bool = False,
    confirm: bool = False,
) -> Dict[str, Any]:
    """Clear cached tool outputs for one instance or all instances."""
    from redis_sre_agent.core.cache_helpers import cache_clear_helper

    logger.info(
        "MCP cache_clear: instance_id=%s clear_all=%s confirm=%s",
        instance_id,
        clear_all,
        confirm,
    )

    try:
        return await cache_clear_helper(
            instance_id=instance_id,
            clear_all=clear_all,
            confirm=confirm,
        )
    except Exception as e:
        logger.error("Cache clear failed: %s", e)
        return {
            "error": str(e),
            "status": "failed",
            "instance_id": instance_id,
        }


@mcp.tool()
def redis_sre_audit_cli_mcp_parity() -> Dict[str, Any]:
    """Audit in-scope CLI leaf commands against MCP tool coverage."""
    from redis_sre_agent.core.cli_mcp_parity import audit_cli_mcp_parity

    logger.info("MCP CLI/MCP parity audit request")

    try:
        return audit_cli_mcp_parity()
    except Exception as e:
        logger.error("CLI/MCP parity audit failed: %s", e)
        return {"error": str(e), "status": "failed"}


@mcp.tool()
def redis_sre_version() -> Dict[str, str]:
    """Show Redis SRE Agent version metadata."""
    from redis_sre_agent.core.cache_helpers import version_helper

    logger.info("MCP version request")
    return version_helper()


@mcp.tool()
async def redis_sre_list_indices(index_name: Optional[str] = None) -> Dict[str, Any]:
    """List known RediSearch indices and their current status."""
    from redis_sre_agent.core.index_helpers import list_indices_helper

    logger.info("MCP list_indices: index_name=%s", index_name)

    try:
        return await list_indices_helper(index_name=index_name)
    except Exception as e:
        logger.error("List indices failed: %s", e)
        return {
            "success": False,
            "status": "failed",
            "error": str(e),
            "index_name": index_name or "all",
        }


@mcp.tool()
async def redis_sre_get_index_schema_status(index_name: Optional[str] = None) -> Dict[str, Any]:
    """Show whether index schemas match the current code definitions."""
    from redis_sre_agent.core.index_helpers import get_index_schema_status_helper

    logger.info("MCP get_index_schema_status: index_name=%s", index_name)

    try:
        return await get_index_schema_status_helper(index_name=index_name)
    except Exception as e:
        logger.error("Get index schema status failed: %s", e)
        return {
            "success": False,
            "status": "failed",
            "error": str(e),
            "index_name": index_name or "all",
        }


@mcp.tool()
async def redis_sre_recreate_indices(
    index_name: Optional[str] = None,
    confirm: bool = False,
) -> Dict[str, Any]:
    """Drop and recreate RediSearch indices after explicit confirmation."""
    from redis_sre_agent.core.index_helpers import recreate_indices_helper

    logger.info("MCP recreate_indices: index_name=%s confirm=%s", index_name, confirm)

    try:
        return await recreate_indices_helper(index_name=index_name, confirm=confirm)
    except Exception as e:
        logger.error("Recreate indices failed: %s", e)
        return {
            "success": False,
            "status": "failed",
            "error": str(e),
            "index_name": index_name or "all",
        }


@mcp.tool()
async def redis_sre_sync_index_schemas(
    index_name: Optional[str] = None,
    confirm: bool = False,
) -> Dict[str, Any]:
    """Create or recreate only drifted indices after explicit confirmation."""
    from redis_sre_agent.core.index_helpers import sync_index_schemas_helper

    logger.info("MCP sync_index_schemas: index_name=%s confirm=%s", index_name, confirm)

    try:
        return await sync_index_schemas_helper(index_name=index_name, confirm=confirm)
    except Exception as e:
        logger.error("Sync index schemas failed: %s", e)
        return {
            "success": False,
            "status": "failed",
            "error": str(e),
            "index_name": index_name or "all",
        }


@mcp.tool()
async def redis_sre_get_support_ticket(ticket_id: str) -> Dict[str, Any]:
    """Retrieve complete support-ticket content by ticket id.

    Args:
        ticket_id: Ticket/document id from redis_sre_search_support_tickets results

    Returns:
        Full ticket content and metadata, or an error payload.
    """
    from redis_sre_agent.core.knowledge_helpers import get_support_ticket_helper

    logger.info("MCP get_support_ticket: %s", ticket_id)

    try:
        result = await get_support_ticket_helper(ticket_id=ticket_id)
        if result.get("error"):
            return {
                "ticket_id": ticket_id,
                "error": result["error"],
                "doc_type": result.get("doc_type"),
            }
        return result
    except Exception as e:
        logger.error(f"Get support ticket failed: {e}")
        return {
            "ticket_id": ticket_id,
            "error": str(e),
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
async def redis_sre_list_threads(
    user_id: Optional[str] = None,
    instance_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    """List conversation threads with optional filtering.

    Use this to find previous conversations with the agent. Each thread represents
    a conversation (triage, chat, or knowledge query) and contains:
    - thread_id: Unique identifier (use with redis_sre_get_thread)
    - subject: A brief description of what the conversation was about
    - created_at/updated_at: Timestamps
    - instance_id: The Redis instance discussed (if any)
    - message_count: Number of messages in the conversation

    ## Filtering

    - **user_id**: Filter by the user who created the thread
    - **instance_id**: Filter by the Redis instance discussed in the thread

    ## Pagination

    Results are sorted by most recently updated first. Use `limit` and `offset`
    for pagination through large result sets.

    ## Example Workflow

    ```
    # List recent threads about a specific instance
    threads = redis_sre_list_threads(instance_id="redis-prod-1", limit=10)

    # Get full details for a specific thread
    thread = redis_sre_get_thread(threads["threads"][0]["thread_id"])
    ```

    Args:
        user_id: Filter by user ID (optional)
        instance_id: Filter by Redis instance ID (optional)
        limit: Maximum number of results (1-100, default 50)
        offset: Number of results to skip for pagination (default 0)

    Returns:
        threads: Array of thread summaries with id, subject, dates, etc.
        total: Number of threads returned
        limit: The limit used
        offset: The offset used
        has_more: Whether there are more results beyond this page
    """
    from redis_sre_agent.core.redis import get_redis_client
    from redis_sre_agent.core.threads import ThreadManager

    logger.info(
        f"MCP list_threads: user_id={user_id}, instance_id={instance_id}, "
        f"limit={limit}, offset={offset}"
    )

    try:
        # Clamp limit to valid range
        limit = max(1, min(100, limit))
        offset = max(0, offset)

        redis_client = get_redis_client()
        tm = ThreadManager(redis_client=redis_client)

        # Get thread summaries from ThreadManager
        summaries = await tm.list_threads(user_id=user_id, limit=limit, offset=offset)

        # Filter by instance_id if specified (done in-memory since ThreadManager
        # doesn't support instance_id filtering directly)
        if instance_id:
            summaries = [s for s in summaries if s.get("instance_id") == instance_id]

        # Enrich with message_count for each thread
        enriched_threads: List[Dict[str, Any]] = []
        for summary in summaries:
            thread_summary = dict(summary)
            try:
                thread = await tm.get_thread(summary.get("thread_id", ""))
                if thread:
                    # Count user/assistant messages
                    user_assistant_msgs = [
                        m for m in thread.messages if m.role in ("user", "assistant")
                    ]
                    thread_summary["message_count"] = len(user_assistant_msgs)

                    # Get latest message preview
                    if user_assistant_msgs:
                        last_msg = user_assistant_msgs[-1]
                        content = last_msg.content or ""
                        thread_summary["latest_message"] = (
                            content[:100] + "..." if len(content) > 100 else content
                        )
                else:
                    thread_summary["message_count"] = 0
            except Exception:
                if "message_count" not in thread_summary:
                    thread_summary["message_count"] = 0
            enriched_threads.append(thread_summary)

        return {
            "threads": enriched_threads,
            "total": len(enriched_threads),
            "limit": limit,
            "offset": offset,
            "has_more": len(summaries) == limit,  # Hint for pagination
        }

    except Exception as e:
        logger.error(f"List threads failed: {e}")
        return {
            "error": str(e),
            "threads": [],
            "total": 0,
            "limit": limit,
            "offset": offset,
        }


@mcp.tool()
async def redis_sre_get_thread_sources(
    thread_id: str,
    task_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Get knowledge fragments recorded for a thread, optionally for one task turn."""
    from redis_sre_agent.core.thread_inspection_helpers import get_thread_sources_helper

    logger.info(f"MCP get_thread_sources: thread_id={thread_id}, task_id={task_id}")

    try:
        return await get_thread_sources_helper(thread_id=thread_id, task_id=task_id)
    except Exception as e:
        logger.error(f"Get thread sources failed: {e}")
        return {
            "error": str(e),
            "thread_id": thread_id,
            "task_id": task_id,
            "fragments": [],
            "count": 0,
        }


@mcp.tool()
async def redis_sre_get_thread_trace(
    message_id: str,
    include_tool_data: bool = False,
) -> Dict[str, Any]:
    """Get the decision trace and derived citations for a single message."""
    from redis_sre_agent.core.thread_inspection_helpers import get_thread_trace_helper

    logger.info(
        f"MCP get_thread_trace: message_id={message_id}, include_tool_data={include_tool_data}"
    )

    try:
        return await get_thread_trace_helper(
            message_id=message_id,
            include_tool_data=include_tool_data,
        )
    except Exception as e:
        logger.error(f"Get thread trace failed: {e}")
        return {
            "error": str(e),
            "message_id": message_id,
            "tool_calls": [],
            "tool_call_count": 0,
            "citations": [],
            "citation_count": 0,
        }


@mcp.tool()
async def redis_sre_get_task(task_id: str) -> Dict[str, Any]:
    """Get a full task payload by task ID."""
    from redis_sre_agent.core.task_inspection_helpers import get_task_helper

    logger.info("MCP get_task: %s", task_id)

    try:
        return await get_task_helper(task_id)
    except ValueError as e:
        return {
            "error": str(e),
            "task_id": task_id,
            "status": "not_found",
        }
    except Exception as e:
        logger.error("Get task failed: %s", e)
        return {
            "error": str(e),
            "task_id": task_id,
        }


@mcp.tool()
async def redis_sre_list_tasks(
    user_id: Optional[str] = None,
    status: Optional[str] = None,
    show_all: bool = False,
    limit: int = 50,
) -> Dict[str, Any]:
    """List recent tasks with optional status filtering."""
    from redis_sre_agent.core.task_inspection_helpers import list_tasks_helper

    logger.info("MCP list_tasks request")

    try:
        return await list_tasks_helper(
            user_id=user_id,
            status=status,
            show_all=show_all,
            limit=limit,
        )
    except ValueError as e:
        return {
            "error": str(e),
            "status": "failed",
            "message": str(e),
        }
    except Exception as e:
        logger.error("List tasks failed: %s", e)
        return {
            "error": str(e),
            "status": "failed",
            "message": f"Failed to list tasks: {e}",
        }


@mcp.tool()
async def redis_sre_purge_tasks(
    status: Optional[str] = None,
    older_than: Optional[str] = None,
    purge_all: bool = False,
    dry_run: bool = False,
    confirm: bool = False,
) -> Dict[str, Any]:
    """Purge tasks in bulk with safeguards and optional dry-run mode."""
    from redis_sre_agent.core.task_purge_helpers import purge_tasks_helper

    logger.info(
        "MCP purge_tasks: status=%s older_than=%s purge_all=%s dry_run=%s confirm=%s",
        status,
        older_than,
        purge_all,
        dry_run,
        confirm,
    )

    try:
        return await purge_tasks_helper(
            status=status,
            older_than=older_than,
            purge_all=purge_all,
            dry_run=dry_run,
            confirm=confirm,
        )
    except Exception as e:
        logger.error("Purge tasks failed: %s", e)
        return {
            "error": str(e),
            "status": "failed",
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
        Use redis_sre_get_task_citations() for tool provenance when needed
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
            "pending_approval": task.get("pending_approval"),
            "resume_supported": task.get("resume_supported", False),
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
async def redis_sre_get_task_approvals(task_id: str) -> Dict[str, Any]:
    """Get approval history for a task.

    Args:
        task_id: Task identifier.

    Returns:
        task_id: Requested task id
        approvals: Approval history in newest-first order
    """
    from redis_sre_agent.core.approvals import ApprovalManager
    from redis_sre_agent.core.tasks import get_task_by_id

    logger.info(f"MCP get_task_approvals: {task_id}")

    try:
        await get_task_by_id(task_id=task_id)
        approvals = await ApprovalManager().list_task_approvals(task_id)
        return {
            "task_id": task_id,
            "approvals": [approval.model_dump(mode="json") for approval in approvals],
        }
    except ValueError as e:
        return {
            "error": str(e),
            "task_id": task_id,
            "status": "not_found",
            "approvals": [],
        }
    except Exception as e:
        logger.error(f"Get task approvals failed: {e}")
        return {
            "error": str(e),
            "task_id": task_id,
            "approvals": [],
        }


@mcp.tool()
async def redis_sre_resume_task(
    task_id: str,
    approval_id: str,
    decision: str,
    decision_by: Optional[str] = None,
    decision_comment: Optional[str] = None,
) -> Dict[str, Any]:
    """Record a human decision and resume a paused task.

    Args:
        task_id: Task identifier
        approval_id: Approval identifier to resolve
        decision: approved or rejected
        decision_by: Optional reviewer identity
        decision_comment: Optional reviewer comment

    Returns:
        task_id: Requested task id
        status: Latest task status after resume attempt
        result: Latest task result payload when available
        pending_approval: Next pending approval if the task paused again
    """
    from redis_sre_agent.core.docket_tasks import (
        get_redis_url,
        resume_task_after_approval,
        validate_task_resume_request,
    )
    from redis_sre_agent.core.tasks import get_task_by_id

    logger.info(f"MCP resume_task: {task_id} approval={approval_id} decision={decision}")

    try:
        task = await get_task_by_id(task_id=task_id)
        if task is None:
            raise ValueError(f"Task {task_id} not found")
        if task.get("status") == "awaiting_approval":
            await validate_task_resume_request(
                task_id=task_id,
                approval_id=approval_id,
                decision=decision,
                decision_by=decision_by,
                decision_comment=decision_comment,
            )
            async with Docket(url=await get_redis_url(), name="sre_docket") as docket:
                task_func = docket.add(resume_task_after_approval, key=task_id)
                await task_func(
                    task_id=task_id,
                    approval_id=approval_id,
                    decision=decision,
                    decision_by=decision_by,
                    decision_comment=decision_comment,
                )
        task = await get_task_by_id(task_id=task_id)
        if task is None:
            raise ValueError(f"Task {task_id} not found")
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
            "pending_approval": task.get("pending_approval"),
            "resume_supported": task.get("resume_supported", False),
            "error_message": task.get("error_message"),
        }
    except ValueError as e:
        return {
            "error": str(e),
            "task_id": task_id,
            "status": "invalid_request",
        }
    except Exception as e:
        logger.error(f"Resume task failed: {e}")
        return {
            "error": str(e),
            "task_id": task_id,
        }


@mcp.tool()
async def redis_sre_get_task_citations(task_id: str) -> Dict[str, Any]:
    """Get citation and tool-call data for a completed task.

    Use this when you need provenance details without inflating the normal
    task-status payload returned by redis_sre_get_task_status().

    Args:
        task_id: The task_id returned from triage or chat tools

    Returns:
        task_id: The requested task id
        thread_id: Thread associated with the task
        status: Current task status
        citation_count: Number of tool-call envelopes available
        tool_calls: Raw tool-call envelopes for citation/provenance use
    """
    from redis_sre_agent.core.tasks import get_task_by_id

    logger.info(f"MCP get_task_citations: {task_id}")

    try:
        task = await get_task_by_id(task_id=task_id)
        tool_calls = task.get("tool_calls") or []

        return {
            "task_id": task_id,
            "thread_id": task.get("thread_id"),
            "status": task.get("status"),
            "citation_count": len(tool_calls),
            "tool_calls": tool_calls,
        }

    except ValueError as e:
        return {
            "error": str(e),
            "task_id": task_id,
            "status": "not_found",
        }
    except Exception as e:
        logger.error(f"Get task citations failed: {e}")
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
async def redis_sre_get_instance(instance_id: str) -> Dict[str, Any]:
    """Get a configured Redis instance by ID."""
    from redis_sre_agent.core.instance_inspection_helpers import get_instance_helper

    logger.info("MCP get_instance: %s", instance_id)

    try:
        return await get_instance_helper(instance_id)
    except Exception as e:
        logger.error("Get instance failed: %s", e)
        return {
            "error": str(e),
            "id": instance_id,
        }


@mcp.tool()
async def redis_sre_test_redis_url(connection_url: str) -> Dict[str, Any]:
    """Test a Redis connection URL without creating an instance."""
    from redis_sre_agent.core.instance_inspection_helpers import (
        check_redis_url_helper,
    )
    from redis_sre_agent.core.instances import mask_redis_url

    logger.info("MCP test_redis_url request")

    try:
        return await check_redis_url_helper(connection_url)
    except Exception as e:
        logger.error("Test redis url failed: %s", e)
        return {
            "success": False,
            "error": str(e),
            "url": mask_redis_url(connection_url),
        }


@mcp.tool()
async def redis_sre_test_instance(instance_id: str) -> Dict[str, Any]:
    """Test connection to a configured Redis instance by ID."""
    from redis_sre_agent.core.instance_inspection_helpers import check_instance_helper

    logger.info("MCP test_instance: %s", instance_id)

    try:
        return await check_instance_helper(instance_id)
    except Exception as e:
        logger.error("Test instance failed: %s", e)
        return {
            "success": False,
            "error": str(e),
            "id": instance_id,
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

        instance_id = f"redis-{environment.lower()}-{ULID()}"
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


@mcp.tool()
async def redis_sre_update_instance(
    instance_id: str,
    name: Optional[str] = None,
    connection_url: Optional[str] = None,
    environment: Optional[str] = None,
    usage: Optional[str] = None,
    description: Optional[str] = None,
    repo_url: Optional[str] = None,
    notes: Optional[str] = None,
    monitoring_identifier: Optional[str] = None,
    logging_identifier: Optional[str] = None,
    instance_type: Optional[str] = None,
    admin_url: Optional[str] = None,
    admin_username: Optional[str] = None,
    admin_password: Optional[str] = None,
    cluster_id: Optional[str] = None,
    redis_cloud_subscription_id: Optional[int] = None,
    redis_cloud_database_id: Optional[int] = None,
    redis_cloud_subscription_type: Optional[str] = None,
    redis_cloud_database_name: Optional[str] = None,
    status: Optional[str] = None,
    version: Optional[str] = None,
    memory: Optional[str] = None,
    connections: Optional[int] = None,
    user_id: Optional[str] = None,
    set_extensions: Optional[Dict[str, Any]] = None,
    unset_extensions: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Update an existing Redis instance configuration."""
    from redis_sre_agent.core.instance_mutation_helpers import update_instance_helper

    logger.info("MCP update_instance: %s", instance_id)

    try:
        return await update_instance_helper(
            instance_id,
            name=name,
            connection_url=connection_url,
            environment=environment,
            usage=usage,
            description=description,
            repo_url=repo_url,
            notes=notes,
            monitoring_identifier=monitoring_identifier,
            logging_identifier=logging_identifier,
            instance_type=instance_type,
            admin_url=admin_url,
            admin_username=admin_username,
            admin_password=admin_password,
            cluster_id=cluster_id,
            redis_cloud_subscription_id=redis_cloud_subscription_id,
            redis_cloud_database_id=redis_cloud_database_id,
            redis_cloud_subscription_type=redis_cloud_subscription_type,
            redis_cloud_database_name=redis_cloud_database_name,
            status=status,
            version=version,
            memory=memory,
            connections=connections,
            user_id=user_id,
            set_extensions=set_extensions,
            unset_extensions=unset_extensions,
        )
    except Exception as e:
        logger.error("Update instance failed: %s", e)
        return {
            "error": str(e),
            "id": instance_id,
            "status": "failed",
        }


@mcp.tool()
async def redis_sre_delete_instance(instance_id: str, confirm: bool = False) -> Dict[str, Any]:
    """Delete a Redis instance configuration."""
    from redis_sre_agent.core.instance_mutation_helpers import delete_instance_helper

    logger.info("MCP delete_instance: %s", instance_id)

    try:
        return await delete_instance_helper(instance_id, confirm=confirm)
    except Exception as e:
        logger.error("Delete instance failed: %s", e)
        return {
            "error": str(e),
            "id": instance_id,
            "status": "failed",
        }


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
