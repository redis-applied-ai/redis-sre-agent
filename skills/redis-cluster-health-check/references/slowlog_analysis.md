---
title: Slowlog Analysis
description: How to interpret Analyzer slowlog results gathered through MCP and turn them into actionable findings.
---

# Slowlog Analysis

When `Slowlog` is non-OK, the count alone is not useful. Fetch the details with
`analyzer_get_database_slowlog` and summarize what is actually slow.

## Tool usage

Call:

```text
analyzer_get_database_slowlog(package_id="<package_id>", database_id=<database_id>, limit=200)
```

The tool returns recent entries with an `entry` string that contains the duration and command
payload.

## What to extract

For each flagged database:

1. Count the dominant commands.
2. Estimate average and max duration for the top commands.
3. Identify obviously problematic patterns.
4. Decide whether the finding is worth highlighting or only noting briefly.

## Command categories

| Category | Common commands | Finding framing |
|---|---|---|
| Long-blocking traversal | `KEYS`, `SCAN` with very high `COUNT`, `SMEMBERS`, `HGETALL`, `LRANGE 0 -1` on large collections | `Long-blocking traversal commands in slowlog` |
| Lua scripting | `EVAL`, `EVALSHA`, `FCALL` | `Long-running Lua scripts in slowlog` |
| Large multi-key ops | `DEL`, `UNLINK`, `MGET`, `MSET` with many keys | `Large multi-key operations in slowlog` |
| RediSearch | `FT.SEARCH`, `FT.AGGREGATE`, `FT.INFO`, `FT.PROFILE`, `FT.EXPLAIN` | `Slow RediSearch queries in slowlog` |
| RedisJSON | `JSON.SET`, `JSON.GET`, `JSON.MGET`, `JSON.ARRAPPEND` on large documents | `Slow JSON operations in slowlog` |
| CRDT effects | `CRDT.EFFECT` | `CRDT replication operations in slowlog` |
| Other | anything else | `Other slow commands in slowlog` |

## What to include in a full slowlog finding

1. One-line summary naming the dominant category.
2. Top commands by count.
3. Average and max duration for the top commands when visible.
4. Specific concerns such as `KEYS`, huge `SCAN COUNT`, large multi-key deletes, or expensive
   RediSearch commands.
5. One clear recommendation matched to the dominant pattern.

## Recommendation patterns

### Long-blocking traversal

Replace `KEYS` with `SCAN` and keep `COUNT` modest. For repeated full-collection traversal,
consider a different data model or an index.

### Lua

Review script logic for large loops or blocking calls. Break long scripts into smaller operations
or move complex work client-side where appropriate.

### Large multi-key operations

Batch `DEL`, `UNLINK`, `MGET`, and similar operations into smaller groups. Prefer `UNLINK` over
`DEL` when asynchronous deletion is acceptable.

### RediSearch

Review index design and query selectivity. Investigate broad matches, wide result sets, and
whether profiling or query-plan review is needed.

### RedisJSON

Review document size, nesting depth, and hot-path field access. A flatter data model or shorter
paths may reduce latency.

### Mixed or other

Tie the commands back to application access patterns. Otherwise-cheap commands with long durations
often indicate large payloads or hot keys.

## When a slowlog finding is not worth highlighting

Mention the slowlog briefly and recommend no action when any of these apply:

- Fewer than 10 entries and no obviously bad command pattern
- Mostly low-duration `CRDT.EFFECT` entries
- A small burst of modest-duration commands that looks transient

Example:

```text
Database <name> (<id>) has 8 slowlog entries, all low-duration CRDT.EFFECT operations. Reviewed,
no action recommended.
```
