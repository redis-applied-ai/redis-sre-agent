"""Index management CLI commands."""

from __future__ import annotations

import asyncio
import json as _json

import click
from rich.console import Console
from rich.table import Table


@click.group()
def index():
    """RediSearch index management commands."""
    pass


@index.command("list")
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
def index_list(as_json: bool):
    """List all SRE agent indices and their status."""

    async def _run():
        from redis_sre_agent.core.redis import (
            SRE_INSTANCES_INDEX,
            SRE_KNOWLEDGE_INDEX,
            SRE_SCHEDULES_INDEX,
            SRE_TASKS_INDEX,
            SRE_THREADS_INDEX,
            get_instances_index,
            get_knowledge_index,
            get_schedules_index,
            get_tasks_index,
            get_threads_index,
        )

        console = Console()
        indices = [
            ("knowledge", SRE_KNOWLEDGE_INDEX, get_knowledge_index),
            ("schedules", SRE_SCHEDULES_INDEX, get_schedules_index),
            ("threads", SRE_THREADS_INDEX, get_threads_index),
            ("tasks", SRE_TASKS_INDEX, get_tasks_index),
            ("instances", SRE_INSTANCES_INDEX, get_instances_index),
        ]

        results = []
        for name, index_name, get_fn in indices:
            try:
                idx = await get_fn()
                exists = await idx.exists()
                info = {}
                if exists:
                    try:
                        # Get index info to show field count
                        client = idx._redis_client
                        raw_info = await client.execute_command("FT.INFO", index_name)
                        # Parse the flat list into a dict
                        info_dict = {}
                        for i in range(0, len(raw_info), 2):
                            key = raw_info[i]
                            if isinstance(key, bytes):
                                key = key.decode()
                            info_dict[key] = raw_info[i + 1]
                        num_docs = info_dict.get("num_docs", 0)
                        if isinstance(num_docs, bytes):
                            num_docs = num_docs.decode()
                        info["num_docs"] = int(num_docs)
                    except Exception:
                        info["num_docs"] = "?"

                results.append(
                    {
                        "name": name,
                        "index_name": index_name,
                        "exists": exists,
                        "num_docs": info.get("num_docs", 0) if exists else 0,
                    }
                )
            except Exception as e:
                results.append(
                    {
                        "name": name,
                        "index_name": index_name,
                        "exists": False,
                        "error": str(e),
                    }
                )

        if as_json:
            print(_json.dumps(results, indent=2))
            return

        table = Table(title="RediSearch Indices")
        table.add_column("Name", no_wrap=True)
        table.add_column("Index Name", no_wrap=True)
        table.add_column("Exists", no_wrap=True)
        table.add_column("Documents", no_wrap=True)

        for r in results:
            exists_str = "✅" if r["exists"] else "❌"
            docs = str(r.get("num_docs", 0)) if r["exists"] else "-"
            if r.get("error"):
                docs = f"Error: {r['error']}"
            table.add_row(r["name"], r["index_name"], exists_str, docs)

        console.print(table)

    asyncio.run(_run())


@index.command("recreate")
@click.option(
    "--index-name",
    type=click.Choice(["knowledge", "schedules", "threads", "tasks", "instances", "all"]),
    default="all",
    help="Which index to recreate (default: all)",
)
@click.option("-y", "--yes", is_flag=True, help="Skip confirmation prompt")
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
def index_recreate(index_name: str, yes: bool, as_json: bool):
    """Drop and recreate RediSearch indices.

    This is useful when the schema has changed (e.g., new fields added).
    WARNING: This will delete all indexed data. The underlying Redis keys
    remain, but you'll need to re-index documents.
    """

    async def _run():
        from redis_sre_agent.core.redis import recreate_indices

        console = Console()

        if not yes and not as_json:
            console.print(
                "[yellow]Warning:[/yellow] This will drop and recreate indices. "
                "Indexed data will need to be re-ingested."
            )
            if not click.confirm("Continue?"):
                console.print("Aborted.")
                return

        result = await recreate_indices(index_name if index_name != "all" else None)

        if as_json:
            print(_json.dumps(result, indent=2))
            return

        if result.get("success"):
            console.print("[green]✅ Successfully recreated indices[/green]")
            for idx_name, status in result.get("indices", {}).items():
                console.print(f"  - {idx_name}: {status}")
        else:
            console.print(f"[red]❌ Failed to recreate indices: {result.get('error')}[/red]")

    asyncio.run(_run())
