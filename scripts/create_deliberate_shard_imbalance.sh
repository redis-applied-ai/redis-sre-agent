#!/bin/bash
# Create a deliberate shard imbalance by moving all master shards of a database to a single node
# Usage: ./scripts/create_deliberate_shard_imbalance.sh [DB_NAME] [TARGET_NODE_ID]
# Defaults: DB_NAME=test-db, TARGET_NODE_ID=1

set -euo pipefail

DB_NAME="${1:-test-db}"
TARGET_NODE_ID="${2:-1}"

echo "🔧 Creating deliberate shard imbalance: all master shards of '$DB_NAME' -> node:$TARGET_NODE_ID"

# Pre-flight checks
if ! docker ps --format '{{.Names}}' | grep -q '^redis-enterprise-node1$'; then
  echo "❌ redis-enterprise-node1 container not running"
  exit 1
fi

# Validate DB exists
if ! docker exec redis-enterprise-node1 rladmin status databases 2>/dev/null | grep -Fq "$DB_NAME"; then
  echo "❌ Database '$DB_NAME' not found. Run scripts/setup_redis_enterprise_cluster.sh first."
  exit 2
fi

# Validate target node exists
if ! docker exec redis-enterprise-node1 rladmin status nodes 2>/dev/null | grep -Eq "node[[:space:]]+$TARGET_NODE_ID[[:space:]]"; then
  echo "❌ Target node id '$TARGET_NODE_ID' not found in cluster. Try '1', '2', or '3'."
  echo "   Nodes:"
  docker exec redis-enterprise-node1 rladmin status nodes 2>/dev/null | head -n 20 || true
  exit 3
fi

# Show current shards (best effort)
echo "ℹ️ Current shards (before):"
docker exec redis-enterprise-node1 rladmin status shards db "$DB_NAME" 2>/dev/null | head -n 40 || true

# Move all master shards for DB to the target node
set +e
OUTPUT=$(docker exec redis-enterprise-node1 rladmin migrate db "$DB_NAME" all_master_shards target_node "$TARGET_NODE_ID" 2>&1)
RC=$?
set -e

echo "$OUTPUT" | tail -n 40

if [ $RC -ne 0 ]; then
  echo "⚠️ Migrate returned non-zero ($RC); verifying placement to see if imbalance already exists..."
  total_masters=$(docker exec redis-enterprise-node1 rladmin status shards db "$DB_NAME" 2>/dev/null | awk '/ master / {print $0}' | wc -l | tr -d ' ')
  masters_on_target=$(docker exec redis-enterprise-node1 rladmin status shards db "$DB_NAME" 2>/dev/null | awk -v tgt="node:$TARGET_NODE_ID" '$0 ~ / master / && $4==tgt {print $0}' | wc -l | tr -d ' ')
  if [ -n "$total_masters" ] && [ "$total_masters" -gt 0 ] && [ "$masters_on_target" = "$total_masters" ]; then
    echo "✅ All master shards already on node:$TARGET_NODE_ID; treating as success"
  else
    echo "❌ Failed to migrate master shards to node:$TARGET_NODE_ID"
    exit $RC
  fi
fi

echo "✅ Imbalance created"

echo "ℹ️ Current shards (after):"
docker exec redis-enterprise-node1 rladmin status shards db "$DB_NAME" 2>/dev/null | head -n 20 || true
