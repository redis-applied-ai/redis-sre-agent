Based on the prior OOM incident recorded for this cluster last week, memory pressure is a known risk here. The cluster hit its maxmemory limit during the backup window, triggering aggressive key eviction. Here is how to investigate the current situation:

1. **Check current memory usage** — run `INFO memory` and compare `used_memory` against `maxmemory`. If the ratio is above 85–90%, you are approaching another OOM event.
2. **Review eviction activity** — check `evicted_keys` in `INFO stats`. A rising count confirms active eviction is already underway.
3. **Identify large key offenders** — use `MEMORY USAGE <key>` on suspected large keys or run `redis-cli --bigkeys` during a low-traffic window to find oversized entries.
4. **Inspect the backup schedule** — given the prior incident occurred during the backup window, confirm that RDB/AOF persistence is not scheduled to overlap with peak load. Check `rdb_bgsave_in_progress` and `aof_rewrite_in_progress` in `INFO persistence`.
5. **Review maxmemory policy** — run `CONFIG GET maxmemory-policy` to confirm the eviction policy is appropriate. For cache workloads, `allkeys-lru` or `volatile-lru` is usually preferred over `noeviction`.
6. **Check fragmentation** — `mem_fragmentation_ratio` above 1.5 indicates significant fragmentation; a controlled restart or `MEMORY PURGE` may help reclaim memory.

Given the documented OOM prior incident, treat any `used_memory` above 80% of `maxmemory` as a critical threshold requiring immediate action — either increase `maxmemory`, evict stale keys, or shed load before the backup window begins.
