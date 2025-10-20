# Important Notes about Redis Enterprise Compatibility with Open Source Redis

## Overview

Redis Enterprise Software is compatible with Redis Open Source but has important differences in command support, configuration settings, and operational management. This document summarizes key compatibility considerations when working with Redis Enterprise databases.

**Critical Note**: Many database configuration details and operational information that would normally be available via Redis commands are **only accessible through the Redis Enterprise Admin REST API** (available via the `re_admin` tool provider).

---

## Command Compatibility

Redis Enterprise blocks or modifies many Redis Open Source commands because it manages clustering, persistence, replication, and other operational aspects automatically.

### ❌ Unsupported Server Management Commands

The following Redis Open Source commands are **NOT supported** in Redis Enterprise:

#### Access Control (ACL) Commands
- `ACL DELUSER` - Use Redis Enterprise Cluster Manager UI or REST API instead
- `ACL GENPASS` - Not supported
- `ACL LOAD` - Not supported
- `ACL LOG` - Not supported
- `ACL SAVE` - Not supported
- `ACL SETUSER` - Use Redis Enterprise Cluster Manager UI or REST API instead

**Note**: ACL users must be managed through the Cluster Manager UI or Admin REST API, not via Redis commands.

#### Configuration Commands
- `CONFIG RESETSTAT` - Not supported

**Note**: `CONFIG GET` and `CONFIG SET` are supported but only for a limited subset of settings (see Configuration Settings section below).

#### Monitoring Commands
- `LATENCY DOCTOR` - Not supported
- `LATENCY GRAPH` - Not supported
- `LATENCY HELP` - Not supported
- `LATENCY HISTORY` - Not supported
- `LATENCY LATEST` - Not supported
- `LATENCY RESET` - Not supported
- `MEMORY DOCTOR` - Not supported
- `MEMORY MALLOC-STATS` - Not supported
- `MEMORY PURGE` - Not supported
- `MEMORY STATS` - Not supported

**Note**: Use Cluster Manager UI metrics and the Admin REST API for monitoring instead.

#### Persistence Commands
All persistence commands are **NOT supported** - Redis Enterprise manages persistence automatically:
- `BGREWRITEAOF` - Not supported
- `BGSAVE` - Not supported
- `LASTSAVE` - Not supported
- `SAVE` - Not supported

**Note**: Configure persistence through Cluster Manager UI or Admin REST API.

#### Replication Commands
All replication commands are **NOT supported** - Redis Enterprise manages replication automatically:
- `FAILOVER` - Not supported
- `MIGRATE` - Not supported
- `PSYNC` - Not supported
- `REPLCONF` - Not supported
- `REPLICAOF` - Not supported
- `RESTORE-ASKING` - Not supported
- `ROLE` - Not supported
- `SLAVEOF` - Not supported (deprecated)
- `SYNC` - Not supported

#### Module Commands
- `MODULE HELP` - Not supported
- `MODULE LOAD` - Not supported (modules managed via Cluster Manager)
- `MODULE LOADEX` - Not supported
- `MODULE UNLOAD` - Not supported

**Note**: `MODULE LIST` is supported. Manage modules via Cluster Manager UI or REST API.

#### General Server Commands
- `DEBUG` - Not supported
- `SHUTDOWN` - Not supported
- `SWAPDB` - Not supported

#### Cluster Commands
Most cluster commands are **NOT supported** unless OSS Cluster API is enabled:
- `ASKING` - Not supported
- `CLUSTER ADDSLOTS` - Not supported
- `CLUSTER ADDSLOTSRANGE` - Not supported
- `CLUSTER BUMPEPOCH` - Not supported
- `CLUSTER COUNT-FAILURE-REPORTS` - Not supported
- `CLUSTER COUNTKEYSINSLOT` - Not supported
- `CLUSTER DELSLOTS` - Not supported
- `CLUSTER DELSLOTSRANGE` - Not supported
- `CLUSTER FAILOVER` - Not supported
- `CLUSTER FLUSHSLOTS` - Not supported
- `CLUSTER FORGET` - Not supported
- `CLUSTER GETKEYSINSLOT` - Not supported
- `CLUSTER LINKS` - Not supported
- `CLUSTER MEET` - Not supported
- `CLUSTER MYID` - Not supported
- `CLUSTER MYSHARDID` - Not supported
- `CLUSTER REPLICAS` - Not supported
- `CLUSTER REPLICATE` - Not supported
- `CLUSTER RESET` - Not supported
- `CLUSTER SAVECONFIG` - Not supported
- `CLUSTER SET-CONFIG-EPOCH` - Not supported
- `CLUSTER SETSLOT` - Not supported
- `CLUSTER SHARDS` - Not supported
- `CLUSTER SLAVES` - Not supported (deprecated)
- `READONLY` - Not supported
- `READWRITE` - Not supported

**Supported Cluster Commands** (only with OSS Cluster API enabled):
- `CLUSTER HELP`
- `CLUSTER INFO`
- `CLUSTER KEYSLOT`
- `CLUSTER NODES`
- `CLUSTER SLOTS` (deprecated as of Redis 7.0)

### ⚠️ Special Cases

#### FLUSHALL / FLUSHDB
- **Standard databases**: ✅ Supported
- **Active-Active databases**: ❌ Not supported via command
  - Use the Active-Active flush REST API request instead

#### INFO Command
- ✅ Supported but returns a **different set of fields** than Redis Open Source
- Not supported in scripts
- Some operational metrics may be missing or different
- **Does NOT show cluster-level configuration** (use Admin REST API instead)

---

## Configuration Settings Compatibility

### ❌ Unsupported in Redis Enterprise

The following Redis Open Source configuration settings are **NOT supported** in Redis Enterprise:

- `busy-reply-threshold` - Supported in Enterprise, NOT in Cloud
- `lua-time-limit` - Supported in Enterprise, NOT in Cloud
- `tracking-table-max-keys` - Not configurable via CONFIG SET
  - Use REST API or `rladmin tune db` command instead

### ✅ Supported Configuration Settings

The following settings CAN be configured via `CONFIG GET` / `CONFIG SET`:

- `activerehashing`
- `hash-max-listpack-entries`
- `hash-max-listpack-value`
- `hash-max-ziplist-entries`
- `hash-max-ziplist-value`
- `hll-sparse-max-bytes`
- `list-compress-depth`
- `list-max-listpack-size`
- `list-max-ziplist-size`
- `notify-keyspace-events`
- `set-max-intset-entries`
- `slowlog-log-slower-than` (must be > 1000 microseconds)
- `slowlog-max-len` (must be between 128 and 1024)
- `stream-node-max-bytes`
- `stream-node-max-entries`
- `zset-max-listpack-entries`
- `zset-max-listpack-value`
- `zset-max-ziplist-entries`
- `zset-max-ziplist-value`

**Important**: Attempting to use `CONFIG GET` or `CONFIG SET` with unsupported settings will return an error.

---

## Database Information Available ONLY via Admin REST API

Many database configuration and operational details are **NOT available via Redis commands** and can only be retrieved through the **Redis Enterprise Admin REST API** (accessible via the `re_admin` tool provider).

### Database Properties Available via REST API

The following information is returned by `GET /v1/bdbs/{uid}`:

#### Basic Information
- `uid` - Database unique ID (BDB ID)
- `name` - Database name
- `type` - Database type (redis, memcached)
- `status` - Database status (active, pending, creation-failed, etc.)
- `redis_version` - Redis version
- `version` - Database version string

#### Memory and Storage
- `memory_size` - Configured memory limit in bytes
- `used_memory` - Current memory usage
- `bigstore` - Whether Redis on Flash is enabled
- `bigstore_ram_size` - RAM portion for Redis on Flash
- `data_persistence` - Persistence type (disabled, aof, snapshot, aof-and-snapshot)
- `aof_policy` - AOF fsync policy (always, everysec)
- `snapshot_policy` - Snapshot schedule configuration

#### Clustering and Sharding
- `sharding` - Whether clustering/sharding is enabled
- `shards_count` - Number of shards
- `shards_placement` - Shard placement policy (dense, sparse)
- `oss_cluster` - Whether OSS Cluster API is enabled
- `oss_cluster_api_preferred_ip_type` - IP type for cluster API
- `proxy_policy` - Proxy policy (single, all-master-shards, all-nodes)

#### Replication
- `replication` - Whether replication is enabled
- `replica_sources` - Replica source configuration
- `replica_sync` - Replica sync status
- `sync_sources` - Active-Active sync sources

#### Networking
- `port` - Database port
- `endpoints` - List of endpoint configurations
  - `addr` - Endpoint addresses
  - `port` - Endpoint ports
  - `dns_name` - DNS names
  - `proxy_policy` - Per-endpoint proxy policy

#### Security
- `authentication_redis_pass` - Whether password auth is enabled
- `authentication_sasl_pass` - SASL password
- `ssl` - Whether TLS is enabled
- `tls_mode` - TLS mode (enabled, disabled, replica_ssl)
- `crdt_sources_tls_mode` - TLS mode for Active-Active sources

#### Modules
- `module_list` - List of enabled modules
  - `module_name` - Module name (e.g., RedisJSON, RedisSearch)
  - `module_args` - Module arguments
  - `semantic_version` - Module version

#### Backup and Import
- `backup` - Whether backup is enabled
- `backup_status` - Current backup status (exporting, succeeded, failed)
- `backup_progress` - Backup progress percentage
- `import_status` - Import status (idle, initializing, importing, succeeded, failed)
- `import_progress` - Import progress percentage

#### Performance and Limits
- `eviction_policy` - Eviction policy (volatile-lru, allkeys-lru, noeviction, etc.)
- `max_aof_file_size` - Maximum AOF file size
- `max_aof_load_time` - Maximum AOF load time
- `max_connections` - Maximum client connections
- `oss_sharding` - Whether OSS sharding is enabled

#### Timestamps
- `created_time` - When database was created
- `last_changed_time` - Last modification timestamp

#### State Machine
- `exec_state` - Current state machine state
- `exec_state_machine` - Name of running state machine
- `exec_state_progress` - State machine progress

### Cluster-Level Information (via REST API)

The following cluster information is available via `GET /v1/cluster`:

- `name` - Cluster name
- `nodes_count` - Number of nodes in cluster
- `shards_count` - Total shards across all databases
- `rack_aware` - Whether rack awareness is enabled
- `license` - License information
- `created_time` - Cluster creation time
- `alert_settings` - Cluster-wide alert configuration

### Node Information (via REST API)

The following node information is available via `GET /v1/nodes/{uid}`:

- `uid` - Node unique ID
- `addr` - Node address
- `status` - Node status (active, down, provisioning)
- `accept_servers` - Whether node accepts new shards (false = maintenance mode)
- `shard_count` - Number of shards on this node
- `total_memory` - Total memory available
- `available_memory` - Available memory
- `cores` - Number of CPU cores
- `software_version` - Redis Enterprise version
- `uptime` - Node uptime in seconds

### Shard Information (via REST API)

The following shard information is available via `GET /v1/shards/{uid}`:

- `uid` - Shard unique ID
- `bdb_uid` - Database ID this shard belongs to
- `node_uid` - Node ID where shard is located
- `role` - Shard role (master, slave)
- `slots` - Hash slot range (e.g., "0-8191")
- `status` - Shard status (active, down, loading)
- `loading_progress` - Loading progress percentage
- `detailed_status` - Detailed status information

### Why This Matters

When diagnosing Redis Enterprise databases, you **cannot** rely solely on Redis commands like `INFO`, `CONFIG GET`, or `CLUSTER INFO` to get complete operational information. You must use the Admin REST API to retrieve:

1. **Actual memory limits and usage** - `INFO` may not show configured limits
2. **Persistence configuration** - Not available via commands
3. **Replication status** - Not available via `ROLE` or `INFO replication`
4. **Clustering configuration** - Limited info via `CLUSTER INFO` (only if OSS Cluster API enabled)
5. **Security settings** - Not available via commands
6. **Module versions** - `MODULE LIST` shows modules but limited version info
7. **Network endpoints** - Not available via commands
8. **Shard distribution** - Not available via commands
9. **Node status** - Not available via commands (especially maintenance mode)
10. **Backup/import status** - Not available via commands

---

## RESP Protocol Support

Redis Enterprise supports both RESP2 and RESP3 protocols. The protocol version can be:
- Viewed via the Admin REST API
- Changed via the Cluster Manager UI or REST API
- Not directly queryable via Redis commands

---

## Client-Side Caching

Client-side caching is supported for databases with Redis versions 7.4 or later. Configuration is managed through the Cluster Manager UI or Admin REST API, not via Redis commands.

---

## OSS Cluster API

Redis Enterprise clustering differs from Redis Open Source clustering. The OSS Cluster API can be enabled per-database to provide compatibility with Redis Cluster clients, but:

- Most `CLUSTER` commands remain unsupported
- Only `CLUSTER HELP`, `CLUSTER INFO`, `CLUSTER KEYSLOT`, `CLUSTER NODES`, and `CLUSTER SLOTS` are available
- Cluster topology is managed by Redis Enterprise, not manually

---

## Best Practices for Redis Enterprise Diagnostics

When troubleshooting or monitoring Redis Enterprise databases:

1. **Use the Admin REST API** for configuration and operational details
2. **Use Redis commands** for data operations and basic monitoring (`INFO`, `SLOWLOG`, `MONITOR`, `DBSIZE`)
3. **Use the Cluster Manager UI** for metrics, logs, and alerts
4. **Check cluster-level health** using `get_cluster_info`, `list_nodes`, `list_shards`
5. **Check node maintenance mode** - nodes with `accept_servers=false` are in maintenance
6. **Don't assume** Redis Open Source commands will work - check compatibility first
7. **Remember** that `INFO` output differs from Open Source Redis

---

## Tool Provider Integration

The `re_admin` tool provider exposes the Redis Enterprise Admin REST API, allowing you to:

- Get cluster information and settings
- List and inspect databases (BDBs)
- View node status and detect maintenance mode
- List shards and check distribution
- Get database statistics and metrics
- Monitor actions and operations
- View alerts and alert configuration

Use these tools when Redis commands don't provide the information you need.

---

## Summary

| Aspect | Redis Open Source | Redis Enterprise |
|--------|------------------|------------------|
| **ACL Management** | Via commands | Via Cluster Manager/API only |
| **Persistence** | Via commands | Via Cluster Manager/API only |
| **Replication** | Via commands | Automatic (view via API) |
| **Clustering** | Manual via commands | Automatic (limited commands) |
| **Modules** | Load via commands | Enable via Cluster Manager/API |
| **Configuration** | Full access via CONFIG | Limited subset via CONFIG |
| **Monitoring** | Full command set | Limited commands + UI/API |
| **Database Details** | Via INFO/CONFIG | Via Admin REST API |
| **Node Management** | N/A | Via Admin REST API |
| **Shard Distribution** | Via CLUSTER commands | Via Admin REST API |

**Key Takeaway**: Redis Enterprise abstracts away operational complexity. Use the Admin REST API (via `re_admin` tool provider) to access configuration and operational details that aren't available via Redis commands.
