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
from testcontainers.redis import RedisContainer

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
    # Skip marker for API tests that require OpenAI
    skip_api = pytest.mark.skip(reason="Use --run-api-tests to run tests that make real API calls")

    for item in items:
        # Skip tests that require OpenAI API calls unless --run-api-tests flag is set
        if (
            "openai_integration" in item.keywords or "agent_behavior" in item.keywords
        ) and not config.getoption("--run-api-tests"):
            item.add_marker(skip_api)


# Test environment variables - only set if not already present
test_env = {
    "REDIS_URL": "redis://localhost:6379/0",
    "APP_NAME": "Redis SRE Agent Test",
    "DEBUG": "true",
}

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
    """Mock OpenAI text vectorizer."""
    with patch("redis_sre_agent.core.redis.OpenAITextVectorizer") as mock_class:
        mock_instance = Mock()
        mock_instance.embed_many.return_value = [
            [0.1] * 1536,  # Mock embedding vector
            [0.2] * 1536,
            [0.3] * 1536,
        ]
        mock_class.return_value = mock_instance
        yield mock_instance


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

    with (
        patch("redis_sre_agent.core.redis.Redis") as mock_redis,
        patch("redis_sre_agent.core.redis.OpenAITextVectorizer") as mock_vectorizer,
        patch("redis_sre_agent.core.redis.AsyncSearchIndex") as mock_index,
        patch("redis_sre_agent.core.tasks.test_task_system", return_value=True),
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


@pytest.fixture(scope="session", autouse=True)
def redis_container(request):
    """
    Redis container for integration tests.
    Only created if INTEGRATION_TESTS environment variable is set.
    """
    if not os.environ.get("INTEGRATION_TESTS"):
        yield None
        return

    container = RedisContainer("redis:8-alpine")
    container.start()

    # Update Redis URL for integration tests
    try:
        redis_url = container.get_connection_url()
    except AttributeError:
        # Try alternative method names
        redis_url = f"redis://localhost:{container.get_exposed_port(6379)}/0"

    os.environ["REDIS_URL"] = redis_url
    # Also expose Prometheus URL default for tests when docker-compose is used
    os.environ.setdefault("PROMETHEUS_URL", "http://localhost:9090")

    yield container

    container.stop()


@pytest_asyncio.fixture()
async def async_redis_client(redis_container):
    """
    Real Redis client for integration tests.
    Only available when redis_container is active.
    """
    if not redis_container:
        pytest.skip("Integration tests not enabled")

    # Prefer the REDIS_URL set by the redis_container fixture; fall back to exposed port
    try:
        redis_url = os.environ.get("REDIS_URL")
        if not redis_url:
            # Fallback for older testcontainers APIs without get_connection_url
            redis_url = f"redis://localhost:{redis_container.get_exposed_port(6379)}/0"
    except AttributeError:
        redis_url = f"redis://localhost:{redis_container.get_exposed_port(6379)}/0"

    client = AsyncRedis.from_url(redis_url)
    yield client
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


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset global singletons between tests."""
    # Import and reset Redis singletons
    from redis_sre_agent.core import redis

    redis._redis_client = None
    redis._vectorizer = None
    redis._document_index = None

    yield

    # Clean up after test
    redis._redis_client = None
    redis._vectorizer = None
    redis._document_index = None
