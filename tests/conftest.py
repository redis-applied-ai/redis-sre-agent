"""
Test configuration and fixtures for Redis SRE Agent.
"""

import os
from typing import TYPE_CHECKING, Any, Dict, List
from unittest.mock import AsyncMock, Mock, patch

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from testcontainers.compose import DockerCompose

if TYPE_CHECKING:
    from redis_sre_agent.core.config import Settings


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
            "redis_sre_agent.core.redis.initialize_redis",
            side_effect=mock_initialize,
        ),
        patch("redis_sre_agent.core.docket_tasks.register_sre_tasks", side_effect=mock_register),
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
    # Note: We intentionally do NOT start docker-compose here.
    # Integration tests use testcontainers via the redis_container fixture,
    # which manages Redis lifecycle automatically with docker-compose.integration.yml.


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

# REDIS_URL is not defaulted here; tests rely on Testcontainers-provided Redis via the use_redis_testcontainer autouse fixture

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
            "redis_sre_agent.core.redis.initialize_redis",
            side_effect=mock_initialize,
        ),
        patch("redis_sre_agent.core.docket_tasks.register_sre_tasks", side_effect=mock_register),
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


class RedisContainerInfo:
    """Container for Redis test infrastructure components.

    This class holds the Docker Compose instance, Redis URL, and test Settings
    object for integration tests. Using dependency injection via the test_settings
    fixture avoids modifying environment variables or reloading modules.
    """

    def __init__(self, compose: DockerCompose, url: str, settings: "Settings"):
        self.compose = compose
        self.url = url
        self.settings = settings

    def get_service_host_and_port(self, service: str, port: int):
        """Delegate to compose for backwards compatibility."""
        return self.compose.get_service_host_and_port(service, port)


@pytest.fixture(scope="session")
def redis_container(worker_id):
    """
    Start a Redis container for integration tests.

    Uses docker-compose.integration.yml which only includes Redis service
    (no app services that need building).

    This fixture uses dependency injection instead of modifying environment
    variables. It creates a test Settings object configured with the container's
    Redis URL, which can be passed to functions via the `config` parameter.

    Returns:
        RedisContainerInfo with compose, url, and settings for dependency injection.
    """
    import asyncio
    from pathlib import Path

    from pydantic import SecretStr

    from redis_sre_agent.core.config import Settings
    from redis_sre_agent.core.redis import create_indices

    # Docker Compose environment variables - these only affect docker-compose,
    # not application code. We still need to set these for container isolation.
    compose_env = {
        "COMPOSE_PROJECT_NAME": f"redis_test_{worker_id}",
        "REDIS_IMAGE": os.environ.get("REDIS_IMAGE", "redis/redis-stack-server:latest"),
    }

    # Save old values for cleanup
    old_compose_env = {key: os.environ.get(key) for key in compose_env}

    # Set compose-specific env vars (only affects docker-compose process)
    for key, value in compose_env.items():
        os.environ[key] = value

    compose = DockerCompose(
        context="./",
        compose_file_name="docker-compose.integration.yml",
        pull=True,
    )

    try:
        compose.start()

        # Get the Redis URL from the container
        host, port = compose.get_service_host_and_port("redis", 6379)
        url = f"redis://{host}:{port}"

        # Create a test Settings object with the container's Redis URL.
        # This uses dependency injection instead of modifying os.environ["REDIS_URL"]
        # or reloading modules. Functions in redis_sre_agent.core.redis now accept
        # an optional `config` parameter for this purpose.
        test_settings = Settings(
            redis_url=SecretStr(url),
            # Other settings are inherited from environment/defaults
        )

        # Create indices using dependency injection (no module reload needed!)
        asyncio.run(create_indices(config=test_settings))

        # Ingest knowledge base artifacts if available
        artifacts_path = Path("./artifacts")
        if artifacts_path.exists():
            # Find the most recent batch
            batch_dirs = sorted([d for d in artifacts_path.iterdir() if d.is_dir()], reverse=True)
            if batch_dirs:
                latest_batch = batch_dirs[0].name
                try:
                    from redis_sre_agent.pipelines.ingestion.processor import IngestionPipeline
                    from redis_sre_agent.pipelines.scraper.base import ArtifactStorage

                    storage = ArtifactStorage(str(artifacts_path))
                    pipeline = IngestionPipeline(storage)
                    # Note: IngestionPipeline doesn't yet support config injection.
                    # For now, we skip ingestion in tests or it uses global settings.
                    # TODO: Add config parameter to IngestionPipeline for full DI support.
                    asyncio.run(pipeline.ingest_batch(latest_batch))
                    print(f"✅ Ingested knowledge base batch: {latest_batch}")
                except Exception as e:
                    print(f"⚠️  Failed to ingest knowledge base: {e}")
                    # Don't fail the fixture - tests can skip if knowledge base is needed

        # Return container info with settings for dependency injection
        yield RedisContainerInfo(compose=compose, url=url, settings=test_settings)

    finally:
        # Restore compose env vars
        for key, old_value in old_compose_env.items():
            if old_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old_value

        compose.stop()


@pytest.fixture(scope="session")
def test_settings(redis_container):
    """Get the test Settings object configured for the Redis container.

    This fixture provides a Settings object with the correct Redis URL for
    the test container. Pass this to functions that accept a `config` parameter
    to use the test Redis instance without modifying environment variables.

    Example:
        async def test_something(test_settings):
            client = get_redis_client(config=test_settings)
            status = await initialize_redis(config=test_settings)
    """
    return redis_container.settings


@pytest.fixture(scope="session")
def redis_url(redis_container):
    """
    Get the Redis URL for the test container.

    Use this when you need just the URL string. For full dependency injection,
    prefer using the `test_settings` fixture instead.
    """
    return redis_container.url


@pytest_asyncio.fixture()
async def async_redis_client(test_settings):
    """Async Redis client connected to the test container.

    Uses dependency injection via test_settings instead of relying on
    environment variables.
    """
    from redis_sre_agent.core.redis import get_redis_client

    client = get_redis_client(config=test_settings)

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
