"""Unit tests for instances API endpoints."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from redis_sre_agent.api.app import app


@pytest.fixture
def client():
    """Test client for FastAPI app."""
    return TestClient(app)


@pytest.fixture
def sample_instance():
    """Sample Redis instance data."""
    from redis_sre_agent.api.instances import RedisInstance
    return RedisInstance(
        id="test-instance-123",
        name="Test Redis Instance",
        connection_url="redis://localhost:6379",
        environment="test",
        usage="cache",
        description="Test Redis instance",
        status="active",
        created_at="2025-09-19T10:00:00Z",
        updated_at="2025-09-19T10:00:00Z",
    )


class TestInstancesAPI:
    """Test instances API endpoints."""

    def test_list_instances_success(self, client, sample_instance):
        """Test successful instance listing."""
        with patch("redis_sre_agent.api.instances.get_instances_from_redis") as mock_get:
            mock_get.return_value = [sample_instance]

            response = client.get("/api/v1/instances")

            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1
            assert data[0]["id"] == "test-instance-123"

    def test_list_instances_empty(self, client):
        """Test instance listing when no instances exist."""
        with patch("redis_sre_agent.api.instances.get_instances_from_redis") as mock_get:
            mock_get.return_value = []

            response = client.get("/api/v1/instances")

            assert response.status_code == 200
            data = response.json()
            assert len(data) == 0

    def test_get_instance_success(self, client, sample_instance):
        """Test successful instance retrieval."""
        with patch("redis_sre_agent.api.instances.get_instances_from_redis") as mock_get:
            mock_get.return_value = [sample_instance]

            response = client.get("/api/v1/instances/test-instance-123")

            assert response.status_code == 200
            data = response.json()
            assert data["id"] == "test-instance-123"
            assert data["name"] == "Test Redis Instance"

    def test_get_instance_not_found(self, client):
        """Test instance retrieval when not found."""
        with patch("redis_sre_agent.api.instances.get_instances_from_redis") as mock_get:
            mock_get.return_value = []

            response = client.get("/api/v1/instances/nonexistent")

            assert response.status_code == 404

    def test_create_instance_success(self, client, sample_instance):
        """Test successful instance creation."""
        create_data = {
            "name": "New Redis Instance",
            "connection_url": "redis://localhost:6380",
            "environment": "development",
            "usage": "session_store",
            "description": "New test instance",
        }

        with patch("redis_sre_agent.api.instances.get_instances_from_redis") as mock_get, \
             patch("redis_sre_agent.api.instances.save_instances_to_redis") as mock_save:
            mock_get.return_value = []  # No existing instances
            mock_save.return_value = True

            response = client.post("/api/v1/instances", json=create_data)

            assert response.status_code == 201
            data = response.json()
            assert data["name"] == "New Redis Instance"

    def test_create_instance_missing_fields(self, client):
        """Test instance creation with missing required fields."""
        incomplete_data = {
            "name": "Incomplete Instance",
            # Missing required fields
        }

        response = client.post("/api/v1/instances", json=incomplete_data)

        assert response.status_code == 422  # Validation error

    def test_update_instance_success(self, client, sample_instance):
        """Test successful instance update."""
        update_data = {
            "description": "Updated description",
            "status": "maintenance",
        }

        # Create updated instance with new values
        from redis_sre_agent.api.instances import RedisInstance
        updated_instance = RedisInstance(
            id=sample_instance.id,
            name=sample_instance.name,
            connection_url=sample_instance.connection_url,
            environment=sample_instance.environment,
            usage=sample_instance.usage,
            description=update_data["description"],
            status=update_data["status"],
            created_at=sample_instance.created_at,
            updated_at="2025-09-19T11:00:00Z",
        )

        with patch("redis_sre_agent.api.instances.get_instances_from_redis") as mock_get, \
             patch("redis_sre_agent.api.instances.save_instances_to_redis") as mock_save:
            mock_get.return_value = [sample_instance]
            mock_save.return_value = True

            response = client.put("/api/v1/instances/test-instance-123", json=update_data)

            assert response.status_code == 200
            data = response.json()
            assert data["description"] == "Updated description"
            assert data["status"] == "maintenance"

    def test_update_instance_not_found(self, client):
        """Test instance update when instance not found."""
        update_data = {"description": "Updated description"}

        with patch("redis_sre_agent.api.instances.get_instances_from_redis") as mock_get:
            mock_get.return_value = []  # No instances found

            response = client.put("/api/v1/instances/nonexistent", json=update_data)

            assert response.status_code == 404

    def test_delete_instance_success(self, client, sample_instance):
        """Test successful instance deletion."""
        with patch("redis_sre_agent.api.instances.get_instances_from_redis") as mock_get, \
             patch("redis_sre_agent.api.instances.save_instances_to_redis") as mock_save:
            mock_get.return_value = [sample_instance]
            mock_save.return_value = True

            response = client.delete("/api/v1/instances/test-instance-123")

            assert response.status_code == 200
            data = response.json()
            assert "message" in data

    def test_delete_instance_not_found(self, client):
        """Test instance deletion when instance not found."""
        with patch("redis_sre_agent.api.instances.get_instances_from_redis") as mock_get:
            mock_get.return_value = []  # No instances found

            response = client.delete("/api/v1/instances/nonexistent")

            assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_test_connection_success(self, client, sample_instance):
        """Test successful connection test."""
        with patch("redis_sre_agent.api.instances.get_instances_from_redis") as mock_get, \
             patch("redis.asyncio.from_url") as mock_redis:
            mock_get.return_value = [sample_instance]

            # Mock Redis client
            mock_client = AsyncMock()
            mock_client.ping.return_value = True
            mock_redis.return_value = mock_client

            response = client.post("/api/v1/instances/test-instance-123/test-connection")

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert "Successfully connected" in data["message"]

    @pytest.mark.asyncio
    async def test_test_connection_failure(self, client, sample_instance):
        """Test connection test failure."""
        with patch("redis_sre_agent.api.instances.get_instances_from_redis") as mock_get, \
             patch("redis.asyncio.from_url") as mock_redis:
            mock_get.return_value = [sample_instance]

            # Mock Redis client that fails to connect
            mock_client = AsyncMock()
            mock_client.ping.side_effect = Exception("Connection timeout")
            mock_redis.return_value = mock_client

            response = client.post("/api/v1/instances/test-instance-123/test-connection")

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is False
            assert "timeout" in data["message"]


class TestInstanceValidation:
    """Test instance data validation."""

    def test_create_instance_invalid_url(self, client):
        """Test instance creation with invalid Redis URL."""
        invalid_data = {
            "name": "Invalid Instance",
            "connection_url": "not-a-valid-url",
            "environment": "test",
            "usage": "cache",
            "description": "Invalid URL test",
        }

        with patch("redis_sre_agent.api.instances.get_instances_from_redis") as mock_get, \
             patch("redis_sre_agent.api.instances.save_instances_to_redis") as mock_save:
            mock_get.return_value = []
            mock_save.return_value = True

            response = client.post("/api/v1/instances", json=invalid_data)

            # Should return validation error
            assert response.status_code == 422

    def test_create_instance_invalid_environment(self, client):
        """Test instance creation with invalid environment."""
        invalid_data = {
            "name": "Invalid Environment Instance",
            "connection_url": "redis://localhost:6379",
            "environment": "invalid_env",  # Not in allowed values
            "usage": "cache",
            "description": "Invalid environment test",
        }

        with patch("redis_sre_agent.api.instances.get_instances_from_redis") as mock_get, \
             patch("redis_sre_agent.api.instances.save_instances_to_redis") as mock_save:
            mock_get.return_value = []
            mock_save.return_value = True

            response = client.post("/api/v1/instances", json=invalid_data)

            # Should return validation error
            assert response.status_code == 422
