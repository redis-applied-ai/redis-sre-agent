"""CLI interface for Redis SRE Agent."""

import asyncio

import click
from docket import Worker

from redis_sre_agent.core.config import settings
from redis_sre_agent.core.docket_tasks import register_sre_tasks

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


@main.command()
@click.argument("query")
@click.option("--limit", "-l", default=5, help="Number of results to return")
@click.option("--category", "-c", help="Filter by category")
def search(query: str, limit: int, category: str):
    """Search the knowledge base directly."""

    async def _search():
        from redis_sre_agent.core.docket_tasks import search_knowledge_base

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
                        if len(content) > 1000:
                            content = content[:1000] + "..."
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
        from redis_sre_agent.core.docket_tasks import check_service_health

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
@click.option("--concurrency", "-c", default=2, help="Number of concurrent tasks")
def worker(concurrency: int):
    """Start the background worker."""

    async def _worker():
        import logging
        import sys
        from datetime import timedelta

        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(name)s %(levelname)s %(message)s",
            datefmt="%H:%M:%S",
        )
        logger = logging.getLogger(__name__)

        # Validate Redis URL
        if (
            not settings.redis_url
            or not getattr(settings.redis_url, "get_secret_value", lambda: "")()
        ):
            click.echo("❌ Redis URL not configured")
            sys.exit(1)

        redis_url = settings.redis_url.get_secret_value()
        logger.info("Starting SRE Docket worker connected to Redis")

        try:
            # Register tasks first (support both sync and async implementations)
            import inspect

            reg = register_sre_tasks()
            if inspect.isawaitable(reg):
                await reg
            click.echo("✅ SRE tasks registered with Docket")

            # Start the worker
            click.echo("✅ Worker started, waiting for SRE tasks... Press Ctrl+C to stop")
            await Worker.run(
                docket_name="sre_docket",
                url=redis_url,
                concurrency=concurrency,
                redelivery_timeout=timedelta(seconds=settings.task_timeout),
                tasks=["redis_sre_agent.core.docket_tasks:SRE_TASK_COLLECTION"],
            )
        except Exception as e:
            logger.error(f"❌ Worker error: {e}")
            raise

    try:
        asyncio.run(_worker())
    except KeyboardInterrupt:
        click.echo("\n👋 SRE worker stopped by user")
    except Exception as e:
        click.echo(f"💥 Unexpected worker error: {e}")
        raise


@main.group()
def task():
    """Task management commands."""
    pass


@task.command("list")
@click.option("--user-id", help="Filter by user ID")
@click.option(
    "--status",
    type=click.Choice(
        ["queued", "in_progress", "done", "failed", "cancelled"], case_sensitive=False
    ),
    help="Filter by a single status (overrides --all/default)",
)
@click.option(
    "--all", "show_all", is_flag=True, help="Show all statuses (including cancelled and failed)"
)
@click.option("--limit", "-l", default=50, help="Number of tasks to show")
@click.option(
    "--tz",
    required=False,
    help="IANA timezone (e.g. 'America/Los_Angeles'). Defaults to local time",
)
def task_list(user_id: str | None, status: str | None, show_all: bool, limit: int, tz: str | None):
    """List recent tasks and their statuses.

    Default: show only in-progress and scheduled (queued) tasks.
    Use --all to show all statuses, or --status to filter to a single status.
    """

    async def _list():
        from rich.console import Console
        from rich.table import Table

        from redis_sre_agent.core.thread_state import ThreadStatus
        from redis_sre_agent.models.tasks import list_tasks

        console = Console()

        # Determine fetch filter for backend: all filtering and ordering is server-side
        backend_status_filter = ThreadStatus(status) if status else None
        tasks = await list_tasks(
            user_id=user_id,
            status_filter=backend_status_filter,
            show_all=show_all and not status,
            limit=limit,
        )

        # Refresh status from KV to avoid stale index results
        try:
            from redis_sre_agent.core.keys import RedisKeys
            from redis_sre_agent.core.redis import get_redis_client

            r = get_redis_client()
            for t in tasks:
                tid = t.get("task_id")
                if not tid:
                    continue
                kv_status = await r.get(RedisKeys.task_status(tid))
                if isinstance(kv_status, bytes):
                    kv_status = kv_status.decode()
                if kv_status:
                    try:
                        t["status"] = ThreadStatus(kv_status)
                    except Exception:
                        pass
        except Exception:
            pass

        if not tasks:
            console.print("[yellow]No tasks found.[/yellow]")
            return

        # Timestamp formatting helper (similar to thread list)
        from datetime import datetime

        try:
            from zoneinfo import ZoneInfo as _ZoneInfo  # Python 3.9+

            zoneinfo_cls = _ZoneInfo
        except Exception:
            zoneinfo_cls = None  # type: ignore

        def _fmt(ts: str | None) -> str:
            if not ts or ts == "-":
                return "-"
            try:
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

        table = Table(title="Tasks", show_lines=False)
        table.add_column("Status", no_wrap=True)
        table.add_column("Updated", no_wrap=True)
        table.add_column("Task ID", no_wrap=True)
        table.add_column("Thread Subject")
        table.add_column("Task Subject")
        table.add_column("Thread ID", no_wrap=True)

        for t in tasks:
            meta = t.get("metadata", {}) or {}
            thread_subject = meta.get("thread_subject") or "Untitled"
            task_subject = meta.get("subject") or "Untitled"
            updated = meta.get("updated_at") or meta.get("created_at") or "-"
            updated_disp = _fmt(updated)
            status_obj = t.get("status")
            status_str = getattr(status_obj, "value", str(status_obj))
            thread_id = t.get("thread_id") or "-"
            task_id_val = t.get("task_id") or "-"

            color = {
                "in_progress": "cyan",
                "queued": "yellow",
                "done": "green",
                "failed": "red",
                "cancelled": "magenta",
            }.get(status_str, "white")

            table.add_row(
                f"[{color}]{status_str}[/{color}]",
                updated_disp,
                task_id_val,
                thread_subject,
                task_subject,
                thread_id,
            )

        console.print(table)

    asyncio.run(_list())


@task.command("get")
@click.argument("task_id")
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
def task_get(task_id: str, as_json: bool):
    """Get a task by TASK_ID and show details."""

    async def _get():
        import json as _json

        from rich.console import Console
        from rich.table import Table

        from redis_sre_agent.models.tasks import get_task_by_id

        console = Console()
        try:
            t = await get_task_by_id(task_id=task_id)
        except Exception as e:
            if as_json:
                print(_json.dumps({"error": str(e), "task_id": task_id}))
            else:
                console.print(f"[red]Error:[/red] {e}")
            return

        if as_json:
            out = dict(t)
            st = out.get("status")
            if hasattr(st, "value"):
                out["status"] = st.value
            print(_json.dumps(out, indent=2))
            return

        meta = t.get("metadata", {}) or {}

        table = Table(title=f"Task {task_id}")
        table.add_column("Field", no_wrap=True)
        table.add_column("Value")
        table.add_row("Status", getattr(t.get("status"), "value", str(t.get("status"))))
        table.add_row("Thread ID", t.get("thread_id") or "-")
        table.add_row("Created", meta.get("created_at") or "-")
        table.add_row("Updated", meta.get("updated_at") or "-")
        table.add_row("Subject", meta.get("subject") or "Untitled")
        table.add_row("User", meta.get("user_id") or "-")
        console.print(table)

        updates = t.get("updates") or []
        if updates:
            ut = Table(title="Recent Updates")
            ut.add_column("Time", no_wrap=True)
            ut.add_column("Type", no_wrap=True)
            ut.add_column("Message")
            for u in updates[:10]:
                ut.add_row(u.get("timestamp") or "-", u.get("type") or "-", u.get("message") or "-")
            console.print(ut)

        result = t.get("result")
        if result:
            rt = Table(title="Result")
            rt.add_column("Key", no_wrap=True)
            rt.add_column("Value")
            for k, v in (result or {}).items():
                rt.add_row(str(k), str(v))
            console.print(rt)

        err = t.get("error_message")
        if err:
            console.print(f"[red]Error:[/red] {err}")

    asyncio.run(_get())


@main.group()
def thread():
    """Thread management commands."""
    pass


@thread.command("list")
@click.option("--user-id", help="Filter by user ID")
@click.option("--limit", "-l", default=50, help="Number of threads to show")
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
        from redis_sre_agent.core.thread_state import ThreadManager

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
        from redis_sre_agent.core.thread_state import ThreadManager
        from redis_sre_agent.models.tasks import get_task_status as _get_task_status

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
        from redis_sre_agent.core.thread_state import ThreadManager

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
        from redis_sre_agent.core.thread_state import ThreadManager

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


@main.group()
def knowledge():
    """Knowledge base management commands."""
    pass


@knowledge.command("search")
@click.argument("query")
@click.option("--limit", "-l", default=5, help="Number of results to return")
@click.option("--category", "-c", help="Filter by category")
def knowledge_search(query: str, limit: int, category: str):
    """Search the knowledge base (query helpers group)."""

    async def _search():
        from redis_sre_agent.core.docket_tasks import search_knowledge_base

        click.echo(f"🔍 Searching knowledge base for: {query}")
        if category:
            click.echo(f"📂 Category filter: {category}")

        try:
            result = await search_knowledge_base(query, category=category, limit=limit)

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
                        content = doc.get("content", "")
                        if len(content) > 1000:
                            content = content[:1000] + "..."
                        click.echo(f"Content: {content}")
                else:
                    click.echo("❌ No results found")

        except Exception as e:
            click.echo(f"❌ Search error: {e}")

    asyncio.run(_search())


@knowledge.command("fragments")
@click.argument("document_hash")
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
@click.option(
    "--include-metadata/--no-metadata", default=True, help="Include document metadata in output"
)
def knowledge_fragments(document_hash: str, as_json: bool, include_metadata: bool):
    """Fetch all fragments for a document by document hash."""

    async def _run():
        import json as _json

        from rich.console import Console
        from rich.table import Table

        from redis_sre_agent.core.knowledge_helpers import get_all_document_fragments

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
        import json as _json

        from rich.console import Console
        from rich.table import Table

        from redis_sre_agent.core.knowledge_helpers import get_related_document_fragments

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


if __name__ == "__main__":
    main()
