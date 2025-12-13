"""Knowledge base CLI commands."""

from __future__ import annotations

import asyncio
import json as _json
from typing import Optional

import click
from rich.console import Console
from rich.table import Table

from redis_sre_agent.core.knowledge_helpers import (
    get_all_document_fragments,
    get_related_document_fragments,
    search_knowledge_base_helper,
)


@click.group()
def knowledge():
    """Knowledge base management commands."""
    pass


@knowledge.command("search")
@click.argument("query", nargs=-1)
@click.option("--category", "-c", type=str, help="Filter by category")
@click.option("--limit", "-l", default=10, help="Number of results to return")
@click.option("--offset", "-o", default=0, help="Offset for pagination")
@click.option("--distance-threshold", "-d", type=float, help="Cosine distance threshold")
@click.option(
    "--hybrid-search",
    "-h",
    is_flag=True,
    default=False,
    help="Use hybrid search (vector + full-text)",
)
@click.option("--version", "-v", type=str, default="latest", help="Redis version filter")
def knowledge_search(
    category: Optional[str],
    limit: int,
    offset: int,
    distance_threshold: Optional[float],
    hybrid_search: bool,
    version: Optional[str],
    query: str = "*",
):
    """Search the knowledge base (query helpers group)."""

    async def _run():
        kwargs = {
            "query": " ".join(query),
            "limit": limit,
            "offset": offset,
            "distance_threshold": distance_threshold,
            "hybrid_search": hybrid_search,
        }

        click.echo(f"🔍 Searching knowledge base for: {query}")
        if category:
            kwargs["category"] = category
            click.echo(f"📂 Category filter: {category}")
        if distance_threshold:
            click.echo(f"📏 Distance threshold: {distance_threshold}")
        if version:
            kwargs["version"] = version
            click.echo(f"🔢 Version filter: {version}")
        click.echo(f"🔢 Limit: {limit}")

        result = await search_knowledge_base_helper(**kwargs)

        if isinstance(result, str):
            click.echo("\n" + result)
        else:
            results = result.get("results", [])
            if results:
                click.echo(f"\n✅ Found {len(results)} results:")
                for i, doc in enumerate(results, 1):
                    click.echo(f"\n--- Result {i} ---")
                    click.echo(f"Title: {doc.get('title', 'Unknown')}")
                    click.echo(f"Source: {doc.get('source', 'Unknown')}")
                    click.echo(f"Category: {doc.get('category', 'general')}")
                    click.echo(f"Version: {doc.get('version', 'None')}")
                    content = doc.get("content", "")
                    if len(content) > 1000:
                        content = content[:1000] + "..."
                    click.echo(f"Content: {content}")
            else:
                click.echo("❌ No results found")

    asyncio.run(_run())


@knowledge.command("fragments")
@click.argument("document_hash")
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
@click.option(
    "--include-metadata/--no-metadata", default=True, help="Include document metadata in output"
)
def knowledge_fragments(document_hash: str, as_json: bool, include_metadata: bool):
    """Fetch all fragments for a document by document hash."""

    async def _run():
        try:
            result = await get_all_document_fragments(
                document_hash, include_metadata=include_metadata
            )
        except Exception as e:
            payload = {"error": str(e), "document_hash": document_hash}
            if as_json:
                print(_json.dumps(payload))
            else:
                click.echo(f"❌ Error: {e}")
            return

        if as_json:
            print(_json.dumps(result, indent=2))
            return

        if result.get("error"):
            click.echo(f"❌ {result['error']}")
            return

        console = Console()
        hdr = Table(title=f"Fragments for document {document_hash}")
        hdr.add_column("Field", no_wrap=True)
        hdr.add_column("Value")
        hdr.add_row("Title", result.get("title") or "-")
        hdr.add_row("Source", result.get("source") or "-")
        hdr.add_row("Category", result.get("category") or "-")
        hdr.add_row("Fragments", str(result.get("fragments_count", 0)))
        console.print(hdr)

        frags = result.get("fragments") or []
        if not frags:
            click.echo("No fragments found.")
            return

        table = Table(title="Document fragments")
        table.add_column("Idx", no_wrap=True)
        table.add_column("Content")
        for f in frags:
            idx = f.get("chunk_index")
            content = (f.get("content") or "").strip()
            if len(content) > 180:
                content = content[:180] + "…"
            table.add_row(str(idx if idx is not None else "-"), content)
        console.print(table)

    asyncio.run(_run())


@knowledge.command("related")
@click.argument("document_hash")
@click.option(
    "--chunk-index", type=int, required=True, help="Target chunk index to center the context around"
)
@click.option(
    "--window",
    type=int,
    default=2,
    show_default=True,
    help="Number of chunks before/after to include",
)
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
def knowledge_related(document_hash: str, chunk_index: int, window: int, as_json: bool):
    """Fetch related fragments around a chunk index for a document."""

    async def _run():
        try:
            result = await get_related_document_fragments(
                document_hash, current_chunk_index=chunk_index, context_window=window
            )
        except Exception as e:
            payload = {"error": str(e), "document_hash": document_hash}
            if as_json:
                print(_json.dumps(payload))
            else:
                click.echo(f"❌ Error: {e}")
            return

        if as_json:
            print(_json.dumps(result, indent=2))
            return

        if result.get("error"):
            click.echo(f"❌ {result['error']}")
            return

        console = Console()
        hdr = Table(title=f"Related fragments for document {document_hash}")
        hdr.add_column("Field", no_wrap=True)
        hdr.add_column("Value")
        hdr.add_row("Title", result.get("title") or "-")
        hdr.add_row("Source", result.get("source") or "-")
        hdr.add_row("Category", result.get("category") or "-")
        hdr.add_row("Target Index", str(result.get("target_chunk_index")))
        hdr.add_row("Context Window", str(result.get("context_window")))
        hdr.add_row("Related Count", str(result.get("related_fragments_count", 0)))
        console.print(hdr)

        frags = result.get("related_fragments") or []
        if not frags:
            click.echo("No related fragments found.")
            return

        table = Table(title="Related fragments")
        table.add_column("Idx", no_wrap=True)
        table.add_column("Target?", no_wrap=True)
        table.add_column("Content")
        for f in frags:
            idx = f.get("chunk_index")
            is_target = "✓" if f.get("is_target_chunk") else ""
            content = (f.get("content") or "").strip()
            if len(content) > 180:
                content = content[:180] + "…"
            table.add_row(str(idx if idx is not None else "-"), is_target, content)
        console.print(table)

    asyncio.run(_run())
