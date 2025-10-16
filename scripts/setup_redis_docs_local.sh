#!/bin/bash
# Setup script for local Redis docs scraping
# Clones the redis/docs repo and runs the local scraper

set -euo pipefail

# Colors
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

# Configuration
DOCS_REPO_URL="https://github.com/redis/docs.git"
DOCS_REPO_PATH="./redis-docs"
BRANCH="main"  # or "latest" for production docs

main() {
    echo "📚 Redis Docs Local Scraper Setup"
    echo "=================================="
    echo

    # Check if repo already exists
    if [ -d "$DOCS_REPO_PATH" ]; then
        log "Docs repo already exists at $DOCS_REPO_PATH"
        log "Updating to latest version..."

        cd "$DOCS_REPO_PATH"
        git fetch origin
        git checkout "$BRANCH"
        git pull origin "$BRANCH"
        cd ..

        success "Docs repo updated to latest $BRANCH"
    else
        log "Cloning Redis docs repo..."
        git clone --depth 1 --branch "$BRANCH" "$DOCS_REPO_URL" "$DOCS_REPO_PATH"
        success "Docs repo cloned successfully"
    fi

    # Show stats
    echo
    log "Repository statistics:"
    echo "  📂 Location: $DOCS_REPO_PATH"
    echo "  🌿 Branch: $BRANCH"
    echo "  📄 Markdown files: $(find "$DOCS_REPO_PATH/content" -name "*.md" | wc -l)"
    echo

    # Run the scraper
    log "Running local docs scraper..."
    echo

    redis-sre-agent pipeline scrape --scrapers redis_docs_local

    echo
    success "Local docs scraping complete!"
    echo
    echo "💡 Next steps:"
    echo "  1. Run ingestion: redis-sre-agent pipeline ingest"
    echo "  2. Or run full pipeline: redis-sre-agent pipeline full --scrapers redis_docs_local"
    echo
}

main "$@"
