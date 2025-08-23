# Redis Cluster Slot Migration Stuck Incomplete

**Category**: operational_runbook  
**Severity**: critical  
**Source**: Generated runbook for Redis SRE Agent

## Symptoms
- Redis Cluster slot migration stuck at 52% completion for over 2 hours.
- Clients receiving MOVED redirections.
- Some keys becoming inaccessible.

## Root Cause Analysis

### 1. Check Cluster Slots Migration Status
```bash
redis-cli -c -h <host> -p <port> CLUSTER SLOTS
# Look for slots with incomplete migration status. Check if any slots are stuck in the migrating state.
```

### 2. Verify Cluster Nodes and Network Health
```bash
redis-cli -c -h <host> -p <port> CLUSTER NODES
# Ensure all nodes are reachable and in the correct state. Look for nodes marked as 'fail' or 'handshake'.
```

## Immediate Remediation

### Option 1: Manual Slot Migration Completion
```bash
redis-cli -c -h <source_host> -p <source_port> CLUSTER SETSLOT <slot> NODE <destination_node_id>
# Manually assign the slot to the destination node. Ensure the destination node is healthy and reachable.
```

### Option 2: Restart Migration Process
1. Pause the current migration process:
   ```bash
   redis-cli -c -h <host> -p <port> CLUSTER SETSLOT <slot> STABLE
   ```
2. Re-initiate the migration:
   ```bash
   redis-cli -c -h <source_host> -p <source_port> CLUSTER SETSLOT <slot> MIGRATING <destination_node_id>
   redis-cli -c -h <destination_host> -p <destination_port> CLUSTER SETSLOT <slot> IMPORTING <source_node_id>
   ```

## Long-term Prevention

### 1. Ensure Network Stability
- Regularly monitor network latency and packet loss between cluster nodes.
- Use tools like `ping` and `traceroute` to diagnose network issues.

### 2. Optimize Resource Allocation
- Ensure nodes have sufficient CPU and memory resources.
- Monitor resource usage and scale up if necessary.

## Monitoring & Alerting

### Key Metrics to Track
```bash
redis-cli -c -h <host> -p <port> INFO replication
# Monitor replication backlog size and link status.

redis-cli -c -h <host> -p <port> INFO cluster
# Track cluster state and slot allocation.
```

### Alert Thresholds
- Alert if slot migration is stuck for more than 30 minutes.
- Alert if any node is marked as 'fail' or 'handshake'.

## Production Checklist
- [ ] Verify all nodes are reachable and in the correct state.
- [ ] Ensure sufficient network bandwidth and low latency between nodes.
- [ ] Confirm all slots are correctly assigned and no slots are in a migrating state.
- [ ] Monitor client logs for MOVED errors and address them promptly.