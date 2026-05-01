---
title: Analyzer Check Catalog
description: How to interpret Analyzer health-check output from MCP and translate it into customer-facing findings.
---

# Analyzer Check Catalog

Reference for the Redis Enterprise Analyzer health checks returned by
`analyzer_get_package_health_checks`.

## Status handling

The MCP tool returns normalized status strings:

| Status | Meaning | Handle as |
|---|---|---|
| `OK` | No finding | Skip |
| `WARNING` | Non-critical issue | Include as finding |
| `CRITICAL` | Error-tier issue | Include as finding and escalate language |
| `SKIP` | Check could not run | Usually note only if the skipped state is itself meaningful |

The main exception is `ProcessSysInfo`. When it reports missing system information, that is a
real finding because several node-level checks depend on it.

## Scope handling

- Database checks usually refer to a database id. Resolve names with
  `analyzer_get_package_databases`.
- Node checks usually refer to a node id. Keep the node id in the text.
- Cluster checks apply to the full package.

Always write database findings as `<database name> (<id>)`.

## Database checks

### `DBBalance`

- Meaning: shard masters and proxy endpoints overlap poorly.
- Impact: extra inter-node hops can increase latency.
- Write-up: call it out as a placement issue, not by the internal check name.
- Recommendation: review proxy and shard placement and rebalance if latency is sensitive.

### `Slowlog`

- Meaning: the database has slowlog entries.
- Impact: the count alone is not actionable.
- Required follow-up: call `analyzer_get_database_slowlog`.
- Recommendation: use the slowlog reference to identify the dominant pattern before writing the
  finding.

### `ShardsUsage`

- Meaning: one or more shards exceed recommended size.
- Impact: larger shards increase recovery, replication, and resharding time.
- Recommendation: increase shard count or reduce per-shard footprint.

### `ShardsUsageDev`

- Meaning: shard sizes are uneven.
- Impact: skewed data distribution and uneven resource use.
- Recommendation: review hash-tag usage and large-key concentration.

### `AvgKeySize`

- Meaning: average key size is high.
- Impact: replication, backup, and full-key access become more expensive.
- Recommendation: identify big keys and work with application owners to split or redesign them.

### `BdbStatuses`

- Meaning: database status or backup state is not clean.
- Impact: sometimes transient.
- Recommendation: call it out plainly and avoid over-alarming when the evidence looks mid-operation.

### `CmdStats`

- Meaning: internal data-loading check.
- Handle as: skip.

## Cluster checks

### `CRDTStatus`

- Meaning: one or more Active-Active sources are out of sync.
- Recommendation: review CRDB replication health and regional bottlenecks.

### `HWRequirements`

- Meaning: node hardware minimums are below recommendation.
- Recommendation: tie the observation to shard density and workload sizing.

### `NodesCount`

- Meaning: the cluster has a risky node count for quorum or failure handling.
- Recommendation: prefer an odd node count with enough nodes for HA.

### `ProvRAMCheck`

- Meaning: the cluster lacks enough provisional RAM to self-heal or patch cleanly.
- Recommendation: add capacity or reduce memory pressure.

### `SaslCheck`

- Meaning: LDAP or SASL configuration matches a known bad condition.
- Recommendation: call out the condition directly and point to remediation.

### `SocketFiles`

- Meaning: socket file counts differ between nodes.
- Recommendation: treat as a configuration inconsistency that needs investigation.

### `StuckSM`

- Meaning: a database or component has a stuck state machine or inactive component.
- Impact: can block upgrades or configuration changes.
- Recommendation: lead with this because it is operationally blocking.

### `TasksSuccessful`

- Meaning: cluster tasks are failed or still running unexpectedly.
- Recommendation: resolve or clear the tasks before further maintenance work.

## Node checks

### `GhostShards`

- Meaning: orphaned `redis-server` processes exist without matching socket files.
- Recommendation: escalate for cleanup with support if necessary.

### `GlibcBad`

- Meaning: the node runs a known-problematic glibc version.
- Recommendation: call for remediation directly.

### `NodeProcesses`

- Meaning: supervisord-managed processes are unhealthy or non-Redis processes consume notable CPU
  or RAM.
- Recommendation: describe the offending process class and the likely operational risk.

### `NodeStatuses`

- Meaning: node status is not active.
- Recommendation: treat as a direct cluster-health issue.

### `ShardStatuses`

- Meaning: shard status or persistence-file state is unhealthy.
- Recommendation: point to inactive shards or missing persistence files specifically.

### `ProcessSysInfo`

- Meaning: `sys_info` is missing for the node.
- Impact: other node checks may skip because of it.
- Recommendation: mention both the missing artifact and the downstream observability gap.

### `Swap`

- Meaning: swap is enabled.
- Recommendation: call out the latency risk from page faults and recommend disabling swap.

## Manual-review items not covered by these checks

These belong in the manual-review section even when the automated findings are clean:

- Cluster software version versus known CVEs
- Shard distribution across nodes
- AOF policy review
- Cluster auto-recovery setting
- Alert threshold configuration
- Node CPU trends and transient spikes
- Shard memory fragmentation
