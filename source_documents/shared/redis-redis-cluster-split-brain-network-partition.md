# Redis Cluster Split-Brain Network Partition

**Category**: shared
**Severity**: critical
**Source**: Generated runbook for Redis SRE Agent

## Symptoms
- Data inconsistency across nodes
- Connection timeouts and intermittent errors
- Multiple master nodes for the same slots
- Conflicting writes leading to data corruption

## Root Cause Analysis

### 1. Check Cluster Nodes Status
```bash
redis-cli -c -h <node-ip> -p <node-port> CLUSTER NODES
# Look for multiple nodes with the 'master' role for the same slots.
```

### 2. Verify Slot Ownership
```bash
redis-cli -c -h <node-ip> -p <node-port> CLUSTER SLOTS
# Ensure each slot is assigned to a single master node. Look for discrepancies.
```

## Immediate Remediation

### Option 1: Manual Slot Reassignment
```bash
redis-cli -c -h <node-ip> -p <node-port> CLUSTER SETSLOT <slot> NODE <node-id>
# Reassign slots to a single master node. Ensure no conflicting masters for the same slot.
```

### Option 2: Cluster Reset and Reconfiguration
1. **Isolate the Network Partition**: Identify and isolate the network issue causing the partition.
2. **Reset the Cluster**:
   ```bash
   redis-cli -c -h <node-ip> -p <node-port> CLUSTER RESET HARD
   # Use with caution: This will reset the cluster configuration.
   ```
3. **Reconfigure the Cluster**: Re-add nodes and reassign slots as needed.

## Long-term Prevention

### 1. Network Monitoring and Alerts
- Implement robust network monitoring to detect and alert on latency or partition events.
- Use tools like Prometheus and Grafana to visualize network health.

### 2. Regular Cluster Resilience Testing
- Conduct regular failover and partition simulations to test cluster resilience.
- Use tools like Redis Cluster Manager (RCM) for automated testing.

## Monitoring & Alerting

### Key Metrics to Track
```bash
# Monitor cluster state and node roles
redis-cli -c -h <node-ip> -p <node-port> INFO replication
# Track: role, connected_slaves, master_link_status

# Monitor network latency
ping <node-ip>
```

### Alert Thresholds
- Alert if multiple masters are detected for the same slot.
- Alert on network latency exceeding 100ms between nodes.

## Production Checklist
- [ ] Verify all nodes have a single master for each slot.
- [ ] Ensure network monitoring is active and alerts are configured.
- [ ] Conduct a post-incident review to identify root causes and prevention measures.
- [ ] Document any changes made during remediation for future reference.
