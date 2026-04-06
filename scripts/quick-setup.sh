#!/bin/bash
# Redis SRE Agent quick demo script.
# Starts a local stack, seeds demo data, and registers a demo instance.

set -euo pipefail

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

require_env_file() {
    if [ ! -f ".env" ]; then
        warning "Missing .env. Start with: cp .env.example .env"
        exit 1
    fi
}

validate_required_env() {
    if grep -Eq '^OPENAI_API_KEY=(|sk-your-real-openai-key)$' .env; then
        warning "Set OPENAI_API_KEY in .env before running the demo."
        exit 1
    fi

    if grep -Eq '^REDIS_SRE_MASTER_KEY=(|your_generated_key)$' .env; then
        warning "Set REDIS_SRE_MASTER_KEY in .env before running the demo."
        exit 1
    fi
}

wait_for_url() {
    local url="$1"
    local name="$2"

    for _ in $(seq 1 45); do
        if curl -fsS "$url" >/dev/null 2>&1; then
            success "$name is ready"
            return 0
        fi
        sleep 2
    done

    warning "$name did not become ready in time"
    exit 1
}

main() {
    echo "Redis SRE Agent Quick Demo"
    echo "=========================="
    echo

    require_env_file
    validate_required_env

    log "Starting local evaluation stack..."
    docker compose up -d \
        redis redis-demo redis-exporter redis-exporter-agent pushgateway \
        prometheus grafana loki promtail tempo \
        sre-agent sre-worker sre-ui

    log "Waiting for services to be ready..."
    wait_for_url "http://localhost:8080/api/v1/health" "API"
    wait_for_url "http://localhost:3002" "UI"

    log "Loading basic demo data..."
    docker compose exec -T redis-demo sh -lc '
        for i in $(seq 1 100); do
            redis-cli SET "user:$i" "{\"id\":$i,\"name\":\"User$i\"}" >/dev/null
            redis-cli SET "session:$i" "{\"user_id\":$i,\"token\":\"tok_$i\"}" >/dev/null
        done
        echo "Loaded $(redis-cli DBSIZE) keys"
    '

    log "Configuring demo instance..."
    if docker compose exec -T sre-agent uv run redis-sre-agent instance list --json | grep -q '"name": "demo"'; then
        log "Demo instance already exists"
    else
        docker compose exec -T sre-agent uv run redis-sre-agent instance create \
            --name demo \
            --connection-url redis://redis-demo:6379/0 \
            --environment development \
            --usage cache \
            --description "Seeded demo Redis target" \
            --json >/dev/null
        success "Registered demo instance"
    fi

    echo
    log "Configured instances:"
    docker compose exec -T sre-agent uv run redis-sre-agent instance list

    echo
    success "Quick demo is ready"
    echo
    echo "Ready to use:"
    echo "  API:       http://localhost:8080"
    echo "  UI:        http://localhost:3002"
    echo "  Grafana:   http://localhost:3001"
    echo "  Prometheus: http://localhost:9090"
    echo
    echo "Try a knowledge question:"
    echo "  docker compose exec -T sre-agent uv run redis-sre-agent \\"
    echo '    query "What are Redis eviction policies?"'
    echo
    echo "Then try live triage with the demo instance ID shown above:"
    echo "  docker compose exec -T sre-agent uv run redis-sre-agent \\"
    echo '    query "Check memory pressure and slow ops" -r <instance_id>'
    echo
    echo "For a fuller setup walkthrough, see docs/quickstarts/end-to-end-setup.md"
}

main "$@"
