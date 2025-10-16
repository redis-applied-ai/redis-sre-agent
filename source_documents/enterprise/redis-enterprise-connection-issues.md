# Redis Enterprise Connection Issues

**Category**: enterprise
**Severity**: critical
**Source**: Generated runbook for Redis SRE Agent

## Symptoms
- Applications cannot connect to Redis databases
- Connection timeouts or refused connections
- "Connection reset by peer" errors
- Intermittent connectivity issues
- Authentication failures

## Root Cause Analysis

### 1. Check Database Status
```bash
# Check if database is online and accessible
rladmin status | grep <database_name>

# Check database endpoint information
rladmin info db <database_name> | grep -E "endpoint|port|status"
```

### 2. Check Node and Cluster Status
```bash
# Check cluster overall health (shows nodes, databases, shards, endpoints)
rladmin status

# Check individual node details
rladmin info node <node_id>
```

### 3. Check Network Connectivity
```bash
# Test basic connectivity to database port
telnet <database_endpoint> <port>

# Test Redis connectivity
redis-cli -h <database_endpoint> -p <port> ping
```

### 4. Check Connection Limits
```bash
# Check current connections vs limits
rladmin info db <database_name> | grep -E "connections|max_connections"

# Check per-node connection usage
rladmin status | grep -A 20 "NODES:" | grep -E "connections|max_connections"
```

### 5. Check Authentication Configuration
```bash
# Check database authentication settings
rladmin info db <database_name> | grep -E "auth|password|acl"
```

## Immediate Remediation

### Option 1: Database Restart
```bash
# If database is unresponsive, restart it
rladmin restart db <database_name>

# Monitor restart progress
rladmin status | grep <database_name>
```

### Option 2: Check and Clear Connection Limits
```bash
# Check current connections
rladmin info db <database_name> | grep connections

# If at connection limit, identify and close idle connections
redis-cli -h <endpoint> -p <port> client list
redis-cli -h <endpoint> -p <port> client kill type normal
```

### Option 3: Verify Network Configuration
```bash
# Check firewall rules
sudo iptables -L | grep <port>

# Check if port is listening
netstat -tlnp | grep <port>

# Check DNS resolution
nslookup <database_endpoint>
```

### Option 4: Authentication Troubleshooting
```bash
# Test authentication
redis-cli -h <endpoint> -p <port> -a <password> ping

# Check ACL configuration (if using ACLs)
redis-cli -h <endpoint> -p <port> -a <password> acl list
```

## Advanced Troubleshooting

### 1. Check Proxy Status
```bash
# Check proxy health and configuration
rladmin status | grep -A5 "Proxy"

# Check proxy logs for connection errors
sudo tail -f /var/opt/redislabs/log/proxy_*.log | grep -i error
```

### 2. Network Diagnostics
```bash
# Check network interface status
ip addr show
ip route show

# Check for packet loss
ping -c 10 <database_endpoint>

# Check network statistics
ss -tuln | grep <port>
```

### 3. SSL/TLS Issues (if applicable)
```bash
# Test SSL connection
openssl s_client -connect <endpoint>:<port>

# Check certificate validity
rladmin info db <database_name> | grep -i ssl
```

### 4. Check Resource Constraints
```bash
# Check if node resources are exhausted
rladmin status | grep -A 20 "NODES:" | grep -E "cpu|memory|free_disk"

# Check system limits
ulimit -n  # File descriptor limits
cat /proc/sys/net/core/somaxconn  # Socket backlog
```

### 5. Application-Side Diagnostics
```bash
# Check application connection pool settings
# Verify connection timeout configurations
# Check for connection leaks in application code
```

## Connection Pool Optimization

### 1. Database Connection Settings
```bash
# Adjust database connection limits if needed
rladmin tune db <database_name> max_connections <value>

# Check current connection distribution
redis-cli -h <endpoint> -p <port> info clients
```

### 2. Proxy Configuration
```bash
# Check proxy connection settings
rladmin info proxy | grep -E "connections|threads"

# Tune proxy if needed (advanced operation)
```

### 3. Application Best Practices
- Implement proper connection pooling
- Set appropriate connection timeouts
- Handle connection failures gracefully
- Monitor connection pool metrics

## Long-term Prevention

### 1. Monitoring and Alerting
- Monitor connection count vs limits
- Alert on connection failures
- Track connection pool health
- Monitor network latency and packet loss

### 2. Capacity Planning
```bash
# Regular assessment of connection usage
rladmin info db <database_name> | grep connections

# Plan for peak connection loads
```

### 3. Network Infrastructure
- Ensure redundant network paths
- Monitor network equipment health
- Regular network performance testing
- Proper firewall and security group configuration

### 4. Application Architecture
- Implement circuit breakers
- Use connection pooling libraries
- Design for connection failure scenarios
- Regular connection pool tuning

## Emergency Escalation

### When to Escalate
- Multiple databases affected
- Cluster-wide connectivity issues
- Network infrastructure problems
- Authentication system failures

### Escalation Information to Collect
```bash
# Collect cluster and database status
rladmin status > cluster_status.txt
rladmin info cluster > cluster_info.txt
rladmin info node all > all_nodes.txt

# Collect database-specific information
rladmin info db <database_name> > db_info.txt

# Network diagnostics
netstat -tlnp > netstat.txt
ss -tuln > ss.txt
ip addr show > ip_config.txt

# Connection information
redis-cli -h <endpoint> -p <port> client list > client_list.txt
redis-cli -h <endpoint> -p <port> info clients > client_info.txt

# System logs
sudo tail -100 /var/opt/redislabs/log/rlec_supervisor.log > supervisor.log
sudo tail -100 /var/log/messages > system.log
```

## Common Connection Error Patterns

### 1. "Connection refused"
- Database is down or not listening
- Firewall blocking connections
- Wrong endpoint or port

### 2. "Connection timeout"
- Network connectivity issues
- High latency or packet loss
- Resource exhaustion on server

### 3. "Authentication failed"
- Wrong password or credentials
- ACL configuration issues
- Database authentication disabled when expected

### 4. "Too many connections"
- Connection limit reached
- Connection pool not properly configured
- Connection leaks in application

## Related Runbooks
- Redis Enterprise High Latency Investigation
- Redis Enterprise Database Sync Issues
- Redis Enterprise Node Maintenance Mode
