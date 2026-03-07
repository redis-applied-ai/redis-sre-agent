## How to connect to Redis

This guide shows how to configure Redis connections in the Redis SRE Agent for:
- Open Source Redis (`oss_single`, `oss_cluster`)
- Redis Cloud (`redis_cloud`)
- Redis Enterprise (`redis_enterprise`)

You can configure instances in two places:
- CLI: `uv run redis-sre-agent instance ...`
- UI: **Redis Instances** page (`Add Instance` / `Edit`)

### Common fields (all Redis types)

Required on create:
- `name`
- `connection_url`
- `environment` (`development`, `staging`, `production`, `test`)
- `usage` (`cache`, `analytics`, `session`, `queue`, `custom`)
- `description`

Common commands:

```bash
# Create
uv run redis-sre-agent instance create \
  --name "<name>" \
  --connection-url "redis://host:6379/0" \
  --environment production \
  --usage cache \
  --description "<description>" \
  --instance-type <type>

# Update
uv run redis-sre-agent instance update <instance_id> \
  --connection-url "redis://new-host:6379/0" \
  --instance-type <type>

# Test connectivity
uv run redis-sre-agent instance test <instance_id>
uv run redis-sre-agent instance test-url --connection-url "redis://host:6379/0"
```

UI flow:
1. Open **Redis Instances**
2. Click **Add Instance** (or **Edit** on an existing instance)
3. Fill common fields, pick **Instance Type**, then fill type-specific fields
4. Save and use **Test Connection**

Note:
- In the **Add Instance** form, **Test Connection** validates URL format.
- For a live connectivity check, save first, then use **Test Connection** on the instance card (or edit an existing instance and test there).

### Open Source Redis (`oss_single`, `oss_cluster`)

Use this for self-managed Redis OSS, including single-node and cluster mode.

CLI examples:

```bash
# OSS single
uv run redis-sre-agent instance create \
  --name "prod-cache" \
  --connection-url "redis://redis-prod.example.com:6379/0" \
  --environment production \
  --usage cache \
  --description "Primary cache" \
  --instance-type oss_single

# OSS cluster
uv run redis-sre-agent instance create \
  --name "prod-cluster" \
  --connection-url "redis://redis-cluster.example.com:6379/0" \
  --environment production \
  --usage cache \
  --description "Clustered cache" \
  --instance-type oss_cluster
```

UI:
- Set **Instance Type** to `Redis OSS (Single Node)` or `Redis OSS (Cluster Mode)`
- No extra type-specific fields are required

### Redis Cloud (`redis_cloud`)

Use this when your target database runs in Redis Cloud.

CLI example:

```bash
uv run redis-sre-agent instance create \
  --name "cloud-prod" \
  --connection-url "rediss://default:<password>@redis-12345.c1.us-east-1-2.ec2.redns.redis-cloud.com:12345" \
  --environment production \
  --usage cache \
  --description "Redis Cloud production database" \
  --instance-type redis_cloud \
  --redis-cloud-subscription-type pro \
  --redis-cloud-subscription-id 123456 \
  --redis-cloud-database-id 987654 \
  --redis-cloud-database-name "prod-cache"
```

UI:
- Set **Instance Type** to `Redis Cloud / Managed Service`
- Optional cloud fields:
  - Subscription Type (`pro` or `essentials`)
  - Subscription ID
  - Database ID
  - Database Name

For Redis Cloud management API tooling during troubleshooting, set:
- `TOOLS_REDIS_CLOUD_API_KEY`
- `TOOLS_REDIS_CLOUD_API_SECRET_KEY`

### Redis Enterprise (`redis_enterprise`)

Use this when your target database runs in a Redis Enterprise cluster.

CLI example:

```bash
uv run redis-sre-agent instance create \
  --name "re-prod-db" \
  --connection-url "rediss://default:<db-password>@re-cluster.example.com:12000" \
  --environment production \
  --usage cache \
  --description "Redis Enterprise production database" \
  --instance-type redis_enterprise \
  --admin-url "https://re-cluster.example.com:9443" \
  --admin-username "admin@redis.com" \
  --admin-password "<admin-password>"
```

UI:
- Set **Instance Type** to `Redis Enterprise`
- Fill:
  - `Admin API URL` (usually `https://<cluster-host>:9443`)
  - `Admin Username`
  - `Admin Password`
- Use **Test Admin API Connection** before saving

To test Admin API credentials outside the UI:

```bash
curl -fsS -X POST http://localhost:8080/api/v1/instances/test-admin-api \
  -H 'Content-Type: application/json' \
  -d '{
    "admin_url": "https://re-cluster.example.com:9443",
    "admin_username": "admin@redis.com",
    "admin_password": "<admin-password>"
  }'
```

### Redis Enterprise Cluster Creation Defaults (API/CLI)

When creating a Redis Enterprise **cluster** (`/api/v1/clusters` or `redis-sre-agent cluster create`), you can omit `admin_url`, `admin_username`, and `admin_password` if these environment variables are set:

- `REDIS_ENTERPRISE_ADMIN_URL`
- `REDIS_ENTERPRISE_ADMIN_USERNAME`
- `REDIS_ENTERPRISE_ADMIN_PASSWORD`

Precedence is field-by-field:
1. Explicit request/CLI value
2. Environment variable default

The env fallback is applied only for `cluster_type=redis_enterprise`.

### Redis Enterprise: Checking Cluster Health

For Redis Enterprise troubleshooting, configure `admin_url` (and credentials) on the instance.

When `admin_url` is configured, the agent connects to the Redis Enterprise cluster during troubleshooting and uses relevant Redis Enterprise Admin API areas to gather information, including cluster, nodes, databases (BDBs), shards, actions, stats, logs, and alerts.

Run troubleshooting against the configured instance:

```bash
uv run redis-sre-agent query -r <instance_id> "Check cluster health"
```

If `admin_url` is missing, Redis Enterprise cluster-level diagnostics are limited.
