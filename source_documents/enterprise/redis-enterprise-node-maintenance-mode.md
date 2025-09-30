# Redis Enterprise Node in Maintenance Mode

**Category**: enterprise
**Severity**: warning
**Source**: Generated runbook for Redis SRE Agent

## Symptoms
- Node showing as "maintenance" in cluster status
- Databases not accessible on specific node
- Cluster operations restricted or failing
- Alerts about node being unavailable
- No one remembers putting node in maintenance mode

## Root Cause Analysis

### 1. Check Node Status
```bash
# Check which nodes are in maintenance mode
rladmin status nodes | grep -E "node:|status:"

# Get detailed node information
rladmin info node <node_id>
```

### 2. Check Maintenance Mode History
```bash
# Check cluster events for maintenance mode changes
rladmin status | grep -A10 -B10 maintenance

# Check logs for maintenance mode entries
sudo grep -i maintenance /var/opt/redislabs/log/rlec_supervisor.log | tail -20
```

### 3. Check Who Set Maintenance Mode
```bash
# Check audit logs if available
sudo grep -i "maintenance\|maint" /var/opt/redislabs/log/audit.log | tail -10

# Check system logs for user actions
sudo grep -i maintenance /var/log/messages | tail -10
```

### 4. Check Node Health
```bash
# Verify node is actually healthy
rladmin status nodes | grep -A5 -B5 <node_id>

# Check node resources
rladmin info node <node_id> | grep -E "cpu|memory|disk"
```

### 5. Check Impact on Databases
```bash
# Check which databases are affected
rladmin status databases | grep -E "name:|shards:"

# Check shard distribution
rladmin status shards | grep <node_id>
```

## Immediate Remediation

### Option 1: Exit Maintenance Mode (if safe)
```bash
# First, verify node is healthy
rladmin info node <node_id>

# If node is healthy, exit maintenance mode
rladmin node <node_id> maintenance_mode off

# Verify node is back online
rladmin status nodes | grep <node_id>
```

### Option 2: Check for Ongoing Operations
```bash
# Check if there are ongoing maintenance operations
rladmin status | grep -i "operation\|task\|migration"

# If operations are running, wait for completion before exiting maintenance
```

### Option 3: Verify Cluster Health Before Exiting
```bash
# Check cluster quorum and health
rladmin status

# Ensure other nodes are healthy
rladmin status nodes | grep -v maintenance

# Check database availability
rladmin status databases | grep -E "status:|endpoint:"
```

## Advanced Troubleshooting

### 1. Check Why Node Was Put in Maintenance
```bash
# Check for recent system changes
sudo last | head -20

# Check for scheduled maintenance windows
# Review change management records

# Check for automated maintenance triggers
sudo crontab -l | grep -i redis
```

### 2. Verify Node Hardware Health
```bash
# Check system resources
top -b -n 1 | head -20
df -h
free -h

# Check for hardware errors
dmesg | grep -i error | tail -10
sudo smartctl -a /dev/sda  # Check disk health
```

### 3. Check Network Connectivity
```bash
# Test connectivity to other cluster nodes
rladmin status nodes | grep addr

# Ping other nodes
ping -c 3 <other_node_ip>

# Check cluster communication
rladmin cluster debug_info | grep -i network
```

### 4. Check for Stuck Processes
```bash
# Check Redis Enterprise processes
ps aux | grep redis
ps aux | grep rlec

# Check for zombie or stuck processes
ps aux | grep -E "Z|<defunct>"
```

## Safe Exit from Maintenance Mode

### 1. Pre-Exit Checklist
```bash
# Verify node health
rladmin info node <node_id> | grep -E "status|health|cpu|memory"

# Check cluster has quorum
rladmin status | grep -E "cluster|quorum"

# Verify no critical operations running
rladmin status | grep -i operation
```

### 2. Exit Maintenance Mode
```bash
# Exit maintenance mode
rladmin node <node_id> maintenance_mode off

# Monitor node status during transition
watch "rladmin status nodes | grep <node_id>"
```

### 3. Post-Exit Verification
```bash
# Verify node is fully operational
rladmin status nodes | grep <node_id>

# Check database accessibility
rladmin status databases

# Verify shard distribution
rladmin status shards | grep <node_id>
```

## Planned Maintenance Mode Entry

### 1. Pre-Maintenance Checklist
```bash
# Check cluster health
rladmin status

# Verify sufficient resources on other nodes
rladmin status nodes | grep -E "cpu|memory|free_disk"

# Check database distribution
rladmin status shards
```

### 2. Enter Maintenance Mode Safely
```bash
# Put node in maintenance mode
rladmin node <node_id> maintenance_mode on

# Verify shards are migrated away
rladmin status shards | grep <node_id>

# Monitor migration progress
watch "rladmin status | grep -i operation"
```

### 3. Document Maintenance
```bash
# Document who, what, when, why
echo "$(date): Node <node_id> put in maintenance by $(whoami) for <reason>" >> /var/log/redis_maintenance.log
```

## Long-term Prevention

### 1. Maintenance Documentation
- Maintain a maintenance log
- Document all planned maintenance windows
- Create maintenance procedures and checklists
- Implement change management process

### 2. Monitoring and Alerting
```bash
# Set up alerts for nodes in maintenance mode
# Monitor maintenance mode duration
# Alert if maintenance mode exceeds expected time
```

### 3. Automation and Procedures
- Create scripts for safe maintenance mode entry/exit
- Implement approval workflows for maintenance
- Automate health checks before/after maintenance
- Set up automatic exit from maintenance after time limit

### 4. Team Communication
- Use maintenance calendars
- Implement notification systems
- Create handover procedures
- Document emergency contacts

## Emergency Escalation

### When to Escalate
- Node stuck in maintenance mode
- Cannot exit maintenance mode safely
- Cluster losing quorum due to maintenance
- Critical databases affected

### Escalation Information to Collect
```bash
# Collect cluster status
rladmin status > cluster_status.txt
rladmin status nodes > node_status.txt
rladmin status databases > database_status.txt

# Collect node-specific information
rladmin info node <node_id> > node_info.txt

# Collect maintenance history
sudo grep -i maintenance /var/opt/redislabs/log/rlec_supervisor.log > maintenance_history.txt

# System information
uptime > system_info.txt
df -h >> system_info.txt
free -h >> system_info.txt
```

## Common Maintenance Mode Scenarios

### 1. Forgotten Maintenance Mode
- Node left in maintenance after completed work
- No documentation of who set it
- Solution: Verify health and exit safely

### 2. Automatic Maintenance Mode
- Node automatically entered maintenance due to health issues
- Check logs for root cause
- Fix underlying issue before exiting

### 3. Stuck in Maintenance Mode
- Cannot exit maintenance mode
- May indicate cluster or node issues
- Requires careful investigation

### 4. Emergency Maintenance
- Node needs immediate maintenance
- Follow emergency procedures
- Ensure cluster stability

## Related Runbooks
- Redis Enterprise High Latency Investigation
- Redis Enterprise Connection Issues
- Redis Enterprise Database Sync Issues
