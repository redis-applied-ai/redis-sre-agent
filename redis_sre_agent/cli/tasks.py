"""Task management CLI commands."""

from __future__ import annotations

import asyncio

import click


@click.group()
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

        from redis_sre_agent.core.tasks import TaskStatus, list_tasks

        console = Console()

        # Determine fetch filter for backend: all filtering and ordering is server-side
        backend_status_filter = TaskStatus(status) if status else None
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
                        t["status"] = TaskStatus(kv_status)
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
            status_str = status_obj.value if isinstance(status_obj, TaskStatus) else str(status_obj)
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

        from redis_sre_agent.core.tasks import TaskStatus, get_task_by_id

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
            if isinstance(st, TaskStatus):
                out["status"] = st.value
            print(_json.dumps(out, indent=2))
            return

        meta = t.get("metadata", {}) or {}
        status_obj = t.get("status")
        status_str = status_obj.value if isinstance(status_obj, TaskStatus) else str(status_obj)

        table = Table(title=f"Task {task_id}")
        table.add_column("Field", no_wrap=True)
        table.add_column("Value")
        table.add_row("Status", status_str)
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


@task.command("purge")
@click.option(
    "--status",
    type=click.Choice(
        ["queued", "in_progress", "done", "failed", "cancelled"], case_sensitive=False
    ),
    help="Filter by a single status",
)
@click.option(
    "--older-than", "older_than", help="Purge tasks older than a duration (e.g. 7d, 24h, 3600s)"
)
@click.option("--all", "purge_all", is_flag=True, help="Purge ALL tasks (dangerous)")
@click.option("--dry-run", is_flag=True, help="Show what would be deleted; make no changes")
@click.option("-y", "--yes", is_flag=True, help="Do not prompt for confirmation")
def task_purge(
    status: str | None, older_than: str | None, purge_all: bool, dry_run: bool, yes: bool
):
    """Delete tasks in bulk with safeguards.

    By default requires --older-than DURATION (and optionally --status), unless --all.
    """

    async def _run():
        from datetime import datetime, timedelta, timezone

        from rich.console import Console

        from redis_sre_agent.core.redis import SRE_TASKS_INDEX, get_redis_client
        from redis_sre_agent.core.tasks import delete_task as delete_task_core

        console = Console()

        def _parse_duration(s: str) -> timedelta:
            if not s:
                raise ValueError("Duration string is empty")
            s = s.strip().lower()
            try:
                if s.endswith("d"):
                    return timedelta(days=float(s[:-1]))
                if s.endswith("h"):
                    return timedelta(hours=float(s[:-1]))
                if s.endswith("m"):
                    return timedelta(minutes=float(s[:-1]))
                if s.endswith("s"):
                    return timedelta(seconds=float(s[:-1]))
                return timedelta(seconds=float(s))
            except Exception as e:
                raise ValueError(f"Invalid duration '{s}': {e}")

        if not purge_all and not older_than and not status:
            console.print(
                "[red]Refusing to purge without a scope. Provide --older-than/--status or --all.[/red]"
            )
            return

        # Confirmation
        if not dry_run and not yes:
            scope_bits = []
            if purge_all:
                scope_bits.append("ALL tasks")
            if status:
                scope_bits.append(f"status={status}")
            if older_than:
                scope_bits.append(f"older_than={older_than}")
            scope = ", ".join(scope_bits) or "(no-scope)"
            console.print(f"You are about to delete [bold]{scope}[/bold].")
            console.print("Add --dry-run to preview or -y to confirm.")
            return

        client = get_redis_client()

        # Compute cutoff timestamp if scoped by age
        cutoff_ts = None
        if older_than:
            delta = _parse_duration(older_than)
            cutoff_ts = (datetime.now(timezone.utc) - delta).timestamp()

        cursor = 0
        page = 1000
        scanned = 0
        deleted = 0

        while True:
            cursor, keys = await client.scan(
                cursor=cursor, match=f"{SRE_TASKS_INDEX}:*", count=page
            )
            if not keys and cursor == 0:
                break
            for k in keys or []:
                redis_key = k.decode() if isinstance(k, bytes) else k
                task_id = redis_key[len(f"{SRE_TASKS_INDEX}:") :]

                # Read filter fields from FT hash
                try:
                    fields = await client.hmget(redis_key, "status", "updated_at", "created_at")
                    st_raw, upd_raw, _ = fields
                    st = (
                        (st_raw.decode() if isinstance(st_raw, bytes) else st_raw) if st_raw else ""
                    )
                    upd = float(upd_raw.decode() if isinstance(upd_raw, bytes) else upd_raw or 0)
                except Exception:
                    st = ""
                    upd = 0.0

                eligible = True
                if status:
                    eligible = eligible and (st.lower() == status.lower())
                if cutoff_ts is not None:
                    eligible = eligible and (upd > 0 and upd < cutoff_ts)

                if not purge_all and not eligible:
                    scanned += 1
                    continue

                if dry_run:
                    console.print(
                        f"[yellow]DRY RUN[/yellow] Would delete task {task_id} (status={st})"
                    )
                else:
                    try:
                        await delete_task_core(task_id=task_id, redis_client=client)
                        deleted += 1
                    except Exception:
                        pass
                scanned += 1

            if cursor == 0:
                break

        console.print(f"[green]Done.[/green] Scanned: {scanned}, Tasks deleted: {deleted}")

    asyncio.run(_run())


@task.command("delete")
@click.argument("task_id")
@click.option("--yes", is_flag=True, help="Do not prompt for confirmation")
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
def task_delete(task_id: str, yes: bool, as_json: bool):
    """Delete a single task by TASK_ID.

    This is intended for targeted cancellation/cleanup of an individual task,
    as opposed to bulk GC via ``task purge``.
    """

    async def _run():
        import json as _json

        from docket import Docket

        from redis_sre_agent.core.docket_tasks import get_redis_url
        from redis_sre_agent.core.redis import get_redis_client
        from redis_sre_agent.core.tasks import delete_task as delete_task_core

        # Interactive confirmation for safety (unless JSON or --yes)
        if not yes and not as_json:
            if not click.confirm(f"Delete task {task_id}?", default=False):
                click.echo("Cancelled")
                return

        # Best-effort: attempt to cancel any in-flight Docket task for this id.
        try:
            async with Docket(url=await get_redis_url(), name="sre_docket") as docket:
                try:
                    await docket.cancel(task_id)
                except Exception:
                    # Best-effort; do not fail CLI if cancel is not possible.
                    pass
        except Exception:
            # If Docket is unavailable, continue with Redis cleanup.
            pass

        client = get_redis_client()

        try:
            await delete_task_core(task_id=task_id, redis_client=client)
        except Exception as e:
            payload = {"task_id": task_id, "status": "error", "error": str(e)}
            if as_json:
                print(_json.dumps(payload))
            else:
                click.echo(f"\N{CROSS MARK} Error deleting task {task_id}: {e}")
            return

        payload = {"task_id": task_id, "status": "deleted"}
        if as_json:
            print(_json.dumps(payload))
        else:
            click.echo(f"\N{WHITE HEAVY CHECK MARK} Deleted task {task_id}")

    asyncio.run(_run())


@task.command("trace")
@click.argument("task_id")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.option("--show-data", is_flag=True, help="Show full tool output data")
def task_trace(task_id: str, as_json: bool, show_data: bool):
    """Show the decision trace (tool calls + citations) for a task.

    This displays the agent's reasoning trace for a specific task, including:
    - Tool calls made (name, arguments, status, and optionally results)
    - Citations/sources referenced (derived from knowledge tool envelopes)
    - OTel trace ID for correlation with Tempo
    """

    async def _trace():
        import json as _json

        from rich.console import Console
        from rich.panel import Panel
        from rich.syntax import Syntax
        from rich.table import Table

        from redis_sre_agent.core.redis import get_redis_client
        from redis_sre_agent.core.tasks import TaskManager

        console = Console()
        client = get_redis_client()
        task_manager = TaskManager(redis_client=client)

        trace = await task_manager.get_decision_trace(task_id)

        if not trace:
            if as_json:
                print(_json.dumps({"error": f"No decision trace found for task {task_id}"}))
            else:
                console.print(f"[yellow]No decision trace found for task {task_id}[/yellow]")
            return

        if as_json:
            print(_json.dumps(trace, indent=2))
            return

        # Display summary
        console.print(f"\n[bold]Decision Trace for Task:[/bold] {task_id}")
        if trace.get("otel_trace_id"):
            console.print(f"[dim]OTel Trace ID:[/dim] {trace['otel_trace_id']}")
        if trace.get("created_at"):
            console.print(f"[dim]Created:[/dim] {trace['created_at']}")
        console.print()

        # Use tool_envelopes (new format) or fall back to tool_calls (legacy)
        tool_envelopes = trace.get("tool_envelopes", [])
        tool_calls = trace.get("tool_calls", [])

        if tool_envelopes:
            # New format: full envelopes with data
            tc_table = Table(title=f"Tool Calls ({len(tool_envelopes)})")
            tc_table.add_column("#", no_wrap=True)
            tc_table.add_column("Tool", no_wrap=True)
            tc_table.add_column("Arguments", overflow="fold")
            tc_table.add_column("Status", no_wrap=True)
            if not show_data:
                tc_table.add_column("Result Preview", overflow="fold")

            for i, env in enumerate(tool_envelopes, 1):
                tool_name = env.get("name") or env.get("tool_key", "unknown")
                args = env.get("args", {})
                args_str = _json.dumps(args) if args else "-"
                if len(args_str) > 60:
                    args_str = args_str[:57] + "..."
                status = env.get("status", "unknown")
                status_style = "green" if status == "success" else "red"

                if show_data:
                    tc_table.add_row(
                        str(i), tool_name, args_str, f"[{status_style}]{status}[/{status_style}]"
                    )
                else:
                    # Show summary or truncated data preview
                    summary = env.get("summary")
                    if summary:
                        result_preview = summary[:80] + "..." if len(summary) > 80 else summary
                    else:
                        data = env.get("data", {})
                        data_str = _json.dumps(data, default=str)
                        result_preview = data_str[:80] + "..." if len(data_str) > 80 else data_str
                    tc_table.add_row(
                        str(i),
                        tool_name,
                        args_str,
                        f"[{status_style}]{status}[/{status_style}]",
                        result_preview,
                    )

            console.print(tc_table)

            # If --show-data, display full data for each tool
            if show_data:
                console.print()
                console.print("[bold]Full Tool Results:[/bold]")
                for i, env in enumerate(tool_envelopes, 1):
                    tool_name = env.get("name") or env.get("tool_key", "unknown")
                    data = env.get("data", {})
                    data_str = _json.dumps(data, indent=2, default=str)
                    syntax = Syntax(data_str, "json", theme="monokai", line_numbers=False)
                    panel = Panel(syntax, title=f"{i}. {tool_name}", border_style="dim")
                    console.print(panel)

        elif tool_calls:
            # Legacy format: tool_calls without data
            tc_table = Table(title=f"Tool Calls ({len(tool_calls)})")
            tc_table.add_column("#", no_wrap=True)
            tc_table.add_column("Tool", no_wrap=True)
            tc_table.add_column("Arguments", overflow="fold")
            tc_table.add_column("Status", no_wrap=True)

            for i, tc in enumerate(tool_calls, 1):
                tool_name = tc.get("name") or tc.get("tool_key", "unknown")
                args = tc.get("args", {})
                args_str = _json.dumps(args) if args else "-"
                if len(args_str) > 80:
                    args_str = args_str[:77] + "..."
                status = tc.get("status", "unknown")
                status_style = "green" if status == "success" else "red"
                tc_table.add_row(
                    str(i), tool_name, args_str, f"[{status_style}]{status}[/{status_style}]"
                )

            console.print(tc_table)
            console.print("[dim]Note: This is a legacy trace without tool result data.[/dim]")
        else:
            console.print("[dim]No tool calls recorded[/dim]")

        console.print()

        # Derive citations from knowledge tool envelopes (new format)
        # or use legacy citations field
        citations = trace.get("citations", [])

        # If we have tool_envelopes, derive citations from knowledge tools
        if tool_envelopes and not citations:
            for env in tool_envelopes:
                tool_key = env.get("tool_key", "")
                name = env.get("name", "")
                if "knowledge" in tool_key.lower() and "search" in name.lower():
                    data = env.get("data", {})
                    results = data.get("results", [])
                    for result in results:
                        citations.append(
                            {
                                "title": result.get("title"),
                                "source": result.get("source"),
                                "score": result.get("score"),
                                "document_id": result.get("id"),
                            }
                        )

        if citations:
            ct_table = Table(title=f"Citations ({len(citations)})")
            ct_table.add_column("#", no_wrap=True)
            ct_table.add_column("Title", overflow="fold")
            ct_table.add_column("Source", no_wrap=True)
            ct_table.add_column("Score", no_wrap=True)

            for i, ct in enumerate(citations, 1):
                title = ct.get("title") or ct.get("document_id") or "Untitled"
                if len(title) > 50:
                    title = title[:47] + "..."
                source = ct.get("source") or "-"
                score = ct.get("score")
                score_str = f"{score:.3f}" if score is not None else "-"
                ct_table.add_row(str(i), title, source, score_str)

            console.print(ct_table)
        else:
            console.print("[dim]No citations recorded[/dim]")

    asyncio.run(_trace())
