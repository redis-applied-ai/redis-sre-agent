#!/bin/bash
# Redis SRE Agent Knowledge Base Setup Script
# Prepares and ingests source documents through the supported pipeline flow.

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
    API_URL="${API_URL:-http://localhost:8080}"
    COMPOSE_SERVICE="${COMPOSE_SERVICE:-sre-agent}"

    echo "📚 Redis SRE Agent Knowledge Base Setup"
    echo "======================================="
    echo

    # Check if SRE Agent is running
    if ! curl -fsS "${API_URL}/api/v1/health" >/dev/null; then
        warning "SRE Agent API is not running. Please start it first:"
        echo "  docker compose up -d ${COMPOSE_SERVICE}"
        exit 1
    fi

    log "Preparing source documents for ingestion..."

    if docker compose exec -T "${COMPOSE_SERVICE}" \
        uv run redis-sre-agent pipeline prepare-sources --prepare-only; then
        success "Source documents prepared successfully"
    else
        warning "Source document preparation failed, but continuing..."
        log "You can manually prepare sources later with:"
        echo "  docker compose exec ${COMPOSE_SERVICE} uv run redis-sre-agent pipeline prepare-sources --prepare-only"
    fi

    log "Ingesting prepared source documents..."

    if docker compose exec -T "${COMPOSE_SERVICE}" \
        uv run redis-sre-agent pipeline ingest; then
        success "Knowledge base ingested successfully"
    else
        warning "Knowledge base ingestion failed, but continuing..."
        log "You can manually ingest prepared documents later with:"
        echo "  docker compose exec ${COMPOSE_SERVICE} uv run redis-sre-agent pipeline ingest"
    fi

    log "Checking knowledge base status..."
    if curl -fsS "${API_URL}/api/v1/knowledge/search?query=redis%20memory&limit=1" | grep -q "results"; then
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
    echo "  curl '${API_URL}/api/v1/knowledge/search?query=memory%20usage&limit=5'"
    echo
}

main "$@"
