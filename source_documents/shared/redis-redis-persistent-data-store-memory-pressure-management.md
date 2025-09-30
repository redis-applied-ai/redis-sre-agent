# Redis Persistent Data Store Memory Pressure Management

**Category**: shared
**Severity**: critical
**Source**: Generated runbook for Redis SRE Agent

## Symptoms
- Redis memory utilization reaching 85% or higher.
- Increased latency in Redis operations.
- Potential out-of-memory (OOM) errors.
- High disk I/O due to AOF/RDB persistence.

## Root Cause Analysis

### 1. Check Current Memory Usage
```bash
redis-cli INFO memory
# Look for 'used_memory' and 'used_memory_peak' to assess current memory usage.
```

### 2. Identify Large Keys
```bash
redis-cli --bigkeys
# This command will help identify keys that are consuming the most memory.
```

## Immediate Remediation

### Option 1: Increase Memory Allocation
```bash
# If running on a virtualized environment or cloud, increase the instance size.
# Ensure the new instance size has sufficient memory to handle the current load plus a buffer.
```

### Option 2: Optimize Data Structures
- Work with the application team to review and optimize data structures.
- Consider using more memory-efficient data types (e.g., use hashes instead of strings for objects).

## Long-term Prevention

### 1. Memory Scaling and Capacity Planning
- Regularly review memory usage trends and forecast future needs.
- Plan for scaling up Redis instances or sharding data across multiple instances.

### 2. Safe Data Cleanup Strategies
- Collaborate with the application team to identify and remove stale or unnecessary data.
- Implement a process for regular data audits to ensure only necessary data is stored.

## Monitoring & Alerting

### Key Metrics to Track
```bash
redis-cli INFO memory | grep 'used_memory'
redis-cli INFO stats | grep 'instantaneous_ops_per_sec'
```

### Alert Thresholds
- Set alerts for when memory usage exceeds 75% to allow for proactive management.
- Monitor disk I/O and set alerts for high usage that could indicate persistence issues.

## Production Checklist
- [ ] Verify that Redis `maxmemory` is set appropriately for the workload.
- [ ] Ensure that swap is enabled and configured correctly to handle unexpected memory spikes.
- [ ] Monitor and adjust AOF/RDB persistence settings to balance durability and performance.
- [ ] Regularly review and update capacity plans based on application growth and usage patterns.
