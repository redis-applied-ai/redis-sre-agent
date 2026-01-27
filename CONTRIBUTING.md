# Contributing to Redis SRE Agent

## Prerequisites

- Python 3.12+
- [uv](https://github.com/astral-sh/uv) package manager
- Docker + Docker Compose v2

### Redis 8

This project requires **Redis 8**. Redis 8 includes the search and vector capabilities needed by the agent.

If you use Docker Compose (`make local-services`), Redis 8 is already configured—no additional setup needed.

For local development without Docker Compose, you can:
- Run Redis 8 via Docker: `docker run -d -p 7843:6379 redis:8`
- Install Redis 8 locally: see [redis.io/docs/install](https://redis.io/docs/latest/operate/oss_and_stack/install/)

## Development Setup

### 1. Clone and Install

```bash
git clone https://github.com/redis-applied-ai/redis-sre-agent.git
cd redis-sre-agent

# Install all dependencies (including dev)
uv sync --dev

# Verify installation
uv run redis-sre-agent --help
```

### 2. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` with your configuration. At minimum:
- `OPENAI_API_KEY` - Your OpenAI API key
- `REDIS_URL` - Redis connection string (default: `redis://localhost:7843/0`)

### 3. Start Services

**Option A: Full Docker Stack** (recommended)
```bash
make local-services
```

This starts Redis 8, Prometheus, Grafana, Loki, LiteLLM proxy, and more. No separate Redis setup needed.

**Option B: Local Development (without Docker Compose)**

Start Redis 8 separately:
```bash
docker run -d -p 7843:6379 redis:8
```

Or use a locally installed Redis 8 instance.

## Running the Application

### Local Development (without Docker)

```bash
# Terminal 1: Start the API
uv run uvicorn redis_sre_agent.api.app:app --host 0.0.0.0 --port 8000 --reload

# Terminal 2: Start the background worker
uv run redis-sre-agent worker
```

### Docker Compose (recommended)

```bash
# Start all services
make local-services

# View logs
make local-services-logs

# Stop services
make local-services-down
```

**Service URLs:**
| Service | URL |
|---------|-----|
| SRE Agent API | http://localhost:8080 |
| SRE Agent UI | http://localhost:3002 |
| Grafana | http://localhost:3001 (admin/admin) |
| Prometheus | http://localhost:9090 |
| LiteLLM UI | http://localhost:4000/ui (admin/admin) |

## Running Tests

```bash
# Unit tests only (fast, no external dependencies)
make test

# Integration tests only (requires Redis)
make test-integration

# All tests
make test-all

# With coverage report
uv run pytest --cov=redis_sre_agent --cov-report=html
open htmlcov/index.html
```

### Test Markers

- `@pytest.mark.integration` - Requires running Redis
- `@pytest.mark.slow` - Long-running tests

## Code Quality

```bash
# Run linting and formatting (same as CI)
uv run pre-commit run -a

# Individual tools
uv run ruff check .
uv run ruff format .
uv run mypy redis_sre_agent/
```

## Documentation

```bash
# Build docs
make docs-build

# Live preview (http://127.0.0.1:8000)
make docs-serve

# Generate reference docs from code
make docs-gen
```

## Makefile Targets

Run `make help` for all available targets:

| Target | Description |
|--------|-------------|
| `make sync` | Install dependencies |
| `make test` | Run unit tests |
| `make test-all` | Run full test suite |
| `make local-services` | Start Docker stack |
| `make local-services-down` | Stop Docker stack |
| `make docs-serve` | Live docs preview |
| `make ui-dev` | Run UI dev server |

## Publishing Releases

### Docker Images

Docker images are published via GitHub Actions workflow (`publish-docker.yml`).

**To publish a release:**

1. Go to Actions → "Publish Docker Image"
2. Click "Run workflow"
3. Enter the tag (e.g., `v0.2.3`)
4. Optionally check "Also tag as latest"
5. Optionally check "Build air-gap image"

Images are pushed to:
- `redislabs/redis-sre-agent:<tag>`
- `ghcr.io/redis-applied-ai/redis-sre-agent:<tag>`

### Version Bumping

Update the version in `pyproject.toml`:
```toml
[project]
version = "0.2.3"
```

## Pull Request Guidelines

1. Create a feature branch from `main`
2. Run tests locally: `make test`
3. Run linting: `uv run pre-commit run -a`
4. Push and create a PR
5. Ensure CI passes before requesting review

## Project Structure

```
redis_sre_agent/
├── agent/          # LangGraph agent implementation
├── api/            # FastAPI endpoints
├── cli/            # Command-line interface
├── core/           # Configuration, data models
├── mcp_server/     # Model Context Protocol server
├── pipelines/      # Data ingestion pipelines
└── tools/          # SRE tool implementations
```
