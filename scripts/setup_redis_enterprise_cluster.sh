#!/bin/bash
# Setup Redis Enterprise 3-node cluster for demo scenarios

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_CMD=(docker compose -f "$REPO_ROOT/docker-compose.yml" -f "$REPO_ROOT/docker-compose.enterprise.yml")

echo "🚀 Setting up Redis Enterprise 3-node cluster..."
echo

# Prefer GNU timeout when available (macOS may only have gtimeout, or neither).
TIMEOUT_BIN=""
if command -v timeout >/dev/null 2>&1; then
    TIMEOUT_BIN="timeout"
elif command -v gtimeout >/dev/null 2>&1; then
    TIMEOUT_BIN="gtimeout"
fi

run_with_timeout() {
    local seconds="$1"
    shift

    if [ -n "$TIMEOUT_BIN" ]; then
        "$TIMEOUT_BIN" "$seconds" "$@"
        return $?
    fi

    echo "⚠️  'timeout' not found; running without timeout: $*"
    "$@"
}

wait_for_cluster_nodes_ready() {
    echo "⏳ Waiting for cluster membership to stabilize..."
    for i in {1..60}; do
        local status_output
        status_output="$(docker exec redis-enterprise-node1 rladmin status nodes 2>/dev/null || true)"

        if echo "$status_output" | grep -q 'node:1' && \
           echo "$status_output" | grep -q 'node:2' && \
           echo "$status_output" | grep -q 'node:3' && \
           ! echo "$status_output" | grep -Eq 'DOWN|never seen'; then
            echo "✅ Cluster membership is healthy"
            return 0
        fi

        echo "   Waiting for cluster membership... ($i/60)"
        sleep 2
    done

    echo "⚠️  Cluster membership did not stabilize in time"
    docker exec redis-enterprise-node1 rladmin status nodes 2>/dev/null || true
    return 1
}

# Check if cluster already exists and is working
echo "🔍 Checking for existing cluster..."
if curl -k -s -u "admin@redis.com:admin" https://localhost:9443/v1/bdbs 2>/dev/null | grep -q "^\["; then
    echo "✅ Cluster already exists and is accessible"

    # Check if database exists
    if curl -k -s -u "admin@redis.com:admin" https://localhost:9443/v1/bdbs 2>/dev/null | grep -q '"name":"test-db"'; then
        echo "✅ Database 'test-db' already exists"
        echo
        echo "📊 Cluster is reachable; proceeding to ensure sharded database configuration"
        echo "   - Node 1 UI: https://localhost:8443 (admin@redis.com / admin)"
        echo "   - Database: redis://admin@localhost:12000/0"
        echo
        echo "(Skipping early exit; will verify database has 3 shards on 3 nodes)"
    else
        echo "⚠️  Database 'test-db' not found, will create it"
    fi
else
    echo "⚠️  No working cluster found, will create new cluster"
    echo

    # Stop and remove existing containers to start fresh
    echo "🧹 Cleaning up existing containers..."
    "${COMPOSE_CMD[@]}" stop redis-enterprise-node1 redis-enterprise-node2 redis-enterprise-node3 2>/dev/null || true
    "${COMPOSE_CMD[@]}" rm -f redis-enterprise-node1 redis-enterprise-node2 redis-enterprise-node3 2>/dev/null || true

    # Remove volumes for clean slate
    echo "🧹 Removing old data volumes..."
    docker volume rm redis-sre-agent_redis_enterprise_node1_data 2>/dev/null || true
    docker volume rm redis-sre-agent_redis_enterprise_node2_data 2>/dev/null || true
    docker volume rm redis-sre-agent_redis_enterprise_node3_data 2>/dev/null || true

    # Start fresh nodes
    echo "🚀 Starting fresh Redis Enterprise nodes..."
    "${COMPOSE_CMD[@]}" up -d redis-enterprise-node1 redis-enterprise-node2 redis-enterprise-node3

    echo "⏳ Waiting 90 seconds for nodes to initialize..."
    sleep 90
fi

# Wait for all nodes to be healthy
echo
echo "⏳ Waiting for Redis Enterprise nodes to be healthy..."
for i in {1..60}; do
    if docker exec redis-enterprise-node1 curl -k -s https://localhost:8443/ > /dev/null 2>&1 && \
       docker exec redis-enterprise-node2 curl -k -s https://localhost:8443/ > /dev/null 2>&1 && \
       docker exec redis-enterprise-node3 curl -k -s https://localhost:8443/ > /dev/null 2>&1; then
        echo "✅ All nodes are healthy"
        break
    fi
    echo "   Waiting for nodes to be ready... ($i/60)"
    sleep 2
done

# Check if we need to create cluster
echo
if curl -k -s -u "admin@redis.com:admin" https://localhost:9443/v1/cluster 2>/dev/null | grep -q "name"; then
    echo "✅ Cluster already configured, skipping cluster creation"
else
    # Create cluster on node 1
    echo "📋 Step 1: Creating cluster on node 1..."
    docker exec redis-enterprise-node1 rladmin cluster create name cluster.local username admin@redis.com password admin

    sleep 10

    # Get node 1 IP
    NODE1_IP=$(docker exec redis-enterprise-node1 hostname -i)
    echo "   Node 1 IP: $NODE1_IP"

    # Join node 2 to cluster
    echo
    echo "📋 Step 2: Joining node 2 to cluster..."
    docker exec redis-enterprise-node2 rladmin cluster join nodes $NODE1_IP username admin@redis.com password admin

    sleep 10

    # Join node 3 to cluster
    echo
    echo "📋 Step 3: Joining node 3 to cluster..."
    if ! run_with_timeout 60 docker exec redis-enterprise-node3 rladmin cluster join nodes $NODE1_IP username admin@redis.com password admin; then
        echo "❌ Node 3 failed to join the cluster"
        exit 1
    fi

    sleep 5
fi

echo
wait_for_cluster_nodes_ready

# Check cluster status
echo
echo "📋 Step 4: Checking cluster status..."
run_with_timeout 10 docker exec redis-enterprise-node1 rladmin status nodes || echo "Status command timed out or failed"

# Wait for REST API to be ready
echo
echo "⏳ Waiting for REST API to be ready..."
for i in {1..30}; do
    if curl -k -s -u "admin@redis.com:admin" https://localhost:9443/v1/bdbs 2>/dev/null | grep -q "^\["; then
        echo "✅ REST API is ready"
        break
    fi
    echo "   Waiting for API... ($i/30)"
    sleep 2
done

# Create database via REST API (delete preexisting via rladmin if present)
echo
echo "📋 Step 5: Creating test database..."
# If a preexisting DB exists, delete it via REST API to ensure a clean state
EXISTING_DB_UID=$(curl -k -s -u "admin@redis.com:admin" https://localhost:9443/v1/bdbs | jq -r '.[] | select(.name=="test-db") | .uid' | head -n 1)
if [ -n "$EXISTING_DB_UID" ]; then
    echo "   ⚠️  Database 'test-db' already exists; deleting via REST API..."
    curl -k -s -u "admin@redis.com:admin" -X DELETE "https://localhost:9443/v1/bdbs/$EXISTING_DB_UID" >/dev/null || true
    # Wait for deletion to complete
    for i in {1..30}; do
        if curl -k -s -u "admin@redis.com:admin" https://localhost:9443/v1/bdbs 2>/dev/null | grep -q '"name":"test-db"'; then
            echo "      Waiting for database deletion... ($i/30)"
            sleep 2
        else
            echo "   ✅ Database 'test-db' deleted"
            break
        fi
    done
fi

# Create database
RESPONSE=$(curl -k -s -u "admin@redis.com:admin" \
  -X POST https://localhost:9443/v1/bdbs \
  -H "Content-Type: application/json" \
  -d '{
    "name": "test-db",
    "type": "redis",
    "memory_size": 33554432,
    "port": 12000,
    "replication": true,
    "sharding": true,
    "oss_sharding": true,
    "shards_count": 2,
    "shards_placement": "sparse",
    "proxy_policy": "all-master-shards"
  }')

if echo "$RESPONSE" | grep -q '"uid"'; then
    echo "   ✅ Database created successfully"
else
    echo "   ❌ Database creation failed"
    echo "   Response: $RESPONSE"
    exit 1
fi

sleep 10

# Wait for database to be active
echo "⏳ Waiting for database to be active..."
for i in {1..30}; do
    if docker exec redis-enterprise redis-cli -h localhost -p 12000 -a admin ping 2>/dev/null | grep -q "PONG"; then
        echo "✅ Database is active and responding"
        break
    fi
    echo "   Waiting for database... ($i/30)"
    sleep 2
done
echo
echo "📋 Step 6: Ensuring 'test-db' has 2 shards across nodes..."
# Determine the REST BDB uid. Use the admin API as the source of truth for
# follow-up REST calls because rladmin output can lag during delete/recreate.
DB_UID=$(curl -k -s -u "admin@redis.com:admin" https://localhost:9443/v1/bdbs | jq -r '.[] | select(.name=="test-db") | .uid' | head -n 1)
if [ -z "$DB_UID" ] || [ "$DB_UID" = "null" ]; then
    DB_UID=$(docker exec redis-enterprise-node1 rladmin status databases 2>/dev/null | awk '/test-db/ {print $1}' | sed 's/db://')
fi
if [ -z "$DB_UID" ]; then
    echo "   ❌ Could not determine database UID for 'test-db'"
else
    echo "   → test-db UID: $DB_UID"
    # Enforce sharded config: 2 shards, spread across nodes (fits 4-shard license with replication)
    RECONF_RESP=$(curl -k -s -u "admin@redis.com:admin" \
      -X PUT "https://localhost:9443/v1/bdbs/$DB_UID" \
      -H "Content-Type: application/json" \
      -d '{
        "sharding": true,
        "oss_sharding": true,
        "shards_count": 2,
        "shards_placement": "sparse",
        "proxy_policy": "all-master-shards"
      }')
    if echo "$RECONF_RESP" | grep -q '"action_uid"'; then
        echo "   ✅ Reconfiguration accepted (reshard may be in progress)"
    else
        echo "   ℹ️ Database configuration updated or already compliant"
    fi

    echo "⏳ Waiting for database to be active after reconfiguration..."
    for i in {1..60}; do
        if docker exec redis-enterprise redis-cli -h localhost -p 12000 -a admin ping 2>/dev/null | grep -q "PONG"; then
            echo "✅ Database is active"
            break
        fi
        echo "   Waiting... ($i/60)"
        sleep 2
    done

    echo
    echo "🔎 Current shard placement for 'test-db' (truncated):"
    docker exec redis-enterprise-node1 rladmin status shards db test-db 2>/dev/null | head -n 20 || true

    echo
    echo "🧪 Rebalance test helpers:"
    echo "   1) Skew all primary shards to node 1 to create imbalance:"
    echo "      bash scripts/create_deliberate_shard_imbalance.sh test-db 1"
    echo "   2) Trigger a cluster-managed rebalance via REST:"
    echo "      bash scripts/trigger_rebalance.sh test-db"
    echo "   3) Track action progress (replace ACTION_UID with value from previous response):"
    echo "      curl -k -u 'admin@redis.com:admin' https://localhost:9443/v1/actions/ACTION_UID | jq . || true"
fi


echo
echo "✅ Redis Enterprise 3-node cluster setup complete!"
echo
echo "📊 Cluster Information:"
echo "   - Node 1 UI: https://localhost:8443 (admin@redis.com / admin)"
echo "   - Node 2 UI: https://localhost:8444"
echo "   - Node 3 UI: https://localhost:8445"
echo "   - Database: redis://admin@localhost:12000/0"
echo
echo "🔧 To put node 2 in maintenance mode:"
echo "   docker exec redis-enterprise-node1 rladmin node 2 maintenance_mode on"
echo
echo "🔍 To check cluster status:"
if [ -n "$TIMEOUT_BIN" ]; then
    echo "   $TIMEOUT_BIN 10 docker exec redis-enterprise-node1 rladmin status nodes"
else
    echo "   docker exec redis-enterprise-node1 rladmin status nodes"
fi
echo
