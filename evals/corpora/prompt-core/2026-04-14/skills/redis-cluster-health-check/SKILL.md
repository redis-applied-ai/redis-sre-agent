---
name: redis-cluster-health-check
document_hash: redis-cluster-health-check
title: Redis Cluster Health Check
description: Produce a customer-facing Redis Enterprise Analyzer findings report with proactive slowlog, events, and time-series drill-downs.
summary: Produce a customer-facing Redis Enterprise Analyzer findings report with proactive slowlog, events, and time-series drill-downs.
priority: critical
---
# Redis Cluster Health Check

Produce a customer-facing markdown findings document from a Redis Enterprise Analyzer support package using the MCP tools in this server.

IMPORTANT: Read this entire skill. Execute all steps and produce a report as described in the skill.

## Scope

This skill does:
- resolves a support package from package id, package hash, account, or cluster context (hostname, etc.)
- pulls Analyzer health-check results and filters to actionable findings
- enriches database findings with database names and targeted drill-downs
- analyzes slowlog findings from raw slowlog entries
- produces a markdown report with summary, cluster, node, database, rollup, manual review, and skipped-check sections

This skill does not:
- invent findings that Analyzer did not support with evidence
- replace TAM or CSM judgment on persistence intent, CVE exposure, or customer-specific tradeoffs

## Important: Work Proactively!

ALWAYS proactively pull events, slowlog entries, cluster AND node time series data, and anything else for the support package you are exploring.

Defaults:
1. Events: all severities, limit=200
2. Time series: cluster scope, interval=5m (add node scope if the cluster view suggests node imbalance)
3. Health checks

## Execution checklist

This is a complex, multi-step health-check workflow. Track progress against this checklist as you work. If your runtime supports separate progress updates, copy this checklist into those progress updates and check items off as they are completed. Do not include this checklist in the final customer-facing report; the final answer must follow the Output structure section exactly.

```text
Health Check Progress:
- [ ] Step 1: Resolve the support package with the narrowest reliable lookup
- [ ] Step 2: Gather overview, non-OK health checks, databases, alerts, events, nodes, topology, and cluster time series
- [ ] Step 3: Gather node time series when cluster metrics suggest node imbalance
- [ ] Step 4: Build the WARNING and CRITICAL findings set from Analyzer health checks
- [ ] Step 5: Run required drill-downs, including raw slowlog retrieval for every Slowlog finding
- [ ] Step 6: Draft the customer-facing report in the exact required markdown structure
- [ ] Step 7: Validate the draft against the output checklist, repair any gaps, and only then finalize
```

Step 1: Resolve the support package with the narrowest reliable lookup.
Use exact package ids, explicit hashes, or exact account and cluster context as described in the package-resolution workflow. Do not invent direct hostname lookup behavior.

Step 2: Gather the base and proactive context.
Before forming conclusions, pull overview, health checks, databases, alerts, events, nodes, topology, and cluster-scope time series at 5m interval. Use all severities for events with limit=200.

Step 3: Gather node time series when needed.
If cluster metrics, topology, node status, shard placement, or health checks suggest node imbalance, pull node-scope time series for the affected node or nodes before finalizing.

Step 4: Build the findings set from Analyzer evidence.
Include WARNING and CRITICAL health-check results, skip OK results, and preserve skipped checks for the audit trail. Do not invent findings that Analyzer did not support with tool evidence.

Step 5: Run targeted drill-downs.
For every Slowlog health check, call `analyzer_get_database_slowlog` and analyze the raw entries before writing the finding. Use the other drill-down tools described below for placement, node, task, CRDT, alert, or broad package context.

Step 6: Draft the final markdown report.
Use the exact required heading order, package metadata lines, severity counts, finding sections, rollup subsections, TAM manual review section, and skipped-check section.

Step 7: Validate and repair before finalizing.
Review the draft against the validation loop below. If any item fails, revise the report and run the validation loop again.

## Tool map

Use these tool names directly:

| Goal | Tool |
|---|---|
| list accounts | `analyzer_list_accounts` |
| search accounts | `analyzer_search_accounts` |
| get exact account | `analyzer_get_account` |
| list clusters | `analyzer_list_clusters` |
| get exact cluster | `analyzer_get_cluster` |
| list packages | `analyzer_list_packages` |
| get exact package | `analyzer_get_package` |
| resolve ambiguous package ref | `analyzer_resolve_package` |
| resolve explicit package hash | `analyzer_get_package_by_hash` |
| get package processing messages | `analyzer_get_package_messages` |
| get cluster package history | `analyzer_get_cluster_packages` |
| get latest package for cluster | `analyzer_get_latest_cluster_package` |
| get package summary and related ids | `analyzer_get_package_overview` |
| get filtered health-check results | `analyzer_get_package_health_checks` |
| get alerts | `analyzer_get_package_alerts` |
| get structured events | `analyzer_get_package_events` |
| get databases | `analyzer_get_package_databases` |
| get slowlog for one database | `analyzer_get_database_slowlog` |
| get command stats for one database | `analyzer_get_database_commands` |
| get nodes | `analyzer_get_package_nodes` |
| get topology | `analyzer_get_package_topology` |
| get metrics samples | `analyzer_get_package_time_series` |
| export normalized package JSON | `analyzer_export_package_json` |

## Workflow

### 1. Resolve the package

Use the narrowest reliable lookup:

1. If the user gives an exact `package_id`, use `analyzer_get_package`.
2. If the user gives a package-like reference and you do not know whether it is an id or hash, use `analyzer_resolve_package`.
3. If the user explicitly says it is a hash, use `analyzer_get_package_by_hash`.
4. If the user gives exact `account_id` and exact `cluster_name`, use `analyzer_get_latest_cluster_package` or `analyzer_get_cluster_packages`.
5. If the user gives only partial cluster context, use `analyzer_list_clusters(query=...)` and `analyzer_list_packages(cluster_query=...)`.
6. If package discovery is ambiguous, ask for one of: exact package id, exact package hash, exact account id, exact cluster name.

Do not pretend there is a direct hostname lookup tool. Only use hostname fragments if they are likely to appear in package or cluster metadata.

### 2. Gather the base package context

Start with:

- `analyzer_get_package_overview(package_id, include_sections=["cluster","databases","nodes","tasks","alerts","health_checks"])`
- `analyzer_get_package_health_checks(package_id, include_ok=false)`
- `analyzer_get_package_databases(package_id, include_modules=true, include_replicas=true)`

Use the overview for package summary and related ids. Use the health-check tool for the actual findings list. Use the database tool so every database finding is written with the database name and id.

If the package looks incomplete or still processing, inspect `analyzer_get_package_messages`.

Important distinction:

- `analyzer_get_package_health_checks` returns per-check findings with text statuses such as `OK`, `WARNING`, and `CRITICAL`
- `analyzer_get_package_overview` also includes summary pipeline state for parser and health-check processing, but those summaries are derived from numeric backend codes and are not the customer-facing finding severities

### 3. Build the findings set

Treat health-check results as follows:

- skip `OK`
- include `WARNING`
- include `CRITICAL`
- skipped checks do not become findings, except that `ProcessSysInfo` missing `sys_info` is itself a finding when present as a warning or critical result

Special case:

- `ProcessSysInfo` with missing `sys_info` is itself a finding and also explains why node checks such as ghost shards, glibc, swap, or process checks may have skipped.

Entity naming rules:

- database findings must use `<database name> (<id>)`
- node findings should use `node <id>`
- cluster findings should use the cluster name when available

### 4. Do targeted drill-downs

Pull extra evidence when needed. When you find issues that require a deeper look, let the user know, but don't ask if the user wants you to look deeper. Instead, do as much work for the user as possible. Complete the drill-downs yourself and report what you found.

Use these drill-downs:

- `Slowlog`: always call `analyzer_get_database_slowlog`; optionally call `analyzer_get_database_commands` to corroborate high-frequency command patterns
- `DBBalance`: use `analyzer_get_package_topology` if you need placement evidence
- `ShardsUsage`, `ShardsUsageDev`, `AvgKeySize`, `BdbStatuses`: `analyzer_get_package_databases` is usually enough
- `GhostShards`, `NodeStatuses`, `ShardStatuses`, `NodeProcesses`, `Swap`, `GlibcBad`: use `analyzer_get_package_nodes`
- `TasksSuccessful`, `StuckSM`: use `analyzer_get_package_overview` and `analyzer_get_package_events`
- `CRDTStatus`: use `analyzer_get_package_events`; use `analyzer_get_package_time_series` only if you need supporting metrics evidence
- alerts or timeline context: use `analyzer_get_package_alerts` and `analyzer_get_package_events`
- broad package inspection or unusual cases: use `analyzer_export_package_json`

## Slowlog analysis

When the `Slowlog` health check fires, the count alone is not useful. Inspect the raw slowlog entries and describe what is actually slow.

### How to read each entry

Each slowlog item includes an `entry` string shaped like:

```text
19.231 ['DEL', 'key1', 'key2', ...]
```

Interpret it as:
- leading float: duration in milliseconds
- first command token: Redis command name
- remaining tokens: arguments

### Command categories

Map commands into these categories:

| Category | Commands | Finding label |
|---|---|---|
| `long_blocking` | `KEYS`, `SCAN` with very high `COUNT`, `SMEMBERS`, `HGETALL`, `LRANGE 0 -1` on large collections | long-blocking traversal commands |
| `lua` | `EVAL`, `EVALSHA`, `FCALL`, `FCALL_RO` | long-running Lua scripts |
| `multi_key` | `DEL`, `UNLINK`, `MGET`, `MSET`, `MSETNX`, `EXISTS`, `TOUCH` with many keys | large multi-key operations |
| `redisearch` | `FT.SEARCH`, `FT.AGGREGATE`, `FT.INFO`, `FT.PROFILE`, `FT.EXPLAIN`, other `FT.*` | slow RediSearch queries |
| `redisjson` | `JSON.SET`, `JSON.GET`, `JSON.MGET`, `JSON.ARRAPPEND`, other `JSON.*` | slow JSON operations |
| `crdt` | `CRDT.EFFECT`, other `CRDT.*` | CRDT replication operations |
| `other` | anything else | other slow commands |

### Notable patterns

Call these out explicitly:

- `KEYS` is always noteworthy in production
- `SCAN` with `COUNT > 10000` is noteworthy
- multi-key operations touching more than roughly 20 keys are noteworthy
- a dominant `redisearch`, `redisjson`, `lua`, or `long_blocking` pattern is noteworthy

### When a slowlog finding is worth raising

Raise it when:

- problematic patterns are present
- there are at least 10 entries with a coherent pattern
- there are 50 or more entries even without a single dominant anti-pattern

Usually keep it brief or mark as reviewed without action when:

- there are fewer than 10 entries and no problematic patterns
- entries are only low-duration `CRDT.EFFECT` operations
- activity appears as a modest one-time burst

### What to include in a slowlog finding

For each database where slowlog matters:

1. one-line summary naming the dominant category
2. top 3 commands by count with count, average duration, and max duration
3. explicit mention of any bad pattern such as `KEYS`, excessive `SCAN COUNT`, or large multi-key operations
4. a direct recommendation tied to the dominant pattern

### Slowlog recommendation patterns

- long-blocking traversal: replace `KEYS` with `SCAN`, keep `COUNT` modest, and avoid full-collection reads on hot paths
- Lua: break large scripts into smaller operations or move complex loops client-side
- multi-key: batch large `DEL` or `MGET` workloads into smaller chunks; prefer `UNLINK` for deletion when appropriate
- RediSearch: review index design and query breadth; investigate with `FT.EXPLAIN` or `FT.PROFILE`
- RedisJSON: reduce document size or path breadth on hot paths; consider a flatter data model if needed
- mixed or other: tie the recommendation to the specific command mix and likely data-shape issue

## Health-check catalog

Use this catalog to translate Analyzer checks into customer-facing findings.

### Database checks

| Check | Meaning | Value handling | Writing guidance |
|---|---|---|---|
| `DBBalance` | proxy and master shard placement overlap is suboptimal | values are `OK`, `Partially unbalanced`, or `Unbalanced` | write as a placement or inter-node-hop latency issue, not as the internal check name |
| `Slowlog` | slowlog entries exist | value is the entry count only | always drill into `analyzer_get_database_slowlog` before writing |
| `ShardsUsage` | one or more shards are above recommended size | value lists offending shard ids; Analyzer warns above about 22.5 GB RAM or 45 GB flash and errors above about 25 GB RAM or 50 GB flash | say large shards lengthen recovery, resharding, and full sync |
| `ShardsUsageDev` | shard sizes are uneven | value is stdev percent; Analyzer warns above about 15% and errors above about 30% | say this suggests skew, hash-tag concentration, or large keys |
| `AvgKeySize` | average key size is too large | value is memory size; Analyzer warns above about 10 MB and errors above about 100 MB | say large keys slow replication and full-key access |
| `BdbStatuses` | database status or backup status is not fully normal | value is status text | treat backup-in-progress as often transient; call it out without overstating |
| `CmdStats` | internal parse/loading check | always informational | never produce a finding |

### Cluster checks

| Check | Meaning | Writing guidance |
|---|---|---|
| `CRDTStatus` | Active-Active sources are out of sync | describe as replication lag or sync health issue |
| `HWRequirements` | minimum node RAM or CPU is below recommendation | state the observed minimum and that Redis Enterprise expects at least 15 GB RAM and 4 CPU cores per node |
| `NodesCount` | node count is risky for quorum or larger-cluster odd-count guidance | say odd counts are preferred for HA and quorum; fewer than 3 nodes is critical |
| `ProvRAMCheck` | insufficient provisional RAM for self-healing or patching | say maintenance and failover headroom is inadequate |
| `SaslCheck` | known SASL or LDAP config bug condition | use the value directly and recommend config review |
| `SocketFiles` | socket file counts differ across nodes | describe as configuration inconsistency requiring investigation |
| `StuckSM` | a database or component has a stuck state machine | treat as high priority because it blocks operations |
| `TasksSuccessful` | one or more cluster tasks did not complete successfully | use the value directly because it names the failing tasks |

### Node checks

| Check | Meaning | Writing guidance |
|---|---|---|
| `GhostShards` | orphan shard processes exist | describe them as orphan `redis-server` processes without expected socket files |
| `GlibcBad` | node is on a known-bad glibc build | state it directly and recommend update |
| `NodeProcesses` | supervisord or other non-Redis processes are unhealthy or too expensive | say what process issue was observed |
| `NodeStatuses` | node is not active | state the node status plainly |
| `ShardStatuses` | shard status or persistence files are unhealthy | mention inactive shards or missing persistence files |
| `ProcessSysInfo` | `sys_info` is missing so other node checks could not run | this is itself a finding and should mention the downstream impact |
| `Swap` | swap is enabled | recommend disabling swap to avoid latency spikes |

## Writing style

Apply these rules to every finding:

- lead with the observation, then the recommendation
- quantify every finding with the actual value or count
- use database names, not bare ids
- use imperative recommendations, not soft suggestions
- hedge only when customer intent is unknown
- do not mention internal check names in customer-facing prose unless needed for traceability
- do not say "it appears" or "it seems"

Severity rules:

- `CRITICAL` findings should sound direct and urgent
- warning-tier findings should sound direct but proportional
- transient findings such as backup in progress can be noted as informational if the context supports it

Ordering rules:

1. cluster findings first, with `StuckSM` and `TasksSuccessful` before sizing or config items
2. node findings next, ordered by severity and node id
3. database findings last, ordered by worst severity in the database
4. within one database, prefer this order: shard size and skew, configuration, slowlog, key size, placement, transient status

## Output structure

Return one markdown document in this shape:

```markdown
# Cluster Health Check: <cluster name>

**Package ID:** <package_id>
**Cluster:** <cluster name>
**Software version:** <version or unknown>
**Nodes:** <node count>
**Databases:** <database count>
**Analysis date:** <today>

## Summary

<1-2 sentence plain-language summary>

**Findings count by severity:**
- Critical: <n>
- Warning: <n>
- Informational: <n>

## Cluster-level findings

## Node-level findings

## Database-level findings

### <database name> (<id>)

- **<finding label>**: <observation>. <recommendation>.

## Common Issues Rollup

### Server Side

### Client Side

### Operational

## TAM Manual Review Required

## Skipped Checks
```

## Final report validation loop

Before returning the final answer, validate the draft report against this checklist. If any item fails, fix the draft and repeat this validation loop until all items pass.

- The final answer is one markdown document and starts with `# Cluster Health Check: <cluster name>`.
- The metadata block contains exactly these bold labels in this order: `Package ID`, `Cluster`, `Software version`, `Nodes`, `Databases`, `Analysis date`.
- The required top-level sections appear in this order: `Summary`, `Cluster-level findings`, `Node-level findings`, `Database-level findings`, `Common Issues Rollup`, `TAM Manual Review Required`, `Skipped Checks`.
- The `Summary` section includes a 1-2 sentence summary and a findings count by severity with `Critical`, `Warning`, and `Informational`.
- The `Common Issues Rollup` section includes the exact subsections `Server Side`, `Client Side`, and `Operational`.
- Every database finding uses `<database name> (<id>)`, not a bare database id.
- Every Slowlog finding is based on raw slowlog entries and includes the dominant category, top 3 commands by count with count, average duration, max duration, any bad pattern, and a direct recommendation.
- The report mentions cluster-scope time-series evidence and node-scope time-series evidence when node imbalance was indicated.
- The `TAM Manual Review Required` section contains the manual review checklist, populated with observed evidence when available and marked for TAM follow-up when the MCP surface does not expose the field.
- The `Skipped Checks` section lists checks that returned `SKIP`, especially when missing `sys_info` explains downstream skipped node checks.
- The final report does not include the internal execution checklist, validation checklist, tool-call trace, or notes about drafting and repair.

## Rollup mapping

Map findings into customer-facing rollups like this:

### Server Side

- `ShardsUsage` -> Shards larger than recommended
- `DBBalance` -> unbalanced endpoints or shard placement
- `TasksSuccessful`, `StuckSM` -> failed or stuck tasks
- `HWRequirements`, `ProvRAMCheck`, `NodesCount` -> limited resources, resilience, or sizing

### Client Side

- `Slowlog` -> long-running commands
- `AvgKeySize` -> large keys
- `ShardsUsageDev` -> uneven shard size

### Operational

- node `sys_info`, ghost shards, glibc, swap, shard status, socket file, or SASL issues
- cluster or node findings that do not map cleanly into a customer-facing server-side or client-side bucket

## TAM manual review section

Always include a checklist for topics Analyzer health checks do not cover fully. Use MCP tools, not UI references.

- cluster software version versus known CVEs
- shard distribution across nodes using `analyzer_get_package_topology` or `analyzer_get_package_nodes`
- AOF policy review from `analyzer_get_package_databases`
- cluster auto-recovery setting if it is not surfaced in current MCP data
- alert threshold configuration using `analyzer_get_package_alerts`
- node CPU trends or spikes using `analyzer_get_package_time_series`
- shard memory fragmentation if relevant metrics are available
- persistence-disabled databases from `analyzer_get_package_databases`

If you have concrete evidence, populate the checklist with the observed version, AOF policies, or list of persistence-disabled databases. If the MCP surface does not expose a field directly, say that the item still requires manual TAM follow-up.

## Skipped checks

List checks that returned `SKIP`, especially when `ProcessSysInfo` explains them. This gives the TAM an audit trail of what Analyzer did not evaluate.

## Constraints

- `account_id` is a string
- prefer `analyzer_get_package` for ids returned by inventory tools
- use `analyzer_get_package_by_hash` only when the user explicitly provides a hash
- time-series access is interval-based, not arbitrary free-form slicing
- the current MCP surface does not provide arbitrary raw log grep
- do not invent accounts, clusters, packages, findings, or causal stories without tool evidence
