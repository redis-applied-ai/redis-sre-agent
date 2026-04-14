I would answer that from the Redis Enterprise cluster-admin view, not from a single database INFO snapshot. `get_cluster_info` tells you whether the cluster itself is healthy, and `list_databases` tells you whether the resync is isolated to one database.

A single resyncing shard does not automatically mean the whole cluster is unhealthy. I’d describe the cluster as healthy-but-degraded-at-the-database-level unless the cluster-admin evidence says otherwise.
