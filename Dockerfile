# STAGE 1: Builder
# We use a separate stage to compile dependencies and build artifacts.
# This allows us to discard build tools and caches in the final image.
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app

# Set uv environment variables for optimization
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
# Install uv-managed Python into a neutral, shared location so it can be used
# by the non-root "app" user in the runtime image. This prevents venv
# interpreters from pointing into /root/.local, which "app" cannot execute.
ENV UV_PYTHON_INSTALL_DIR=/opt/uv/python

# Install system dependencies required ONLY for building/fetching (like git)
# We don't need Docker CLI here unless your build script relies on it.
RUN apt-get update && apt-get install -y \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies
# 1. Copy only dependency files first to leverage Docker layer caching
COPY pyproject.toml uv.lock ./

# 2. Install dependencies using cache mount.
# --mount=type=cache prevents the uv cache (~GBs) from being saved to the image layer,
# directly solving your "ResourceExhausted" error.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# 3. Copy application code
COPY . .

# 4. Install the project itself and generate artifacts
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev && \
    mkdir -p /app/artifacts && \
    # Ensure /opt/uv exists even if uv uses the system Python
    mkdir -p /opt/uv && \
    # Attempt to build artifacts, but don't fail build if it requires runtime services
    (uv run --no-sync redis-sre-agent pipeline prepare-sources \
    --source-dir /app/source_documents \
    --prepare-only \
    --artifacts-path /app/artifacts || \
    echo "Warning: Could not prepare source documents at build time")


# STAGE 2: Runtime
# This is the final image. It will be much smaller.
FROM python:3.12-slim

# Copy uv binary into the runtime image so entrypoint scripts and docker-compose
# commands that use `uv run` work correctly.
COPY --from=builder /bin/uv /bin/uv

# Copy uv's managed Python installation from the builder stage. With
# UV_PYTHON_INSTALL_DIR set to /opt/uv/python in the builder, the
# /app/.venv/bin/python interpreter inside the project venv will point into
# this directory instead of /root/.local, making it executable by the "app"
# user in the runtime image.
COPY --from=builder /opt/uv /opt/uv

WORKDIR /app

# Ensure uv in the runtime container also uses the shared Python install
# under /opt/uv/python instead of /root/.local/share/uv.
ENV UV_PYTHON_INSTALL_DIR=/opt/uv/python

# Install ONLY runtime system dependencies
# We repeat the Docker/Redis install here because they are needed at runtime.
RUN apt-get update && apt-get install -y \
    git \
    curl \
    ca-certificates \
    redis-tools \
    gnupg \
    lsb-release \
    && mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null \
    && apt-get update \
    && apt-get install -y docker-ce-cli \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Create the application user and docker group before copying app files so we
# can set ownership in a single COPY layer instead of a separate chown layer.
RUN useradd --create-home --shell /bin/bash app && \
    (groupadd -g 999 docker || true) && \
    usermod -aG docker app

# Copy the application and virtual environment from the builder stage with
# correct ownership. This avoids an extra  chown -R layer over /app.
COPY --from=builder --chown=app:app /app /app

# Add the virtual environment to PATH
# This allows us to run "uvicorn" or "python" directly without "uv run"
ENV PATH="/app/.venv/bin:$PATH"

# Install the entrypoint script
COPY scripts/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

USER app

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]

# Optimized CMD: Call uvicorn directly from the venv.
# We don't need 'uv run' overhead in production.
CMD ["uvicorn", "redis_sre_agent.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
