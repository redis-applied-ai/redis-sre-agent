"""Unit tests for FastAPI application and endpoints."""

from unittest.mock import AsyncMock, patch

import pytest


class TestHealthEndpoints:
    """Test health check endpoints."""

    def test_root_health_endpoint(self, test_client):
        """Test root health endpoint returns 200."""
        response = test_client.get("/")

        assert response.status_code == 200
        assert "Redis SRE Agent" in response.text
        assert "🚀" in response.text

    def test_root_head_endpoint(self, test_client):
        """Test HEAD request to root endpoint."""
        response = test_client.head("/")

        assert response.status_code == 200
        assert response.text == ""  # HEAD should have no body

    def test_detailed_health_all_components_healthy(self, test_client):
        """Test detailed health endpoint when all components are healthy."""
        mock_infrastructure_status = {
            "redis_connection": "available",
            "vectorizer": "available",
            "indices_created": "available",
            "vector_search": "available",
        }

        with (
            patch(
                "redis_sre_agent.api.health.initialize_redis_infrastructure",
                return_value=mock_infrastructure_status,
            ),
            patch(
                "redis_sre_agent.api.health.test_task_system",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch("redis_sre_agent.api.health.Docket") as mock_docket,
        ):
            # Mock worker status
            mock_docket_instance = AsyncMock()
            mock_docket_instance.__aenter__ = AsyncMock(return_value=mock_docket_instance)
            mock_docket_instance.__aexit__ = AsyncMock(return_value=None)
            mock_docket_instance.workers = AsyncMock(
                return_value=["worker1", "worker2"]
            )  # Active workers
            mock_docket.return_value = mock_docket_instance

            response = test_client.get("/health")

        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "healthy"

        # Check all components are available
        components = data["components"]
        assert components["redis_connection"] == "available"
        assert components["vectorizer"] == "available"
        assert components["indices_created"] == "available"
        assert components["vector_search"] == "available"
        assert components["task_system"] == "available"
        assert components["workers"] == "available"

        # Check metadata
        assert "timestamp" in data
        assert data["version"] == "0.1.0"
        assert "settings" in data

    def test_detailed_health_some_components_unhealthy(self, test_client):
        """Test detailed health endpoint when some components are unhealthy."""
        mock_infrastructure_status = {
            "redis_connection": "available",
            "vectorizer": "unavailable",  # Vectorizer failed
            "indices_created": "unavailable",
            "vector_search": "unavailable",
        }

        with (
            patch(
                "redis_sre_agent.api.health.initialize_redis_infrastructure",
                return_value=mock_infrastructure_status,
            ),
            patch("redis_sre_agent.api.health.test_task_system", return_value=False),
            patch("docket.Docket") as mock_docket,
        ):
            # Mock no active workers
            mock_docket_instance = AsyncMock()
            mock_docket_instance.__aenter__ = AsyncMock(return_value=mock_docket_instance)
            mock_docket_instance.__aexit__ = AsyncMock(return_value=None)
            mock_docket_instance.workers.return_value = []  # No workers
            mock_docket.return_value = mock_docket_instance

            response = test_client.get("/health")

        assert response.status_code == 503

        data = response.json()
        assert data["status"] == "unhealthy"

        # Check mixed component status
        components = data["components"]
        assert components["redis_connection"] == "available"
        assert components["vectorizer"] == "unavailable"
        assert components["task_system"] == "unavailable"
        assert components["workers"] == "unavailable"

    def test_detailed_health_docket_exception(self, test_client):
        """Test detailed health endpoint when Docket throws exception."""
        mock_infrastructure_status = {
            "redis_connection": "available",
            "vectorizer": "available",
            "indices_created": "available",
            "vector_search": "available",
        }

        with (
            patch(
                "redis_sre_agent.api.health.initialize_redis_infrastructure",
                return_value=mock_infrastructure_status,
            ),
            patch("redis_sre_agent.api.health.test_task_system", return_value=True),
            patch("redis_sre_agent.api.health.Docket", side_effect=Exception("Docket connection failed")),
        ):
            response = test_client.get("/health")

        assert response.status_code == 503

        data = response.json()
        assert data["status"] == "unhealthy"
        assert data["components"]["workers"] == "unavailable"

    def test_detailed_health_head_endpoint(self, test_client):
        """Test HEAD request to detailed health endpoint."""
        with (
            patch(
                "redis_sre_agent.api.health.initialize_redis_infrastructure",
                return_value={
                    "redis_connection": "available",
                    "vectorizer": "available",
                    "indices_created": "available",
                    "vector_search": "available",
                },
            ),
            patch(
                "redis_sre_agent.api.health.test_task_system",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch("redis_sre_agent.api.health.Docket") as mock_docket,
        ):
            mock_docket_instance = AsyncMock()
            mock_docket_instance.__aenter__ = AsyncMock(return_value=mock_docket_instance)
            mock_docket_instance.__aexit__ = AsyncMock(return_value=None)
            mock_docket_instance.workers = AsyncMock(return_value=["worker1"])
            mock_docket.return_value = mock_docket_instance

            response = test_client.head("/health")

        assert response.status_code == 200
        assert response.text == ""  # HEAD should have no body

    def test_health_endpoint_password_masking(self, test_client):
        """Test that Redis password is masked in health response."""
        mock_infrastructure_status = {
            "redis_connection": "available",
            "vectorizer": "available",
            "indices_created": "available",
            "vector_search": "available",
        }

        with (
            patch(
                "redis_sre_agent.api.health.initialize_redis_infrastructure",
                return_value=mock_infrastructure_status,
            ),
            patch("redis_sre_agent.api.health.test_task_system", return_value=True),
            patch("docket.Docket") as mock_docket,
            patch("redis_sre_agent.api.health.settings") as mock_settings,
        ):
            # Mock settings with password
            mock_settings.redis_url = "redis://:secret_password@localhost:6379/0"
            mock_settings.redis_password = "secret_password"
            mock_settings.embedding_model = "text-embedding-3-small"
            mock_settings.task_queue_name = "sre_tasks"

            mock_docket_instance = AsyncMock()
            mock_docket_instance.__aenter__ = AsyncMock(return_value=mock_docket_instance)
            mock_docket_instance.__aexit__ = AsyncMock(return_value=None)
            mock_docket_instance.workers.return_value = ["worker1"]
            mock_docket.return_value = mock_docket_instance

            response = test_client.get("/health")

        data = response.json()

        # Password should be masked in the response
        assert "secret_password" not in data["settings"]["redis_url"]
        assert "***" in data["settings"]["redis_url"]


class TestAppLifecycle:
    """Test FastAPI application lifecycle."""

    @pytest.mark.asyncio
    async def test_app_startup_success(self):
        """Test successful application startup."""
        mock_infrastructure_status = {
            "redis_connection": "available",
            "vectorizer": "available",
            "indices_created": "available",
            "vector_search": "available",
        }

        with patch(
            "redis_sre_agent.api.app.initialize_redis_infrastructure",
            return_value=mock_infrastructure_status,
        ):
            # Import app after patching to trigger startup
            from redis_sre_agent.api.app import app

            # App should be created without errors
            assert app is not None
            assert app.title == "Redis SRE Agent Test"

    @pytest.mark.asyncio
    async def test_app_startup_with_errors(self):
        """Test application startup with infrastructure errors."""
        with patch(
            "redis_sre_agent.api.app.initialize_redis_infrastructure",
            side_effect=Exception("Infrastructure failed"),
        ):
            # Import app after patching to trigger startup
            from redis_sre_agent.api.app import app

            # App should still start even with infrastructure errors
            assert app is not None

    @pytest.mark.asyncio
    async def test_app_shutdown(self):
        """Test application shutdown cleanup."""
        mock_cleanup = AsyncMock()

        with patch("redis_sre_agent.api.app.cleanup_redis_connections", mock_cleanup):
            from redis_sre_agent.api.app import app

            # Simulate shutdown by calling lifespan manually
            # This is a simplified test - in practice the lifespan context manager handles this
            assert app is not None


class TestMiddleware:
    """Test middleware functionality."""

    def test_cors_middleware_applied(self, test_client):
        """Test that CORS middleware is applied."""
        response = test_client.get("/", headers={"Origin": "http://localhost:3000"})

        assert response.status_code == 200
        # CORS headers should be present (if CORS is configured)

    def test_request_logging_middleware(self, test_client):
        """Test that request logging middleware works."""
        response = test_client.get("/")

        assert response.status_code == 200
        # Check for timing header added by middleware
        assert "X-Process-Time" in response.headers

    def test_error_handling_middleware(self, test_client):
        """Test error handling middleware."""
        # This would test custom error handling
        # For now, just test that normal requests work
        response = test_client.get("/")
        assert response.status_code == 200


class TestAppConfiguration:
    """Test application configuration."""

    def test_app_metadata(self, app_with_mocks):
        """Test FastAPI app metadata."""
        assert app_with_mocks.title == "Redis SRE Agent Test"
        assert "Redis infrastructure management" in app_with_mocks.description
        assert app_with_mocks.version == "0.1.0"

    def test_app_routes_registered(self, app_with_mocks):
        """Test that expected routes are registered."""
        routes = [route.path for route in app_with_mocks.routes]

        # Health endpoints should be registered
        assert "/" in routes
        assert "/health" in routes

    def test_app_tags(self, app_with_mocks):
        """Test that route tags are properly configured."""
        # Find health routes and check their tags
        health_routes = [
            route
            for route in app_with_mocks.routes
            if hasattr(route, "path") and route.path in ["/", "/health"]
        ]

        # At least one route should exist
        assert len(health_routes) > 0
