"""
Test configuration and fixtures for Redis SRE Agent.
"""

import os
from typing import Any, Dict, List
from unittest.mock import AsyncMock, Mock, patch

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis as AsyncRedis
from testcontainers.redis import RedisContainer

# Test environment variables
os.environ.update(
    {
        "REDIS_URL": "redis://localhost:6379/0",
        "OPENAI_API_KEY": "test-openai-key",
        "APP_NAME": "Redis SRE Agent Test",
        "DEBUG": "true",
    }
)


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
    os.environ.update(
        {
            "REDIS_URL": "redis://localhost:6379/0",
            "OPENAI_API_KEY": "test-openai-key",
            "APP_NAME": "Redis SRE Agent Test",
            "DEBUG": "true",
        }
    )

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
    redis_url = container.get_connection_url()
    os.environ["REDIS_URL"] = redis_url

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

    redis_url = redis_container.get_connection_url()
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
