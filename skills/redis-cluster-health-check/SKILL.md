---
name: redis-cluster-health-check
title: Redis Cluster Health Check
description: Review a Redis Enterprise Analyzer support package and produce a TAM-ready cluster health check report. Use when the user asks to analyze a support package, run a cluster health check, review Analyzer findings, or produce customer-facing recommendations from a package id or package hash.
summary: Gather Analyzer health checks, cluster metadata, database details, and slowlog evidence through MCP tools, then produce a structured markdown report.
priority: high
version: latest
---

# Redis Cluster Health Check

Use this skill to turn a Redis Enterprise Analyzer support package into a TAM-ready markdown
report.

## Scope

- Use direct Analyzer MCP tools.
- Do not ask the agent to run packaged scripts. This runtime does not execute skill scripts.
- Do not tell the user to use `present_files` or save output under `/mnt/user-data/outputs/`
  unless they explicitly ask for a file artifact.
- If the package cannot be resolved or Analyzer data is incomplete, say so explicitly.

## Inputs

- Required: a package reference. This can be a package id or package hash.
- Optional: exact cluster name or account context when the reference is ambiguous.

## Workflow

### 1. Resolve the package

1. Call `analyzer_resolve_package(reference="<user reference>")`.
2. If the tool does not return an item, ask for a clearer package id, hash, or cluster context.
3. Capture the resolved `package_id`.
4. If package processing looks incomplete, call
   `analyzer_get_package_messages(package_id="<package_id>", limit=20)` and mention the gap.

### 2. Gather overview and scope

1. Call `analyzer_get_package_overview(package_id="<package_id>")`.
2. Record cluster name, software version, node count, database count, shard count, task status,
   active alerts, parser status, and health-check totals.
3. Use this for the report header and summary paragraph.

### 3. Pull non-OK health checks

1. Call
   `analyzer_get_package_health_checks(package_id="<package_id>", include_ok=false, limit=200)`.
2. Separate findings into cluster, node, and database scope.
3. Use [references/check_catalog.md](references/check_catalog.md) to interpret each check.
4. Treat `SKIP` as informational unless the skipped state itself is the finding, such as
   `ProcessSysInfo`.

### 4. Hydrate database names and configuration

1. Call
   `analyzer_get_package_databases(package_id="<package_id>", include_config=true, include_modules=true, include_replicas=true)`.
2. Build a lookup from database id to human-readable name.
3. Use database config for manual-review items such as AOF policy, persistence disabled, modules,
   and replica context.
4. Always write database findings as `<database name> (<id>)`.

### 5. Drill into slowlog only when needed

1. For each non-OK `Slowlog` database check, call
   `analyzer_get_database_slowlog(package_id="<package_id>", database_id=<id>, limit=200)`.
2. Use [references/slowlog_analysis.md](references/slowlog_analysis.md) to categorize the slow
   commands and decide whether the finding is worth calling out.
3. If the slowlog is low-volume and benign, say it was reviewed and no action is recommended.
4. If the dominant pattern is RediSearch, Lua, RedisJSON, or long-blocking traversal, use Redis
   best-practice guidance already available in the environment when helpful, but do not block the
   report on another skill.

### 6. Pull supporting evidence only when it improves the story

- Use `analyzer_get_package_nodes(package_id="<package_id>", include_shards=true)` when node
  checks fail or you need node and shard context.
- Use `analyzer_get_package_topology(package_id="<package_id>")` when database placement, endpoint
  overlap, or shard distribution needs explanation.
- Use `analyzer_get_package_alerts(package_id="<package_id>", status="active", limit=100)` when
  active alerts help corroborate the health-check story.
- Use `analyzer_get_package_time_series(package_id="<package_id>", scope="cluster", interval="last 24 hours")`
  or node and shard scope only when the user explicitly wants time-series evidence.

### 7. Write the report

1. Follow [references/output_template.md](references/output_template.md).
2. Apply [references/voice_and_style.md](references/voice_and_style.md).
3. State findings first and recommendations second.
4. Quantify every finding with Analyzer values.
5. Group repeated findings when many databases share the same issue.
6. Include the manual-review checklist for items Analyzer does not cover directly.

### 8. Deliver the result

- Default output is a single markdown report in the response.
- If the user explicitly wants a file, save it in the workspace and mention the path.
- Keep the conversational wrapper short. The markdown report is the main deliverable.

## Tool map

| Need | MCP tool |
|---|---|
| Resolve package id or hash | `analyzer_resolve_package` |
| Check Analyzer parser status | `analyzer_get_package_messages` |
| High-level package summary | `analyzer_get_package_overview` |
| Non-OK health checks | `analyzer_get_package_health_checks` |
| Database names and config | `analyzer_get_package_databases` |
| Slowlog drill-down | `analyzer_get_database_slowlog` |
| Node context | `analyzer_get_package_nodes` |
| Placement and shard distribution | `analyzer_get_package_topology` |
| Active alerts | `analyzer_get_package_alerts` |
| Optional trend evidence | `analyzer_get_package_time_series` |

## Guardrails

- Do not restate raw Analyzer payloads without interpretation.
- Do not invent metrics or health-check thresholds that are not present in Analyzer output.
- Do not use bare database ids when a database name is available.
- Do not overstate informational findings such as transient backup status or partially unbalanced
  placement when the evidence suggests low operational impact.
- Do not omit the manual-review section. Analyzer does not cover every item in a customer health
  check.
