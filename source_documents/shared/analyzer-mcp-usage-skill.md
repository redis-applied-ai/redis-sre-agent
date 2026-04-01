---
title: Analyzer MCP Usage Skill
doc_type: skill
category: shared
name: analyzer-mcp-usage
summary: Use Analyzer MCP tools to discover accounts, packages, and triage support packages with evidence-backed Redis Enterprise reasoning.
priority: normal
pinned: false
---

Use this skill when the user wants to work with Redis Enterprise Analyzer through MCP.

1. If the user asks what is in Analyzer, start with:
   - `analyzer_list_accounts`
   - `analyzer_list_packages`
   - `analyzer_list_clusters` if you need cluster candidates
2. If the user gives only a partial cluster name, use `analyzer_list_clusters(query=...)` and only continue once you have an exact cluster.
3. If the user gives a package hash, use `analyzer_get_package_by_hash`, then move to package inspection.
4. If the user gives exact `account_id` and `cluster_name`, use:
   - `analyzer_get_latest_cluster_package`
   - `analyzer_get_cluster_packages`
5. If the user gives a `package_id`, or once you find one, triage in this order:
   - `analyzer_get_package_overview`
   - `analyzer_get_package_health_checks`
   - `analyzer_get_package_alerts`
   - `analyzer_get_package_events`
   - then branch into `analyzer_get_package_databases`, `analyzer_get_package_nodes`, `analyzer_get_package_topology`, `analyzer_get_database_slowlog`, `analyzer_get_database_commands`, and `analyzer_get_package_time_series`
6. Explain findings in Redis Enterprise terms. Do not just dump tool output. State the most important findings, why they matter, and what to inspect next.

Important constraints:

- `account_id` must be passed as a string
- do not invent accounts, packages, or clusters
- the current Analyzer MCP surface does not support arbitrary raw log grep
- hostname lookup is only reliable if the hostname appears in searchable package or cluster metadata
