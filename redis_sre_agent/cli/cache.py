"""Cache CLI commands for managing tool output cache."""

from __future__ import annotations

import asyncio
import json as _json
from typing import Optional

import click
from rich.console import Console
from rich.table import Table

from redis_sre_agent.core.redis import get_redis_client
from redis_sre_agent.tools.cache import ToolCache


def get_tool_cache(instance_id: Optional[str] = None) -> ToolCache:
    """Get a ToolCache instance for CLI operations."""
    redis_client = get_redis_client()
    return ToolCache(
        redis_client=redis_client,
        instance_id=instance_id or "__all__",
    )


@click.group()
def cache():
    """Manage tool output cache."""
    pass


@cache.command("clear")
@click.option("--instance", "-i", "instance_id", help="Redis instance ID to clear cache for")
@click.option("--all", "clear_all", is_flag=True, help="Clear cache for all instances")
def cache_clear(instance_id: Optional[str], clear_all: bool):
    """Clear cached tool outputs.

    Use --instance to clear cache for a specific Redis instance,
    or --all to clear cache across all instances.
    """
    async def _clear():
        console = Console()

        if not instance_id and not clear_all:
            console.print("[red]Error: Must specify --instance or --all[/red]")
            raise SystemExit(1)

        if clear_all:
            tool_cache = get_tool_cache("__all__")
            deleted = await tool_cache.clear_all()
            console.print(f"[green]✓ Cleared {deleted} cached keys across all instances[/green]")
        else:
            tool_cache = get_tool_cache(instance_id)
            deleted = await tool_cache.clear()
            console.print(f"[green]✓ Cleared {deleted} cached keys for instance {instance_id}[/green]")

    asyncio.run(_clear())


@cache.command("stats")
@click.option("--instance", "-i", "instance_id", help="Redis instance ID to get stats for")
@click.option("--all", "show_all", is_flag=True, help="Show stats across all instances")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def cache_stats(instance_id: Optional[str], show_all: bool, as_json: bool):
    """Show cache statistics.

    Use --instance to get stats for a specific Redis instance,
    or --all to get aggregate stats across all instances.
    """
    async def _stats():
        console = Console()
        tool_cache = get_tool_cache(instance_id if instance_id else "__all__")

        if show_all:
            stats = await tool_cache.stats_all()

            if as_json:
                console.print(_json.dumps(stats, indent=2))
            else:
                console.print(f"[bold]Cache Statistics (All Instances)[/bold]")
                console.print(f"  Total cached keys: {stats.get('total_keys', 0)}")
                instances = stats.get('instances', [])
                if instances:
                    console.print(f"  Instances with cache: {', '.join(instances)}")
                else:
                    console.print("  No cached data found")
        elif instance_id:
            stats = await tool_cache.stats()

            if as_json:
                console.print(_json.dumps(stats, indent=2))
            else:
                console.print(f"[bold]Cache Statistics for {instance_id}[/bold]")
                console.print(f"  Cached keys: {stats.get('cached_keys', 0)}")
                console.print(f"  Enabled: {stats.get('enabled', True)}")
                if stats.get('error'):
                    console.print(f"  [red]Error: {stats['error']}[/red]")
        else:
            # Default: show all
            stats = await tool_cache.stats_all()

            if as_json:
                console.print(_json.dumps(stats, indent=2))
            else:
                console.print(f"[bold]Cache Statistics[/bold]")
                console.print(f"  Total cached keys: {stats.get('total_keys', 0)}")
                instances = stats.get('instances', [])
                if instances:
                    console.print(f"  Instances: {', '.join(instances)}")

    asyncio.run(_stats())
