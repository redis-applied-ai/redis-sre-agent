"""CLI interface for Redis SRE Agent."""

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
async def query(query: str):
    """Execute an agent query."""
    click.echo(f"Query: {query}")
    click.echo("🚧 Agent query functionality coming soon...")


@main.command()
async def status():
    """Show system status."""
    click.echo("🚧 System status functionality coming soon...")


@main.command()
async def worker():
    """Start the background worker."""
    click.echo("🚧 Worker startup functionality coming soon...")


if __name__ == "__main__":
    main()
