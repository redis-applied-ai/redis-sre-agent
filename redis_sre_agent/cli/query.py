"""Top-level `query` CLI command."""

from __future__ import annotations

import asyncio
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


@click.command()
@click.argument("query")
@click.option("--redis-instance-id", "-r", help="Redis instance ID to investigate")
@click.option("--thread-id", "-t", help="Thread ID to continue an existing conversation")
@click.option("--triage", is_flag=True, help="Force full triage agent (bypasses routing)")
def query(query: str, redis_instance_id: Optional[str], thread_id: Optional[str], triage: bool):
    """Execute an agent query.

    Supports conversation threads for multi-turn interactions. Use --thread-id
    to continue an existing conversation, or omit it to start a new one.

    The agent is automatically selected based on the query:
    - Knowledge agent: General Redis questions (no instance)
    - Chat agent: Quick questions with a Redis instance
    - Triage agent: Full health checks or --triage flag
    """

    async def _query():
        console = Console()
        redis_client = get_redis_client()
        thread_manager = ThreadManager(redis_client=redis_client)

        # Resolve instance if provided
        instance = None
        if redis_instance_id:
            instance = await get_instance_by_id(redis_instance_id)
            if not instance:
                console.print(f"[red]❌ Instance not found: {redis_instance_id}[/red]")
                exit(1)

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
        routing_context = {"instance_id": instance.id} if instance else None

        # Determine which agent to use
        if triage:
            agent_type = AgentType.REDIS_TRIAGE
            console.print("[dim]🔧 Agent: Triage (forced)[/dim]")
        else:
            agent_type = await route_to_appropriate_agent(
                query=query,
                context=routing_context,
            )
            agent_label = {
                AgentType.REDIS_TRIAGE: "Triage",
                AgentType.REDIS_CHAT: "Chat",
                AgentType.KNOWLEDGE_ONLY: "Knowledge",
            }.get(agent_type, agent_type.value)
            console.print(f"[dim]🔧 Agent: {agent_label}[/dim]")

        # Get the appropriate agent
        if agent_type == AgentType.REDIS_TRIAGE:
            agent = get_sre_agent()
        elif agent_type == AgentType.REDIS_CHAT:
            agent = get_chat_agent(redis_instance=instance)
        else:
            agent = get_knowledge_agent()

        try:
            context = {"instance_id": instance.id} if instance else None

            # Run the agent
            response = await agent.process_query(
                query,
                session_id="cli",
                user_id="cli_user",
                max_iterations=settings.max_iterations,
                context=context,
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

    asyncio.run(_query())
