"""CLI interface for Redis SRE Agent."""

import asyncio

import click

from .pipeline import pipeline
from .runbook import runbook


@click.group()
def main():
    """Redis SRE Agent CLI."""
    pass


# Add commands
main.add_command(pipeline)
main.add_command(runbook)


@main.command()
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
                contextualized_query, session_id="cli", user_id="cli_user"
            )
            click.echo(f"\n✅ Response:\n{response}")
        except Exception as e:
            click.echo(f"❌ Error: {e}")

    asyncio.run(_query())


@main.command()
@click.argument("query")
@click.option("--limit", "-l", default=5, help="Number of results to return")
@click.option("--category", "-c", help="Filter by category")
def search(query: str, limit: int, category: str):
    """Search the knowledge base directly."""

    async def _search():
        from redis_sre_agent.tools.sre_functions import search_knowledge_base

        click.echo(f"🔍 Searching knowledge base for: {query}")
        if category:
            click.echo(f"📂 Category filter: {category}")

        try:
            result = await search_knowledge_base(query, category=category, limit=limit)

            # The function returns a formatted string now
            if isinstance(result, str):
                click.echo("\n" + result)
            else:
                # Fallback for dict format
                results = result.get("results", [])
                if results:
                    click.echo(f"\n✅ Found {len(results)} results:")
                    for i, doc in enumerate(results, 1):
                        click.echo(f"\n--- Result {i} ---")
                        click.echo(f"Title: {doc.get('title', 'Unknown')}")
                        click.echo(f"Source: {doc.get('source', 'Unknown')}")
                        click.echo(f"Category: {doc.get('category', 'general')}")
                        content = doc.get("content", "")
                        if len(content) > 200:
                            content = content[:200] + "..."
                        click.echo(f"Content: {content}")
                else:
                    click.echo("❌ No results found")

        except Exception as e:
            click.echo(f"❌ Search error: {e}")

    asyncio.run(_search())


@main.command()
@click.option(
    "--redis-url", "-r", help="Redis URL to check status for (e.g., redis://localhost:6379)"
)
def status(redis_url: str):
    """Show system status."""

    async def _status():
        from redis_sre_agent.tools.sre_functions import check_service_health

        if not redis_url:
            click.echo("❌ Error: --redis-url is required for status checks")
            return

        click.echo(f"🔍 Checking status for Redis: {redis_url}")

        try:
            result = await check_service_health("redis", redis_url=redis_url)
            status_str = result.get("overall_status", "unknown")

            if status_str == "healthy":
                click.echo("✅ System Status: HEALTHY")
            elif status_str == "warning":
                click.echo("⚠️  System Status: WARNING")
            elif status_str == "critical":
                click.echo("❌ System Status: CRITICAL")
            else:
                click.echo(f"❓ System Status: {status_str.upper()}")

            # Show Redis diagnostics if available
            redis_diag = result.get("redis_diagnostics")
            if redis_diag and "diagnostics" in redis_diag:
                memory = redis_diag["diagnostics"].get("memory", {})
                if "used_memory_human" in memory:
                    click.echo(f"   Memory: {memory['used_memory_human']}")

                info = redis_diag["diagnostics"].get("info", {})
                if "connected_clients" in info:
                    click.echo(f"   Clients: {info['connected_clients']}")

                # Show specific health issues
                if status_str not in ["healthy"]:
                    click.echo("\n📋 Health Issues:")

                    # Memory issues
                    memory_issues = memory.get("issues", [])
                    if memory_issues:
                        for issue in memory_issues:
                            click.echo(f"   ⚠️  {issue}")

                    # Check for any diagnostic errors
                    for section_name, section_data in redis_diag["diagnostics"].items():
                        if isinstance(section_data, dict) and "error" in section_data:
                            click.echo(
                                f"   ❌ {section_name.title()} diagnostic failed: {section_data['error']}"
                            )

                    # Show fragmentation if high
                    if memory.get("mem_fragmentation_ratio", 1.0) > 1.5:
                        ratio = memory.get("mem_fragmentation_ratio", 1.0)
                        click.echo(f"   ⚠️  High memory fragmentation: {ratio:.2f}")

                    # Show maxmemory info if relevant
                    if (
                        memory.get("maxmemory", 0) == 0
                        and memory.get("used_memory", 0) > 1024 * 1024 * 1024
                    ):
                        click.echo("   ⚠️  No memory limit set with high usage")

        except Exception as e:
            click.echo(f"❌ Status check failed: {e}")

    asyncio.run(_status())


@main.command()
def worker():
    """Start the background worker."""
    click.echo("🚧 Worker startup functionality coming soon...")


if __name__ == "__main__":
    main()
