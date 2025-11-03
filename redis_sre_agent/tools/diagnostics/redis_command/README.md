# Redis CLI Command Tool Provider

Provides direct access to Redis diagnostic commands via redis-py for troubleshooting and monitoring.

## Overview

This provider executes read-only Redis diagnostic commands to help troubleshoot performance, security, memory, and replication issues. All commands are safe and non-destructive.

## Configuration

### Direct Configuration

```python
from redis_sre_agent.tools.diagnostics.redis_command import RedisCommandToolProvider

async with RedisCommandToolProvider(
    connection_url="redis://localhost:6379"
) as provider:
    result = await provider.info(section="memory")
    print(result)
```

### With Redis Instance

```python
from redis_sre_agent.core.instances import RedisInstance
from redis_sre_agent.tools.diagnostics.redis_command import RedisCommandToolProvider

redis_instance = RedisInstance(
    id="prod-cache",
    name="Production Cache",
    connection_url="redis://prod-redis:6379",
    environment="production",
    usage="cache"
)

async with RedisCommandToolProvider(redis_instance=redis_instance) as provider:
    result = await provider.slowlog(count=20)
```

## Available Tools

### 1. `redis_cli_{hash}_info`

Get Redis server information and statistics.

**Parameters:**
- `section` (string, optional): INFO section ("server", "memory", "clients", "stats", "replication", "cpu", "keyspace")

**Example:**
```python
{
    "section": "memory"
}
```

### 2. `redis_cli_{hash}_slowlog`

Query slow query log for performance diagnostics.

**Parameters:**
- `count` (integer, optional): Number of entries to retrieve (default: 10)

**Example:**
```python
{
    "count": 20
}
```

### 3. `redis_cli_{hash}_acl_log`

Query ACL security log for authentication and authorization failures.

**Parameters:**
- `count` (integer, optional): Number of entries to retrieve (default: 10)

**Example:**
```python
{
    "count": 10
}
```

### 4. `redis_cli_{hash}_config_get`

Get Redis configuration values.

**Parameters:**
- `pattern` (string, required): Configuration parameter pattern

**Example:**
```python
{
    "pattern": "maxmemory*"
}
```

### 5. `redis_cli_{hash}_client_list`

List connected Redis clients.

**Parameters:**
- `client_type` (string, optional): Client type filter ("normal", "master", "replica", "pubsub")

**Example:**
```python
{
    "client_type": "normal"
}
```

### 6. `redis_cli_{hash}_memory_doctor`

Get Redis's own memory analysis and recommendations.

**Parameters:** None

### 7. `redis_cli_{hash}_latency_doctor`

Get Redis's own latency analysis and recommendations.

**Parameters:** None

### 8. `redis_cli_{hash}_cluster_info`

Get cluster state and information (cluster mode only).

**Parameters:** None

### 9. `redis_cli_{hash}_replication_info`

Get replication status, role, and lag.

**Parameters:** None

### 10. `redis_cli_{hash}_memory_stats`

Get detailed memory statistics and breakdown.

**Parameters:** None

## Usage Examples

### Check Memory Usage

```python
async with RedisCliToolProvider() as provider:
    # Get memory info
    result = await provider.info(section="memory")
    print(f"Used memory: {result['data']['used_memory_human']}")

    # Get detailed analysis
    doctor = await provider.memory_doctor()
    print(doctor['analysis'])
```

### Diagnose Performance Issues

```python
async with RedisCliToolProvider() as provider:
    # Check slow queries
    slowlog = await provider.slowlog(count=10)
    for entry in slowlog['entries']:
        print(f"Slow command: {entry['command']} ({entry['duration_us']}μs)")

    # Get latency analysis
    latency = await provider.latency_doctor()
    print(latency['analysis'])
```

### Security Diagnostics

```python
async with RedisCliToolProvider() as provider:
    # Check ACL failures
    acl_log = await provider.acl_log(count=20)
    for entry in acl_log['entries']:
        print(f"ACL failure: {entry['reason']} - {entry['username']}")
```

### Check Configuration

```python
async with RedisCliToolProvider() as provider:
    # Get memory-related config
    config = await provider.config_get(pattern="maxmemory*")
    print(config['config'])

    # Get all config
    all_config = await provider.config_get(pattern="*")
```

### Monitor Connections

```python
async with RedisCliToolProvider() as provider:
    # List all clients
    clients = await provider.client_list()
    print(f"Connected clients: {clients['count']}")

    # List only normal clients
    normal = await provider.client_list(client_type="normal")
```

### Replication Diagnostics

```python
async with RedisCliToolProvider() as provider:
    repl = await provider.replication_info()
    print(f"Role: {repl['role']['type']}")
    print(f"Replication info: {repl['info']}")
```

## Integration with ToolManager

The provider automatically registers with ToolManager:

```python
from redis_sre_agent.tools.manager import ToolManager

async with ToolManager() as manager:
    tools = manager.get_tools()

    # Find Redis CLI tools
    redis_tools = [t for t in tools if "redis_cli" in t.name]
    print(f"Found {len(redis_tools)} Redis CLI tools")
```

## Safety Features

- **Read-only operations**: All commands are diagnostic/read-only
- **No destructive commands**: No FLUSHDB, DEL, CONFIG SET, etc.
- **No KEYS command**: Avoided due to performance impact on large databases
- **Graceful error handling**: Returns error status instead of raising exceptions

## Common Use Cases

### Memory Issues
1. `info(section="memory")` - Check current memory usage
2. `memory_doctor()` - Get Redis's memory recommendations
3. `memory_stats()` - Detailed memory breakdown
4. `config_get(pattern="maxmemory*")` - Check memory limits

### Performance Issues
1. `slowlog(count=20)` - Find slow queries
2. `latency_doctor()` - Get latency analysis
3. `info(section="stats")` - Check command statistics
4. `client_list()` - Check for problematic clients

### Security Issues
1. `acl_log(count=20)` - Check authentication failures
2. `config_get(pattern="acl*")` - Check ACL configuration
3. `client_list()` - Identify connected clients

### Replication Issues
1. `replication_info()` - Check replication status and lag
2. `info(section="replication")` - Detailed replication info
3. `config_get(pattern="repl*")` - Check replication config

## See Also

- [Prometheus Metrics Provider](../../metrics/prometheus/README.md) - For time-series metrics
- [Redis Documentation](https://redis.io/commands) - Official Redis command reference
