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
from redis_sre_agent.core.config import settings
from redis_sre_agent.core.instances import get_instance_by_id
from redis_sre_agent.core.redis import get_redis_client
from redis_sre_agent.core.threads import ThreadManager

logger = logging.getLogger(__name__)


@click.command()
@click.argument("query")
@click.option("--redis-instance-id", "-r", help="Redis instance ID to investigate")
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
    support_package_id: Optional[str],
    thread_id: Optional[str],
    agent: str,
):
    """Execute an agent query.

    Supports conversation threads for multi-turn interactions. Use --thread-id
    to continue an existing conversation, or omit it to start a new one.

    \b
    The agent is automatically selected based on the query, or use --agent:
      - knowledge: General Redis questions (no instance needed)
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

        # Resolve instance if provided
        instance = None
        if redis_instance_id:
            instance = await get_instance_by_id(redis_instance_id)
            if not instance:
                console.print(f"[red]❌ Instance not found: {redis_instance_id}[/red]")
                exit(1)

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

        else:
            # Create new thread
            initial_context = {}
            if instance:
                initial_context["instance_id"] = instance.id
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
            if support_package_path:
                context["support_package_path"] = str(support_package_path)

            # Run the agent
            response = await selected_agent.process_query(
                query,
                session_id="cli",
                user_id="cli_user",
                max_iterations=settings.max_iterations,
                context=context if context else None,
                conversation_history=conversation_history if conversation_history else None,
            )

            # Save messages to thread
            await thread_manager.append_messages(
                active_thread_id,
                [
                    {"role": "user", "content": query},
                    {"role": "assistant", "content": str(response)},
                ],
            )

            console.print("\n[bold green]✅ Response:[/bold green]\n")
            console.print(Markdown(str(response)))

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
        loop.close()
