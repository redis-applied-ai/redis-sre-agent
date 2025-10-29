"""Top-level `query` CLI command.

Extracted from main.py to modularize CLI.
"""

from __future__ import annotations

import asyncio

import click

from redis_sre_agent.agent.knowledge_agent import get_knowledge_agent
from redis_sre_agent.agent.langgraph_agent import get_sre_agent
from redis_sre_agent.core.config import settings
from redis_sre_agent.core.instances import get_instance_by_id


@click.command()
@click.argument("query")
@click.option("--redis-instance", "-r", help="Redis instance ID to investigate")
def query(query: str, redis_instance_id: str):
    """Execute an agent query."""

    async def _query():
        if redis_instance_id:
            instance = await get_instance_by_id(redis_instance_id)
        else:
            instance = None

        click.echo(f"🔍 Query: {query}")

        if instance:
            click.echo(f"🔗 Redis instance: {instance.name}")
            agent = get_sre_agent()
        else:
            agent = get_knowledge_agent()

        try:
            response = await agent.process_query(
                query,
                session_id="cli",
                user_id="cli_user",
                max_iterations=settings.max_iterations,
            )

            from rich.console import Console
            from rich.markdown import Markdown

            console = Console()
            console.print("\n✅ Response:\n")
            console.print(Markdown(str(response)))
        except Exception as e:
            click.echo(f"❌ Error: {e}")

    asyncio.run(_query())
