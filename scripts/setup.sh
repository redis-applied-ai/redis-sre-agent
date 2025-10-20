#!/bin/bash
# Redis SRE Agent Setup Script
# This script sets up the complete Redis SRE Agent environment

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if Docker and Docker Compose are available
check_prerequisites() {
    log "Checking prerequisites..."

    if ! command -v docker &> /dev/null; then
        error "Docker is not installed or not in PATH"
        exit 1
    fi

    if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
        error "Docker Compose is not installed or not in PATH"
        exit 1
    fi

    success "Prerequisites check passed"
}

# Start core services
start_core_services() {
    log "Starting core services (Redis, Prometheus, Grafana)..."

    # Start core infrastructure first
    docker-compose up -d redis redis-demo prometheus grafana redis-exporter node-exporter

    log "Waiting for Redis to be healthy..."
    timeout 60 bash -c 'until docker-compose exec -T redis redis-cli ping | grep -q PONG; do sleep 2; done'

    success "Core services started successfully"
}

# Setup Redis Enterprise
setup_redis_enterprise() {
    log "Setting up Redis Enterprise..."

    # Start Redis Enterprise container
    docker-compose up -d redis-enterprise

    log "Waiting for Redis Enterprise to start..."
    sleep 45

    # Check if container is healthy
    log "Checking Redis Enterprise container health..."
    timeout 120 bash -c 'until docker exec redis-enterprise-node1 curl -k -s https://localhost:8443/ >/dev/null 2>&1; do sleep 5; done'

    # Create required directories and fix permissions
    log "Setting up Redis Enterprise directories..."
    docker exec redis-enterprise-node1 mkdir -p /opt/redislabs/tmp 2>/dev/null || true
    docker exec -u root redis-enterprise-node1 chown -R redislabs:redislabs /opt/redislabs/persist 2>/dev/null || true
    docker exec -u root redis-enterprise-node1 chown -R redislabs:redislabs /opt/redislabs/tmp 2>/dev/null || true

    # Check if cluster already exists
    if docker exec redis-enterprise-node1 bash -c "echo 'status' | rladmin" 2>/dev/null | grep -q "CLUSTER NODES"; then
        success "Redis Enterprise cluster already exists"
    else
        # Create cluster using the correct approach
        log "Creating Redis Enterprise cluster..."
        if docker exec redis-enterprise-node1 bash -c "echo 'cluster create name cluster.local username admin@redis.com password admin' | rladmin" 2>/dev/null; then
            success "Redis Enterprise cluster created"
            sleep 15  # Wait for cluster to fully initialize
        else
            warning "Cluster creation failed, trying alternative approach..."
            # Try REST API bootstrap
            curl -k -X POST "https://localhost:9443/v1/bootstrap/create_cluster" \
                -H "Content-Type: application/json" \
                -d '{
                    "action": "create_cluster",
                    "cluster": {"name": "cluster.local"},
                    "node": {
                        "paths": {
                            "persistent_path": "/opt/redislabs/persist",
                            "ephemeral_path": "/opt/redislabs/tmp"
                        }
                    },
                    "credentials": {
                        "username": "admin@redis.com",
                        "password": "admin"
                    }
                }' &>/dev/null || true
            sleep 20
        fi
    fi

    # Verify cluster status
    log "Verifying cluster status..."
    if docker exec redis-enterprise-node1 bash -c "echo 'status' | rladmin" 2>/dev/null | grep -q "OK"; then
        success "Redis Enterprise cluster is operational"
    else
        warning "Cluster status unclear, continuing with database creation..."
    fi

    # Create database
    log "Creating Redis Enterprise database..."
    sleep 10

    # Try REST API approach for database creation with authentication
    if curl -k -X POST "https://localhost:9443/v1/bdbs" \
        -H "Content-Type: application/json" \
        -u "admin@redis.com:admin" \
        -d '{
            "name": "demo-db",
            "type": "redis",
            "memory_size": 104857600,
            "port": 12000,
            "authentication_redis_pass": "admin"
        }' &>/dev/null; then
        success "Redis Enterprise database created"

        # Wait for database to be ready
        log "Waiting for database to be active..."
        timeout 60 bash -c 'until docker exec redis-enterprise-node1 bash -c "echo \"status\" | rladmin" 2>/dev/null | grep -q "active"; do sleep 5; done' || true

    else
        warning "Database creation failed, but continuing..."
    fi
}

# Load demo data
load_demo_data() {
    log "Loading demo data into Redis instances..."

    # Load data into demo Redis
    log "Loading enterprise-like data into demo Redis..."
    docker-compose exec -T redis-demo bash -c '
        redis-cli CONFIG SET maxmemory 256mb
        redis-cli CONFIG SET maxmemory-policy allkeys-lru

        for i in {1..1000}; do
            redis-cli SET "user:$i" "{\"id\":$i,\"name\":\"User$i\",\"email\":\"user$i@company.com\"}" >/dev/null
            redis-cli SET "session:$i" "{\"user_id\":$i,\"token\":\"tok_$i\"}" >/dev/null
            redis-cli SADD "active_users" "user:$i" >/dev/null
        done

        for i in {1..500}; do
            redis-cli SET "cache:product:$i" "{\"id\":$i,\"name\":\"Product$i\",\"price\":$((i * 10))}" >/dev/null
            redis-cli EXPIRE "cache:product:$i" 3600 >/dev/null
        done

        echo "Demo Redis: $(redis-cli DBSIZE) keys loaded"
    '

    # Load data into Redis Enterprise (if available)
    if docker exec redis-enterprise-node1 redis-cli -p 12000 -a admin ping &>/dev/null; then
        log "Loading enterprise data into Redis Enterprise..."
        docker exec redis-enterprise-node1 bash -c '
            for i in {1..100}; do
                redis-cli -p 12000 -a admin SET "enterprise:user:$i" "{\"id\":$i,\"name\":\"EnterpriseUser$i\",\"department\":\"Engineering\"}" >/dev/null
                redis-cli -p 12000 -a admin SET "enterprise:session:$i" "{\"user_id\":$i,\"token\":\"ent_tok_$i\"}" >/dev/null
                redis-cli -p 12000 -a admin SADD "enterprise:active_users" "enterprise:user:$i" >/dev/null
            done

            for i in {1..50}; do
                redis-cli -p 12000 -a admin SET "enterprise:cache:config:$i" "{\"service\":\"service$i\",\"config\":{\"timeout\":30}}" >/dev/null
                redis-cli -p 12000 -a admin EXPIRE "enterprise:cache:config:$i" 7200 >/dev/null
            done

            echo "Redis Enterprise: $(redis-cli -p 12000 -a admin DBSIZE) keys loaded"
        '
    else
        warning "Redis Enterprise database not available, skipping enterprise data load"
    fi

    success "Demo data loaded successfully"
}

# Start SRE Agent services
start_sre_services() {
    log "Starting SRE Agent services..."

    # Start the API first
    docker-compose up -d sre-agent

    log "Waiting for SRE Agent API to be ready..."
    timeout 60 bash -c 'until curl -s http://localhost:8000/api/v1/health >/dev/null; do sleep 2; done'

    # Start the worker
    docker-compose up -d sre-worker

    # Start the UI
    docker-compose up -d sre-ui

    log "Waiting for UI to be ready..."
    timeout 60 bash -c 'until curl -s http://localhost:3002 >/dev/null; do sleep 2; done'

    success "SRE Agent services started successfully"
}

# Configure initial instances
configure_instances() {
    log "Configuring Redis instances..."

    # Wait a bit for the API to fully initialize
    sleep 10

    # Configure demo instance
    log "Configuring demo Redis instance..."
    curl -X POST "http://localhost:8000/api/v1/instances" \
        -H "Content-Type: application/json" \
        -d '{
            "name": "Demo with Enterprise Data",
            "connection_url": "redis://redis-demo:6379",
            "environment": "development",
            "usage": "App data",
            "description": "Demo Redis instance loaded with enterprise-like data (users, sessions, cache, analytics)",
            "notes": "Contains 1000 users, 1000 sessions, 500 cached products, analytics data. Configured with 256MB maxmemory and LRU eviction."
        }' >/dev/null 2>&1 || warning "Failed to configure demo instance"

    # Configure Redis Enterprise instance (if available)
    if docker exec redis-enterprise-node1 redis-cli -p 12000 -a admin ping &>/dev/null; then
        log "Configuring Redis Enterprise instance..."
        curl -X POST "http://localhost:8000/api/v1/instances" \
            -H "Content-Type: application/json" \
            -d '{
                "name": "Redis Enterprise Production",
                "connection_url": "redis://:admin@redis-enterprise:12000/0",
                "environment": "production",
                "usage": "enterprise",
                "description": "Redis Enterprise Software database with advanced clustering and enterprise features",
                "notes": "Redis Enterprise cluster with 100MB database on port 12000. Supports advanced features like active-active geo-distribution, Redis modules, and enterprise security.",
                "instance_type": "enterprise"
            }' >/dev/null 2>&1 || warning "Failed to configure Redis Enterprise instance"
    fi

    success "Instance configuration completed"
}

# Verify setup
verify_setup() {
    log "Verifying setup..."

    # Test SRE Agent API
    if curl -s http://localhost:8000/api/v1/health | grep -q "healthy"; then
        success "SRE Agent API is healthy"
    else
        warning "SRE Agent API health check failed"
    fi

    # Test Redis instances
    log "Testing Redis instance connections..."
    sleep 5

    # Get list of instances and test connections
    INSTANCES=$(curl -s http://localhost:8000/api/v1/instances | jq -r '.[].id' 2>/dev/null || echo "")

    if [ -n "$INSTANCES" ]; then
        for instance_id in $INSTANCES; do
            log "Testing connection for instance: $instance_id"
            RESULT=$(curl -s -X POST "http://localhost:8000/api/v1/instances/$instance_id/test-connection" | jq -r '.success' 2>/dev/null || echo "false")
            if [ "$RESULT" = "true" ]; then
                success "Instance $instance_id connection test passed"
            else
                warning "Instance $instance_id connection test failed"
            fi
        done
    else
        warning "No instances found to test"
    fi

    success "Setup verification completed"
}

# Main setup function
main() {
    echo "🚀 Redis SRE Agent Setup"
    echo "========================"
    echo

    check_prerequisites
    start_core_services
    setup_redis_enterprise
    load_demo_data
    start_sre_services
    configure_instances
    verify_setup

    echo
    echo "🎉 Setup completed successfully!"
    echo
    echo "Services available at:"
    echo "  • SRE Agent UI:      http://localhost:3002"
    echo "  • SRE Agent API:     http://localhost:8000"
    echo "  • Prometheus:        http://localhost:9090"
    echo "  • Grafana:           http://localhost:3001 (admin/admin)"
    echo "  • Redis Enterprise:  https://localhost:8443 (admin@redis.com/admin)"
    echo
    echo "Redis instances:"
    echo "  • Demo Redis:        localhost:7844 (no auth)"
    echo "  • Agent Redis:       localhost:7843 (no auth)"
    echo "  • Enterprise Redis:  localhost:12000 (password: admin)"
    echo
    echo "To get started:"
    echo "  1. Open http://localhost:3002"
    echo "  2. Select a Redis instance from the dropdown"
    echo "  3. Ask questions about Redis performance and troubleshooting"
    echo
}

# Run main function
main "$@"
