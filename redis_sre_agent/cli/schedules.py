"""Schedule CLI commands."""

from __future__ import annotations

import asyncio
import json as _json
from datetime import datetime

import click
from docket import Docket
from rich.console import Console
from rich.table import Table

from redis_sre_agent.core.docket_tasks import get_redis_url, process_agent_turn
from redis_sre_agent.core.keys import RedisKeys
from redis_sre_agent.core.redis import get_redis_client
from redis_sre_agent.core.schedules import get_schedule
from redis_sre_agent.core.tasks import TaskManager
from redis_sre_agent.core.threads import ThreadManager


@click.group()
def schedule():
    """Schedule management commands."""
    pass


@schedule.command("list")
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
@click.option(
    "--tz",
    required=False,
    help="IANA timezone (e.g. 'America/Los_Angeles'). Defaults to local time",
)
@click.option("--limit", "-l", default=50, help="Number of schedules to show")
def schedules_list(as_json: bool, tz: str | None, limit: int):
    """List schedules in the system."""

    async def _list():
        import json as _json
        from datetime import datetime

        from rich.console import Console
        from rich.table import Table

        from redis_sre_agent.core.schedules import list_schedules

        try:
            items = await list_schedules()
        except Exception as e:
            if as_json:
                print(_json.dumps({"error": str(e)}))
            else:
                click.echo(f"❌ Error: {e}")
            return

        if as_json:
            print(_json.dumps(items[:limit], indent=2))
            return

        try:
            from zoneinfo import ZoneInfo as _ZoneInfo

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
                return ts or "-"

        if not items:
            click.echo("No schedules found.")
            return

        console = Console()
        table = Table(title="Schedules", show_lines=False)
        table.add_column("ID", no_wrap=True)
        table.add_column("Name")
        table.add_column("Enabled", no_wrap=True)
        table.add_column("Interval", no_wrap=True)
        table.add_column("Next Run", no_wrap=True)
        table.add_column("Last Run", no_wrap=True)

        for s in items[:limit]:
            interval = f"{s.get('interval_type') or '-'} {s.get('interval_value') or 0}"
            enabled = "yes" if s.get("enabled") else "no"
            table.add_row(
                s.get("id") or "-",
                s.get("name") or "Untitled",
                enabled,
                interval,
                _fmt(s.get("next_run_at")),
                _fmt(s.get("last_run_at")),
            )

        console.print(table)

    asyncio.run(_list())


@schedule.command("get")
@click.argument("schedule_id")
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
@click.option(
    "--tz",
    required=False,
    help="IANA timezone (e.g. 'America/Los_Angeles'). Defaults to local time",
)
def schedules_get(schedule_id: str, as_json: bool, tz: str | None):
    """Get a single schedule by ID."""

    async def _get():
        import json as _json
        from datetime import datetime

        from rich.console import Console
        from rich.table import Table

        from redis_sre_agent.core.schedules import get_schedule

        try:
            s = await get_schedule(schedule_id)
        except Exception as e:
            payload = {"error": str(e), "id": schedule_id}
            if as_json:
                print(_json.dumps(payload))
            else:
                click.echo(f"❌ Error: {e}")
            return

        if not s:
            msg = {"error": "Schedule not found", "id": schedule_id}
            if as_json:
                print(_json.dumps(msg))
            else:
                click.echo("❌ Schedule not found")
            return

        if as_json:
            print(_json.dumps(s, indent=2))
            return

        try:
            from zoneinfo import ZoneInfo as _ZoneInfo

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
                return ts or "-"

        console = Console()
        table = Table(title=f"Schedule {schedule_id}")
        table.add_column("Field", no_wrap=True)
        table.add_column("Value")
        table.add_row("ID", s.get("id") or "-")
        table.add_row("Name", s.get("name") or "Untitled")
        table.add_row("Description", s.get("description") or "-")
        table.add_row("Enabled", "yes" if s.get("enabled") else "no")
        table.add_row("Interval Type", s.get("interval_type") or "-")
        table.add_row("Interval Value", str(s.get("interval_value") or 0))
        table.add_row("Redis Instance", s.get("redis_instance_id") or "-")
        table.add_row("Created", _fmt(s.get("created_at")))
        table.add_row("Updated", _fmt(s.get("updated_at")))
        table.add_row("Last Run", _fmt(s.get("last_run_at")))
        table.add_row("Next Run", _fmt(s.get("next_run_at")))
        console.print(table)

        instr = (s.get("instructions") or "").strip()
        if instr:
            it = Table(title="Instructions")
            it.add_column("Text")
            it.add_row(instr)
            console.print(it)

    asyncio.run(_get())


@schedule.command("create")
@click.option("--name", required=True, help="Schedule name")
@click.option(
    "--interval-type",
    type=click.Choice(["minutes", "hours", "days", "weeks"], case_sensitive=False),
    required=True,
)
@click.option("--interval-value", type=int, required=True)
@click.option("--instructions", required=True, help="Agent instructions to execute")
@click.option("--redis-instance-id", required=False)
@click.option("--description", required=False)
@click.option("--enabled/--disabled", default=True, help="Enable immediately (default: enabled)")
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
def schedules_create(
    name: str,
    interval_type: str,
    interval_value: int,
    instructions: str,
    redis_instance_id: str | None,
    description: str | None,
    enabled: bool,
    as_json: bool,
):
    """Create a new schedule."""

    async def _create():
        import json as _json
        from datetime import datetime, timezone

        from redis_sre_agent.core.schedules import Schedule, store_schedule

        try:
            sched = Schedule(
                name=name,
                description=description,
                interval_type=interval_type.lower(),
                interval_value=interval_value,
                redis_instance_id=redis_instance_id,
                instructions=instructions,
                enabled=enabled,
            )
            # Set initial next_run_at
            sched.next_run_at = sched.calculate_next_run().isoformat()
            # Ensure updated_at reflects creation
            sched.updated_at = datetime.now(timezone.utc).isoformat()

            ok = await store_schedule(sched.model_dump())
            if not ok:
                raise RuntimeError("Failed to store schedule")

            payload = {"id": sched.id, "status": "created"}
            if as_json:
                print(_json.dumps(payload))
            else:
                click.echo(f"✅ Created schedule {sched.id}")
        except Exception as e:
            if as_json:
                print(_json.dumps({"error": str(e)}))
            else:
                click.echo(f"❌ Error: {e}")

    asyncio.run(_create())


@schedule.command("update")
@click.argument("schedule_id")
@click.option("--name")
@click.option("--description")
@click.option("--instructions")
@click.option("--redis-instance-id")
@click.option(
    "--interval-type",
    type=click.Choice(["minutes", "hours", "days", "weeks"], case_sensitive=False),
)
@click.option("--interval-value", type=int)
@click.option("--enable/--disable", default=None, help="Enable or disable schedule")
@click.option(
    "--recalc-next-run/--keep-next-run",
    default=True,
    help="Recalculate next_run_at when interval changes (default: recalc)",
)
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
def schedules_update(
    schedule_id: str,
    name: str | None,
    description: str | None,
    instructions: str | None,
    redis_instance_id: str | None,
    interval_type: str | None,
    interval_value: int | None,
    enable: bool | None,
    recalc_next_run: bool,
    as_json: bool,
):
    """Update fields of an existing schedule."""

    async def _update():
        import json as _json
        from datetime import datetime, timezone

        from redis_sre_agent.core.schedules import Schedule, get_schedule, store_schedule

        try:
            current = await get_schedule(schedule_id)
            if not current:
                raise RuntimeError("Schedule not found")

            # Merge updates
            data = dict(current)
            if name is not None:
                data["name"] = name
            if description is not None:
                data["description"] = description
            if instructions is not None:
                data["instructions"] = instructions
            if redis_instance_id is not None:
                data["redis_instance_id"] = redis_instance_id
            if interval_type is not None:
                data["interval_type"] = interval_type.lower()
            if interval_value is not None:
                data["interval_value"] = interval_value
            if enable is not None:
                data["enabled"] = bool(enable)

            # Validate with model; preserve id and created_at
            data["id"] = current.get("id")
            data["created_at"] = current.get("created_at")

            sched = Schedule(**data)

            # Optionally recalc next_run_at when interval changed or explicitly requested
            changed_interval = (interval_type is not None) or (interval_value is not None)
            if recalc_next_run and (
                changed_interval or (enable is True and not current.get("enabled", True))
            ):
                sched.next_run_at = sched.calculate_next_run().isoformat()

            sched.updated_at = datetime.now(timezone.utc).isoformat()

            ok = await store_schedule(sched.model_dump())
            if not ok:
                raise RuntimeError("Failed to store schedule")

            payload = {"id": sched.id, "status": "updated"}
            if as_json:
                print(_json.dumps(payload))
            else:
                click.echo(f"✅ Updated schedule {sched.id}")
        except Exception as e:
            if as_json:
                print(_json.dumps({"error": str(e), "id": schedule_id}))
            else:
                click.echo(f"❌ Error: {e}")

    asyncio.run(_update())


@schedule.command("enable")
@click.argument("schedule_id")
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
def schedules_enable(schedule_id: str, as_json: bool):
    """Enable a schedule."""

    async def _enable():
        import json as _json
        from datetime import datetime, timezone

        from redis_sre_agent.core.schedules import Schedule, get_schedule, store_schedule

        try:
            current = await get_schedule(schedule_id)
            if not current:
                raise RuntimeError("Schedule not found")

            current["enabled"] = True
            sched = Schedule(**current)
            # If missing next_run_at, compute one
            if not sched.next_run_at:
                sched.next_run_at = sched.calculate_next_run().isoformat()
            sched.updated_at = datetime.now(timezone.utc).isoformat()

            ok = await store_schedule(sched.model_dump())
            if not ok:
                raise RuntimeError("Failed to store schedule")

            payload = {"id": sched.id, "status": "enabled"}
            if as_json:
                print(_json.dumps(payload))
            else:
                click.echo(f"✅ Enabled schedule {sched.id}")
        except Exception as e:
            if as_json:
                print(_json.dumps({"error": str(e), "id": schedule_id}))
            else:
                click.echo(f"❌ Error: {e}")

    asyncio.run(_enable())


@schedule.command("disable")
@click.argument("schedule_id")
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
def schedules_disable(schedule_id: str, as_json: bool):
    """Disable a schedule."""

    async def _disable():
        import json as _json
        from datetime import datetime, timezone

        from redis_sre_agent.core.schedules import Schedule, get_schedule, store_schedule

        try:
            current = await get_schedule(schedule_id)
            if not current:
                raise RuntimeError("Schedule not found")

            current["enabled"] = False
            sched = Schedule(**current)
            sched.updated_at = datetime.now(timezone.utc).isoformat()

            ok = await store_schedule(sched.model_dump())
            if not ok:
                raise RuntimeError("Failed to store schedule")

            payload = {"id": sched.id, "status": "disabled"}
            if as_json:
                print(_json.dumps(payload))
            else:
                click.echo(f"✅ Disabled schedule {sched.id}")
        except Exception as e:
            if as_json:
                print(_json.dumps({"error": str(e), "id": schedule_id}))
            else:
                click.echo(f"❌ Error: {e}")

    asyncio.run(_disable())


@schedule.command("delete")
@click.argument("schedule_id")
@click.option("--yes", is_flag=True, help="Skip confirmation")
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
def schedules_delete(schedule_id: str, yes: bool, as_json: bool):
    """Delete a schedule."""

    async def _delete():
        import json as _json

        from redis_sre_agent.core.schedules import delete_schedule

        try:
            if not yes and not as_json:
                if not click.confirm(f"Delete schedule {schedule_id}?", default=False):
                    click.echo("Cancelled")
                    return

            ok = await delete_schedule(schedule_id)
            if not ok:
                raise RuntimeError("Delete failed or schedule not found")

            payload = {"id": schedule_id, "status": "deleted"}
            if as_json:
                print(_json.dumps(payload))
            else:
                click.echo(f"✅ Deleted schedule {schedule_id}")
        except Exception as e:
            if as_json:
                print(_json.dumps({"error": str(e), "id": schedule_id}))
            else:
                click.echo(f"❌ Error: {e}")

    asyncio.run(_delete())


@schedule.command("run-now")
@click.argument("schedule_id")
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
def schedules_run_now(schedule_id: str, as_json: bool):
    """Trigger a schedule to run immediately (enqueue an agent turn)."""

    async def _run():
        import json as _json
        from datetime import datetime, timezone

        from redis_sre_agent.core.schedules import get_schedule

        try:
            schedule = await get_schedule(schedule_id)
            if not schedule:
                msg = {"error": "Schedule not found", "id": schedule_id}
                if as_json:
                    print(_json.dumps(msg))
                else:
                    click.echo("❌ Schedule not found")
                return

            # Prepare run context (mirror API behavior)
            current_time = datetime.now(timezone.utc)
            run_context = {
                "schedule_id": schedule_id,
                "schedule_name": schedule.get("name"),
                "automated": True,
                "manual_trigger": True,
                "original_query": schedule.get("instructions"),
                "scheduled_at": current_time.isoformat(),
            }
            if schedule.get("redis_instance_id"):
                run_context["instance_id"] = schedule.get("redis_instance_id")

            # Create a thread for this run
            redis_client = get_redis_client()
            thread_manager = ThreadManager(redis_client=redis_client)
            thread_id = await thread_manager.create_thread(
                user_id="scheduler",
                session_id=f"manual_schedule_{schedule_id}_{current_time.strftime('%Y%m%d_%H%M%S')}",
                initial_context=run_context,
                tags=["automated", "scheduled", "manual_trigger"],
            )
            # Set subject to schedule name (fallback to first line of instructions)
            try:
                subj = (schedule.get("name") or "").strip()
                if not subj:
                    instr = (schedule.get("instructions") or "").strip()
                    subj = instr.splitlines()[0][:80] if instr else "Scheduled Run"
                await thread_manager.set_thread_subject(thread_id, subj)
            except Exception:
                pass

            docket_task_id = None
            async with Docket(url=await get_redis_url(), name="sre_docket") as docket:
                key = f"manual_schedule_{schedule_id}_{current_time.strftime('%Y%m%d_%H%M%S')}"
                try:
                    task_func = docket.add(process_agent_turn, key=key)
                    docket_task_id = await task_func(
                        thread_id=thread_id,
                        message=schedule.get("instructions") or "",
                        context=run_context,
                    )
                except Exception as e:
                    if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
                        docket_task_id = "already_running"
                    else:
                        raise

            payload = {
                "schedule_id": schedule_id,
                "status": "pending",
                "scheduled_at": current_time.isoformat(),
                "thread_id": thread_id,
                "docket_task_id": str(docket_task_id) if docket_task_id is not None else None,
            }
            if as_json:
                print(_json.dumps(payload))
            else:
                click.echo(f"✅ Triggered schedule {schedule_id} (thread {thread_id})")
        except Exception as e:
            if as_json:
                print(_json.dumps({"error": str(e), "id": schedule_id}))
            else:
                click.echo(f"❌ Error: {e}")

    asyncio.run(_run())


@schedule.command("runs")
@click.argument("schedule_id")
@click.option("--json", "as_json", is_flag=True, help="Output JSON")
@click.option(
    "--tz",
    required=False,
    help="IANA timezone (e.g. 'America/Los_Angeles'). Defaults to local time",
)
@click.option("--limit", "limit", default=50, help="Number of runs to show")
def schedules_runs(schedule_id: str, as_json: bool, tz: str | None, limit: int):
    """List recent runs for a schedule."""

    async def _runs():
        try:
            sched = await get_schedule(schedule_id)
            if not sched:
                msg = {"error": "Schedule not found", "id": schedule_id}
                if as_json:
                    print(_json.dumps(msg))
                else:
                    click.echo("❌ Schedule not found")
                return

            client = get_redis_client()
            thread_manager = ThreadManager(redis_client=client)

            summaries = await thread_manager.list_threads(user_id="scheduler", limit=200)
            runs = []
            task_manager = TaskManager(redis_client=client)

            for summary in summaries:
                thread_id = summary["thread_id"]
                state = await thread_manager.get_thread(thread_id)
                if not state or state.context.get("schedule_id") != schedule_id:
                    continue

                # Default values
                task_id = None
                task_status = "queued"
                started_at = summary.get("created_at")
                completed_at = None

                # Look up the latest task for this thread
                try:
                    zkey = RedisKeys.thread_tasks_index(thread_id)
                    tids = await client.zrevrange(zkey, 0, 0)
                    if tids:
                        tid0 = tids[0]
                        if isinstance(tid0, bytes):
                            tid0 = tid0.decode()
                        task_id = tid0
                except Exception:
                    task_id = None

                if task_id:
                    try:
                        task = await task_manager.get_task_state(task_id)
                    except Exception:
                        task = None
                    if task:
                        # Normalize enum or str to a string status value
                        task_status = getattr(task.status, "value", str(task.status))
                        started_at = task.metadata.created_at or started_at
                        if task_status == "done":
                            completed_at = task.metadata.updated_at

                scheduled_at = state.context.get("scheduled_at") or summary.get("created_at")

                runs.append(
                    {
                        "thread_id": thread_id,
                        "task_id": task_id,
                        "schedule_id": schedule_id,
                        "status": task_status,
                        "scheduled_at": scheduled_at,
                        "started_at": started_at,
                        "completed_at": completed_at,
                        "created_at": summary.get("created_at"),
                        "subject": summary.get("subject") or "Scheduled Run",
                    }
                )

            # Sort and trim
            def _to_sort_key(val: str | None) -> float:
                if not val:
                    return 0.0
                try:
                    dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
                    return dt.timestamp()
                except Exception:
                    return 0.0

            runs.sort(key=lambda x: _to_sort_key(x.get("scheduled_at")), reverse=True)
            runs = runs[:limit]

            if as_json:
                print(_json.dumps(runs, indent=2))
                return

            # Pretty output
            try:
                from zoneinfo import ZoneInfo as _ZoneInfo

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
                        dt = dt.astimezone()
                    return dt.strftime("%Y-%m-%d %H:%M:%S %Z")
                except Exception:
                    return ts or "-"

            console = Console()
            table = Table(title=f"Runs for schedule {schedule_id}")
            table.add_column("Task", no_wrap=True)
            table.add_column("Thread", no_wrap=True)
            table.add_column("Status", no_wrap=True)
            table.add_column("Scheduled")
            table.add_column("Started")
            table.add_column("Completed")
            table.add_column("Subject")

            def _short(s: str) -> str:
                return s[:8] if s and len(s) > 8 else (s or "-")

            for r in runs:
                table.add_row(
                    _short(r.get("task_id") or "-"),
                    _short(r.get("thread_id") or "-"),
                    r.get("status") or "-",
                    _fmt(r.get("scheduled_at")),
                    _fmt(r.get("started_at")),
                    _fmt(r.get("completed_at")),
                    r.get("subject") or "Scheduled Run",
                )

            console.print(table)
        except Exception as e:
            if as_json:
                print(_json.dumps({"error": str(e), "id": schedule_id}))
            else:
                click.echo(f"❌ Error: {e}")

    asyncio.run(_runs())
