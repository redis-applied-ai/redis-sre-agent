"""
Test configuration and fixtures for Redis SRE Agent.
"""

import os
import subprocess
import time
from typing import Any, Dict, List
from unittest.mock import AsyncMock, Mock, patch

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis as AsyncRedis
from testcontainers.compose import DockerCompose


# Apply critical patches at session level BEFORE any app imports
@pytest.fixture(scope="session", autouse=True)
def mock_redis_infrastructure():
    """Mock Redis infrastructure functions to prevent connection attempts during test collection."""

    async def mock_initialize():
        return {"redis": True, "indices": True}

    async def mock_register():
        pass

    async def mock_cleanup():
        pass

    with (
        patch(
            "redis_sre_agent.core.redis.initialize_redis_infrastructure",
            side_effect=mock_initialize,
        ),
        patch("redis_sre_agent.core.docket_tasks.register_sre_tasks", side_effect=mock_register),
        patch("redis_sre_agent.core.redis.cleanup_redis_connections", side_effect=mock_cleanup),
    ):
        yield


# Load environment variables from .env file
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    # dotenv not available, skip loading
    pass


def pytest_addoption(parser):
    """Add custom pytest command-line options."""
    parser.addoption(
        "--run-api-tests",
        action="store_true",
        default=False,
        help="Run tests that make real API calls (OpenAI, etc.)",
    )


def pytest_configure(config):
    """Configure pytest based on command-line options."""
    # Set environment variables based on flags
    if config.getoption("--run-api-tests"):
        os.environ["OPENAI_INTEGRATION_TESTS"] = "true"
        os.environ["AGENT_BEHAVIOR_TESTS"] = "true"
        os.environ["INTEGRATION_TESTS"] = "true"  # Needed for redis_container fixture

    # If running full suite and INTEGRATION_TESTS requested, ensure docker compose is up
    if os.environ.get("INTEGRATION_TESTS") and not os.environ.get("CI"):
        try:
            # Start only infra services to avoid building app images during tests
            subprocess.run(
                [
                    "docker",
                    "compose",
                    "-f",
                    "docker-compose.yml",
                    "-f",
                    "docker-compose.test.yml",
                    "up",
                    "-d",
                    "redis",
                    "redis-exporter",
                    "prometheus",
                    "node-exporter",
                    "grafana",
                ],
                check=False,
            )
            # Give services a moment to start
            time.sleep(3)
        except Exception:
            # Non-fatal; testcontainers fallback will still work
            pass


def pytest_collection_modifyitems(config, items):
    """Add skip markers to tests based on configuration."""
    # Skip markers
    skip_api = pytest.mark.skip(reason="Use --run-api-tests to run tests that make real API calls")
    skip_integration = pytest.mark.skip(reason="Use --run-api-tests to run integration tests")

    for item in items:
        # Skip tests that require OpenAI API calls unless --run-api-tests flag is set
        if (
            "openai_integration" in item.keywords or "agent_behavior" in item.keywords
        ) and not config.getoption("--run-api-tests"):
            item.add_marker(skip_api)

        # Require --run-api-tests for integration tests and attach redis container fixture
        if "integration" in item.keywords:
            if not config.getoption("--run-api-tests"):
                item.add_marker(skip_integration)
                continue
            # Add redis_container as a fixture dependency only when running integration
            item.fixturenames.append("redis_container")


# Test environment variables - only set if not already present
test_env = {
    "APP_NAME": "Redis SRE Agent Test",
    "DEBUG": "true",
}

# Set default REDIS_URL for unit tests (will be overridden by redis_container for integration tests)
if not os.environ.get("REDIS_URL"):
    test_env["REDIS_URL"] = "redis://localhost:6379/0"

# Only set test API key if no real key is present
if not os.environ.get("OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY") == "":
    test_env["OPENAI_API_KEY"] = "test-openai-key"

os.environ.update(test_env)


@pytest.fixture
def sample_sre_data() -> List[Dict[str, Any]]:
    """Sample SRE knowledge data for testing."""
    return [
        {
            "title": "Redis Memory Usage Alert",
            "content": "When Redis memory usage exceeds 80%, check for large keys and consider implementing eviction policies.",
            "source": "runbooks/redis-memory.md",
            "category": "monitoring",
            "severity": "warning",
        },
        {
            "title": "Service Health Check Failure",
            "content": "If health checks fail, verify network connectivity, check service logs, and restart if necessary.",
            "source": "runbooks/health-checks.md",
            "category": "incident",
            "severity": "critical",
        },
        {
            "title": "CPU Usage Monitoring",
            "content": "Monitor CPU usage across all instances. Alert when usage exceeds 75% for more than 5 minutes.",
            "source": "monitoring/cpu-alerts.yaml",
            "category": "monitoring",
            "severity": "info",
        },
    ]


@pytest.fixture
def mock_vectorizer():
    """Mock OpenAI text vectorizer with async embedding methods."""
    with patch("redis_sre_agent.core.redis.OpenAITextVectorizer") as mock_class:
        mv = Mock()
        # Async methods used by implementation
        mv.aembed_many = AsyncMock(
            return_value=[
                [0.1] * 1536,  # Mock embedding vector
                [0.2] * 1536,
                [0.3] * 1536,
            ]
        )
        mv.aembed = AsyncMock(return_value=[0.1] * 1536)
        # Keep sync methods for any legacy/test expectations
        mv.embed_many = AsyncMock(return_value=mv.aembed_many.return_value)
        mv.embed = AsyncMock(return_value=[0.1] * 1536)
        mock_class.return_value = mv
        yield mv


@pytest.fixture
def mock_search_index():
    """Mock RedisVL AsyncSearchIndex."""
    with patch("redis_sre_agent.core.redis.AsyncSearchIndex") as mock_class:
        mock_instance = AsyncMock()
        mock_instance.exists.return_value = True
        mock_instance.create.return_value = None
        mock_instance.load.return_value = None
        mock_instance.query.return_value = [
            {
                "title": "Mock Result",
                "content": "Mock content for testing",
                "source": "test",
                "score": 0.95,
            }
        ]
        mock_class.from_dict.return_value = mock_instance
        mock_class.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_redis_client():
    """Mock Redis async client."""
    with patch("redis_sre_agent.core.redis.Redis") as mock_class:
        mock_instance = AsyncMock()
        mock_instance.ping.return_value = True
        mock_instance.hset.return_value = 1
        mock_instance.expire.return_value = True
        mock_instance.get.return_value = None
        mock_instance.set.return_value = True
        mock_instance.aclose.return_value = None
        mock_class.from_url.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_docket():
    """Mock Docket task queue."""
    with patch("docket.Docket") as mock_class:
        mock_instance = AsyncMock()
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=None)
        mock_instance.register = AsyncMock()
        mock_instance.workers.return_value = []
        mock_class.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def app_with_mocks():
    """FastAPI app with all dependencies mocked."""
    # Don't override OPENAI_API_KEY if it's already set
    app_test_env = {
        "REDIS_URL": "redis://localhost:6379/0",
        "APP_NAME": "Redis SRE Agent Test",
        "DEBUG": "true",
    }

    if not os.environ.get("OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY") == "":
        app_test_env["OPENAI_API_KEY"] = "test-openai-key"

    os.environ.update(app_test_env)

    # Create async mock for initialize_redis_infrastructure
    async def mock_initialize():
        return {"redis": True, "indices": True}

    # Create async mock for register_sre_tasks
    async def mock_register():
        pass

    with (
        patch("redis_sre_agent.core.redis.Redis") as mock_redis,
        patch("redis_sre_agent.core.redis.OpenAITextVectorizer") as mock_vectorizer,
        patch("redis_sre_agent.core.redis.AsyncSearchIndex") as mock_index,
        patch("redis_sre_agent.core.docket_tasks.test_task_system", return_value=True),
        patch(
            "redis_sre_agent.core.redis.initialize_redis_infrastructure",
            side_effect=mock_initialize,
        ),
        patch("redis_sre_agent.core.docket_tasks.register_sre_tasks", side_effect=mock_register),
        patch("redis_sre_agent.core.redis.cleanup_redis_connections", new_callable=AsyncMock),
    ):
        # Configure mocks
        mock_redis_instance = AsyncMock()
        mock_redis_instance.ping.return_value = True
        mock_redis_instance.aclose.return_value = None
        mock_redis.from_url.return_value = mock_redis_instance

        mock_vectorizer_instance = Mock()
        mock_vectorizer.return_value = mock_vectorizer_instance

        mock_index_instance = AsyncMock()
        mock_index_instance.exists.return_value = True
        mock_index_instance.create.return_value = None
        mock_index.from_dict.return_value = mock_index_instance

        from redis_sre_agent.api.app import app

        yield app


@pytest.fixture
def test_client(app_with_mocks):
    """Test client for the FastAPI app."""
    return TestClient(app_with_mocks)


@pytest_asyncio.fixture
async def async_test_client(app_with_mocks):
    """Async test client for the FastAPI app."""
    async with AsyncClient(
        transport=ASGITransport(app=app_with_mocks), base_url="http://test"
    ) as client:
        yield client


@pytest.fixture
def sample_task_result():
    """Sample task result for testing."""
    return {
        "task_id": "01234567890123456789012345",
        "status": "completed",
        "timestamp": "2025-08-19T21:00:00+00:00",
        "results": {"analysis": "test result"},
    }


@pytest.fixture(scope="session")
def worker_id(request):
    """
    Get the worker ID for the current test.

    In pytest-xdist, the config has "workerid" in workerinput.
    This fixture abstracts that logic to provide a consistent worker_id
    across all tests.
    """
    workerinput = getattr(request.config, "workerinput", {})
    return workerinput.get("workerid", "master")


@pytest.fixture(scope="session")
def redis_container(worker_id):
    """
    If using xdist, create a unique Compose project for each xdist worker by
    setting COMPOSE_PROJECT_NAME. That prevents collisions on container/volume
    names.

    Uses docker-compose.integration.yml which only includes Redis service
    (no app services that need building).
    """
    # Set the Compose project name so containers do not clash across workers
    os.environ["COMPOSE_PROJECT_NAME"] = f"redis_test_{worker_id}"
    os.environ.setdefault("REDIS_IMAGE", "redis/redis-stack-server:latest")

    compose = DockerCompose(
        context="./",
        compose_file_name="docker-compose.integration.yml",
        pull=True,
    )
    compose.start()

    # Get the Redis URL and set it in environment
    host, port = compose.get_service_host_and_port("redis", 6379)
    url = f"redis://{host}:{port}"

    # Set REDIS_URL environment variable so get_redis_client() uses testcontainers
    old_redis_url = os.environ.get("REDIS_URL")
    os.environ["REDIS_URL"] = url

    # Reload settings to pick up the new REDIS_URL
    import redis_sre_agent.core.config as config_module
    from redis_sre_agent.core.config import Settings

    config_module.settings = Settings()

    # Also clear any Redis connection pools that might be cached
    # Force reload of modules to pick up new settings
    import importlib

    from redis_sre_agent.core import docket_tasks as tasks_module
    from redis_sre_agent.core import redis as redis_module

    importlib.reload(redis_module)
    importlib.reload(tasks_module)

    # Create indices in the test Redis container
    import asyncio
    from pathlib import Path

    from redis_sre_agent.core.redis import create_indices
    from redis_sre_agent.pipelines.ingestion.processor import IngestionPipeline
    from redis_sre_agent.pipelines.scraper.base import ArtifactStorage

    asyncio.run(create_indices())

    # Ingest knowledge base artifacts if available
    artifacts_path = Path("./artifacts")
    if artifacts_path.exists():
        # Find the most recent batch
        batch_dirs = sorted([d for d in artifacts_path.iterdir() if d.is_dir()], reverse=True)
        if batch_dirs:
            latest_batch = batch_dirs[0].name
            try:
                storage = ArtifactStorage(str(artifacts_path))
                pipeline = IngestionPipeline(storage)
                asyncio.run(pipeline.ingest_batch(latest_batch))
                print(f"✅ Ingested knowledge base batch: {latest_batch}")
            except Exception as e:
                print(f"⚠️  Failed to ingest knowledge base: {e}")
                # Don't fail the fixture - tests can skip if knowledge base is needed

    yield compose

    # Restore original REDIS_URL
    if old_redis_url:
        os.environ["REDIS_URL"] = old_redis_url
    else:
        os.environ.pop("REDIS_URL", None)

    compose.stop()


@pytest.fixture(scope="session")
def redis_url(redis_container):
    """
    Use the `DockerCompose` fixture to get host/port of the 'redis' service
    on container port 6379 (mapped to an ephemeral port on the host).
    """
    host, port = redis_container.get_service_host_and_port("redis", 6379)
    return f"redis://{host}:{port}"


@pytest_asyncio.fixture()
async def async_redis_client(redis_url):
    client = AsyncRedis.from_url(redis_url, decode_responses=False)

    # Flush database to ensure clean state for this test
    await client.flushdb()

    yield client

    # Cleanup
    await client.aclose()


@pytest.fixture
def mock_prometheus_response():
    """Mock Prometheus API response."""
    return {
        "status": "success",
        "data": {
            "resultType": "vector",
            "result": [
                {
                    "metric": {"__name__": "cpu_usage", "instance": "server1"},
                    "value": [1692470400, "75.5"],
                }
            ],
        },
    }


@pytest.fixture
def mock_health_check_response():
    """Mock service health check response."""
    return [
        {
            "endpoint": "http://service1/health",
            "status": "healthy",
            "response_time_ms": 45,
            "status_code": 200,
            "timestamp": "2025-08-19T21:00:00+00:00",
        },
        {
            "endpoint": "http://service2/health",
            "status": "unhealthy",
            "response_time_ms": 5000,
            "status_code": 503,
            "timestamp": "2025-08-19T21:00:00+00:00",
        },
    ]
