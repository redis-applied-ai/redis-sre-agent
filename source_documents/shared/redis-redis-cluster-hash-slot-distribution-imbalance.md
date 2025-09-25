# Redis Cluster Hash Slot Distribution Imbalance

**Category**: shared  
**Severity**: warning  
**Source**: Generated runbook for Redis SRE Agent

## Symptoms
- One Redis Cluster node is receiving 80% more traffic than others.
- High CPU and memory usage on the "hot" node.
- Other nodes in the cluster are underutilized.
- Potential performance degradation and service disruptions.

## Root Cause Analysis

### 1. Analyze Slot Distribution
```bash
redis-cli -c -h [host] -p [port] CLUSTER SLOTS
# Check the output for uneven distribution of slots across nodes.
# Look for nodes with significantly more slots assigned.
```

### 2. Check Node Traffic
```bash
redis-cli -c -h [host] -p [port] INFO stats
# Focus on 'instantaneous_ops_per_sec' and 'total_commands_processed'.
# Compare these metrics across nodes to identify traffic imbalance.
```

## Immediate Remediation

### Option 1: Manual Slot Rebalancing
```bash
redis-cli -c -h [host] -p [port] CLUSTER SETSLOT [slot] NODE [node-id]
# Move slots from the overloaded node to underutilized nodes.
# Ensure minimal disruption by moving slots during low traffic periods.
```

### Option 2: Automated Rebalancing
1. Use Redis Cluster Manager (redis-trib.rb or redis-cli with --cluster option).
2. Execute the following command:
   ```bash
   redis-cli --cluster rebalance --cluster-use-empty-masters [host]:[port]
   # This will automatically redistribute slots to achieve balance.
   # Monitor the process to ensure it completes successfully.
   ```

## Long-term Prevention

### 1. Regular Slot Distribution Audits
- Schedule periodic checks using `CLUSTER SLOTS` to ensure even distribution.
- Automate alerts for significant slot imbalances.

### 2. Hash Tag Optimization
- Use hash tags to control key distribution.
- Ensure keys that are frequently accessed together are hashed to the same slot.

## Monitoring & Alerting

### Key Metrics to Track
```bash
redis-cli -c -h [host] -p [port] INFO stats | grep 'instantaneous_ops_per_sec\|total_commands_processed'
# Track these metrics to monitor node load.
```

### Alert Thresholds
- Alert if `instantaneous_ops_per_sec` on any node exceeds 150% of the average across all nodes.
- Alert if `total_commands_processed` shows a 50% deviation from the cluster average.

## Production Checklist
- [ ] Verify current slot distribution using `CLUSTER SLOTS`.
- [ ] Check node traffic using `INFO stats`.
- [ ] Execute rebalancing procedures if necessary.
- [ ] Implement hash tag optimization strategies.
- [ ] Set up monitoring and alerting for key metrics.
- [ ] Document any changes made to the cluster configuration.