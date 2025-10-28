# Redis Enterprise Admin API Tool Provider

This provider enables LLMs to inspect and monitor Redis Enterprise clusters through the REST API. It provides read-only access to cluster information, database details, node status, and operational metrics.

## Features

### Cluster Management
- **Get cluster info**: View cluster configuration, settings, and alert configuration
- **Get cluster stats**: Monitor cluster-wide performance metrics
- **Get cluster alerts**: Check cluster-level alert settings

### Database (BDB) Operations
- **List databases**: Discover all databases in the cluster
- **Get database**: View detailed database configuration and status
- **Get database stats**: Monitor database performance metrics
- **Get database alerts**: Check database-specific alert configuration

### Node Management
- **List nodes**: View all nodes in the cluster
- **Get node**: Inspect individual node details including:
  - Status (active, offline, maintenance mode via `accept_servers` field)
  - Resource utilization
  - Shard placement
  - Network addresses
- **Get node stats**: Monitor node-specific performance metrics

### Shard Management
- **List shards**: View all shards and their distribution
- **Get shard**: Inspect individual shard details including:
  - Role (master/replica)
  - Assigned slots
  - Node placement
  - Status

### Actions & Operations
- **List actions**: Monitor all running, pending, or completed operations
- **Get action**: Check status of specific long-running operations including:
  - Progress percentage
  - Status (queued, running, completed, failed)
  - Error messages
  - Pending operations per shard

### Module Information
- **List modules**: View available Redis modules (RediSearch, RedisJSON, etc.)

## Configuration

The provider takes admin API credentials from the `RedisInstance` object, allowing each instance to have its own admin API configuration:

- `admin_url`: Redis Enterprise admin API URL (e.g., `https://cluster.example.com:9443`)
- `admin_username`: Admin API username
- `admin_password`: Admin API password

The `RedisInstance` must have `instance_type='redis_enterprise'` and `admin_url` set.

Optional environment variable for SSL verification:
```bash
TOOLS_REDIS_ENTERPRISE_ADMIN_VERIFY_SSL=true  # Default: true
```

## Use Cases

### 1. Detecting Maintenance Mode

**Question**: "Is node 2 in maintenance mode?"

The LLM can call `get_node(uid=2)` and check the `accept_servers` field:
- `accept_servers: false` = Node is in maintenance mode (not accepting new shards)
- `accept_servers: true` = Node is accepting new shards

### 2. Checking Migration Status

**Question**: "Are there any ongoing migrations?"

The LLM can call `list_actions()` and filter for migration-related actions, checking:
- Action name (e.g., "migrate_shard", "rebalance")
- Status (queued, running, completed, failed)
- Progress percentage
- Pending operations

### 3. Monitoring Replication

**Question**: "What's the replication status for database 5?"

The LLM can call `get_database(uid=5)` and examine:
- `replication` field (true/false)
- `replica_sources` for replica-of configuration
- `sync_sources` for synchronization status

Then call `list_shards()` filtered by database to see:
- Master/replica shard distribution
- Shard placement across nodes

### 4. Identifying Stuck Operations

**Question**: "Are there any stuck or long-running operations?"

The LLM can call `list_actions()` and analyze:
- Actions with status "running" for extended periods
- Actions with progress stuck at same percentage
- Actions with status "failed"
- `pending_ops` field showing operations waiting to run

Example response analysis:
```json
{
  "action_uid": "abc-123",
  "name": "SMCreateBDB",
  "status": "running",
  "progress": 45.0,
  "creation_time": 1742595918,  // Compare with current time
  "additional_info": {
    "pending_ops": {
      "3": {
        "op_name": "wait_for_persistence",
        "status_description": "Waiting for AOF sync",
        "progress": 45.0,
        "heartbeat": 1742596000  // Last progress update
      }
    }
  }
}
```

### 5. Cluster Health Check

**Question**: "Give me a health overview of the cluster"

The LLM can orchestrate multiple calls:
1. `get_cluster_info()` - Check cluster configuration
2. `list_nodes()` - Verify all nodes are active
3. `list_databases()` - Check database statuses
4. `list_actions()` - Look for failed or stuck operations
5. `get_cluster_stats()` - Review performance metrics

### 6. Shard Distribution Analysis

**Question**: "How are shards distributed across nodes?"

The LLM can call:
1. `list_nodes()` - Get all nodes and their `shard_count`
2. `list_shards()` - Get detailed shard placement
3. Analyze distribution for:
   - Imbalanced shard counts
   - Master/replica placement
   - Rack awareness violations

### 7. Alert Configuration Review

**Question**: "What alerts are configured for database 3?"

The LLM can call:
1. `get_database_alerts(uid=3)` - Database-specific alerts
2. `get_cluster_alerts()` - Cluster-wide alert settings
3. Compare thresholds and enabled alerts

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

## Example Usage

```python
from redis_sre_agent.core.instances import RedisInstance
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

    # List all databases
    databases = await provider.list_databases()

    # Check for stuck operations
    actions = await provider.list_actions()
    stuck = [a for a in actions["actions"]
             if a["status"] == "running" and a["progress"] < 100]

    # Check node maintenance mode
    node = await provider.get_node(uid=2)
    in_maintenance = not node["node"]["accept_servers"]
```

## Security Considerations

- All operations are **read-only** - no modifications to cluster configuration
- Requires valid admin credentials
- SSL verification enabled by default
- Credentials should be stored in environment variables or secure secret management
- API calls are logged for audit purposes

## Limitations

- Read-only access (no cluster modifications)
- Requires network access to Redis Enterprise cluster API (port 9443)
- Some endpoints may require specific permissions based on user role
- Rate limiting may apply based on cluster configuration
