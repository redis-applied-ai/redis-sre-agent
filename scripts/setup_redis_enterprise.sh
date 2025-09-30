#!/bin/bash

# Redis Enterprise Setup Script
# This script automates the setup of Redis Enterprise cluster for testing enterprise runbooks

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
CLUSTER_FQDN="cluster.local"
ADMIN_EMAIL="admin@redis.local"
ADMIN_PASSWORD="RedisEnterprise123!"
DATABASE_NAME="test-db"
DATABASE_PORT="12000"

log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

success() {
    echo -e "${GREEN}✅ $1${NC}"
}

warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

error() {
    echo -e "${RED}❌ $1${NC}"
}

wait_for_service() {
    local service_name=$1
    local url=$2
    local max_attempts=${3:-30}
    local attempt=1

    log "Waiting for $service_name to be ready..."

    while [ $attempt -le $max_attempts ]; do
        if curl -k -f -s "$url" > /dev/null 2>&1; then
            success "$service_name is ready!"
            return 0
        fi

        echo -n "."
        sleep 2
        attempt=$((attempt + 1))
    done

    error "$service_name failed to start after $((max_attempts * 2)) seconds"
    return 1
}

check_prerequisites() {
    log "Checking prerequisites..."

    # Check if Docker is running
    if ! docker info > /dev/null 2>&1; then
        error "Docker is not running. Please start Docker and try again."
        exit 1
    fi

    # Check if curl is available
    if ! command -v curl > /dev/null 2>&1; then
        error "curl is required but not installed."
        exit 1
    fi

    # Check if jq is available (optional but helpful)
    if ! command -v jq > /dev/null 2>&1; then
        warning "jq is not installed. JSON responses will not be formatted."
    fi

    success "Prerequisites check passed"
}

start_redis_enterprise() {
    log "Starting Redis Enterprise container..."

    cd "$PROJECT_ROOT"

    # Start only the Redis Enterprise service
    docker-compose up -d redis-enterprise

    # Wait for the service to be ready
    wait_for_service "Redis Enterprise" "https://localhost:8443/" 60
}

setup_cluster() {
    log "Setting up Redis Enterprise cluster..."

    # Try using rladmin inside the container for cluster setup
    log "Attempting cluster setup using rladmin..."

    # First, try to check if cluster already exists
    local cluster_status=$(docker exec redis-enterprise-node1 rladmin status 2>/dev/null || echo "NO_CLUSTER")

    if echo "$cluster_status" | grep -q "CLUSTER OK"; then
        success "Cluster already exists and is healthy"
        return 0
    fi

    # Try to create cluster using rladmin
    log "Creating cluster using rladmin..."
    local setup_result=$(docker exec redis-enterprise-node1 rladmin cluster create \
        name "$CLUSTER_FQDN" \
        username "$ADMIN_EMAIL" \
        password "$ADMIN_PASSWORD" 2>&1 || echo "SETUP_FAILED")

    if echo "$setup_result" | grep -q "SETUP_FAILED\|error\|Error"; then
        warning "rladmin cluster create failed, trying REST API approach..."

        # Fallback to REST API
        local setup_payload=$(cat <<EOF
{
    "action": "create_cluster",
    "cluster": {
        "name": "$CLUSTER_FQDN"
    },
    "node": {
        "paths": {
            "persistent_path": "/opt/redislabs/persist",
            "ephemeral_path": "/tmp"
        }
    },
    "credentials": {
        "username": "$ADMIN_EMAIL",
        "password": "$ADMIN_PASSWORD"
    },
    "license": ""
}
EOF
)

        local response=$(curl -k -s -X POST \
            -H "Content-Type: application/json" \
            -d "$setup_payload" \
            https://localhost:9443/v1/bootstrap/create_cluster)

        if echo "$response" | grep -q "error"; then
            error "Failed to create cluster via REST API: $response"
            return 1
        fi
    fi

    success "Cluster setup initiated"

    # Wait for cluster to stabilize and verify
    log "Waiting for cluster to stabilize..."
    sleep 15

    # Verify cluster is working
    local final_status=$(docker exec redis-enterprise-node1 rladmin status 2>/dev/null || echo "VERIFICATION_FAILED")
    if echo "$final_status" | grep -q "CLUSTER OK\|cluster_ok"; then
        success "Cluster is operational"
    else
        warning "Cluster status unclear, but proceeding with database creation"
    fi
}

create_database() {
    log "Creating test database..."

    # Try using rladmin first
    log "Attempting database creation using rladmin..."
    local db_result=$(docker exec redis-enterprise-node1 rladmin create db \
        "$DATABASE_NAME" \
        memory_size 100MB \
        port "$DATABASE_PORT" 2>&1 || echo "DB_CREATE_FAILED")

    if echo "$db_result" | grep -q "DB_CREATE_FAILED\|error\|Error"; then
        warning "rladmin create db failed, trying REST API approach..."

        # Fallback to REST API
        local db_payload=$(cat <<EOF
{
    "name": "$DATABASE_NAME",
    "type": "redis",
    "memory_size": 100000000,
    "port": $DATABASE_PORT,
    "replication": false,
    "persistence": "disabled",
    "aof_policy": "appendfsync-every-sec",
    "snapshot_policy": [],
    "sharding": false,
    "proxy_policy": "single"
}
EOF
)

        local response=$(curl -k -s -X POST \
            -H "Content-Type: application/json" \
            -u "$ADMIN_EMAIL:$ADMIN_PASSWORD" \
            -d "$db_payload" \
            https://localhost:9443/v1/bdbs)

        if echo "$response" | grep -q "error"; then
            error "Failed to create database via REST API: $response"
            return 1
        fi
    fi

    success "Database '$DATABASE_NAME' creation initiated"

    # Wait for database to be active
    log "Waiting for database to become active..."
    sleep 10

    # Verify database is accessible
    local db_status=$(docker exec redis-enterprise-node1 rladmin status databases 2>/dev/null || echo "DB_STATUS_FAILED")
    if echo "$db_status" | grep -q "$DATABASE_NAME"; then
        success "Database is listed in cluster"
    else
        warning "Database status unclear, but proceeding with connection test"
    fi
}

test_database_connection() {
    log "Testing database connection..."

    # Test connection using redis-cli inside the container
    local test_result=$(docker exec redis-enterprise-node1 redis-cli -p $DATABASE_PORT ping 2>/dev/null || echo "FAILED")

    if [ "$test_result" = "PONG" ]; then
        success "Database connection test passed"

        # Set a test key
        docker exec redis-enterprise-node1 redis-cli -p $DATABASE_PORT set test:key "Redis Enterprise is working!" > /dev/null
        local value=$(docker exec redis-enterprise-node1 redis-cli -p $DATABASE_PORT get test:key)

        if [ "$value" = "Redis Enterprise is working!" ]; then
            success "Database read/write test passed"
        else
            warning "Database read/write test failed"
        fi
    else
        error "Database connection test failed"
        return 1
    fi
}

show_cluster_info() {
    log "Retrieving cluster information..."

    echo ""
    echo "🎉 Redis Enterprise cluster setup complete!"
    echo ""
    echo "📋 Cluster Information:"
    echo "  • Cluster Manager UI: https://localhost:8443"
    echo "  • REST API: https://localhost:9443"
    echo "  • Admin Email: $ADMIN_EMAIL"
    echo "  • Admin Password: $ADMIN_PASSWORD"
    echo ""
    echo "💾 Database Information:"
    echo "  • Database Name: $DATABASE_NAME"
    echo "  • Database Port: $DATABASE_PORT"
    echo "  • Connection: redis://localhost:$DATABASE_PORT"
    echo ""
    echo "🔧 Testing Commands:"
    echo "  • Test connection: docker exec redis-enterprise-node1 redis-cli -p $DATABASE_PORT ping"
    echo "  • Check cluster status: docker exec redis-enterprise-node1 rladmin status"
    echo "  • Check database status: docker exec redis-enterprise-node1 rladmin status databases"
    echo ""
    echo "📚 Enterprise Runbook Testing:"
    echo "  • Use 'rladmin' commands inside the container to test enterprise runbooks"
    echo "  • Access the cluster UI to simulate enterprise scenarios"
    echo "  • Test database operations, maintenance mode, etc."
    echo ""

    # Show cluster status
    log "Current cluster status:"
    docker exec redis-enterprise-node1 rladmin status 2>/dev/null || warning "Could not retrieve cluster status"
}

cleanup() {
    log "Cleaning up on exit..."
    # Any cleanup tasks if needed
}

main() {
    echo ""
    echo "🚀 Redis Enterprise Setup for SRE Agent Testing"
    echo "=============================================="
    echo ""

    # Set up cleanup trap
    trap cleanup EXIT

    # Run setup steps
    check_prerequisites
    start_redis_enterprise

    # Wait a bit more for full startup
    sleep 20

    setup_cluster
    create_database
    test_database_connection
    show_cluster_info

    echo ""
    success "Redis Enterprise setup completed successfully!"
    echo ""
    echo "💡 Next steps:"
    echo "  1. Access the cluster UI at https://localhost:8443"
    echo "  2. Test enterprise runbooks using 'rladmin' commands"
    echo "  3. Use the SRE agent to query enterprise-specific scenarios"
    echo ""
}

# Handle script arguments
case "${1:-}" in
    "cleanup")
        log "Stopping Redis Enterprise..."
        cd "$PROJECT_ROOT"
        docker-compose down redis-enterprise
        docker volume rm redis-sre-agent_redis_enterprise_data 2>/dev/null || true
        success "Redis Enterprise cleanup completed"
        ;;
    "status")
        log "Checking Redis Enterprise status..."
        docker exec redis-enterprise-node1 rladmin status 2>/dev/null || error "Redis Enterprise is not running"
        ;;
    "logs")
        log "Showing Redis Enterprise logs..."
        docker logs redis-enterprise-node1
        ;;
    *)
        main
        ;;
esac
