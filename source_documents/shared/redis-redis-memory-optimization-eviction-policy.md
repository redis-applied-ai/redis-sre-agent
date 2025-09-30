# Redis Memory Optimization and Eviction Policy

**Category**: shared
**Severity**: warning
**Source**: Generated runbook for Redis SRE Agent

## Symptoms
- Redis memory usage is approaching the `maxmemory` limit.
- Unexpected data eviction occurs, impacting application functionality.
- Performance degradation is observed.
- Alerts triggered for high memory usage.

## Root Cause Analysis

### 1. Check Current Memory Usage
```bash
redis-cli MEMORY STATS
# Look for total memory usage and peak memory usage to assess current state.
```

### 2. Verify Eviction Policy
```bash
redis-cli CONFIG GET maxmemory-policy
# Ensure the eviction policy aligns with application needs (e.g., volatile-lru, allkeys-lru).
```

## Immediate Remediation

### Option 1: Adjust Eviction Policy
```bash
redis-cli CONFIG SET maxmemory-policy allkeys-lru
# Switch to an LRU policy if not already set. This helps in evicting less frequently used keys.
# Warning: Changing eviction policy can impact data retention strategy.
```

### Option 2: Increase Maxmemory
1. Evaluate available system resources.
2. Increase `maxmemory` if feasible:
   ```bash
   redis-cli CONFIG SET maxmemory <new_value>
   # Ensure the new value does not exceed physical memory limits.
   ```

## Long-term Prevention

### 1. Optimize Data Encoding
- Use special encoding for small data types (e.g., `ziplist` for small lists).
- Regularly review and refactor data structures to use memory-efficient encodings.

### 2. Implement Capacity Planning
- Analyze historical memory usage trends.
- Forecast future memory needs based on application growth.
- Plan for scaling Redis instances or clusters accordingly.

## Monitoring & Alerting

### Key Metrics to Track
```bash
redis-cli INFO memory
# Monitor used_memory, used_memory_peak, and maxmemory.
```

### Alert Thresholds
- Alert when `used_memory` exceeds 80% of `maxmemory`.
- Alert on frequent changes in eviction count.

## Production Checklist
- [ ] Verify current memory usage and peak memory usage.
- [ ] Confirm eviction policy aligns with application requirements.
- [ ] Ensure `maxmemory` is set appropriately and does not exceed physical limits.
- [ ] Implement regular monitoring and alerting for memory usage.
- [ ] Review and optimize data structures for memory efficiency.
- [ ] Conduct capacity planning and adjust resources as needed.
