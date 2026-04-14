I’d verify the Redis Enterprise cluster-admin view first. `get_cluster_info` and `list_nodes` are the right evidence surfaces here, because the current signal points to maintenance activity rather than a generic OSS Redis failure.

If maintenance mode is active, that explains the failover churn. The next guidance should stay grounded in replica health and the documented maintenance workflow before anyone changes maintenance state or treats this like a generic Redis failover issue.
