#!/bin/bash
# Redis SRE Agent Knowledge Base Setup Script
# Populates the knowledge base with Redis documentation and runbooks

set -euo pipefail

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

main() {
    echo "📚 Redis SRE Agent Knowledge Base Setup"
    echo "======================================="
    echo

    # Check if SRE Agent is running
    if ! curl -s http://localhost:8000/health >/dev/null; then
        warning "SRE Agent API is not running. Please start it first:"
        echo "  docker-compose up -d sre-agent"
        exit 1
    fi

    log "Populating knowledge base with Redis documentation..."

    # Use the CLI to populate knowledge base
    if docker-compose exec -T sre-agent uv run redis-sre-agent knowledge populate --scrapers redis_kb 2>/dev/null; then
        success "Knowledge base populated successfully"
    else
        warning "Knowledge base population failed, but continuing..."
        log "You can manually populate it later with:"
        echo "  docker-compose exec sre-agent uv run redis-sre-agent knowledge populate"
    fi

    log "Checking knowledge base status..."
    if curl -s "http://localhost:8000/knowledge/search?q=redis+memory&limit=1" | grep -q "results"; then
        success "Knowledge base is working and searchable"
    else
        warning "Knowledge base search may not be working properly"
    fi

    echo
    success "Knowledge base setup completed!"
    echo
    echo "💡 The knowledge base contains:"
    echo "  • Redis documentation"
    echo "  • SRE runbooks and troubleshooting guides"
    echo "  • Best practices and configuration examples"
    echo
    echo "🔍 Test the knowledge base:"
    echo "  curl 'http://localhost:8000/knowledge/search?q=memory+usage&limit=5'"
    echo
}

main "$@"
