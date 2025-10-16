# Redis Enterprise Database Sync Issues

**Category**: enterprise
**Severity**: critical
**Source**: Generated runbook for Redis SRE Agent

## Symptoms
- Database replication lag increasing
- Sync status showing "out of sync" or "syncing"
- Active-Active database conflicts
- Cross-region replication failures
- Database showing inconsistent data across replicas

## Root Cause Analysis

### 1. Check Database Sync Status
```bash
rladmin status | grep -A 30 "DATABASES:"
# Look for databases with sync_status != "synced"
```

### 2. Check Replication Status
```bash
rladmin info db <database_name>
# Check detailed replication status for specific database
```

### 3. Check Active-Active Status (if applicable)
```bash
crdb-cli crdb list
crdb-cli crdb status --crdb-guid <guid>
# Check Active-Active database status and conflicts
```

### 4. Check Network Connectivity
```bash
rladmin status | grep -A 20 "NODES:"
# Verify all nodes are online and communicating
```

### 5. Check Cluster Resources
```bash
rladmin info cluster
# Check cluster memory, CPU, and network utilization
```

## Immediate Remediation

### Option 1: Force Database Sync
```bash
# For replica databases
rladmin restart db <database_name>
# This will restart the database and force a full sync
```

### Option 2: Check and Resolve Network Issues
```bash
# Test connectivity between nodes
rladmin status | grep -A 20 "NODES:"
# Check for network partitions or connectivity issues

# Check cluster network configuration
rladmin info cluster | grep -i network
```

### Option 3: Resolve Active-Active Conflicts
```bash
# Check for conflicts in Active-Active setup
crdb-cli crdb status --crdb-guid <guid>

# Resolve conflicts if present
crdb-cli crdb resolve-conflict --crdb-guid <guid> --conflict-id <conflict_id>
```

### Option 4: Check Disk Space and Resources
```bash
# Check disk space on all nodes
rladmin status | grep -A 20 "NODES:" | grep -E "node:|free_disk"

# Check memory usage
rladmin info cluster | grep memory
```

## Advanced Troubleshooting

### 1. Check Replication Logs
```bash
# Check Redis Enterprise logs for replication errors
sudo tail -f /var/opt/redislabs/log/rlec_supervisor.log | grep -i sync
sudo tail -f /var/opt/redislabs/log/rlec_supervisor.log | grep -i replication
```

### 2. Check Database Configuration
```bash
# Verify database replication settings
rladmin info db <database_name>
# Check replication source, replica settings
```

### 3. Monitor Replication Metrics
```bash
# Check replication lag metrics
rladmin status | grep -A5 -B5 <database_name>
```

### 4. Check for Split-Brain Scenarios
```bash
# Verify cluster quorum
rladmin status
# Ensure majority of nodes are online and in consensus
```

## Long-term Prevention

### 1. Monitor Replication Health
- Set up alerts for replication lag > 30 seconds
- Monitor sync status regularly
- Track cross-region network latency

### 2. Optimize Network Configuration
```bash
# Ensure proper network configuration for replication
# Check MTU settings, bandwidth, and latency between sites
```

### 3. Resource Planning
- Monitor cluster resource utilization
- Plan for adequate bandwidth between regions
- Ensure sufficient disk space for replication logs

### 4. Regular Health Checks
```bash
# Create monitoring script for database sync status
#!/bin/bash
rladmin status | grep -A 30 "DATABASES:" | grep -v "synced" | grep -v "Status"
if [ $? -eq 0 ]; then
    echo "WARNING: Databases with sync issues detected"
    rladmin status
fi
```

## Emergency Escalation

### When to Escalate
- Multiple databases showing sync issues
- Active-Active conflicts cannot be resolved
- Data inconsistency detected across regions
- Cluster showing signs of split-brain

### Escalation Information to Collect
```bash
# Collect comprehensive cluster information
rladmin status > cluster_status.txt
rladmin info cluster > cluster_info.txt
rladmin info db all > all_databases.txt

# For Active-Active databases
crdb-cli crdb list > crdb_list.txt
crdb-cli crdb status --crdb-guid <guid> > crdb_status.txt

# Collect logs
sudo tar -czf redis_enterprise_logs.tar.gz /var/opt/redislabs/log/
```

## Related Runbooks
- Redis Enterprise High Latency Investigation
- Redis Enterprise Node Maintenance Mode
- Redis Enterprise Connection Issues
