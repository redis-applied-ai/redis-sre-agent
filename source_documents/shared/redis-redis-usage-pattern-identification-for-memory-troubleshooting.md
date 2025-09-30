# Redis Usage Pattern Identification for Memory Troubleshooting

**Category**: shared
**Severity**: info
**Source**: Generated runbook for Redis SRE Agent

## Symptoms
- High memory usage on Redis instance
- Frequent evictions or OOM (Out Of Memory) errors
- Unclear if Redis is used as a cache or persistent store

## Root Cause Analysis

### 1. Analyze Key Patterns
```bash
redis-cli --scan --pattern '*' | head -n 100
# Look for patterns in key names that might indicate usage type, such as session keys for caching or user data for persistent storage.
```

### 2. Check TTL Coverage
```bash
redis-cli --scan --pattern '*' | xargs -L 1 redis-cli ttl | grep -v '-1'
# Keys with TTLs are likely used for caching. A high percentage of keys with TTLs suggests cache usage.
```

### 3. Detect Persistence Configuration
```bash
redis-cli config get save
# Check if persistence is enabled. If 'save' is configured, Redis is likely used as a persistent store.
```

## Immediate Remediation

### Option 1: Adjust `maxmemory` Settings
```bash
redis-cli config set maxmemory <new_memory_limit>
# Adjust the maxmemory setting to prevent OOM errors. Ensure this is within the physical memory limits of the server.
```

### Option 2: Change Eviction Policy
```bash
redis-cli config set maxmemory-policy allkeys-lru
# Change the eviction policy to 'allkeys-lru' to better manage memory usage if Redis is used as a cache.
```

## Long-term Prevention

### 1. Implement Capacity Planning
- Analyze historical memory usage trends.
- Forecast future memory needs based on application growth.
- Plan for scaling Redis instances or sharding data.

### 2. Optimize Data Storage
- Use data compression techniques for large datasets.
- Regularly review and clean up unused keys.

## Monitoring & Alerting

### Key Metrics to Track
```bash
redis-cli info memory | grep 'used_memory'
redis-cli info stats | grep 'evicted_keys'
```

### Alert Thresholds
- Alert if `used_memory` exceeds 80% of `maxmemory`.
- Alert if `evicted_keys` count increases rapidly.

## Production Checklist
- [ ] Verify Redis `maxmemory` is set appropriately for the workload.
- [ ] Ensure the correct eviction policy is configured.
- [ ] Monitor key patterns and TTL coverage regularly.
- [ ] Review persistence settings to align with usage patterns.

This runbook provides a structured approach to identifying Redis usage patterns, enabling SREs to make informed decisions about memory management and optimization strategies.
