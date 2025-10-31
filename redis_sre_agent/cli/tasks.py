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

        from redis_sre_agent.core.tasks import get_task_by_id

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
