#!/bin/bash
# build-airgap.sh - Build air-gapped deployment bundle for Redis SRE Agent
#
# This script creates a complete bundle for air-gapped deployment:
# - Docker image with pre-bundled embedding models
# - Pre-built knowledge base artifacts
# - Configuration templates
# - Documentation
#
# Usage:
#   ./scripts/build-airgap.sh [OPTIONS]
#
# Options:
#   --tag TAG           Image tag (default: redis-sre-agent:airgap)
#   --output DIR        Output directory (default: ./airgap-bundle)
#   --skip-artifacts    Skip building knowledge base artifacts
#   --skip-image        Skip building Docker image
#   --push REGISTRY     Push to registry after build
#   --help              Show this help message

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() { echo -e "${BLUE}[INFO]${NC} $1"; }
success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# Default values
IMAGE_TAG="redis-sre-agent:airgap"
OUTPUT_DIR="./airgap-bundle"
SKIP_ARTIFACTS=false
SKIP_IMAGE=false
PUSH_REGISTRY=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --tag) IMAGE_TAG="$2"; shift 2 ;;
        --output) OUTPUT_DIR="$2"; shift 2 ;;
        --skip-artifacts) SKIP_ARTIFACTS=true; shift ;;
        --skip-image) SKIP_IMAGE=true; shift ;;
        --push) PUSH_REGISTRY="$2"; shift 2 ;;
        --help)
            head -25 "$0" | tail -20
            exit 0
            ;;
        *) error "Unknown option: $1" ;;
    esac
done

log "Building air-gapped deployment bundle"
log "  Image tag: $IMAGE_TAG"
log "  Output: $OUTPUT_DIR"

# Create output directory
mkdir -p "$OUTPUT_DIR"

# Build knowledge base artifacts (if not skipped)
if [ "$SKIP_ARTIFACTS" = false ]; then
    log "Building knowledge base artifacts..."
    if [ -d "source_documents" ] && [ "$(ls -A source_documents 2>/dev/null)" ]; then
        uv run redis-sre-agent pipeline prepare-sources \
            --source-dir ./source_documents \
            --prepare-only \
            --artifacts-path ./artifacts || warning "Artifact build failed, continuing..."

        # Copy artifacts to bundle
        if [ -d "artifacts" ]; then
            cp -r artifacts "$OUTPUT_DIR/"
            success "Knowledge base artifacts copied"
        fi
    else
        warning "No source_documents found, skipping artifact build"
    fi
else
    log "Skipping artifact build (--skip-artifacts)"
fi

# Build Docker image (if not skipped)
if [ "$SKIP_IMAGE" = false ]; then
    log "Building Docker image: $IMAGE_TAG"
    docker build -f Dockerfile.airgap -t "$IMAGE_TAG" .
    success "Docker image built: $IMAGE_TAG"

    # Export image to tarball
    log "Exporting image to tarball..."
    docker save "$IMAGE_TAG" | gzip > "$OUTPUT_DIR/redis-sre-agent-airgap.tar.gz"
    success "Image exported: $OUTPUT_DIR/redis-sre-agent-airgap.tar.gz"

    # Push to registry if specified
    if [ -n "$PUSH_REGISTRY" ]; then
        FULL_TAG="$PUSH_REGISTRY/$IMAGE_TAG"
        log "Pushing to registry: $FULL_TAG"
        docker tag "$IMAGE_TAG" "$FULL_TAG"
        docker push "$FULL_TAG"
        success "Pushed to: $FULL_TAG"
    fi
else
    log "Skipping image build (--skip-image)"
fi

# Copy configuration templates
log "Copying configuration templates..."
cp docker-compose.airgap.yml "$OUTPUT_DIR/"
cp .env.airgap.example "$OUTPUT_DIR/.env.example"
cp config.airgap.yaml "$OUTPUT_DIR/config.yaml"

success "Configuration templates copied"

# Create README for the bundle
cat > "$OUTPUT_DIR/README.md" << 'EOF'
# Redis SRE Agent - Air-Gapped Deployment Bundle

This bundle contains everything needed to deploy Redis SRE Agent in an
air-gapped environment without internet access.

## Contents

- `redis-sre-agent-airgap.tar.gz` - Docker image with pre-bundled models
- `docker-compose.airgap.yml` - Minimal compose file
- `.env.example` - Configuration template
- `config.yaml` - Agent configuration (MCP servers disabled)
- `artifacts/` - Pre-built knowledge base (if available)

## Quick Start

1. Load the Docker image:
   ```bash
   docker load < redis-sre-agent-airgap.tar.gz
   ```

2. Configure environment:
   ```bash
   cp .env.example .env
   # Edit .env with your internal URLs
   ```

3. Start services:
   ```bash
   docker-compose -f docker-compose.airgap.yml up -d
   ```

## Requirements

- Redis with RediSearch module (external)
- OpenAI-compatible LLM API (internal proxy)
- Optional: Prometheus, Loki (internal)

## Configuration

See `.env.example` for all configuration options.

Key settings:
- `REDIS_URL` - Your internal Redis instance
- `OPENAI_BASE_URL` - Your internal LLM proxy
- `EMBEDDING_PROVIDER=local` - Uses bundled embedding model
EOF

success "Bundle README created"

# Print summary
echo
success "Air-gapped bundle created: $OUTPUT_DIR"
echo
log "Bundle contents:"
ls -la "$OUTPUT_DIR"
echo
log "Next steps:"
echo "  1. Transfer $OUTPUT_DIR to air-gapped environment"
echo "  2. Load image: docker load < redis-sre-agent-airgap.tar.gz"
echo "  3. Configure: cp .env.example .env && edit .env"
echo "  4. Start: docker-compose -f docker-compose.airgap.yml up -d"
