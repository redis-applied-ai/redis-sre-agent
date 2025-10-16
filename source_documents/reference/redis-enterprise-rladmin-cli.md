# Redis Enterprise rladmin CLI Reference

**Category**: reference
**Severity**: high
**Source**: Redis Enterprise CLI Documentation

## Overview

`rladmin` is the Redis Enterprise command-line administration tool for managing clusters, nodes, databases, and shards. It can be used interactively or non-interactively.

## Usage Modes

### Interactive Mode
```bash
# Enter interactive mode
rladmin

# Then type commands at the prompt
rladmin> status
rladmin> info cluster
rladmin> exit
```

### Non-Interactive Mode
```bash
# Pipe commands for automation
echo "status" | rladmin

# Multiple commands
echo -e "status\ninfo cluster" | rladmin

# In Docker containers
docker exec -i redis-enterprise-node1 rladmin <<EOF
status
info cluster
EOF
```

## Core Commands

### status
Displays current cluster status including nodes, databases, endpoints, and shards.

```bash
# Show complete cluster status
rladmin status

# In non-interactive mode
echo "status" | rladmin
```

**Output includes:**
- CLUSTER: Cluster name and configuration
- NODES: All nodes with status, role, address, and resources
- DATABASES: All databases with status, endpoints, and replication
- ENDPOINTS: Database connection endpoints
- SHARDS: Shard distribution across nodes

**Note:** There are NO subcommands like `status databases` or `status nodes`. Use `status` alone to see everything.

### info
Shows detailed configuration of cluster, databases, nodes, or proxies.

```bash
# Cluster information
rladmin info cluster

# All databases
rladmin info db all

# Specific database by name
rladmin info db <database_name>

# Specific database by ID
rladmin info db db:<id>

# All nodes
rladmin info node all

# Specific node
rladmin info node <node_id>

# Proxy information
rladmin info proxy all
```

### node
Manage node operations.

```bash
# Put node in maintenance mode
rladmin node <node_id> maintenance_mode on

# Exit maintenance mode
rladmin node <node_id> maintenance_mode off

# Remove a node from cluster
rladmin node <node_id> remove

# Snapshot node configuration
rladmin node <node_id> snapshot
```

### restart
Restart databases or services.

```bash
# Restart a database
rladmin restart db <database_name>

# Restart a database by ID
rladmin restart db db:<id>
```

### tune
Modify database configuration.

```bash
# Tune database parameters
rladmin tune db <database_name> <parameter> <value>

# Examples:
rladmin tune db mydb max_connections 10000
rladmin tune db mydb eviction_policy allkeys-lru
rladmin tune db mydb max_memory 10gb
```

### migrate
Move shards or endpoints between nodes.

```bash
# Migrate shard to different node
rladmin migrate shard <shard_id> target_node <node_id>

# Migrate endpoint
rladmin migrate endpoint <endpoint_id> target_node <node_id>
```

### failover
Trigger failover operations.

```bash
# Failover a database
rladmin failover db <database_name>

# Failover specific shard
rladmin failover shard <shard_id>
```

### cluster
Cluster-level operations.

```bash
# Set cluster configuration
rladmin cluster config <parameter> <value>

# Reset cluster configuration
rladmin cluster reset_password
```

### verify
Verify cluster integrity.

```bash
# Verify cluster health
rladmin verify cluster

# Verify database
rladmin verify db <database_name>
```

### help
Get help on commands.

```bash
# Show available commands
rladmin help

# In interactive mode, use ? for help
rladmin> ?
```

## Common Patterns

### Check Cluster Health
```bash
echo "status" | rladmin
```

### Get Database Details
```bash
echo "info db mydb" | rladmin | grep -E "status|endpoint|memory|shards"
```

### Monitor Node Status
```bash
echo "status" | rladmin | grep -A 10 "NODES:"
```

### Check Maintenance Mode
```bash
echo "info node 1" | rladmin | grep maintenance
```

### Restart Unresponsive Database
```bash
echo "restart db mydb" | rladmin
```

### Check Shard Distribution
```bash
echo "status" | rladmin | grep -A 20 "SHARDS:"
```

## Automation Examples

### Docker Container Execution
```bash
# Single command
docker exec -i redis-enterprise-node1 rladmin <<< "status"

# Multiple commands
docker exec -i redis-enterprise-node1 rladmin <<EOF
status
info cluster
info db all
EOF
```

### Script Usage
```bash
#!/bin/bash
# Check if database is healthy

DB_NAME="mydb"

# Get database status
DB_STATUS=$(echo "info db $DB_NAME" | rladmin | grep "status:" | awk '{print $2}')

if [ "$DB_STATUS" != "active" ]; then
    echo "Database $DB_NAME is not active: $DB_STATUS"
    exit 1
fi

echo "Database $DB_NAME is healthy"
```

### Monitoring Script
```bash
#!/bin/bash
# Monitor cluster health

while true; do
    echo "=== Cluster Status at $(date) ==="
    echo "status" | rladmin | grep -E "CLUSTER|NODES|DATABASES"
    sleep 60
done
```

## Important Notes

1. **No subcommands for status**: Use `rladmin status` alone, not `rladmin status databases` or `rladmin status nodes`

2. **Interactive vs Non-Interactive**:
   - Interactive: Type `rladmin` then enter commands
   - Non-interactive: Pipe commands with `echo "command" | rladmin`

3. **Docker Execution**: Always use `-i` flag with `docker exec` for piping commands

4. **Parsing Output**: Use `grep`, `awk`, or `sed` to parse output for automation

5. **Database Identification**: Can use database name or `db:<id>` format

6. **Node Identification**: Use numeric node ID (e.g., `1`, `2`, `3`)

## Common Errors

### "invalid token 'list databases'"
**Problem**: Trying to use non-existent `list` command
**Solution**: Use `rladmin status` instead

### "invalid token 'status databases'"
**Problem**: Trying to use non-existent subcommand
**Solution**: Use `rladmin status` alone (shows all info)

### Command hangs in Docker
**Problem**: Running interactive mode without `-i` flag
**Solution**: Use `docker exec -i` and pipe commands

## Related Documentation

- Redis Enterprise REST API for programmatic access
- Redis Enterprise Cluster Manager UI for visual administration
- Redis CLI (`redis-cli`) for database-level operations

## See Also

- `redis-enterprise-connection-issues.md` - Troubleshooting connectivity
- `redis-enterprise-node-maintenance-mode.md` - Node maintenance procedures
- `redis-enterprise-high-latency-investigation.md` - Performance troubleshooting
