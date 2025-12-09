"""Thread management CLI commands."""

from __future__ import annotations

import asyncio
import json
from zoneinfo import ZoneInfo

import click
from rich.console import Console
from rich.table import Table

from redis_sre_agent.core.keys import RedisKeys
from redis_sre_agent.core.redis import (
    SRE_THREADS_INDEX,
    get_redis_client,
    get_threads_index,
)
from redis_sre_agent.core.threads import ThreadManager


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
        console = Console()
        tm = ThreadManager(redis_client=get_redis_client())

        # Show all threads by default
        threads = await tm.list_threads(user_id=user_id, limit=limit, offset=0)

        # Helper to parse/sort and format timestamps
        from datetime import datetime

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
            print(json.dumps(threads, indent=2))
            return

        def _fmt(ts: str | None) -> str:
            if not ts or ts == "-":
                return "-"
            try:
                # ThreadManager emits UTC ISO with offset (e.g., +00:00)
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                if tz:
                    try:
                        dt = dt.astimezone(ZoneInfo(tz))
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
        console = Console()
        tm = ThreadManager(redis_client=get_redis_client())
        state = await tm.get_thread(thread_id)
        if not state:
            if as_json:
                print(json.dumps({"error": "Thread not found", "thread_id": thread_id}))
            else:
                console.print(f"[red]Thread not found:[/red] {thread_id}")
            return

        if as_json:
            print(json.dumps(state.model_dump(), indent=2))
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
        tm = ThreadManager(redis_client=get_redis_client())
        state = await tm.get_thread(thread_id)
        if not state:
            payload = {"error": "Thread not found", "thread_id": thread_id}
            if as_json:
                print(json.dumps(payload))
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
                json.dumps(
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


@thread.command("reindex")
@click.option("--drop", is_flag=True, help="Drop existing threads index before recreating")
@click.option("--limit", "-l", default=0, help="Max threads to backfill (0 = all)")
@click.option("--start", default=0, help="Start offset in index")
def thread_reindex(drop: bool, limit: int, start: int):
    """Recreate the threads FT.SEARCH index and backfill from existing thread data."""

    async def _reindex():
        console = Console()
        tm = ThreadManager(redis_client=get_redis_client())

        # Drop and recreate index if requested
        idx = await get_threads_index()
        try:
            exists = await idx.exists()
        except Exception:
            exists = False

        if exists and drop:
            try:
                # Preferred path (RedisVL newer versions)
                await idx.drop()  # type: ignore[attr-defined]
                console.print(f"[yellow]Dropped index:[/yellow] {SRE_THREADS_INDEX}")

            except Exception as e:
                console.print(f"[yellow]idx.drop() unavailable/failed:[/yellow] {e}")
                try:
                    client = await tm._get_client()
                    await client.execute_command("FT.DROPINDEX", SRE_THREADS_INDEX)
                    console.print(
                        f"[yellow]Dropped index via FT.DROPINDEX:[/yellow] {SRE_THREADS_INDEX}"
                    )
                except Exception as e2:
                    console.print(
                        f"[red]Failed to drop {SRE_THREADS_INDEX} via FT.DROPINDEX:[/red] {e2}"
                    )
            # If we couldn't drop, we will attempt to recreate below which will no-op if unchanged

        try:
            # Create will no-op if exists
            if not await idx.exists():
                await idx.create()
                console.print(f"[green]Created index:[/green] {SRE_THREADS_INDEX}")
            else:
                console.print(f"[green]Index exists:[/green] {SRE_THREADS_INDEX}")
        except Exception as e:
            console.print(f"[yellow]Warning ensuring index:[/yellow] {e}")

        # Backfill all thread docs
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

        console.print(f"[green]Done.[/green] Reindexed and backfilled {processed} thread docs.")

    asyncio.run(_reindex())


@thread.command("backfill-scheduled-subjects")
@click.option("--limit", "-l", default=0, help="Max threads to scan (0 = all)")
@click.option("--start", default=0, help="Start offset in index")
@click.option("--dry-run", is_flag=True, help="Do not write changes; only report")
def thread_backfill_scheduled_subjects(limit: int, start: int, dry_run: bool):
    """Set subject to schedule_name for existing scheduled threads missing a subject.

    A thread is considered scheduled if any of the following hold:
    - metadata.user_id == 'scheduler'
    - 'scheduled' in metadata.tags
    - context.automated is True and context.schedule_name exists
    """

    async def _run():
        from rich.console import Console

        from redis_sre_agent.core.keys import RedisKeys
        from redis_sre_agent.core.redis import get_redis_client
        from redis_sre_agent.core.threads import ThreadManager

        console = Console()
        tm = ThreadManager(redis_client=get_redis_client())

        client = await tm._get_client()
        scanned = 0
        subject_updates = 0
        tag_updates = 0

        page = 500
        offset = start
        while True:
            ids = await client.zrevrange(RedisKeys.threads_index(), offset, offset + page - 1)
            if not ids:
                break
            for raw in ids:
                if limit and scanned >= limit:
                    break
                tid = raw.decode() if isinstance(raw, bytes) else raw
                state = await tm.get_thread(tid)
                if not state:
                    scanned += 1
                    continue

                meta = state.metadata
                ctx = state.context or {}
                schedule_name = ctx.get("schedule_name") or None
                is_scheduled = (
                    (meta.user_id or "") == "scheduler"
                    or ("scheduled" in (meta.tags or []))
                    or (bool(ctx.get("automated")) and bool(schedule_name))
                )

                # Backfill subject
                subj = (meta.subject or "").strip()
                if (
                    is_scheduled
                    and schedule_name
                    and (not subj or subj.lower() in {"untitled", "unknown"})
                ):
                    if dry_run:
                        console.print(
                            f"[yellow]DRY RUN[/yellow] Would set subject for {tid} -> {schedule_name}"
                        )
                    else:
                        await tm.set_thread_subject(tid, schedule_name)
                    subject_updates += 1

                # Ensure 'scheduled' tag is present for scheduled threads
                if is_scheduled and "scheduled" not in (meta.tags or []):
                    if dry_run:
                        console.print(
                            f"[yellow]DRY RUN[/yellow] Would add 'scheduled' tag to {tid}"
                        )
                    else:
                        meta.tags = list(sorted(set((meta.tags or []) + ["scheduled"])))
                        # Persist metadata change
                        await tm._save_thread_state(state)
                    tag_updates += 1

                scanned += 1

            if limit and scanned >= limit:
                break
            offset += page

        console.print(
            f"[green]Done.[/green] Scanned: {scanned}, Subjects updated: {subject_updates}, Tags updated: {tag_updates}"
        )

    asyncio.run(_run())


@thread.command("backfill")
@click.option("--limit", "-l", default=0, help="Max threads to backfill (0 = all)")
@click.option("--start", default=0, help="Start offset in index")
def thread_backfill(limit: int, start: int):
    """Backfill the threads FT.SEARCH index from existing thread data."""

    async def _backfill():
        pass


@thread.command("backfill-empty-subjects")
@click.option("--limit", "-l", default=0, help="Max threads to update (0 = all)")
@click.option("--start", default=0, help="Start offset in index")
@click.option("--dry-run", is_flag=True, help="Report only; no writes")
def thread_backfill_empty_subjects(limit: int, start: int, dry_run: bool):
    """Set subject for threads where subject is empty/placeholder.

    Derives subject from context.original_query or the first user message.
    """

    async def _run():
        from rich.console import Console

        from redis_sre_agent.core.redis import get_redis_client
        from redis_sre_agent.core.threads import ThreadManager

        console = Console()
        tm = ThreadManager(redis_client=get_redis_client())

        client = await tm._get_client()
        scanned = 0
        updated = 0

        # Prefer scanning the FT hash keys to include threads not present in the zset
        from redis_sre_agent.core.redis import SRE_THREADS_INDEX

        cursor = 0
        page = 1000
        while True:
            cursor, keys = await client.scan(
                cursor=cursor, match=f"{SRE_THREADS_INDEX}:*", count=page
            )
            if not keys:
                if cursor == 0:
                    break
            for key in keys or []:
                if limit and scanned >= limit:
                    break
                redis_key = key.decode() if isinstance(key, bytes) else key
                prefix = f"{SRE_THREADS_INDEX}:"
                tid = redis_key[len(prefix) :] if redis_key.startswith(prefix) else redis_key

                state = await tm.get_thread(tid)
                if not state:
                    scanned += 1
                    continue
                subj = (state.metadata.subject or "").strip()
                if subj and subj.lower() not in {"untitled", "unknown"}:
                    scanned += 1
                    continue

                # Determine candidate subject
                candidate = None
                ctx = state.context or {}
                oq = ctx.get("original_query")
                if isinstance(oq, str) and oq.strip():
                    candidate = oq.strip()
                else:
                    msgs = ctx.get("messages") if isinstance(ctx, dict) else None
                    if isinstance(msgs, list):
                        for m in msgs:
                            if isinstance(m, dict) and m.get("role") == "user":
                                c = m.get("content")
                                if isinstance(c, str) and c.strip():
                                    candidate = c.strip()
                                    break

                if not candidate:
                    scanned += 1
                    continue

                line = candidate.splitlines()[0].strip()
                if len(line) > 80:
                    line = line[:77].rstrip() + "\u2026"

                if dry_run:
                    console.print(f"[yellow]DRY RUN[/yellow] Would set subject for {tid} -> {line}")
                else:
                    await tm.set_thread_subject(tid, line)
                updated += 1
                scanned += 1

            if cursor == 0 or (limit and scanned >= limit):
                break

        console.print(f"[green]Done.[/green] Scanned: {scanned}, Subjects updated: {updated}")

    asyncio.run(_run())


@thread.command("purge")
@click.option(
    "--older-than", "older_than", help="Purge threads older than a duration (e.g. 7d, 24h, 3600s)"
)
@click.option("--all", "purge_all", is_flag=True, help="Purge ALL threads (dangerous)")
@click.option(
    "--include-tasks/--no-include-tasks",
    default=True,
    help="Also delete tasks that belong to each thread",
)
@click.option("--dry-run", is_flag=True, help="Show what would be deleted; make no changes")
@click.option("-y", "--yes", is_flag=True, help="Do not prompt for confirmation")
def thread_purge(
    older_than: str | None, purge_all: bool, include_tasks: bool, dry_run: bool, yes: bool
):
    """Delete threads in bulk with safeguards.

    By default requires --older-than DURATION unless --all is specified.
    """

    async def _run():
        from datetime import datetime, timedelta, timezone

        from rich.console import Console

        from redis_sre_agent.core.keys import RedisKeys
        from redis_sre_agent.core.redis import SRE_TASKS_INDEX, SRE_THREADS_INDEX, get_redis_client
        from redis_sre_agent.core.tasks import delete_task as delete_task_core
        from redis_sre_agent.core.threads import ThreadManager

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
                # default seconds if no suffix
                return timedelta(seconds=float(s))
            except Exception as e:
                raise ValueError(f"Invalid duration '{s}': {e}")

        if not purge_all and not older_than:
            console.print(
                "[red]Refusing to purge without a scope. Provide --older-than or --all.[/red]"
            )
            return

        # Confirmation
        if not dry_run and not yes:
            scope = "ALL threads" if purge_all else f"threads older than {older_than}"
            console.print(f"You are about to delete [bold]{scope}[/bold].")
            console.print("Add --dry-run to preview or -y to confirm.")
            return

        tm = ThreadManager(redis_client=get_redis_client())
        client = await tm._get_client()

        # Compute cutoff timestamp if scoped by age
        cutoff_ts = None
        if older_than:
            delta = _parse_duration(older_than)
            cutoff_ts = (datetime.now(timezone.utc) - delta).timestamp()

        cursor = 0
        page = 1000
        scanned = 0
        deleted = 0
        deleted_tasks = 0

        while True:
            cursor, keys = await client.scan(
                cursor=cursor, match=f"{SRE_THREADS_INDEX}:*", count=page
            )
            if not keys and cursor == 0:
                break
            for k in keys or []:
                redis_key = k.decode() if isinstance(k, bytes) else k
                tid = (
                    redis_key.split(":", 1)[1]
                    if ":" in redis_key
                    else redis_key[len(f"{SRE_THREADS_INDEX}:") :]
                )

                # Age filter via FT hash field 'created_at' (numeric seconds)
                eligible = True
                if cutoff_ts is not None:
                    try:
                        created = await client.hget(redis_key, "created_at")
                        created_f = float(
                            created.decode() if isinstance(created, bytes) else (created or 0)
                        )
                        if created_f <= 0 or created_f > cutoff_ts:
                            eligible = False
                    except Exception:
                        eligible = False

                if not purge_all and not eligible:
                    scanned += 1
                    continue

                # Plan deletion
                if dry_run:
                    console.print(f"[yellow]DRY RUN[/yellow] Would delete thread {tid}")
                else:
                    # Optionally delete tasks belonging to this thread
                    if include_tasks:
                        task_ids = await client.zrevrange(RedisKeys.thread_tasks_index(tid), 0, -1)
                        for raw in task_ids or []:
                            t_id = raw.decode() if isinstance(raw, bytes) else raw
                            try:
                                await delete_task_core(task_id=t_id, redis_client=client)
                                deleted_tasks += 1
                            except Exception:
                                # Best-effort
                                pass
                        # Also clean up any leftover FT docs without KV
                        t_cursor = 0
                        while True:
                            t_cursor, t_keys = await client.scan(
                                cursor=t_cursor, match=f"{SRE_TASKS_INDEX}:*", count=1000
                            )
                            for tk in t_keys or []:
                                tk_s = tk.decode() if isinstance(tk, bytes) else tk
                                # If thread_id matches, delete FT doc; skip if not
                                thid = await client.hget(tk_s, "thread_id")
                                thid_s = thid.decode() if isinstance(thid, bytes) else thid
                                if thid_s == tid:
                                    await client.delete(tk_s)
                            if t_cursor == 0:
                                break

                    ok = await tm.delete_thread(tid)
                    if ok:
                        # Also remove the FT hash doc for this thread (best-effort)
                        try:
                            await client.delete(f"{SRE_THREADS_INDEX}:{tid}")
                        except Exception:
                            pass
                        deleted += 1
                scanned += 1

            if cursor == 0:
                break

        console.print(
            f"[green]Done.[/green] Scanned: {scanned}, Threads deleted: {deleted}"
            + (f", Tasks deleted: {deleted_tasks}" if include_tasks else "")
        )

    asyncio.run(_run())
