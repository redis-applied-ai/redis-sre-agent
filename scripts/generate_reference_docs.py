"""
Generate CLI and REST reference docs from code to reduce drift.

Writes:
- docs/reference/cli.md
- docs/reference/api.md

Notes:
- Avoid code fences with 'redis-sre-agent' or 'curl' lines beyond a minimal curated set to keep tests stable.
"""

from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
from typing import Dict, List, Tuple

from redis_sre_agent.api.app import app
from redis_sre_agent.cli.main import main as cli_main


def _is_group(cmd) -> bool:
    return hasattr(cmd, "get_command")


def _collect_click_tree() -> List[Tuple[str, str]]:
    """Return a list of (command_path, help) for top-level and subcommands.

    command_path examples:
    - "query"
    - "schedule create"
    """
    import click

    ctx = click.Context(cli_main)
    items: List[Tuple[str, str]] = []

    for name in cli_main.list_commands(ctx):
        top = cli_main.get_command(ctx, name)
        if top is None:
            continue
        help_text = (getattr(top, "help", None) or getattr(top, "short_help", None) or "").strip()
        items.append((name, help_text))
        if _is_group(top):
            sub_ctx = click.Context(top)
            for sub_name in top.list_commands(sub_ctx):
                sub = top.get_command(sub_ctx, sub_name)
                if sub is None:
                    continue
                sub_help = (
                    getattr(sub, "help", None) or getattr(sub, "short_help", None) or ""
                ).strip()
                items.append((f"{name} {sub_name}", sub_help))
    return items


def _collect_routes() -> List[Tuple[str, str, str]]:
    """Return a list of (method, path, summary). Filters out HEAD/OPTIONS."""
    routes: List[Tuple[str, str, str]] = []
    for r in getattr(app, "routes", []):
        methods = sorted(
            set(m for m in getattr(r, "methods", set()) if m not in {"HEAD", "OPTIONS"})
        )
        path = getattr(r, "path", "")
        summary = getattr(r, "summary", "") or getattr(r, "name", "")
        if not methods or not path:
            continue
        for m in methods:
            routes.append((m, path, summary))
    # sort by path then method
    routes.sort(key=lambda x: (x[1], x[0]))
    return routes


def _write_cli_md(dest: Path, items: List[Tuple[str, str]]):
    lines: List[str] = []
    lines.append("## CLI Reference (generated)\n")
    lines.append("Generated from the Click command tree.\n\n")
    lines.append("### Commands\n\n")
    for path, help_text in items:
        # Take only the first line of help text to keep the list clean
        first_line = help_text.split("\n")[0].strip() if help_text else ""
        lines.append(f"- {path} — {first_line}")
    lines.append("\nSee How-to guides for examples.")
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_api_md(dest: Path, routes: List[Tuple[str, str, str]]):
    sections: Dict[str, List[Tuple[str, str, str]]] = OrderedDict(
        [
            ("Health & readiness", []),
            ("Clusters", []),
            ("Instances", []),
            ("Knowledge", []),
            ("Schedules", []),
            ("Support packages", []),
            ("Tasks, threads, and streaming", []),
            ("OpenAPI & docs", []),
            ("Other", []),
        ]
    )

    def section_for_path(path: str) -> str:
        if path in {"/", "/api/v1/", "/api/v1/health", "/api/v1/metrics", "/api/v1/metrics/health"}:
            return "Health & readiness"
        if path.startswith("/api/v1/clusters"):
            return "Clusters"
        if path.startswith("/api/v1/instances"):
            return "Instances"
        if path.startswith("/api/v1/knowledge"):
            return "Knowledge"
        if path.startswith("/api/v1/schedules"):
            return "Schedules"
        if path.startswith("/api/v1/support-packages"):
            return "Support packages"
        if (
            path.startswith("/api/v1/tasks")
            or path.startswith("/api/v1/threads")
            or path.startswith("/api/v1/ws")
        ):
            return "Tasks, threads, and streaming"
        if path in {"/docs", "/docs/oauth2-redirect", "/openapi.json", "/redoc"}:
            return "OpenAPI & docs"
        return "Other"

    for route in routes:
        sections[section_for_path(route[1])].append(route)

    lines: List[str] = []
    lines.append("## REST API Reference (generated)\n")
    lines.append(
        "This page is generated from the FastAPI route tree.\n\n"
        "For live schemas and request models, start the API and open "
        "`http://localhost:8000/docs` (local) or `http://localhost:8080/docs` "
        "(Docker Compose).\n\n"
    )
    lines.append("### Start here\n\n")
    lines.append("- Health and readiness: `/`, `/api/v1/health`, `/api/v1/metrics`")
    lines.append("- Manage Redis targets: `/api/v1/instances`, `/api/v1/clusters`")
    lines.append(
        "- Run agent work: `/api/v1/tasks`, `/api/v1/threads`, `/api/v1/ws/tasks/{thread_id}`"
    )
    lines.append("- Search and ingest knowledge: `/api/v1/knowledge/*`")
    lines.append("- Schedule recurring checks: `/api/v1/schedules/*`")
    lines.append("- Analyze support packages: `/api/v1/support-packages/*`\n")
    lines.append("For copy/paste workflows, see [Using the API](../how-to/api.md).\n")

    for section, items in sections.items():
        if not items:
            continue
        lines.append(f"\n### {section}\n")
        lines.append("| Method | Path | Summary |")
        lines.append("|---|---|---|")
        for method, path, summary in items:
            lines.append(f"| `{method}` | `{path}` | {summary} |")
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    root = Path(__file__).resolve().parents[1]
    cli_items = _collect_click_tree()
    routes = _collect_routes()

    _write_cli_md(root / "docs/reference/cli.md", cli_items)
    _write_api_md(root / "docs/reference/api.md", routes)


if __name__ == "__main__":
    main()
