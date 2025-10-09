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
        from redis_sre_agent.core.tasks import search_knowledge_base

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
        from redis_sre_agent.core.tasks import check_service_health

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


@main.group()
def knowledge():
    """Knowledge base management commands."""
    pass


@knowledge.command()
@click.option("--artifacts-path", default="./artifacts", help="Path to store artifacts")
@click.option(
    "--scrapers",
    default="redis_kb",
    help="Comma-separated list of scrapers to run (redis_docs,redis_runbooks,redis_kb,runbook_generator)",
)
def scrape(artifacts_path: str, scrapers: str):
    """Scrape knowledge sources and store artifacts."""
    click.echo("🔍 Starting knowledge scraping...")

    scraper_list = [s.strip() for s in scrapers.split(",")]

    async def run_scraping():
        from ..pipelines.orchestrator import PipelineOrchestrator

        orchestrator = PipelineOrchestrator(artifacts_path)
        try:
            results = await orchestrator.run_scraping_pipeline(scraper_list)

            click.echo("✅ Scraping completed!")
            click.echo(f"   Batch date: {results['batch_date']}")
            click.echo(f"   Total documents: {results['total_documents']}")
            click.echo(f"   Scrapers run: {', '.join(results['scrapers_run'])}")

            # Show scraper results
            for scraper_name, scraper_result in results["scraper_results"].items():
                if "error" in scraper_result:
                    click.echo(f"   ❌ {scraper_name}: {scraper_result['error']}")
                else:
                    click.echo(
                        f"   ✅ {scraper_name}: {scraper_result['documents_scraped']} documents"
                    )

        except Exception as e:
            click.echo(f"❌ Scraping failed: {e}")

    asyncio.run(run_scraping())


@knowledge.command()
@click.option("--artifacts-path", default="./artifacts", help="Path to artifacts directory")
@click.option("--batch-date", help="Batch date (YYYY-MM-DD), defaults to today")
def ingest(artifacts_path: str, batch_date: str):
    """Ingest scraped artifacts into the knowledge base."""
    click.echo("📥 Starting knowledge ingestion...")

    async def run_ingestion():
        from ..pipelines.orchestrator import PipelineOrchestrator

        orchestrator = PipelineOrchestrator(artifacts_path)
        try:
            results = await orchestrator.run_ingestion_pipeline(batch_date)

            click.echo("✅ Ingestion completed!")
            click.echo(f"   Batch date: {results['batch_date']}")
            click.echo(f"   Documents processed: {results['documents_processed']}")
            click.echo(f"   Documents indexed: {results['documents_indexed']}")

        except Exception as e:
            click.echo(f"❌ Ingestion failed: {e}")

    asyncio.run(run_ingestion())


@knowledge.command()
@click.option("--artifacts-path", default="./artifacts", help="Path to store artifacts")
@click.option(
    "--scrapers",
    default="redis_kb",
    help="Comma-separated list of scrapers to run (redis_docs,redis_runbooks,redis_kb,runbook_generator)",
)
def update(artifacts_path: str, scrapers: str):
    """Run full knowledge update pipeline (scrape + ingest)."""
    click.echo("🔄 Starting full knowledge update...")

    scraper_list = [s.strip() for s in scrapers.split(",")]

    async def run_full_pipeline():
        from ..pipelines.orchestrator import PipelineOrchestrator

        orchestrator = PipelineOrchestrator(artifacts_path)
        try:
            results = await orchestrator.run_full_pipeline(scraper_list)

            click.echo("✅ Full pipeline completed!")
            click.echo(f"   Batch date: {results['batch_date']}")
            click.echo(f"   Total documents scraped: {results['scraping']['total_documents']}")
            click.echo(f"   Documents indexed: {results['ingestion']['chunks_indexed']}")

            # Show scraper results
            for scraper_name, scraper_result in results["scraping"]["scraper_results"].items():
                if "error" in scraper_result:
                    click.echo(f"   ❌ {scraper_name}: {scraper_result['error']}")
                else:
                    click.echo(
                        f"   ✅ {scraper_name}: {scraper_result['documents_scraped']} documents"
                    )

        except Exception as e:
            click.echo(f"❌ Pipeline failed: {e}")

    asyncio.run(run_full_pipeline())


if __name__ == "__main__":
    main()
