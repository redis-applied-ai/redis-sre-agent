#!/bin/bash
# Redis SRE Agent Cleanup Script
# Stops all services and optionally removes data

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
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Show usage
usage() {
    echo "Usage: $0 [OPTIONS]"
    echo
    echo "Options:"
    echo "  --remove-data    Remove all persistent data (volumes)"
    echo "  --remove-images  Remove Docker images"
    echo "  --help          Show this help message"
    echo
    echo "Examples:"
    echo "  $0                    # Stop services only"
    echo "  $0 --remove-data      # Stop services and remove data"
    echo "  $0 --remove-data --remove-images  # Full cleanup"
}

# Stop services
stop_services() {
    log "Stopping Redis SRE Agent services..."
    docker-compose down
    success "Services stopped"
}

# Remove data volumes
remove_data() {
    warning "This will permanently delete all Redis data, metrics, and configurations!"
    read -p "Are you sure? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        log "Removing data volumes..."
        docker-compose down -v
        success "Data volumes removed"
    else
        log "Data removal cancelled"
    fi
}

# Remove Docker images
remove_images() {
    log "Removing Docker images..."

    # Remove built images
    docker rmi redis-sre-agent-sre-agent:latest 2>/dev/null || true
    docker rmi redis-sre-agent-sre-worker:latest 2>/dev/null || true
    docker rmi redis-sre-agent-sre-ui:latest 2>/dev/null || true

    # Remove unused images
    docker image prune -f

    success "Docker images removed"
}

# Main function
main() {
    local remove_data=false
    local remove_images=false

    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --remove-data)
                remove_data=true
                shift
                ;;
            --remove-images)
                remove_images=true
                shift
                ;;
            --help)
                usage
                exit 0
                ;;
            *)
                error "Unknown option: $1"
                usage
                exit 1
                ;;
        esac
    done

    echo "🧹 Redis SRE Agent Cleanup"
    echo "=========================="
    echo

    if [ "$remove_data" = true ]; then
        remove_data
    else
        stop_services
    fi

    if [ "$remove_images" = true ]; then
        remove_images
    fi

    echo
    success "Cleanup completed!"
    echo
    echo "💡 To start fresh:"
    echo "  ./scripts/setup.sh"
    echo
}

main "$@"
