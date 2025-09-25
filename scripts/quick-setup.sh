#!/bin/bash
# Redis SRE Agent Quick Setup Script
# Minimal setup for development and testing

set -euo pipefail

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

main() {
    echo "⚡ Redis SRE Agent Quick Setup"
    echo "============================="
    echo
    
    log "Starting essential services..."
    docker-compose up -d redis redis-demo sre-agent sre-worker sre-ui
    
    log "Waiting for services to be ready..."
    timeout 60 bash -c 'until curl -s http://localhost:8000/health >/dev/null; do sleep 2; done'
    timeout 60 bash -c 'until curl -s http://localhost:3002 >/dev/null; do sleep 2; done'
    
    log "Loading basic demo data..."
    docker-compose exec -T redis-demo bash -c '
        for i in {1..100}; do
            redis-cli SET "user:$i" "{\"id\":$i,\"name\":\"User$i\"}" >/dev/null
            redis-cli SET "session:$i" "{\"user_id\":$i,\"token\":\"tok_$i\"}" >/dev/null
        done
        echo "Loaded $(redis-cli DBSIZE) keys"
    '
    
    log "Configuring demo instance..."
    sleep 5
    curl -X POST "http://localhost:8000/api/v1/instances" \
        -H "Content-Type: application/json" \
        -d '{
            "name": "Demo Redis",
            "connection_url": "redis://redis-demo:6379",
            "environment": "development",
            "usage": "App data",
            "description": "Demo Redis instance for testing"
        }' >/dev/null 2>&1 || true
    
    echo
    success "Quick setup completed!"
    echo
    echo "🎯 Ready to use:"
    echo "  • SRE Agent UI: http://localhost:3002"
    echo "  • SRE Agent API: http://localhost:8000"
    echo
    echo "💡 For full setup with Redis Enterprise and monitoring:"
    echo "   ./scripts/setup.sh"
    echo
}

main "$@"
