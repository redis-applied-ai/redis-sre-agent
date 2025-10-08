"""Tests for the main FastAPI application."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


class TestAppInitialization:
    """Test application initialization."""

    def test_app_exists(self):
        """Test that the app is created."""
        from redis_sre_agent.api.app import app

        assert app is not None
        assert "Redis SRE Agent" in app.title

    def test_app_has_routers(self):
        """Test that all routers are included."""
        from redis_sre_agent.api.app import app

        # Check that routes exist
        routes = [route.path for route in app.routes]

        # Health and metrics routes
        assert "/health" in routes or any("/health" in r for r in routes)
        assert "/metrics" in routes or any("/metrics" in r for r in routes)

        # API routes
        assert any("/api/v1" in r for r in routes)

    def test_app_debug_mode(self):
        """Test app debug mode setting."""
        from redis_sre_agent.api.app import app
        from redis_sre_agent.core.config import settings

        assert app.debug == settings.debug

    def test_app_version(self):
        """Test app version."""
        from redis_sre_agent.api.app import app

        assert app.version == "0.1.0"


class TestGetAppStartupState:
    """Test get_app_startup_state function."""

    def test_get_startup_state_returns_copy(self):
        """Test that get_app_startup_state returns a copy."""
        from redis_sre_agent.api.app import _app_startup_state, get_app_startup_state

        state = get_app_startup_state()

        # Should be a copy, not the same object
        assert state is not _app_startup_state
        assert isinstance(state, dict)

    def test_get_startup_state_with_data(self):
        """Test getting startup state with data."""
        import redis_sre_agent.api.app as app_module
        from redis_sre_agent.api.app import get_app_startup_state

        # Set some test data
        app_module._app_startup_state = {"redis": "connected", "test": True}

        state = get_app_startup_state()

        assert state["redis"] == "connected"
        assert state["test"] is True


class TestLifespan:
    """Test application lifespan management."""

    @pytest.mark.asyncio
    async def test_lifespan_startup_success(self):
        """Test successful startup."""
        from redis_sre_agent.api.app import app, lifespan

        with patch("redis_sre_agent.api.app.initialize_redis_infrastructure") as mock_init:
            with patch("redis_sre_agent.core.tasks.register_sre_tasks") as mock_register:
                with patch("redis_sre_agent.api.app.cleanup_redis_connections") as mock_cleanup:
                    mock_init.return_value = {"redis": "connected"}
                    mock_register.return_value = None
                    mock_cleanup.return_value = None

                    async with lifespan(app):
                        # During startup
                        pass

                    # Verify startup was called
                    mock_init.assert_called_once()
                    mock_register.assert_called_once()

                    # Verify cleanup was called on shutdown
                    mock_cleanup.assert_called_once()

    @pytest.mark.asyncio
    async def test_lifespan_startup_redis_error(self):
        """Test startup with Redis initialization error."""
        from redis_sre_agent.api.app import app, get_app_startup_state, lifespan

        with patch("redis_sre_agent.api.app.initialize_redis_infrastructure") as mock_init:
            with patch("redis_sre_agent.api.app.cleanup_redis_connections") as mock_cleanup:
                mock_init.side_effect = Exception("Redis connection failed")
                mock_cleanup.return_value = None

                async with lifespan(app):
                    # Should not raise, but store error
                    state = get_app_startup_state()
                    assert "error" in state

                mock_cleanup.assert_called_once()

    @pytest.mark.asyncio
    async def test_lifespan_startup_task_registration_error(self):
        """Test startup with task registration error."""
        from redis_sre_agent.api.app import app, lifespan

        with patch("redis_sre_agent.api.app.initialize_redis_infrastructure") as mock_init:
            with patch("redis_sre_agent.core.tasks.register_sre_tasks") as mock_register:
                with patch("redis_sre_agent.api.app.cleanup_redis_connections") as mock_cleanup:
                    mock_init.return_value = {"redis": "connected"}
                    mock_register.side_effect = Exception("Task registration failed")
                    mock_cleanup.return_value = None

                    async with lifespan(app):
                        # Should not raise, just log warning
                        pass

                    mock_init.assert_called_once()
                    mock_register.assert_called_once()
                    mock_cleanup.assert_called_once()

    @pytest.mark.asyncio
    async def test_lifespan_shutdown_error(self):
        """Test shutdown with cleanup error."""
        from redis_sre_agent.api.app import app, lifespan

        with patch("redis_sre_agent.api.app.initialize_redis_infrastructure") as mock_init:
            with patch("redis_sre_agent.core.tasks.register_sre_tasks") as mock_register:
                with patch("redis_sre_agent.api.app.cleanup_redis_connections") as mock_cleanup:
                    mock_init.return_value = {"redis": "connected"}
                    mock_register.return_value = None
                    mock_cleanup.side_effect = Exception("Cleanup failed")

                    async with lifespan(app):
                        # Should not raise during shutdown
                        pass

                    mock_cleanup.assert_called_once()


class TestMiddleware:
    """Test middleware setup."""

    def test_middleware_is_setup(self):
        """Test that middleware is configured."""
        from redis_sre_agent.api.app import app

        # Check that middleware is present
        assert len(app.user_middleware) > 0 or len(app.middleware_stack) is not None


class TestRouterInclusion:
    """Test that all routers are properly included."""

    def test_health_router_included(self):
        """Test health router is included."""
        from redis_sre_agent.api.app import app

        routes = [route.path for route in app.routes]
        assert any("health" in r for r in routes)

    def test_metrics_router_included(self):
        """Test metrics router is included."""
        from redis_sre_agent.api.app import app

        routes = [route.path for route in app.routes]
        assert any("metrics" in r for r in routes)

    def test_agent_router_included(self):
        """Test agent router is included with prefix."""
        from redis_sre_agent.api.app import app

        routes = [route.path for route in app.routes]
        # Agent routes should have /api/v1 prefix
        assert any("/api/v1" in r and "agent" in r.lower() for r in routes)

    def test_instances_router_included(self):
        """Test instances router is included with prefix."""
        from redis_sre_agent.api.app import app

        routes = [route.path for route in app.routes]
        assert any("/api/v1" in r and "instances" in r for r in routes)

    def test_knowledge_router_included(self):
        """Test knowledge router is included."""
        from redis_sre_agent.api.app import app

        routes = [route.path for route in app.routes]
        assert any("knowledge" in r for r in routes)

    def test_tasks_router_included(self):
        """Test tasks router is included with prefix."""
        from redis_sre_agent.api.app import app

        routes = [route.path for route in app.routes]
        assert any("/api/v1" in r and ("tasks" in r or "triage" in r) for r in routes)

    def test_websockets_router_included(self):
        """Test websockets router is included with prefix."""
        from redis_sre_agent.api.app import app

        routes = [route.path for route in app.routes]
        assert any("/api/v1" in r and "ws" in r for r in routes)


class TestAppConfiguration:
    """Test application configuration."""

    def test_app_title_from_settings(self):
        """Test app title comes from settings."""
        from redis_sre_agent.api.app import app
        from redis_sre_agent.core.config import settings

        assert app.title == settings.app_name

    def test_app_has_description(self):
        """Test app has description."""
        from redis_sre_agent.api.app import app

        assert app.description is not None
        assert "SRE" in app.description or "Redis" in app.description

    def test_app_has_lifespan(self):
        """Test app has lifespan configured."""
        from redis_sre_agent.api.app import app

        # The app should have a lifespan context manager
        assert hasattr(app, "router")
        assert app.router.lifespan_context is not None


class TestAppEndpoints:
    """Test that app responds to basic endpoints."""

    def test_health_endpoint_exists(self):
        """Test health endpoint is accessible."""
        from redis_sre_agent.api.app import app

        client = TestClient(app)
        response = client.get("/health")

        # Should get a response (may be 200 or error depending on Redis)
        assert response.status_code in [200, 500, 503]

    def test_metrics_endpoint_exists(self):
        """Test metrics endpoint is accessible."""
        from redis_sre_agent.api.app import app

        client = TestClient(app)
        response = client.get("/metrics")

        # Should get a response
        assert response.status_code in [200, 500]

    def test_openapi_docs_exists(self):
        """Test OpenAPI docs are available."""
        from redis_sre_agent.api.app import app

        client = TestClient(app)
        response = client.get("/docs")

        # Should redirect or return docs
        assert response.status_code in [200, 307]

    def test_openapi_json_exists(self):
        """Test OpenAPI JSON schema is available."""
        from redis_sre_agent.api.app import app

        client = TestClient(app)
        response = client.get("/openapi.json")

        assert response.status_code == 200
        data = response.json()
        assert "openapi" in data
        assert "info" in data
