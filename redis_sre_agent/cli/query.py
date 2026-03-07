"""Top-level `query` CLI command."""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

import click
from langchain_core.messages import AIMessage, HumanMessage
from rich.console import Console
from rich.markdown import Markdown

from redis_sre_agent.agent.chat_agent import get_chat_agent
from redis_sre_agent.agent.knowledge_agent import get_knowledge_agent
from redis_sre_agent.agent.langgraph_agent import get_sre_agent
from redis_sre_agent.agent.router import AgentType, route_to_appropriate_agent
from redis_sre_agent.core.citation_message import (
    format_citation_message,
    should_include_citations,
)
from redis_sre_agent.core.clusters import get_cluster_by_id
from redis_sre_agent.core.config import settings
from redis_sre_agent.core.instances import (
    get_instance_by_id,
    get_preferred_instance_by_cluster_id,
)
from redis_sre_agent.core.redis import get_redis_client
from redis_sre_agent.core.target_context import (
    TurnTarget,
    extract_turn_target,
    require_at_most_one_target,
    require_continuation_target_compatibility,
)
from redis_sre_agent.core.threads import ThreadManager

logger = logging.getLogger(__name__)


@click.command()
@click.argument("query")
@click.option("--redis-instance-id", "-r", help="Redis instance ID to investigate")
@click.option("--redis-cluster-id", "-c", help="Redis cluster ID to investigate")
@click.option("--support-package-id", "-p", help="Support package ID to analyze")
@click.option("--thread-id", "-t", help="Thread ID to continue an existing conversation")
@click.option(
    "--agent",
    "-a",
    type=click.Choice(["auto", "triage", "chat", "knowledge"], case_sensitive=False),
    default="auto",
    help="Agent to use (default: auto-select based on query)",
)
def query(
    query: str,
    redis_instance_id: Optional[str],
    redis_cluster_id: Optional[str],
    support_package_id: Optional[str],
    thread_id: Optional[str],
    agent: str,
):
    """Execute an agent query.

    Supports conversation threads for multi-turn interactions. Use --thread-id
    to continue an existing conversation, or omit it to start a new one.

    \b
    The agent is automatically selected based on the query, or use --agent:
      - knowledge: General Redis questions (target-scoped thread)
      - chat: Quick questions with a Redis instance
      - triage: Full health checks and diagnostics
      - auto: Let the router decide (default)
    """

    async def _query():
        from redis_sre_agent.cli.support_package import get_manager as get_support_package_manager
        from redis_sre_agent.tools.mcp.pool import MCPConnectionPool

        console = Console()
        redis_client = get_redis_client()
        thread_manager = ThreadManager(redis_client=redis_client)

        # Start MCP connection pool (keeps connections warm)
        mcp_pool = MCPConnectionPool.get_instance()
        await mcp_pool.start()

        provided_instance_id = redis_instance_id.strip() if redis_instance_id else None
        provided_cluster_id = redis_cluster_id.strip() if redis_cluster_id else None
        provided_target = TurnTarget(
            instance_id=provided_instance_id,
            cluster_id=provided_cluster_id,
        )
        try:
            require_at_most_one_target(provided_target)
        except ValueError as e:
            console.print(f"[red]❌ {e}[/red]")
            exit(1)

        # Resolve instance/cluster if provided
        instance = None
        active_cluster_id = provided_cluster_id
        if provided_instance_id:
            instance = await get_instance_by_id(provided_instance_id)
            if not instance:
                console.print(f"[red]❌ Instance not found: {provided_instance_id}[/red]")
                exit(1)
            if not active_cluster_id:
                active_cluster_id = instance.cluster_id

        elif active_cluster_id:
            cluster = await get_cluster_by_id(active_cluster_id)
            if not cluster:
                console.print(f"[red]❌ Cluster not found: {active_cluster_id}[/red]")
                exit(1)

            instance = await get_preferred_instance_by_cluster_id(active_cluster_id)
            console.print(f"[dim] Redis cluster: {cluster.name}[/dim]")
            if not instance:
                console.print(
                    "[dim] No linked Redis instance found for this cluster; "
                    "continuing with cluster context only.[/dim]"
                )

        # Resolve support package if provided
        support_package_path = None
        if support_package_id:
            manager = get_support_package_manager()
            metadata = await manager.get_metadata(support_package_id)
            if not metadata:
                console.print(f"[red]❌ Support package not found: {support_package_id}[/red]")
                exit(1)
            # Extract if needed and get path
            support_package_path = await manager.extract(support_package_id)
            console.print(f"[dim]📦 Support package: {metadata.filename}[/dim]")

        # Get or create thread
        active_thread_id = thread_id
        conversation_history = []

        if thread_id:
            # Continue existing thread
            thread = await thread_manager.get_thread(thread_id)
            if not thread:
                console.print(f"[red]❌ Thread not found: {thread_id}[/red]")
                exit(1)

            console.print(f"[dim]📎 Continuing thread: {thread_id}[/dim]")

            thread_target = extract_turn_target(thread.context)
            thread_instance_id = thread_target.instance_id
            thread_cluster_id = thread_target.cluster_id
            try:
                is_initial_turn = len(thread.messages or []) == 0
                if not (is_initial_turn and not thread_target.has_any()):
                    await require_continuation_target_compatibility(
                        provided_target=provided_target,
                        thread_target=thread_target,
                        get_instance_by_id=get_instance_by_id,
                    )
            except ValueError as e:
                console.print(f"[red]❌ {e}[/red]")
                exit(1)

            # For compatible continuation aliases, keep execution pinned to
            # the saved thread target whenever thread instance_id exists.
            if provided_target.has_any():
                if thread_instance_id:
                    if not instance or instance.id != thread_instance_id:
                        instance = await get_instance_by_id(thread_instance_id)
                        if not instance:
                            console.print(
                                "[red]❌ Thread target is locked to an instance that no longer "
                                f"exists: {thread_instance_id}[/red]"
                            )
                            exit(1)
                    active_cluster_id = (
                        thread_cluster_id or instance.cluster_id or active_cluster_id
                    )
                elif thread_cluster_id:
                    active_cluster_id = thread_cluster_id
                    if provided_instance_id and (
                        not instance or instance.id != provided_instance_id
                    ):
                        instance = await get_instance_by_id(provided_instance_id)
                        if not instance:
                            console.print(
                                f"[red]❌ Instance not found: {provided_instance_id}[/red]"
                            )
                            exit(1)

            # Load conversation history
            for msg in thread.messages:
                if msg.role == "user":
                    conversation_history.append(HumanMessage(content=msg.content))
                elif msg.role == "assistant":
                    conversation_history.append(AIMessage(content=msg.content))

            # Use instance from thread context if not provided
            if not instance and thread.context.get("instance_id"):
                instance = await get_instance_by_id(thread.context["instance_id"])
                if instance:
                    console.print(f"[dim]🔗 Using instance from thread: {instance.name}[/dim]")
                    active_cluster_id = active_cluster_id or instance.cluster_id

            if not instance and not active_cluster_id and thread.context.get("cluster_id"):
                active_cluster_id = thread.context["cluster_id"]
                instance = await get_preferred_instance_by_cluster_id(active_cluster_id)
                if instance:
                    console.print(
                        f"[dim]🔗 Using instance from thread cluster: {instance.name}[/dim]"
                    )

        else:
            # Create new thread
            initial_context = {}
            if instance:
                initial_context["instance_id"] = instance.id
            if active_cluster_id:
                initial_context["cluster_id"] = active_cluster_id
            if support_package_id:
                initial_context["support_package_id"] = support_package_id
                initial_context["support_package_path"] = str(support_package_path)

            active_thread_id = await thread_manager.create_thread(
                user_id="cli_user",
                session_id="cli",
                initial_context=initial_context,
                tags=["cli"],
            )
            await thread_manager.update_thread_subject(active_thread_id, query)
            console.print(f"[dim]📎 Created thread: {active_thread_id}[/dim]")

        console.print(f"[bold]🔍 Query:[/bold] {query}")

        if instance:
            console.print(f"[dim]🔗 Redis instance: {instance.name}[/dim]")

        # Build context for routing
        routing_context = {}
        if instance:
            routing_context["instance_id"] = instance.id
        if active_cluster_id:
            routing_context["cluster_id"] = active_cluster_id
        if support_package_path:
            routing_context["support_package_path"] = str(support_package_path)

        # Map CLI agent choice to AgentType
        agent_choice_map = {
            "triage": AgentType.REDIS_TRIAGE,
            "chat": AgentType.REDIS_CHAT,
            "knowledge": AgentType.KNOWLEDGE_ONLY,
        }

        # Determine which agent to use
        if agent != "auto":
            agent_type = agent_choice_map[agent.lower()]
            agent_label = agent.capitalize()
            console.print(f"[dim]🔧 Agent: {agent_label} (selected)[/dim]")
        else:
            agent_type = await route_to_appropriate_agent(
                query=query,
                context=routing_context,
                conversation_history=conversation_history if conversation_history else None,
            )
            agent_label = {
                AgentType.REDIS_TRIAGE: "Triage",
                AgentType.REDIS_CHAT: "Chat",
                AgentType.KNOWLEDGE_ONLY: "Knowledge",
            }.get(agent_type, agent_type.value)
            console.print(f"[dim]🔧 Agent: {agent_label}[/dim]")

        # Get the appropriate agent instance
        if agent_type == AgentType.REDIS_TRIAGE:
            selected_agent = get_sre_agent()
        elif agent_type == AgentType.REDIS_CHAT:
            selected_agent = get_chat_agent(redis_instance=instance)
        else:
            selected_agent = get_knowledge_agent()

        try:
            # Build context with instance and/or support package
            context = {}
            if instance:
                context["instance_id"] = instance.id
            if active_cluster_id:
                context["cluster_id"] = active_cluster_id
            if support_package_path:
                context["support_package_path"] = str(support_package_path)

            # Run the agent
            agent_response = await selected_agent.process_query(
                query,
                session_id="cli",
                user_id="cli_user",
                max_iterations=settings.max_iterations,
                context=context if context else None,
                conversation_history=conversation_history if conversation_history else None,
            )

            # Extract response text and search results from AgentResponse
            response_text = agent_response.response
            search_results = agent_response.search_results

            # Generate message_id for the assistant response (for decision trace)
            from ulid import ULID

            assistant_message_id = str(ULID())

            # Store decision trace if there are tool envelopes
            if agent_response.tool_envelopes:
                await thread_manager.set_message_trace(
                    message_id=assistant_message_id,
                    tool_envelopes=agent_response.tool_envelopes,
                )
                console.print(f"[dim]📋 Decision trace: {assistant_message_id}[/dim]")

            # Build messages list with message_id in metadata
            messages_to_save = [
                {"role": "user", "content": query},
                {
                    "role": "assistant",
                    "content": response_text,
                    "metadata": {"message_id": assistant_message_id},
                },
            ]

            # Add citation system message if there are search results
            if should_include_citations(search_results):
                citation_msg = format_citation_message(search_results)
                messages_to_save.append({"role": "system", "content": citation_msg})

            # Save messages to thread
            await thread_manager.append_messages(active_thread_id, messages_to_save)

            console.print("\n[bold green]✅ Response:[/bold green]\n")
            console.print(Markdown(response_text))

            # Show thread ID for follow-up queries
            console.print("\n[dim]💡 To continue this conversation:[/dim]")
            console.print(
                f'[dim]   redis-sre-agent query --thread-id {active_thread_id} "your follow-up"[/dim]'
            )

        except Exception as e:
            console.print(f"[red]❌ Error: {e}[/red]")
            exit(1)
        finally:
            # Force-close MCP pool to avoid cross-task cleanup errors on exit
            await mcp_pool.shutdown(force=True)

    def _suppress_shutdown_errors(loop: asyncio.AbstractEventLoop, context: dict) -> None:
        """Custom exception handler to suppress expected shutdown errors.

        The MCP SDK uses anyio/asyncio async generators which can raise
        RuntimeError("Attempted to exit cancel scope in a different task")
        during process shutdown. This is cosmetic and doesn't affect functionality.
        """
        exception = context.get("exception")

        # Suppress known MCP shutdown errors
        if isinstance(exception, RuntimeError):
            err_msg = str(exception)
            if "different task" in err_msg or "cancel scope" in err_msg:
                logger.debug(f"Suppressed expected shutdown error: {err_msg}")
                return

        # Also suppress CancelledError during shutdown
        if isinstance(exception, asyncio.CancelledError):
            logger.debug("Suppressed CancelledError during shutdown")
            return

        # For other errors, use the default handler
        loop.default_exception_handler(context)

    # Install custom exception handler and run
    loop = asyncio.new_event_loop()
    loop.set_exception_handler(_suppress_shutdown_errors)
    try:
        loop.run_until_complete(_query())
    finally:
        # Cancel all pending tasks to avoid "Task was destroyed but it is pending" errors
        # This is needed because MCP client uses async generators that may not complete cleanly
        pending = asyncio.all_tasks(loop)
        for task in pending:
            task.cancel()
        # Wait for all tasks to complete their cancellation
        if pending:
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        loop.close()
