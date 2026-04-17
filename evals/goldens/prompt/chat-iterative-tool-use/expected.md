The first checks should stay narrow.

Start with `INFO memory` and `MEMORY STATS` on the attached cache, confirm whether `used_memory` is near `maxmemory`, and use `evicted_keys` plus allocator overhead to decide whether the latency is memory-pressure related.

Do not jump straight into a broad metric sweep or whole-keyspace inspection until those two checks come back ambiguous.
