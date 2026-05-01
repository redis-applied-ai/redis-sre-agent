---
title: Output Template
description: The markdown structure to produce for a Redis Enterprise cluster health check.
---

# Output Template

Produce one markdown document with this structure.

```markdown
# Cluster Health Check: <cluster name>

**Package ID:** <package id>  
**Cluster:** <cluster name>  
**Software version:** <version>  
**Nodes:** <node count>  
**Databases:** <database count>  
**Shards:** <shard count>  
**Analysis date:** <today's date>

---

## Summary

<1-2 sentence summary of the main findings and themes>

**Findings count by severity:**
- Critical: <n>
- Warning: <n>
- Informational: <n>

---

## Cluster-level findings

<cluster findings in priority order, or "No cluster-level findings from Analyzer health checks.">

---

## Node-level findings

<node findings grouped by node id, or "No node-level findings from Analyzer health checks.">

---

## Database-level findings

### <database name> (<id>)

- **<finding title>**: <finding text>
- **<finding title>**: <finding text>

<repeat per database with findings>

---

## Common Issues Rollup

### Server Side

- **Shards > recommended size** (<n> databases): <database list>
- **Unbalanced endpoints** (<n> databases): <database list>
- **Failed or running tasks** (<n> affected items): <summary>
- **Limited resources** (<n> findings): <summary>
- **Operational** (<n> findings): <summary of node and cluster operational issues that do not fit the customer slide categories>

### Client Side

- **Long running commands (Slowlog)** (<n> databases): <database list>
- **Large keys** (<n> databases): <database list>
- **Uneven shard size** (<n> databases): <database list>

---

## TAM Manual Review Required

- [ ] **Cluster software version vs known CVEs** — Current version is `<version>`.
- [ ] **Shard distribution across nodes** — Review placement with topology and node data.
- [ ] **AOF policy review** — List unique AOF policies observed and confirm intent.
- [ ] **Cluster auto-recovery setting** — Verify separately.
- [ ] **Alert threshold configuration** — Review per-database alert settings.
- [ ] **Node CPU trends and transient spikes** — Review metrics separately.
- [ ] **Shard memory fragmentation** — Review metrics separately.
- [ ] **Persistence configuration review** — List databases with persistence disabled.

---

## Skipped Checks

- <check name and why it was skipped>
```

## Rollup mapping

Use these customer-facing categories for the rollup:

| Category | Health-check sources |
|---|---|
| `Shards > recommended size` | `ShardsUsage` |
| `Unbalanced endpoints` | `DBBalance` |
| `Failed or running tasks` | `TasksSuccessful`, `StuckSM` |
| `Limited resources` | `HWRequirements`, `ProvRAMCheck`, `NodesCount` |
| `Long running commands (Slowlog)` | `Slowlog` after drill-down |
| `Large keys` | `AvgKeySize` |
| `Uneven shard size` | `ShardsUsageDev` |

If a finding does not map cleanly to a customer slide category, either keep it in `Operational`
or leave it in the detailed sections only.
