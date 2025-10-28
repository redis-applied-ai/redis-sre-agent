"""Top-level `query` CLI command.

Extracted from main.py to modularize CLI.
"""

from __future__ import annotations

import asyncio

import click

from redis_sre_agent.core.config import settings


@click.command()
@click.argument("query")
@click.option("--redis-url", "-r", help="Redis URL to investigate (e.g., redis://localhost:6379)")
def query(query: str, redis_url: str):
    """Execute an agent query."""

    async def _query():
        from redis_sre_agent.agent.langgraph_agent import get_sre_agent

        click.echo(f"🔍 Query: {query}")
        if redis_url:
            click.echo(f"🔗 Redis URL: {redis_url}")

        agent = get_sre_agent()

        # Add Redis URL context to the query if provided
        contextualized_query = query
        if redis_url:
            contextualized_query = f"Please investigate this Redis instance: {redis_url}. {query}"

        try:
            response = await agent.process_query(
                contextualized_query,
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
