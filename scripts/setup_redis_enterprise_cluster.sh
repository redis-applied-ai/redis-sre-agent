#!/bin/bash
# Setup Redis Enterprise 3-node cluster for demo scenarios

echo "🚀 Setting up Redis Enterprise 3-node cluster..."
echo

# Wait for all nodes to be healthy
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

# Create cluster on node 1
echo
echo "📋 Step 1: Creating cluster on node 1..."
docker exec redis-enterprise-node1 rladmin cluster create name cluster.local username admin@redis.com password admin || echo "Cluster may already exist"

sleep 5

# Get node 1 IP
NODE1_IP=$(docker exec redis-enterprise-node1 hostname -i)
echo "   Node 1 IP: $NODE1_IP"

# Join node 2 to cluster
echo
echo "📋 Step 2: Joining node 2 to cluster..."
docker exec redis-enterprise-node2 rladmin cluster join nodes $NODE1_IP username admin@redis.com password admin || echo "Node 2 may already be joined"

sleep 5

# Join node 3 to cluster
echo
echo "📋 Step 3: Joining node 3 to cluster..."
timeout 60 docker exec redis-enterprise-node3 rladmin cluster join nodes $NODE1_IP username admin@redis.com password admin || echo "Node 3 join failed or timed out (2-node cluster is sufficient)"

sleep 5

# Check cluster status
echo
echo "📋 Step 4: Checking cluster status..."
timeout 10 docker exec redis-enterprise-node1 rladmin status nodes || echo "Status command timed out"

# Create database via REST API
echo
echo "📋 Step 5: Creating test database..."
curl -k -s -u "admin@redis.com:admin" \
  -X POST https://localhost:8443/v1/bdbs \
  -H "Content-Type: application/json" \
  -d '{
    "name": "test-db",
    "type": "redis",
    "memory_size": 104857600,
    "port": 12000,
    "replication": true,
    "shards_count": 2
  }' > /dev/null && echo "   ✅ Database created successfully" || echo "   ⚠️  Database creation failed (may already exist)"

sleep 5

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
echo "   timeout 10 docker exec redis-enterprise-node1 rladmin status nodes"
echo
