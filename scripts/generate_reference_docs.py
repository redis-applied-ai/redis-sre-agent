"""
Generate CLI and REST reference docs from code to reduce drift.

Writes:
- docs/api/cli_ref.md   (CLI reference; RedisVL-style command tables)
- docs/api/rest_api.md  (FastAPI route tables grouped by area)

The CLI doc emits:
- a top-level "Command groups" summary table
- one section per group with a "Subcommand | Arguments | Description" table

The REST doc emits one "Method | Path | Summary" table per area.
"""

from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
from typing import Dict, List, Tuple

import click

from redis_sre_agent.api.app import app
from redis_sre_agent.cli.main import main as cli_main


def _is_group(cmd) -> bool:
    return hasattr(cmd, "get_command")


def _short_help(cmd) -> str:
    text = (getattr(cmd, "help", None) or getattr(cmd, "short_help", None) or "").strip()
    return text.split("\n")[0].strip()


def _required_signature(cmd: click.Command) -> str:
    """Compact signature of required positional arguments and required options.

    Pipes in choice metavars are escaped so the cell stays a single
    Markdown table cell.
    """
    parts: List[str] = []
    fake_ctx = click.Context(cmd)
    for p in cmd.params:
        if isinstance(p, click.Argument):
            metavar = (p.make_metavar(fake_ctx) or p.name.upper()).replace("|", "\\|")
            parts.append(f"`{metavar}`")
        elif isinstance(p, click.Option) and p.required:
            flag = p.opts[0]
            metavar = (p.make_metavar(fake_ctx) or "").replace("|", "\\|")
            if metavar and metavar != "BOOLEAN":
                parts.append(f"`{flag} {metavar}`")
            else:
                parts.append(f"`{flag}`")
    return " ".join(parts)


def _md_escape(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ").strip()


def _collect_groups() -> List[Tuple[str, str, click.Command, List[Tuple[str, click.Command]]]]:
    """Return [(group_name, group_help, group_cmd, [(sub_name, sub_cmd), ...])]."""
    ctx = click.Context(cli_main)
    out: List[Tuple[str, str, click.Command, List[Tuple[str, click.Command]]]] = []
    for name in cli_main.list_commands(ctx):
        top = cli_main.get_command(ctx, name)
        if top is None:
            continue
        subs: List[Tuple[str, click.Command]] = []
        if _is_group(top):
            sub_ctx = click.Context(top)
            for sub_name in top.list_commands(sub_ctx):
                sub = top.get_command(sub_ctx, sub_name)
                if sub is not None:
                    subs.append((sub_name, sub))
        out.append((name, _short_help(top), top, subs))
    return out


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


def _write_cli_md(
    dest: Path,
    groups: List[Tuple[str, str, click.Command, List[Tuple[str, click.Command]]]],
):
    lines: List[str] = []
    lines.append("---")
    lines.append("description: Auto-generated reference for every redis-sre-agent subcommand.")
    lines.append("---")
    lines.append("")
    lines.append("# CLI reference")
    lines.append("")
    lines.append(
        "This page is generated from the Click command tree. Run "
        "`redis-sre-agent <command> --help` for full flag descriptions and examples. "
        "For end-to-end workflows, see "
        "[CLI workflows](../user_guide/how_to_guides/cli_workflows.md)."
    )
    lines.append("")
    lines.append("## Command groups")
    lines.append("")
    lines.append("| Command | Description |")
    lines.append("|---|---|")
    for name, help_text, top, subs in groups:
        lines.append(f"| `redis-sre-agent {name}` | {_md_escape(help_text) or '—'} |")
    lines.append("")

    for name, help_text, top, subs in groups:
        if not subs:
            continue
        lines.append(f"## {name}")
        lines.append("")
        if help_text:
            lines.append(_md_escape(help_text))
            lines.append("")
        lines.append("| Subcommand | Arguments | Description |")
        lines.append("|---|---|---|")
        for sub_name, sub in subs:
            sig = _required_signature(sub) or ""
            lines.append(
                f"| `redis-sre-agent {name} {sub_name}` | {sig} | "
                f"{_md_escape(_short_help(sub)) or '—'} |"
            )
        lines.append("")

    # Top-level leaf commands (no subcommands) get a brief callout
    leaves = [g for g in groups if not g[3]]
    if leaves:
        lines.append("## Top-level commands")
        lines.append("")
        lines.append("| Command | Arguments | Description |")
        lines.append("|---|---|---|")
        for name, help_text, top, _ in leaves:
            sig = _required_signature(top) or ""
            lines.append(f"| `redis-sre-agent {name}` | {sig} | {_md_escape(help_text) or '—'} |")
        lines.append("")

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
    lines.append("---")
    lines.append("description: Auto-generated reference for the Redis SRE Agent FastAPI server.")
    lines.append("---")
    lines.append("")
    lines.append("# REST API reference")
    lines.append("")
    lines.append("This page is generated from the FastAPI route tree.")
    lines.append("")
    lines.append(
        "For live schemas and request models, start the API and open "
        "`http://localhost:8000/docs` (local) or `http://localhost:8080/docs` "
        "(Docker Compose)."
    )
    lines.append("")
    lines.append("## Start here")
    lines.append("")
    lines.append("- Health and readiness: `/`, `/api/v1/health`, `/api/v1/metrics`")
    lines.append("- Manage Redis targets: `/api/v1/instances`, `/api/v1/clusters`")
    lines.append(
        "- Run agent work: `/api/v1/tasks`, `/api/v1/threads`, `/api/v1/ws/tasks/{thread_id}`"
    )
    lines.append("- Search and ingest knowledge: `/api/v1/knowledge/*`")
    lines.append("- Schedule recurring checks: `/api/v1/schedules/*`")
    lines.append("- Analyze support packages: `/api/v1/support-packages/*`")
    lines.append("")
    lines.append(
        "For copy/paste workflows, see "
        "[API workflows](../user_guide/how_to_guides/api_workflows.md)."
    )

    for section, items in sections.items():
        if not items:
            continue
        lines.append("")
        lines.append(f"## {section}")
        lines.append("")
        lines.append("| Method | Path | Summary |")
        lines.append("|---|---|---|")
        for method, path, summary in items:
            lines.append(f"| `{method}` | `{path}` | {summary} |")
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    root = Path(__file__).resolve().parents[1]
    groups = _collect_groups()
    routes = _collect_routes()

    _write_cli_md(root / "docs/api/cli_ref.md", groups)
    _write_api_md(root / "docs/api/rest_api.md", routes)


if __name__ == "__main__":
    main()
