#!/bin/bash
# build-airgap.sh - Build air-gapped deployment bundle for Redis SRE Agent
#
# This script creates a complete bundle for air-gapped deployment:
# - Docker images for the API/worker and optional UI
# - Pre-built knowledge base artifacts
# - Configuration templates
# - Documentation
#
# Usage:
#   ./scripts/build-airgap.sh [OPTIONS]
#
# Options:
#   --tag TAG            Agent image tag (default: redis-sre-agent:airgap)
#   --ui-tag TAG         UI image tag (default: redis-sre-agent-ui:airgap)
#   --output DIR         Output directory (default: ./airgap-bundle)
#   --skip-artifacts     Skip building knowledge base artifacts
#   --skip-image         Skip building the agent Docker image
#   --skip-ui-image      Skip building the UI Docker image
#   --push REGISTRY      Push built images to REGISTRY after build
#   --help               Show this help message

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() { echo -e "${BLUE}[INFO]${NC} $1"; }
success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

IMAGE_TAG="redis-sre-agent:airgap"
UI_IMAGE_TAG="redis-sre-agent-ui:airgap"
OUTPUT_DIR="./airgap-bundle"
SKIP_ARTIFACTS=false
SKIP_IMAGE=false
SKIP_UI_IMAGE=false
PUSH_REGISTRY=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --tag) IMAGE_TAG="$2"; shift 2 ;;
        --ui-tag) UI_IMAGE_TAG="$2"; shift 2 ;;
        --output) OUTPUT_DIR="$2"; shift 2 ;;
        --skip-artifacts) SKIP_ARTIFACTS=true; shift ;;
        --skip-image) SKIP_IMAGE=true; shift ;;
        --skip-ui-image) SKIP_UI_IMAGE=true; shift ;;
        --push) PUSH_REGISTRY="$2"; shift 2 ;;
        --help)
            head -25 "$0" | tail -20
            exit 0
            ;;
        *) error "Unknown option: $1" ;;
    esac
done

log "Building air-gapped deployment bundle"
log "  Agent image tag: $IMAGE_TAG"
log "  UI image tag: $UI_IMAGE_TAG"
log "  Output: $OUTPUT_DIR"

mkdir -p "$OUTPUT_DIR"

if [ "$SKIP_ARTIFACTS" = false ]; then
    log "Building knowledge base artifacts..."
    if [ -d "source_documents" ] && [ "$(ls -A source_documents 2>/dev/null)" ]; then
        uv run redis-sre-agent pipeline prepare-sources \
            --source-dir ./source_documents \
            --prepare-only \
            --artifacts-path ./artifacts || warning "Artifact build failed, continuing..."

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

if [ "$SKIP_IMAGE" = false ]; then
    log "Building agent Docker image: $IMAGE_TAG"
    docker build -f Dockerfile.airgap -t "$IMAGE_TAG" .
    success "Docker image built: $IMAGE_TAG"

    log "Exporting agent image to tarball..."
    docker save "$IMAGE_TAG" | gzip > "$OUTPUT_DIR/redis-sre-agent-airgap.tar.gz"
    success "Agent image exported: $OUTPUT_DIR/redis-sre-agent-airgap.tar.gz"

    if [ -n "$PUSH_REGISTRY" ]; then
        FULL_TAG="$PUSH_REGISTRY/$IMAGE_TAG"
        log "Pushing agent image to registry: $FULL_TAG"
        docker tag "$IMAGE_TAG" "$FULL_TAG"
        docker push "$FULL_TAG"
        success "Pushed agent image to: $FULL_TAG"
    fi
else
    log "Skipping agent image build (--skip-image)"
fi

if [ "$SKIP_UI_IMAGE" = false ]; then
    log "Building UI Docker image: $UI_IMAGE_TAG"
    docker build -f ui/Dockerfile --target production -t "$UI_IMAGE_TAG" ./ui
    success "UI Docker image built: $UI_IMAGE_TAG"

    log "Exporting UI image to tarball..."
    docker save "$UI_IMAGE_TAG" | gzip > "$OUTPUT_DIR/redis-sre-agent-ui-airgap.tar.gz"
    success "UI image exported: $OUTPUT_DIR/redis-sre-agent-ui-airgap.tar.gz"

    if [ -n "$PUSH_REGISTRY" ]; then
        FULL_UI_TAG="$PUSH_REGISTRY/$UI_IMAGE_TAG"
        log "Pushing UI image to registry: $FULL_UI_TAG"
        docker tag "$UI_IMAGE_TAG" "$FULL_UI_TAG"
        docker push "$FULL_UI_TAG"
        success "Pushed UI image to: $FULL_UI_TAG"
    fi
else
    log "Skipping UI image build (--skip-ui-image)"
fi

log "Copying configuration templates..."
cp docker-compose.airgap.yml "$OUTPUT_DIR/"
cp .env.airgap.example "$OUTPUT_DIR/.env.example"
cp config.airgap.yaml "$OUTPUT_DIR/config.yaml"
success "Configuration templates copied"

CONFIGURE_STEP_NUMBER=2
START_CORE_STEP_NUMBER=3
START_UI_STEP_NUMBER=4

if [ "$SKIP_UI_IMAGE" = false ]; then
    LOAD_UI_STEP_NUMBER=2
    CONFIGURE_STEP_NUMBER=3
    START_CORE_STEP_NUMBER=4
    START_UI_STEP_NUMBER=5
fi

cat > "$OUTPUT_DIR/README.md" <<EOF
# Redis SRE Agent - Air-Gapped Deployment Bundle

This bundle contains everything needed to deploy Redis SRE Agent in an
air-gapped environment without internet access.

## Contents

- \`redis-sre-agent-airgap.tar.gz\` - Docker image with pre-bundled models
EOF

if [ "$SKIP_UI_IMAGE" = false ]; then
    cat >> "$OUTPUT_DIR/README.md" <<'EOF'
- `redis-sre-agent-ui-airgap.tar.gz` - Optional UI image served by nginx
EOF
fi

cat >> "$OUTPUT_DIR/README.md" <<'EOF'
- `docker-compose.airgap.yml` - Minimal compose file with optional `ui` profile
- `.env.example` - Configuration template
- `config.yaml` - Agent configuration (MCP servers disabled)
- `artifacts/` - Pre-built knowledge base (if available)

## Quick Start

1. Load the agent Docker image:
   ```bash
   docker load < redis-sre-agent-airgap.tar.gz
   ```
EOF

if [ "$SKIP_UI_IMAGE" = false ]; then
    printf '\n%s\n' "${LOAD_UI_STEP_NUMBER}. Load the UI image (optional):" >> "$OUTPUT_DIR/README.md"
    cat >> "$OUTPUT_DIR/README.md" <<'EOF'
   ```bash
   docker load < redis-sre-agent-ui-airgap.tar.gz
   ```
EOF
fi

printf '\n%s\n' "${CONFIGURE_STEP_NUMBER}. Configure environment:" >> "$OUTPUT_DIR/README.md"
cat >> "$OUTPUT_DIR/README.md" <<'EOF'
   ```bash
   cp .env.example .env
   # Edit .env with your internal URLs
   ```
EOF

printf '\n%s\n' "${START_CORE_STEP_NUMBER}. Start core services:" >> "$OUTPUT_DIR/README.md"
cat >> "$OUTPUT_DIR/README.md" <<'EOF'
   ```bash
   docker compose -f docker-compose.airgap.yml up -d
   ```
EOF

if [ "$SKIP_UI_IMAGE" = false ]; then
    printf '\n%s\n' "${START_UI_STEP_NUMBER}. Start with the published UI image:" >> "$OUTPUT_DIR/README.md"
    cat >> "$OUTPUT_DIR/README.md" <<'EOF'
   ```bash
   docker compose --profile ui -f docker-compose.airgap.yml up -d
   ```
EOF
fi

cat >> "$OUTPUT_DIR/README.md" <<'EOF'

## Requirements

- Redis with RediSearch module (external)
- OpenAI-compatible LLM API (internal proxy)
- Optional: Prometheus, Loki (internal)

## Configuration

See `.env.example` for all configuration options.

Key settings:
- `REDIS_URL` - Your internal Redis instance
- `OPENAI_BASE_URL` - Your internal LLM proxy
EOF

if [ "$SKIP_UI_IMAGE" = false ]; then
    cat >> "$OUTPUT_DIR/README.md" <<'EOF'
- `SRE_UI_IMAGE` - Published UI image tag to mirror internally
- `SRE_UI_API_UPSTREAM` - Backend URL proxied by the UI container
EOF
fi

cat >> "$OUTPUT_DIR/README.md" <<'EOF'
- `EMBEDDING_PROVIDER=local` - Uses bundled embedding model
EOF

success "Bundle README created"

echo
success "Air-gapped bundle created: $OUTPUT_DIR"
echo
log "Bundle contents:"
ls -la "$OUTPUT_DIR"
echo
log "Next steps:"
echo "  1. Transfer $OUTPUT_DIR to air-gapped environment"
echo "  2. Load agent image: docker load < redis-sre-agent-airgap.tar.gz"
if [ "$SKIP_UI_IMAGE" = false ]; then
    echo "  3. Load UI image (optional): docker load < redis-sre-agent-ui-airgap.tar.gz"
    echo "  4. Configure: cp .env.example .env && edit .env"
    echo "  5. Start core services: docker compose -f docker-compose.airgap.yml up -d"
    echo "  6. Start with UI: docker compose --profile ui -f docker-compose.airgap.yml up -d"
else
    echo "  3. Configure: cp .env.example .env && edit .env"
    echo "  4. Start core services: docker compose -f docker-compose.airgap.yml up -d"
    echo "  5. Start with UI later by mirroring a published redis-sre-agent-ui image"
fi
