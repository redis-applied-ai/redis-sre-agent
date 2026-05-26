"""Feedback CLI subgroup — thin wrapper around core.feedback."""

from __future__ import annotations

import asyncio
import json
import re
import sys
from datetime import datetime, timedelta, timezone

import click

from redis_sre_agent.cli.logging_utils import log_cli_exception

_SINCE_RE = re.compile(r"^(\d+)([smhd])$")
_SINCE_UNITS = {"s": "seconds", "m": "minutes", "h": "hours", "d": "days"}

_VERDICT_CHOICES = click.Choice(["up", "down", "withdrawn"], case_sensitive=False)

_LIMIT_MAX = 500

_VALID_STATUSES = {"queued", "in_progress", "awaiting_approval", "done", "failed", "cancelled"}


def _parse_since(value: str) -> datetime:
    """Parse a duration string like '24h', '30m', '7d' into a UTC cutoff datetime.

    Raises click.BadParameter for ISO-8601 dates or unrecognised formats.
    """
    # Reject ISO-8601 explicitly (contains '-' digit pattern or 'T')
    if re.search(r"\d{4}-\d{2}-\d{2}", value) or "T" in value:
        raise click.BadParameter(
            "ISO-8601 dates are not supported in Phase 1. Use a duration like '24h', '30m', '7d'."
        )
    m = _SINCE_RE.match(value.strip())
    if not m:
        raise click.BadParameter(
            f"Invalid duration '{value}'. Expected format: <number><unit> where unit is s/m/h/d "
            "(e.g. '24h', '30m', '7d')."
        )
    amount = int(m.group(1))
    unit = _SINCE_UNITS[m.group(2)]
    delta = timedelta(**{unit: amount})
    return datetime.now(timezone.utc) - delta


@click.group()
def feedback():
    """Agent response feedback commands (up / down / withdraw / show / list)."""
    pass


@feedback.command("up")
@click.argument("task_id")
@click.option("--comment", default=None, help="Optional comment (max 2048 chars).")
def feedback_up(task_id: str, comment: str | None):
    """Submit a thumbs-up for TASK_ID."""

    async def _run():
        from redis_sre_agent.core.feedback import (
            FeedbackError,
            TaskNotFoundError,
            submit_feedback,
        )

        try:
            record = await submit_feedback(task_id, "up", comment)
        except TaskNotFoundError as exc:
            click.echo(str(exc), err=True)
            sys.exit(1)
        except FeedbackError as exc:
            log_cli_exception(__name__, "feedback CLI command failed", exc)
            click.echo(str(exc), err=True)
            sys.exit(1)
        except Exception as exc:
            log_cli_exception(__name__, "feedback CLI command failed", exc)
            click.echo(str(exc), err=True)
            sys.exit(1)

        print(record.model_dump_json(indent=2))

    asyncio.run(_run())


@feedback.command("down")
@click.argument("task_id")
@click.option("--comment", default=None, help="Optional comment (max 2048 chars).")
def feedback_down(task_id: str, comment: str | None):
    """Submit a thumbs-down for TASK_ID."""

    async def _run():
        from redis_sre_agent.core.feedback import (
            FeedbackError,
            TaskNotFoundError,
            submit_feedback,
        )

        try:
            record = await submit_feedback(task_id, "down", comment)
        except TaskNotFoundError as exc:
            click.echo(str(exc), err=True)
            sys.exit(1)
        except FeedbackError as exc:
            log_cli_exception(__name__, "feedback CLI command failed", exc)
            click.echo(str(exc), err=True)
            sys.exit(1)
        except Exception as exc:
            log_cli_exception(__name__, "feedback CLI command failed", exc)
            click.echo(str(exc), err=True)
            sys.exit(1)

        print(record.model_dump_json(indent=2))

    asyncio.run(_run())


@feedback.command("withdraw")
@click.argument("task_id")
def feedback_withdraw(task_id: str):
    """Withdraw feedback for TASK_ID (sets verdict to 'withdrawn')."""

    async def _run():
        from redis_sre_agent.core.feedback import (
            FeedbackError,
            TaskNotFoundError,
            submit_feedback,
        )

        try:
            record = await submit_feedback(task_id, "withdrawn")
        except TaskNotFoundError as exc:
            click.echo(str(exc), err=True)
            sys.exit(1)
        except FeedbackError as exc:
            log_cli_exception(__name__, "feedback CLI command failed", exc)
            click.echo(str(exc), err=True)
            sys.exit(1)
        except Exception as exc:
            log_cli_exception(__name__, "feedback CLI command failed", exc)
            click.echo(str(exc), err=True)
            sys.exit(1)

        print(record.model_dump_json(indent=2))

    asyncio.run(_run())


@feedback.command("show")
@click.argument("task_id")
def feedback_show(task_id: str):
    """Show current feedback for TASK_ID (joined view with task info).

    Prints JSON of the FeedbackView (with 'feedback' and 'task' keys), or
    literal 'null' when no feedback has been submitted yet.  Exits 0 in both
    cases.  Exits non-zero when the task does not exist or a Redis / validation
    error occurs.
    """

    async def _run():
        from redis_sre_agent.core.feedback import (
            TaskNotFoundError,
            get_feedback_view,
        )

        try:
            view = await get_feedback_view(task_id)
        except TaskNotFoundError as exc:
            click.echo(str(exc), err=True)
            sys.exit(1)
        except Exception as exc:
            log_cli_exception(__name__, "feedback CLI command failed", exc)
            click.echo(str(exc), err=True)
            sys.exit(1)

        if view is None:
            print("null")
        else:
            print(view.model_dump_json(indent=2))

    asyncio.run(_run())


@feedback.command("list")
@click.option(
    "--since",
    default=None,
    help="Only include records updated within this duration (e.g. '24h', '30m', '7d'). ISO-8601 dates are rejected.",
)
@click.option(
    "--verdict",
    type=_VERDICT_CHOICES,
    default=None,
    help="Filter by verdict: up, down, or withdrawn.",
)
@click.option(
    "--limit",
    default=50,
    show_default=True,
    help=f"Maximum rows to return (default 50, max {_LIMIT_MAX}). Values above {_LIMIT_MAX} are clamped.",
)
@click.option(
    "--table",
    "use_table",
    is_flag=True,
    default=False,
    help="Render output as a Rich table instead of JSON Lines.",
)
@click.option(
    "--status",
    default=None,
    help=("Filter by task status. Accepted values: " + ", ".join(sorted(_VALID_STATUSES)) + "."),
)
def feedback_list(
    since: str | None, verdict: str | None, limit: int, use_table: bool, status: str | None
):
    """List feedback views with optional filters.

    Default output is JSON Lines (one FeedbackView JSON object per line).
    Use --table for a Rich table.
    Results are sorted by feedback.updated_at descending before the limit is applied.
    --limit values above 500 are clamped to 500.
    --since rejects ISO-8601 dates; use durations like '24h', '7d', '30m'.
    """
    # Validate --since before entering async context so Click surfaces a clean error.
    cutoff_str: str | None = since
    if since is not None:
        try:
            _parse_since(since)
        except click.BadParameter as exc:
            click.echo(f"Error: {exc.format_message()}", err=True)
            sys.exit(1)

    # Validate --status before entering async context.
    if status is not None and status not in _VALID_STATUSES:
        click.echo(
            f"Error: invalid status {status!r}. Valid values: {', '.join(sorted(_VALID_STATUSES))}",
            err=True,
        )
        sys.exit(1)

    # Clamp --limit
    effective_limit = min(limit, _LIMIT_MAX)

    async def _run():
        from redis_sre_agent.core.feedback import FeedbackView, list_feedback_views

        try:
            views: list[FeedbackView] = await list_feedback_views(
                since=cutoff_str,
                verdict=verdict,
                status=status,
                limit=effective_limit,
            )
        except Exception as exc:
            log_cli_exception(__name__, "feedback list failed", exc)
            click.echo(str(exc), err=True)
            sys.exit(1)

        if use_table:
            _render_table(views)
        else:
            _render_jsonl(views)

    asyncio.run(_run())


def _truncate(text: str | None, max_len: int = 40) -> str:
    """Truncate text to max_len chars, appending ellipsis if truncated."""
    if not text:
        return ""
    if len(text) <= max_len:
        return text
    return text[:max_len] + "…"


def _render_jsonl(views: list) -> None:
    """Print one FeedbackView JSON object per line (no surrounding array)."""
    for view in views:
        print(json.dumps(view.model_dump(mode="json")))


def _render_table(views: list) -> None:
    """Render feedback views as a Rich table with six columns."""
    from rich.console import Console
    from rich.table import Table

    console = Console(width=200)

    if not views:
        console.print("[yellow]No feedback records found.[/yellow]")
        return

    table = Table(title="Feedback Records", show_lines=False)
    table.add_column("task_id", no_wrap=True)
    table.add_column("status", no_wrap=True)
    table.add_column("subject_preview")
    table.add_column("verdict", no_wrap=True)
    table.add_column("comment_preview")
    table.add_column("updated_at", no_wrap=True)

    _verdict_colors = {"up": "green", "down": "red", "withdrawn": "yellow"}

    for view in views:
        fb = view.feedback
        task = view.task
        color = _verdict_colors.get(fb.verdict, "white")
        table.add_row(
            fb.task_id,
            task.status,
            _truncate(task.subject),
            f"[{color}]{fb.verdict}[/{color}]",
            _truncate(fb.comment),
            fb.updated_at,
        )

    console.print(table)
