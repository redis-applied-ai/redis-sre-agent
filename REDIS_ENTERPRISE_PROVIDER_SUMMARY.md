# Redis Enterprise Admin API Tool Provider - Summary

## What Was Built

A comprehensive Redis Enterprise admin API tool provider that enables LLMs to inspect and monitor Redis Enterprise clusters through the REST API.

### Branch
`feat/redis-enterprise-admin-api-provider`

## Key Features

### 15 Tools for Cluster Management

1. **Cluster Operations**
   - `get_cluster_info` - View cluster configuration and settings
   - `get_cluster_stats` - Monitor cluster-wide performance metrics
   - `get_cluster_alerts` - Check cluster-level alert settings

2. **Database (BDB) Operations**
   - `list_databases` - Discover all databases in the cluster
   - `get_database` - View detailed database configuration and status
   - `get_database_stats` - Monitor database performance metrics
   - `get_database_alerts` - Check database-specific alert configuration

3. **Node Management**
   - `list_nodes` - View all nodes in the cluster
   - `get_node` - Inspect individual node details (including maintenance mode)
   - `get_node_stats` - Monitor node-specific performance metrics

4. **Shard Management**
   - `list_shards` - View all shards and their distribution
   - `get_shard` - Inspect individual shard details

5. **Actions & Operations**
   - `list_actions` - Monitor all running, pending, or completed operations
   - `get_action` - Check status of specific long-running operations

6. **Module Information**
   - `list_modules` - View available Redis modules (RediSearch, RedisJSON, etc.)

## Architecture Decisions

### 1. Instance-Level Configuration (Not Global)
**Problem**: Original design used global config with a single admin URL for all instances.

**Solution**: Admin API credentials come from the `RedisInstance` object:
- `admin_url`: Redis Enterprise admin API URL
- `admin_username`: Admin API username
- `admin_password`: Admin API password

This allows each Redis Enterprise instance to have its own admin API configuration.

### 2. RedisInstance Model Updates
Added three new fields to `RedisInstance`:
```python
admin_url: Optional[str] = None
admin_username: Optional[str] = None
admin_password: Optional[str] = None
```

These fields are only applicable when `instance_type='redis_enterprise'`.

### 3. Testing Strategy
**No testcontainers** - Redis Enterprise setup is too complex and slow for unit tests.

Instead, tests use **mocked HTTP responses** to verify:
- Tool schema generation
- HTTP request construction
- Response parsing
- Error handling

All 14 tests pass successfully.

## Use Cases Addressed

### 1. Detecting Maintenance Mode
**Question**: "Is node 2 in maintenance mode?"

**Solution**: Call `get_node(uid=2)` and check `accept_servers` field:
- `accept_servers: false` = Node is in maintenance mode
- `accept_servers: true` = Node is accepting new shards

### 2. Monitoring Migration Status
**Question**: "Are there any ongoing migrations?"

**Solution**: Call `list_actions()` and filter for migration-related actions:
- Check action name (e.g., "migrate_shard", "rebalance")
- Monitor status (queued, running, completed, failed)
- Track progress percentage
- Review pending operations

### 3. Checking Replication Status
**Question**: "What's the replication status for database 5?"

**Solution**:
1. Call `get_database(uid=5)` to examine:
   - `replication` field
   - `replica_sources` for replica-of configuration
   - `sync_sources` for synchronization status
2. Call `list_shards()` to see master/replica distribution

### 4. Identifying Stuck Operations
**Question**: "Are there any stuck or long-running operations?"

**Solution**: Call `list_actions()` and analyze:
- Actions with status "running" for extended periods
- Actions with progress stuck at same percentage
- Actions with status "failed"
- `pending_ops` field showing operations waiting to run

### 5. Cluster Health Check
**Question**: "Give me a health overview of the cluster"

**Solution**: Orchestrate multiple calls:
1. `get_cluster_info()` - Check cluster configuration
2. `list_nodes()` - Verify all nodes are active
3. `list_databases()` - Check database statuses
4. `list_actions()` - Look for failed or stuck operations
5. `get_cluster_stats()` - Review performance metrics

### 6. Shard Distribution Analysis
**Question**: "How are shards distributed across nodes?"

**Solution**:
1. `list_nodes()` - Get all nodes and their `shard_count`
2. `list_shards()` - Get detailed shard placement
3. Analyze for imbalanced distribution or rack awareness violations

## Files Created/Modified

### New Files
- `redis_sre_agent/tools/admin/__init__.py`
- `redis_sre_agent/tools/admin/redis_enterprise/__init__.py`
- `redis_sre_agent/tools/admin/redis_enterprise/provider.py` (1,029 lines)
- `redis_sre_agent/tools/admin/redis_enterprise/README.md`
- `tests/tools/test_redis_enterprise_admin_provider.py` (14 tests)

### Modified Files
- `redis_sre_agent/api/instances.py` - Added admin_url, admin_username, admin_password fields

## API Endpoints Used

| Tool | Endpoint | Purpose |
|------|----------|---------|
| get_cluster_info | GET /v1/cluster | Cluster configuration |
| list_databases | GET /v1/bdbs | All databases |
| get_database | GET /v1/bdbs/{uid} | Single database |
| list_nodes | GET /v1/nodes | All nodes |
| get_node | GET /v1/nodes/{uid} | Single node |
| list_modules | GET /v1/modules | Available modules |
| get_database_stats | GET /v1/bdbs/stats/{uid} | Database metrics |
| get_cluster_stats | GET /v1/cluster/stats | Cluster metrics |
| list_actions | GET /v2/actions | All operations |
| get_action | GET /v2/actions/{uid} | Single operation |
| list_shards | GET /v1/shards | All shards |
| get_shard | GET /v1/shards/{uid} | Single shard |
| get_cluster_alerts | GET /v1/cluster | Alert settings |
| get_database_alerts | GET /v1/bdbs/{uid}/alerts | Database alerts |
| get_node_stats | GET /v1/nodes/stats/{uid} | Node metrics |

## Security Considerations

- **Read-only operations** - No cluster modifications possible
- **Per-instance credentials** - Each instance has its own admin API access
- **SSL verification** - Enabled by default (configurable via env var)
- **Credential storage** - Stored in RedisInstance object (should use secure storage)
- **Audit logging** - All API calls are logged

## Example Usage

```python
from redis_sre_agent.api.instances import RedisInstance
from redis_sre_agent.tools.admin.redis_enterprise import RedisEnterpriseAdminToolProvider

# Create a Redis instance with admin API configuration
instance = RedisInstance(
    id="prod-cluster-1",
    name="production-cluster",
    connection_url="redis://cluster.example.com:6379",
    environment="production",
    usage="cache",
    description="Production Redis Enterprise cluster",
    instance_type="redis_enterprise",
    admin_url="https://cluster.example.com:9443",
    admin_username="admin@example.com",
    admin_password="secret",
)

# Create provider for this instance
async with RedisEnterpriseAdminToolProvider(redis_instance=instance) as provider:
    # Get cluster info
    cluster_info = await provider.get_cluster_info()

    # Check for stuck operations
    actions = await provider.list_actions()
    stuck = [a for a in actions["actions"]
             if a["status"] == "running" and a["progress"] < 100]

    # Check node maintenance mode
    node = await provider.get_node(uid=2)
    in_maintenance = not node["node"]["accept_servers"]
```

## Next Steps

1. **Integration Testing** - Test against a real Redis Enterprise cluster
2. **Tool Registration** - Register provider with the tool manager
3. **Agent Integration** - Enable LLM to use these tools in conversations
4. **Documentation** - Add to main README and user guides
5. **Secure Credential Storage** - Consider using secrets manager for admin credentials

## Commit

Branch: `feat/redis-enterprise-admin-api-provider`
Commit: `7a32254` - "Add Redis Enterprise admin API tool provider"
