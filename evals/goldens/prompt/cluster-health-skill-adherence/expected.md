# Cluster Health Check: checkout-prod-cluster

**Package ID:** pkg-eval-001
**Cluster:** checkout-prod-cluster
**Software version:** 7.8.4-72
**Nodes:** 3
**Databases:** 2
**Analysis date:** 2026-05-12

## Summary

checkout-prod-cluster has one critical database-capacity issue and several warning-level operational findings that need follow-up. The most urgent items are oversized orders-cache shards, a failed import task, and missing node telemetry that left part of the package unchecked.

**Findings count by severity:**
- Critical: 1
- Warning: 7
- Informational: 1

## Cluster-level findings

- **Failed cluster task**: checkout-prod-cluster recorded a failed `import-orders-cache` task during shard rebalance. Re-run the import only after you confirm shard placement and capacity headroom are stable.
- **Maintenance headroom is below recommendation**: checkout-prod-cluster has 12 GB provisional RAM free, below the 15 GB headroom recommendation. Increase maintenance headroom before planned failover, patching, or self-healing events.
- **Cluster metrics show rising load**: cluster CPU rose from 42% to 71% over the 15-minute window while provisional RAM free fell from 18 GB to 12 GB. Reduce background workload pressure and add capacity before the next maintenance event.

## Node-level findings

- **node 2 has swap enabled**: node 2 is using 2.0 GB of swap and also peaked at 88% CPU in the node time series. Disable swap and investigate why node 2 is carrying the hottest workload.
- **node 3 is missing `sys_info`**: node 3 did not collect `sys_info`, which blocked downstream node checks such as GhostShards, GlibcBad, Swap, and NodeProcesses. Restore node telemetry collection and re-run Analyzer so the skipped checks can complete.

## Database-level findings

### orders-cache (bdb-101)

- **Oversized shards**: orders-cache has a shard at 26.4 GB RAM, above the critical guidance threshold. Split or reshard the database before the next full sync, recovery event, or maintenance action.
- **Uneven shard sizing**: orders-cache shows 34% shard-size standard deviation between shards. Rebalance key distribution and review hash-tag concentration or large-key hotspots.
- **slow RediSearch queries**: orders-cache slowlog is dominated by RediSearch commands. Top 3 commands by count: `FT.SEARCH` (12 calls, average 30.5 ms, max 35.1 ms), `FT.AGGREGATE` (4 calls, average 41.2 ms, max 48.0 ms), and `DEL` (2 calls, average 19.3 ms, max 20.1 ms). The notable pattern is repeated wide `FT.SEARCH`/`FT.AGGREGATE` usage plus 24-key `DEL` bursts. Review index design and query breadth, investigate the query plan with `FT.EXPLAIN` or `FT.PROFILE`, and batch multi-key deletions into smaller chunks.
- **Large average keys**: orders-cache average key size is 12 MB. Shrink document size or flatten the hottest JSON payloads so replication and full-key reads do not stay expensive.

### sessions-cache (bdb-102)

- **Placement overlap increases inter-node hops**: sessions-cache is unbalanced, and 2 of 2 endpoints place proxy and master shards on the same node. Rebalance endpoint placement so proxy and master traffic does not concentrate on one node.
- **Backup is in progress**: sessions-cache reports `backup_in_progress`. Monitor the backup to completion before treating this as a persistent health issue.

## Common Issues Rollup

### Server Side

- Shards larger than recommended in orders-cache (bdb-101).
- Failed cluster task and low provisional RAM headroom on checkout-prod-cluster.
- Unbalanced endpoint placement in sessions-cache (bdb-102).

### Client Side

- Long-running RediSearch queries and multi-key delete bursts in orders-cache (bdb-101).
- Large average keys and shard skew in orders-cache (bdb-101).

### Operational

- node 2 has swap enabled and the highest observed CPU peak.
- node 3 is missing `sys_info`, which caused GhostShards and related checks to skip.

## TAM Manual Review Required

- [x] Cluster software version versus known CVEs: observed version is 7.8.4-72; TAM still needs the current CVE cross-check.
- [x] Shard distribution across nodes using topology and node data: node 2 carried the highest CPU peak at 88%, and sessions-cache endpoint overlap keeps proxy and master traffic on node 1.
- [x] AOF policy review from database inventory: orders-cache uses `every-1-sec`; sessions-cache has persistence disabled.
- [ ] Cluster auto-recovery setting: current MCP data does not expose it directly, so TAM follow-up is still required.
- [x] Alert threshold configuration using package alerts: RAM headroom warning is firing at 12 GB versus a 15 GB threshold, and node CPU imbalance is firing at 88% versus an 80% threshold.
- [x] Node CPU trends or spikes using package time series: cluster CPU climbed from 42% to 71%, and node 2 peaked at 88%.
- [ ] Shard memory fragmentation: current MCP data does not expose a direct fragmentation metric, so TAM follow-up is still required.
- [x] Persistence-disabled databases from package databases: sessions-cache (bdb-102) has persistence disabled.

## Skipped Checks

- node 3 `GhostShards`: skipped because `sys_info` is missing.
- node 3 `GlibcBad`: skipped because `sys_info` is missing.
- node 3 `Swap`: skipped because `sys_info` is missing.
- node 3 `NodeProcesses`: skipped because `sys_info` is missing.
