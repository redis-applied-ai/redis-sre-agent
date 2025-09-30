# Redis Memory Optimization Eviction Policy for Cache Instances

**Category**: shared
**Severity**: warning
**Source**: Generated runbook for Redis SRE Agent

## Symptoms
- Redis memory usage is approaching the `maxmemory` limit.
- Increased eviction rates observed.
- Cache hit rate is decreasing.
- No persistence configured, safe to evict keys.

## Root Cause Analysis

### 1. Check Current Memory Usage
```bash
redis-cli info memory
# Look for 'used_memory' and 'maxmemory' to assess current memory usage.
```

### 2. Verify Current Eviction Policy
```bash
redis-cli config get maxmemory-policy
# Ensure the policy is set to 'allkeys-lru' or another suitable policy for cache instances.
```

## Immediate Remediation

### Option 1: Adjust Eviction Policy
```bash
redis-cli CONFIG SET maxmemory-policy allkeys-lru
# Switch to an LRU policy if not already set. This policy evicts the least recently used keys first, optimizing for cache use cases.
```

### Option 2: Increase maxmemory (if resources allow)
```bash
redis-cli CONFIG SET maxmemory <new_value>
# Increase the maxmemory setting to accommodate more data if the server has available resources.
```

## Long-term Prevention

### 1. Optimize TTL Settings
- Review and adjust TTL values for keys to ensure they align with application requirements and reduce unnecessary memory usage.
- Use `EXPIRE` command to set appropriate TTLs for frequently accessed keys.

### 2. Monitor and Adjust maxmemory
- Regularly review memory usage patterns and adjust `maxmemory` settings based on observed trends and available resources.

## Monitoring & Alerting

### Key Metrics to Track
```bash
# Monitor memory usage
redis-cli info memory | grep used_memory

# Monitor eviction rate
redis-cli info stats | grep evicted_keys

# Monitor cache hit rate
redis-cli info stats | grep keyspace_hits
redis-cli info stats | grep keyspace_misses
```

### Alert Thresholds
- Alert if `used_memory` exceeds 80% of `maxmemory`.
- Alert if `evicted_keys` rate increases significantly.
- Alert if cache hit rate drops below 90%.

## Production Checklist
- [ ] Verify `maxmemory-policy` is set to `allkeys-lru`.
- [ ] Ensure `maxmemory` is set appropriately for the workload.
- [ ] Monitor memory usage and eviction rates regularly.
- [ ] Adjust TTLs for keys to optimize memory usage.
- [ ] Review and adjust `maxmemory` settings based on resource availability and usage patterns.
