#!/bin/bash
# Docker entrypoint script for Redis SRE Agent
# Handles knowledge base initialization on first startup
# Note: We intentionally do NOT use 'set -e' here because knowledge base
# initialization is optional and should not prevent the application from starting.

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() {
    echo -e "${BLUE}[ENTRYPOINT]${NC} $1"
}

success() {
    echo -e "${GREEN}[ENTRYPOINT]${NC} $1"
}

warning() {
    echo -e "${YELLOW}[ENTRYPOINT]${NC} $1"
}

# Check if knowledge base needs initialization
check_knowledge_base() {
    log "Checking knowledge base status..."

    # Check if Redis is available
    # Credentials should be included in REDIS_URL: redis://user:pass@host:port/db
    if ! redis-cli -u "${REDIS_URL:-redis://localhost:6379/0}" ping >/dev/null 2>&1; then
        warning "Redis not available yet, skipping knowledge base check"
        return 1
    fi

    # Check if knowledge base has any documents
    # grep -c returns 0 and exits with status 1 when there are no matches, so
    # we ignore its exit code and default empty output to 0.
    local doc_count=$(redis-cli -u "${REDIS_URL:-redis://localhost:6379/0}" \
        FT._LIST 2>/dev/null | grep -c "sre_knowledge" || true)

    if [ -z "$doc_count" ]; then
        doc_count=0
    fi

    if [ "$doc_count" -eq 0 ]; then
        log "Knowledge base is empty"
        return 1
    else
        success "Knowledge base already initialized ($doc_count indices found)"
        return 0
    fi
}

# Initialize knowledge base from pre-built artifacts
init_knowledge_base() {
    log "Initializing knowledge base from pre-built artifacts..."

    # Check if artifacts exist
    if [ ! -d "/app/artifacts" ] || [ -z "$(ls -A /app/artifacts 2>/dev/null)" ]; then
        warning "No pre-built artifacts found, skipping initialization"
        warning "Run 'redis-sre-agent pipeline prepare-sources' to populate knowledge base"
        return 0
    fi

    # Find the most recent batch that has a manifest (date-formatted directories only: YYYY-MM-DD)
    local latest_batch=""
    for batch in $(ls -1 /app/artifacts | grep -E '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' | sort -r); do
        if [ -f "/app/artifacts/$batch/batch_manifest.json" ]; then
            latest_batch="$batch"
            break
        fi
    done

    if [ -z "$latest_batch" ]; then
        warning "No batch directories with manifests found in artifacts"
        warning "Run 'redis-sre-agent pipeline prepare-sources' to create artifacts"
        return 0
    fi

    log "Found pre-built batch: $latest_batch"
    log "Ingesting into knowledge base..."

    # Run ingestion using the installed CLI directly (no 'uv run' to avoid network checks in air-gap)
    if redis-sre-agent pipeline ingest \
        --batch-date "$latest_batch" \
        --artifacts-path /app/artifacts; then
        success "Knowledge base initialized successfully"
        return 0
    else
        warning "Knowledge base initialization failed, but continuing startup"
        warning "You can manually initialize with: redis-sre-agent pipeline ingest"
        return 1
    fi
}

# Main entrypoint logic
main() {
    log "Starting Redis SRE Agent..."

    # Wait for Redis to be available (with timeout)
    if [ "${WAIT_FOR_REDIS:-true}" = "true" ]; then
        log "Waiting for Redis to be available..."
        local max_attempts=30
        local attempt=0

        while [ $attempt -lt $max_attempts ]; do
            if redis-cli -u "${REDIS_URL:-redis://localhost:6379/0}" ping >/dev/null 2>&1; then
                success "Redis is available"
                break
            fi
            attempt=$((attempt + 1))
            sleep 2
        done

        if [ $attempt -eq $max_attempts ]; then
            warning "Redis not available after ${max_attempts} attempts"
            warning "Continuing anyway, but knowledge base may not work"
        fi
    fi

    # Initialize knowledge base if needed (only on first startup)
    if [ "${SKIP_KNOWLEDGE_INIT:-false}" != "true" ]; then
        if ! check_knowledge_base; then
            init_knowledge_base
        fi
    else
        log "Skipping knowledge base initialization (SKIP_KNOWLEDGE_INIT=true)"
    fi

    # Execute the main command
    log "Starting application: $*"
    exec "$@"
}

main "$@"
