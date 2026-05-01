"""Helpers for auditing CLI to MCP parity."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Iterable

import click

from redis_sre_agent.cli.main import main
from redis_sre_agent.mcp_server.server import mcp

EXCLUDED_CLI_COMMAND_PATHS = frozenset(
    {
        "eval compare",
        "eval list",
        "eval live-suite",
        "eval run",
        "mcp list-tools",
        "mcp serve",
        "worker start",
        "worker status",
        "worker stop",
    }
)

CLI_TO_MCP_TOOL_NAMES = {
    "cache clear": "redis_sre_cache_clear",
    "cache stats": "redis_sre_cache_stats",
    "cluster backfill-instance-links": "redis_sre_backfill_instance_links",
    "cluster create": "redis_sre_create_cluster",
    "cluster delete": "redis_sre_delete_cluster",
    "cluster get": "redis_sre_get_cluster",
    "cluster list": "redis_sre_list_clusters",
    "cluster update": "redis_sre_update_cluster",
    "index list": "redis_sre_list_indices",
    "index recreate": "redis_sre_recreate_indices",
    "index schema-status": "redis_sre_get_index_schema_status",
    "index sync-schemas": "redis_sre_sync_index_schemas",
    "instance create": "redis_sre_create_instance",
    "instance delete": "redis_sre_delete_instance",
    "instance get": "redis_sre_get_instance",
    "instance list": "redis_sre_list_instances",
    "instance test": "redis_sre_test_instance",
    "instance test-url": "redis_sre_test_redis_url",
    "instance update": "redis_sre_update_instance",
    "knowledge fragments": "redis_sre_get_knowledge_fragments",
    "knowledge related": "redis_sre_get_related_knowledge_fragments",
    "knowledge search": "redis_sre_knowledge_search",
    "pipeline cleanup": "redis_sre_cleanup_pipeline_batches",
    "pipeline full": "redis_sre_run_pipeline_full",
    "pipeline ingest": "redis_sre_run_pipeline_ingest",
    "pipeline prepare-sources": "redis_sre_prepare_source_documents",
    "pipeline runbooks": "redis_sre_generate_pipeline_runbooks",
    "pipeline scrape": "redis_sre_run_pipeline_scrape",
    "pipeline show-batch": "redis_sre_get_pipeline_batch",
    "pipeline status": "redis_sre_get_pipeline_status",
    "query": "redis_sre_query",
    "runbook evaluate": "redis_sre_evaluate_runbooks",
    "runbook generate": "redis_sre_generate_runbook",
    "schedule create": "redis_sre_create_schedule",
    "schedule delete": "redis_sre_delete_schedule",
    "schedule disable": "redis_sre_disable_schedule",
    "schedule enable": "redis_sre_enable_schedule",
    "schedule get": "redis_sre_get_schedule",
    "schedule list": "redis_sre_list_schedules",
    "schedule run-now": "redis_sre_run_schedule_now",
    "schedule runs": "redis_sre_list_schedule_runs",
    "schedule update": "redis_sre_update_schedule",
    "skills list": "redis_sre_list_skills",
    "skills read-reference": "redis_sre_get_skill_resource",
    "skills read-resource": "redis_sre_get_skill_resource",
    "skills scaffold": "redis_sre_scaffold_skill_package",
    "skills show": "redis_sre_get_skill",
    "support-package delete": "redis_sre_delete_support_package",
    "support-package extract": "redis_sre_extract_support_package",
    "support-package info": "redis_sre_get_support_package_info",
    "support-package list": "redis_sre_list_support_packages",
    "support-package upload": "redis_sre_upload_support_package",
    "task delete": "redis_sre_delete_task",
    "task get": "redis_sre_get_task",
    "task list": "redis_sre_list_tasks",
    "task purge": "redis_sre_purge_tasks",
    "thread backfill": "redis_sre_backfill_threads",
    "thread backfill-empty-subjects": "redis_sre_backfill_empty_thread_subjects",
    "thread backfill-scheduled-subjects": "redis_sre_backfill_scheduled_thread_subjects",
    "thread get": "redis_sre_get_thread",
    "thread list": "redis_sre_list_threads",
    "thread purge": "redis_sre_purge_threads",
    "thread reindex": "redis_sre_reindex_threads",
    "thread sources": "redis_sre_get_thread_sources",
    "thread trace": "redis_sre_get_thread_trace",
    "version": "redis_sre_version",
}


def _walk_click_commands(command: click.Command, prefix: tuple[str, ...]) -> set[str]:
    if isinstance(command, click.MultiCommand):
        ctx = click.Context(command)
        command_paths: set[str] = set()
        for name in command.list_commands(ctx):
            child = command.get_command(ctx, name)
            if child is None:
                continue
            command_paths.update(_walk_click_commands(child, prefix + (name,)))
        return command_paths
    return {" ".join(prefix)}


def list_cli_command_paths() -> set[str]:
    """Return every CLI leaf command path."""
    ctx = click.Context(main)
    command_paths: set[str] = set()
    for name in main.list_commands(ctx):
        child = main.get_command(ctx, name)
        if child is None:
            continue
        command_paths.update(_walk_click_commands(child, (name,)))
    return command_paths


def list_in_scope_cli_command_paths() -> set[str]:
    """Return CLI commands expected to have MCP parity."""
    return list_cli_command_paths() - EXCLUDED_CLI_COMMAND_PATHS


def list_mcp_tool_names() -> set[str]:
    """Return registered MCP tool names."""

    def _load_tool_names() -> set[str]:
        return {tool.name for tool in asyncio.run(mcp.list_tools())}

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return _load_tool_names()

    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(_load_tool_names).result()


def audit_cli_mcp_parity(
    *,
    cli_command_paths: Iterable[str] | None = None,
    mcp_tool_names: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Audit in-scope CLI leaf commands against MCP tool coverage."""
    if cli_command_paths is None:
        cli_paths = list_cli_command_paths()
        in_scope_paths = sorted(list_in_scope_cli_command_paths())
    else:
        cli_paths = set(cli_command_paths)
        in_scope_paths = sorted(cli_paths - EXCLUDED_CLI_COMMAND_PATHS)
    tool_names = set(list_mcp_tool_names() if mcp_tool_names is None else mcp_tool_names)
    excluded_paths = sorted(cli_paths & EXCLUDED_CLI_COMMAND_PATHS)
    stale_exclusions = sorted(EXCLUDED_CLI_COMMAND_PATHS - cli_paths)
    missing_cli_mappings = sorted(
        path for path in in_scope_paths if path not in CLI_TO_MCP_TOOL_NAMES
    )
    missing_mcp_tools = {
        path: CLI_TO_MCP_TOOL_NAMES[path]
        for path in in_scope_paths
        if path in CLI_TO_MCP_TOOL_NAMES and CLI_TO_MCP_TOOL_NAMES[path] not in tool_names
    }

    status = "ok"
    if missing_cli_mappings or missing_mcp_tools or stale_exclusions:
        status = "failed"

    return {
        "status": status,
        "cli_command_count": len(cli_paths),
        "in_scope_cli_command_count": len(in_scope_paths),
        "mcp_tool_count": len(tool_names),
        "excluded_cli_commands": excluded_paths,
        "stale_exclusions": stale_exclusions,
        "missing_cli_mappings": missing_cli_mappings,
        "missing_mcp_tools": missing_mcp_tools,
    }
