"""
Generate CLI and REST reference docs from code to reduce drift.

Writes:
- docs/reference/cli.md
- docs/reference/api.md

Notes:
- Avoid code fences with 'redis-sre-agent' or 'curl' lines beyond a minimal curated set to keep tests stable.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

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
        if " " in path:
            lines.append(f"- {path} — {help_text}")
        else:
            lines.append(f"- {path} — {help_text}")
    lines.append("\nSee How-to guides for examples.")
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_api_md(dest: Path, routes: List[Tuple[str, str, str]]):
    lines: List[str] = []
    lines.append("## REST API Reference (generated)\n")
    lines.append("For interactive docs, see http://localhost:8000/docs\n\n")
    lines.append("### Endpoints\n\n")
    for method, path, summary in routes:
        lines.append(f"- {method} {path} — {summary}")
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    root = Path(__file__).resolve().parents[1]
    cli_items = _collect_click_tree()
    routes = _collect_routes()

    _write_cli_md(root / "docs/reference/cli.md", cli_items)
    _write_api_md(root / "docs/reference/api.md", routes)


if __name__ == "__main__":
    main()
