Here are the remediation steps for elevated Redis cache latency:

1. **Reduce connection pressure** — check `CLIENT LIST` for stale or piled-up connections and close idle ones. If using a connection pool, verify the pool size matches concurrency demand.
2. **Flush slow commands** — run `SLOWLOG GET 25` to identify expensive operations, then optimize or pipeline them. Avoid `KEYS *` in production.
3. **Check memory headroom** — run `INFO memory` and verify `used_memory` is well below `maxmemory`. If eviction is active (`evicted_keys` rising), increase `maxmemory` or switch to a less-aggressive eviction policy.
4. **Inspect persistence load** — if `rdb_bgsave_in_progress` or `aof_rewrite_in_progress` is 1, a background save is competing for I/O. Schedule saves outside peak hours or switch to AOF with `appendfsync everysec`.
5. **Review network and CPU** — confirm the Redis host has sufficient CPU headroom and that the client-to-server round-trip time is normal. A single slow replica sync can delay writes cluster-wide.

If latency persists after these steps, capture `LATENCY HISTORY` and `LATENCY LATEST` output and escalate to the on-call SRE for deeper analysis.
