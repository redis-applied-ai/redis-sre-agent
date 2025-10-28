# Important Notes about Redis Cloud Compatibility with Open Source Redis

## Overview

Redis Cloud (and Redis Enterprise) are compatible with Redis Open Source but have important differences in command support, configuration settings, and operational management. This document summarizes key compatibility considerations when working with Redis Cloud databases.

**Critical Note**: Many database configuration details and operational information that would normally be available via Redis commands are **only accessible through the Redis Cloud Management REST API** (available via the `redis_cloud` tool provider).

---

## Command Compatibility

### ❌ Unsupported Server Management Commands

The following Redis Open Source commands are **NOT supported** in Redis Cloud:

#### Access Control (ACL) Commands
- `ACL DELUSER` - Use Redis Cloud console or REST API instead
- `ACL GENPASS` - Not supported
- `ACL LOAD` - Not supported
- `ACL LOG` - Not supported
- `ACL SAVE` - Not supported
- `ACL SETUSER` - Use Redis Cloud console or REST API instead

**Note**: ACL users must be managed through the Redis Cloud console or Management API, not via Redis commands.

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

**Note**: Use Redis Cloud console metrics and the Management API for monitoring instead.

#### Persistence Commands
All persistence commands are **NOT supported** - Redis Cloud manages persistence automatically:
- `BGREWRITEAOF` - Not supported
- `BGSAVE` - Not supported
- `LASTSAVE` - Not supported
- `SAVE` - Not supported

**Note**: Configure persistence through Redis Cloud console or REST API.

#### Replication Commands
All replication commands are **NOT supported** - Redis Cloud manages replication automatically:
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
- `MODULE LOAD` - Not supported (modules managed via console)
- `MODULE LOADEX` - Not supported
- `MODULE UNLOAD` - Not supported

**Note**: `MODULE LIST` is supported. Enable modules when creating a database via console or REST API.

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

---

## Configuration Settings Compatibility

### ❌ Unsupported in Redis Cloud

The following Redis Open Source configuration settings are **NOT supported** in Redis Cloud:

- `busy-reply-threshold` - Not configurable
- `lua-time-limit` - Not configurable
- `tracking-table-max-keys` - Not configurable via CONFIG SET

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

## Database Information Available ONLY via REST API

Many database configuration and operational details are **NOT available via Redis commands** and can only be retrieved through the **Redis Cloud Management REST API** (accessible via the `redis_cloud` tool provider).

### Database Properties Available via REST API

The following information is returned by `GET /subscriptions/{id}/databases/{id}`:

#### Basic Information
- `databaseId` - Unique database identifier
- `name` - Database name
- `protocol` - Protocol (redis, memcached)
- `provider` - Cloud provider (AWS, GCP, Azure)
- `region` - Cloud region
- `status` - Database status (active, pending, error, etc.)

#### Version Information
- `redisVersion` - Redis version (e.g., "7.4")
- `respVersion` - RESP protocol version (resp2, resp3)

#### Memory and Storage
- `datasetSizeInGb` - Total dataset size in GB
- `memoryUsedInMb` - Current memory usage in MB
- `memoryStorage` - Storage type (ram, ram-and-flash)
- `dataEvictionPolicy` - Eviction policy (noeviction, allkeys-lru, etc.)

#### Clustering
- `clustering.numberOfShards` - Number of shards
- `clustering.regexRules` - Hashing rules for clustering
- `clustering.hashingPolicy` - Hashing policy (standard, custom)
- `supportOSSClusterApi` - Whether OSS Cluster API is enabled
- `useExternalEndpointForOSSClusterApi` - External endpoint for cluster API

#### Persistence
- `dataPersistence` - Persistence configuration (e.g., "snapshot-every-1-hour", "aof-every-1-second")

#### Replication
- `replication` - Whether replication is enabled
- `replica.syncSources` - Replica sync source configuration

#### Networking
- `publicEndpoint` - Public connection endpoint
- `privateEndpoint` - Private connection endpoint (if VPC peering enabled)

#### Security
- `security.enableDefaultUser` - Whether default user is enabled
- `security.password` - Database password
- `security.sslClientAuthentication` - SSL client auth enabled
- `security.tlsClientAuthentication` - TLS client auth enabled
- `security.enableTls` - Whether TLS is enabled
- `security.sourceIps` - Allowed source IP addresses

#### Modules
- `modules` - List of enabled Redis modules (RedisJSON, RedisSearch, etc.)
  - `modules[].id` - Module ID
  - `modules[].name` - Module name
  - `modules[].version` - Module version

#### Performance
- `throughputMeasurement.by` - Throughput measurement type (operations-per-second, number-of-shards)
- `throughputMeasurement.value` - Throughput value

#### Timestamps
- `activatedOn` - When database was activated
- `lastModified` - Last modification timestamp

#### Alerts
- `alerts` - Configured alerts for the database

### Why This Matters

When diagnosing Redis Cloud databases, you **cannot** rely solely on Redis commands like `INFO`, `CONFIG GET`, or `CLUSTER INFO` to get complete operational information. You must use the Redis Cloud Management API to retrieve:

1. **Actual memory limits and usage** - `INFO` may not show configured limits
2. **Persistence configuration** - Not available via commands
3. **Replication status** - Not available via `ROLE` or `INFO replication`
4. **Clustering configuration** - Limited info via `CLUSTER INFO` (only if OSS Cluster API enabled)
5. **Security settings** - Not available via commands
6. **Module versions** - `MODULE LIST` shows modules but limited version info
7. **Network endpoints** - Not available via commands
8. **Throughput limits** - Not available via commands

---

## RESP Protocol Support

Redis Cloud supports both RESP2 and RESP3 protocols. The protocol version can be:
- Viewed via the REST API (`respVersion` field)
- Changed via the REST API or console
- Not directly queryable via Redis commands

---

## Client-Side Caching

Client-side caching is supported for databases with Redis versions 7.4 or later. Configuration is managed through the Redis Cloud console or REST API, not via Redis commands.

---

## OSS Cluster API

Redis Cloud clustering differs from Redis Open Source clustering. The OSS Cluster API can be enabled per-database to provide compatibility with Redis Cluster clients, but:

- Most `CLUSTER` commands remain unsupported
- Only `CLUSTER HELP`, `CLUSTER INFO`, `CLUSTER KEYSLOT`, `CLUSTER NODES`, and `CLUSTER SLOTS` are available
- Cluster topology is managed by Redis Cloud, not manually

---

## Best Practices for Redis Cloud Diagnostics

When troubleshooting or monitoring Redis Cloud databases:

1. **Use the REST API** for configuration and operational details
2. **Use Redis commands** for data operations and basic monitoring (`INFO`, `SLOWLOG`, `MONITOR`, `DBSIZE`)
3. **Use the Redis Cloud console** for metrics, logs, and alerts
4. **Don't assume** Redis Open Source commands will work - check compatibility first
5. **Remember** that `INFO` output differs from Open Source Redis

---

## Tool Provider Integration

The `redis_cloud` tool provider exposes the Redis Cloud Management API, allowing you to:

- List subscriptions and databases
- Get detailed database configuration (all fields listed above)
- View account information and available regions
- Monitor tasks and async operations
- Manage users and access control
- View cloud account details

Use these tools when Redis commands don't provide the information you need.

---

## Summary

| Aspect | Redis Open Source | Redis Cloud |
|--------|------------------|-------------|
| **ACL Management** | Via commands | Via console/API only |
| **Persistence** | Via commands | Via console/API only |
| **Replication** | Via commands | Automatic (view via API) |
| **Clustering** | Manual via commands | Automatic (limited commands) |
| **Modules** | Load via commands | Enable via console/API |
| **Configuration** | Full access via CONFIG | Limited subset via CONFIG |
| **Monitoring** | Full command set | Limited commands + console/API |
| **Database Details** | Via INFO/CONFIG | Via REST API |

**Key Takeaway**: Redis Cloud abstracts away operational complexity. Use the Management API (via `redis_cloud` tool provider) to access configuration and operational details that aren't available via Redis commands.
