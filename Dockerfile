FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies including Docker CLI
RUN apt-get update && apt-get install -y \
    git \
    curl \
    ca-certificates \
    gnupg \
    lsb-release \
    && mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null \
    && apt-get update \
    && apt-get install -y docker-ce-cli \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Copy dependency files and project metadata required at build time
COPY pyproject.toml uv.lock ./
COPY README.md ./

# Copy application code
COPY . .

# Install dependencies and package in editable mode
RUN uv sync --frozen --no-dev

# Pre-build knowledge base artifacts for faster production startup
# This prepares batch artifacts from source documents without requiring Redis at build time
RUN mkdir -p /app/artifacts && \
    uv run redis-sre-agent pipeline prepare-sources \
        --source-dir /app/source_documents \
        --prepare-only \
        --artifacts-path /app/artifacts || \
    echo "Warning: Could not prepare source documents at build time"

# Copy and setup entrypoint script
COPY scripts/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Create non-root user and add to docker group
RUN useradd --create-home --shell /bin/bash app \
    && groupadd -g 999 docker || true \
    && usermod -aG docker app \
    && chown -R app:app /app
USER app

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Use entrypoint for initialization
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]

# Default command (can be overridden)
CMD ["uv", "run", "uvicorn", "redis_sre_agent.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
