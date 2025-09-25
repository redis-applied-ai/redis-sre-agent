#!/bin/bash
# Redis SRE Agent Validation Script
# Validates that all services are running correctly

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

success() {
    echo -e "${GREEN}[✓]${NC} $1"
}

warning() {
    echo -e "${YELLOW}[!]${NC} $1"
}

error() {
    echo -e "${RED}[✗]${NC} $1"
}

# Check if a service is responding
check_service() {
    local name="$1"
    local url="$2"
    local expected_status="${3:-200}"
    
    if curl -s -o /dev/null -w "%{http_code}" "$url" | grep -q "$expected_status"; then
        success "$name is responding"
        return 0
    else
        error "$name is not responding at $url"
        return 1
    fi
}

# Check Redis connection
check_redis() {
    local name="$1"
    local host="$2"
    local port="$3"
    
    if docker-compose exec -T "$host" redis-cli -p "$port" ping 2>/dev/null | grep -q PONG; then
        success "$name is responding"
        return 0
    else
        error "$name is not responding at $host:$port"
        return 1
    fi
}

main() {
    echo "🔍 Redis SRE Agent Validation"
    echo "============================="
    echo
    
    local all_good=true
    
    log "Checking core services..."
    
    # Check SRE Agent API
    if check_service "SRE Agent API" "http://localhost:8000/health"; then
        # Check detailed health
        local health_status=$(curl -s "http://localhost:8000/health" | jq -r '.redis_connection // "unknown"' 2>/dev/null || echo "unknown")
        if [ "$health_status" = "available" ]; then
            success "SRE Agent health check passed"
        else
            warning "SRE Agent health check shows issues: $health_status"
        fi
    else
        all_good=false
    fi
    
    # Check SRE Agent UI
    if ! check_service "SRE Agent UI" "http://localhost:3002"; then
        all_good=false
    fi
    
    # Check Redis instances
    log "Checking Redis instances..."
    
    if ! check_redis "Agent Redis" "redis" "6379"; then
        all_good=false
    fi
    
    if ! check_redis "Demo Redis" "redis-demo" "6379"; then
        all_good=false
    fi
    
    # Check Redis Enterprise (optional)
    if docker-compose ps redis-enterprise | grep -q "Up"; then
        if check_redis "Redis Enterprise" "redis-enterprise" "12000"; then
            success "Redis Enterprise is available"
        else
            warning "Redis Enterprise container is up but database not responding"
        fi
    else
        warning "Redis Enterprise is not running (this is optional)"
    fi
    
    # Check monitoring services (optional)
    log "Checking monitoring services..."
    
    if docker-compose ps prometheus | grep -q "Up"; then
        if check_service "Prometheus" "http://localhost:9090/-/healthy"; then
            success "Prometheus is available"
        else
            warning "Prometheus container is up but not responding"
        fi
    else
        warning "Prometheus is not running (this is optional)"
    fi
    
    if docker-compose ps grafana | grep -q "Up"; then
        if check_service "Grafana" "http://localhost:3001/api/health"; then
            success "Grafana is available"
        else
            warning "Grafana container is up but not responding"
        fi
    else
        warning "Grafana is not running (this is optional)"
    fi
    
    # Check worker status
    log "Checking worker status..."
    if docker-compose ps sre-worker | grep -q "Up"; then
        success "SRE Worker is running"
        
        # Check if worker is processing tasks
        local worker_logs=$(docker-compose logs --tail 10 sre-worker 2>/dev/null || echo "")
        if echo "$worker_logs" | grep -q "Worker started"; then
            success "SRE Worker appears to be functioning"
        else
            warning "SRE Worker may not be fully initialized"
        fi
    else
        error "SRE Worker is not running"
        all_good=false
    fi
    
    # Check instances configuration
    log "Checking instance configuration..."
    local instances=$(curl -s "http://localhost:8000/api/v1/instances" 2>/dev/null || echo "[]")
    local instance_count=$(echo "$instances" | jq length 2>/dev/null || echo "0")
    
    if [ "$instance_count" -gt 0 ]; then
        success "Found $instance_count configured Redis instance(s)"
    else
        warning "No Redis instances configured - run setup script to configure instances"
    fi
    
    # Test basic functionality
    log "Testing basic functionality..."
    
    # Test knowledge search
    local search_result=$(curl -s "http://localhost:8000/knowledge/search?q=redis&limit=1" 2>/dev/null || echo "{}")
    local result_count=$(echo "$search_result" | jq '.results | length' 2>/dev/null || echo "0")
    
    if [ "$result_count" -gt 0 ]; then
        success "Knowledge base search is working"
    else
        warning "Knowledge base may be empty - run ./scripts/setup-knowledge.sh"
    fi
    
    echo
    if [ "$all_good" = true ]; then
        success "All essential services are running correctly!"
        echo
        echo "🎯 Ready to use:"
        echo "  • SRE Agent UI: http://localhost:3002"
        echo "  • SRE Agent API: http://localhost:8000"
        echo
        echo "💡 Try asking: 'What is the memory usage of my Redis instance?'"
    else
        error "Some essential services have issues"
        echo
        echo "🔧 Troubleshooting:"
        echo "  • Check logs: docker-compose logs -f"
        echo "  • Restart services: docker-compose restart"
        echo "  • Full reset: ./scripts/cleanup.sh --remove-data && ./scripts/setup.sh"
        exit 1
    fi
}

main "$@"
