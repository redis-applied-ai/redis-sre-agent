"""Thread management CLI commands.

Extracted from main.py to keep CLI modular without behavior changes.
"""

from __future__ import annotations

import asyncio

import click


@click.group()
def thread():
    """Thread management commands."""
    pass


@thread.command("list")
@click.option("--user-id", help="Filter by user ID")
@click.option("--limit", "-l", default=10, help="Number of threads to show")
@click.option(
    "--tz",
    required=False,
    help="IANA timezone (e.g. 'America/Los_Angeles'). Defaults to local time",
)
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
def thread_list(
    user_id: str | None,
    limit: int,
    tz: str | None,
    as_json: bool,
):
    """List threads (shows all threads by default, ordered by Redis index)."""

    async def _list():
        import json as _json

        from rich.console import Console
        from rich.table import Table

        from redis_sre_agent.core.redis import get_redis_client
        from redis_sre_agent.core.threads import ThreadManager

        console = Console()
        tm = ThreadManager(redis_client=get_redis_client())

        # Show all threads by default
        threads = await tm.list_threads(user_id=user_id, limit=limit, offset=0)

        # Helper to parse/sort and format timestamps
        from datetime import datetime

        try:
            from zoneinfo import ZoneInfo as _ZoneInfo  # Python 3.9+

            zoneinfo_cls = _ZoneInfo
        except Exception:
            zoneinfo_cls = None  # type: ignore

        def _to_ts(s: str | None) -> float:
            if not s or s == "-":
                return 0.0
            try:
                return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
            except Exception:
                return 0.0

        # Sort threads by updated_at (fallback to created_at) descending, client-side
        threads = sorted(
            threads or [],
            key=lambda th: _to_ts(th.get("updated_at") or th.get("created_at")),
            reverse=True,
        )

        if as_json:
            print(_json.dumps(threads, indent=2))
            return

        def _fmt(ts: str | None) -> str:
            if not ts or ts == "-":
                return "-"
            try:
                # ThreadManager emits UTC ISO with offset (e.g., +00:00)
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                if tz and zoneinfo_cls is not None:
                    try:
                        dt = dt.astimezone(zoneinfo_cls(tz))
                    except Exception:
                        dt = dt.astimezone()
                else:
                    dt = dt.astimezone()  # local timezone
                return dt.strftime("%Y-%m-%d %H:%M:%S %Z")
            except Exception:
                return ts

        if not threads:
            console.print("[yellow]No threads found.[/yellow]")
            return

        table = Table(title="Threads", show_lines=False)
        table.add_column("Updated", no_wrap=True)
        table.add_column("Subject")
        table.add_column("Thread ID", no_wrap=True)
        table.add_column("Instance", no_wrap=True)

        instance_names = {}

        for th in threads[:limit]:
            updated_iso = th.get("updated_at") or th.get("created_at") or "-"
            updated_disp = _fmt(updated_iso)
            subject = th.get("subject") or "Untitled"
            instance_id = th.get("instance_id") or "-"
            if instance_id not in instance_names:
                instance_names[instance_id] = th.get("instance_name") or instance_id
            table.add_row(
                updated_disp,
                subject,
                th.get("thread_id") or "-",
                instance_names.get(instance_id, "-"),
            )

        console.print(table)

    asyncio.run(_list())


@thread.command("get")
@click.argument("thread_id")
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
def thread_get(thread_id: str, as_json: bool):
    """Get full thread details by ID."""

    async def _get():
        import json as _json

        from rich.console import Console
        from rich.table import Table

        from redis_sre_agent.core.redis import get_redis_client
        from redis_sre_agent.core.tasks import get_task_status as _get_task_status
        from redis_sre_agent.core.threads import ThreadManager

        console = Console()
        tm = ThreadManager(redis_client=get_redis_client())
        state = await tm.get_thread_state(thread_id)
        if not state:
            if as_json:
                print(_json.dumps({"error": "Thread not found", "thread_id": thread_id}))
            else:
                console.print(f"[red]Thread not found:[/red] {thread_id}")
            return

        if as_json:
            try:
                payload = await _get_task_status(thread_id=thread_id)
                st = payload.get("status")
                if hasattr(st, "value"):
                    payload["status"] = st.value
                print(_json.dumps(payload, indent=2))
            except Exception as e:
                print(_json.dumps({"error": str(e), "thread_id": thread_id}))
            return

        meta = state.metadata
        ctx = state.context or {}

        table = Table(title=f"Thread {thread_id}")
        table.add_column("Field", no_wrap=True)
        table.add_column("Value")
        table.add_row("Created", meta.created_at or "-")
        table.add_row("Updated", meta.updated_at or "-")
        table.add_row("Subject", meta.subject or "Untitled")
        table.add_row("User", meta.user_id or "-")
        table.add_row("Tags", ", ".join(meta.tags or []) or "-")
        table.add_row("Instance", ctx.get("instance_name") or ctx.get("instance_id") or "-")
        table.add_row("Priority", str(meta.priority))
        console.print(table)

        # Updates
        if state.updates:
            ut = Table(title="Updates")
            ut.add_column("Time", no_wrap=True)
            ut.add_column("Type", no_wrap=True)
            ut.add_column("Message")
            for u in state.updates[:20]:
                ut.add_row(u.timestamp or "-", u.update_type or "-", u.message or "-")
            console.print(ut)

        # Result
        if state.result:
            rt = Table(title="Result")
            rt.add_column("Key", no_wrap=True)
            rt.add_column("Value")
            for k, v in (state.result or {}).items():
                rt.add_row(str(k), str(v))
            console.print(rt)

    asyncio.run(_get())


@thread.command("sources")
@click.argument("thread_id")
@click.option("--task-id", required=False, help="Filter to a specific turn/task ID")
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
def thread_sources(thread_id: str, task_id: str | None, as_json: bool):
    """List knowledge fragments retrieved for a thread (optionally a specific turn)."""

    async def _run():
        import json as _json

        from rich.console import Console
        from rich.table import Table

        from redis_sre_agent.core.redis import get_redis_client
        from redis_sre_agent.core.threads import ThreadManager

        tm = ThreadManager(redis_client=get_redis_client())
        state = await tm.get_thread_state(thread_id)
        if not state:
            payload = {"error": "Thread not found", "thread_id": thread_id}
            if as_json:
                print(_json.dumps(payload))
            else:
                click.echo(f"❌ Thread not found: {thread_id}")
            return

        # Collect knowledge_sources updates
        items = []
        for u in state.updates or []:
            try:
                if (u.update_type or "") != "knowledge_sources":
                    continue
                md = u.metadata or {}
                if task_id and (md.get("task_id") != task_id):
                    continue
                for frag in md.get("fragments") or []:
                    items.append(
                        {
                            "timestamp": u.timestamp,
                            "task_id": md.get("task_id"),
                            "id": frag.get("id"),
                            "document_hash": frag.get("document_hash"),
                            "chunk_index": frag.get("chunk_index"),
                            "title": frag.get("title"),
                            "source": frag.get("source"),
                        }
                    )
            except Exception:
                continue

        if as_json:
            print(
                _json.dumps(
                    {"thread_id": thread_id, "task_id": task_id, "fragments": items}, indent=2
                )
            )
            return

        if not items:
            click.echo("No knowledge fragments recorded for this thread.")
            return

        console = Console()
        tbl = Table(title=f"Knowledge fragments for thread {thread_id}")
        tbl.add_column("Time", no_wrap=True)
        tbl.add_column("Task", no_wrap=True)
        tbl.add_column("Frag ID", no_wrap=True)
        tbl.add_column("Doc Hash", no_wrap=True)
        tbl.add_column("Idx", no_wrap=True)
        tbl.add_column("Title")
        tbl.add_column("Source")
        for it in items:
            tbl.add_row(
                it.get("timestamp") or "-",
                (it.get("task_id") or "-")[:12],
                (it.get("id") or "-")[:12],
                (it.get("document_hash") or "-")[:12],
                str(it.get("chunk_index") if it.get("chunk_index") is not None else "-"),
                it.get("title") or "-",
                it.get("source") or "-",
            )
        console.print(tbl)

    asyncio.run(_run())


@thread.command("backfill")
@click.option("--limit", "-l", default=0, help="Max threads to backfill (0 = all)")
@click.option("--start", default=0, help="Start offset in index")
def thread_backfill(limit: int, start: int):
    """Backfill the threads FT.SEARCH index from existing thread data."""

    async def _backfill():
        from rich.console import Console

        from redis_sre_agent.core.keys import RedisKeys
        from redis_sre_agent.core.redis import (
            SRE_THREADS_INDEX,
            get_redis_client,
            get_threads_index,
        )
        from redis_sre_agent.core.threads import ThreadManager

        console = Console()
        tm = ThreadManager(redis_client=get_redis_client())

        # Ensure index exists
        try:
            idx = await get_threads_index()
            if not await idx.exists():
                await idx.create()
                console.print(f"[green]Created index:[/green] {SRE_THREADS_INDEX}")
        except Exception as e:
            console.print(f"[yellow]Warning creating/ensuring index:[/yellow] {e}")

        client = await tm._get_client()
        processed = 0
        page = 500
        offset = start
        while True:
            ids = await client.zrevrange(RedisKeys.threads_index(), offset, offset + page - 1)
            if not ids:
                break
            for raw in ids:
                if limit and processed >= limit:
                    break
                tid = raw.decode() if isinstance(raw, bytes) else raw
                await tm._upsert_thread_search_doc(tid)
                processed += 1
                if processed % 200 == 0:
                    console.print(f"Backfilled {processed} threads…")
            if limit and processed >= limit:
                break
            offset += page

        console.print(f"[green]Done.[/green] Backfilled {processed} thread docs.")

    asyncio.run(_backfill())
