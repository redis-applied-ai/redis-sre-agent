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

        with (
            patch("redis_sre_agent.api.instances.get_instances_from_redis") as mock_get,
            patch("redis_sre_agent.api.instances.save_instances_to_redis") as mock_save,
        ):
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

        RedisInstance(
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

        with (
            patch("redis_sre_agent.api.instances.get_instances_from_redis") as mock_get,
            patch("redis_sre_agent.api.instances.save_instances_to_redis") as mock_save,
        ):
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
        with (
            patch("redis_sre_agent.api.instances.get_instances_from_redis") as mock_get,
            patch("redis_sre_agent.api.instances.save_instances_to_redis") as mock_save,
        ):
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
        with (
            patch("redis_sre_agent.api.instances.get_instances_from_redis") as mock_get,
            patch("redis_sre_agent.core.redis.test_redis_connection") as mock_test,
        ):
            mock_get.return_value = [sample_instance]
            mock_test.return_value = True

            response = client.post("/api/v1/instances/test-instance-123/test-connection")

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert "Successfully connected" in data["message"]

    @pytest.mark.asyncio
    async def test_test_connection_failure(self, client):
        """Test connection test failure with bad URL."""
        from redis_sre_agent.api.instances import RedisInstance

        # Create instance with invalid connection URL
        bad_instance = RedisInstance(
            id="test-instance-123",
            name="bad-redis",
            connection_url="redis://invalid-host:9999",  # Invalid host
            environment="testing",
            usage="cache",
            description="Test instance with bad URL",
            created_by="user",
        )

        with patch("redis_sre_agent.api.instances.get_instances_from_redis") as mock_get:
            mock_get.return_value = [bad_instance]

            response = client.post("/api/v1/instances/test-instance-123/test-connection")

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is False
            assert "Failed to connect" in data["message"]


class TestInstancesAPIErrorHandling:
    """Test error handling in instances API."""

    def test_list_instances_redis_error(self, client):
        """Test list instances when Redis fails."""
        with patch("redis_sre_agent.api.instances.get_instances_from_redis") as mock_get:
            mock_get.side_effect = Exception("Redis connection failed")

            response = client.get("/api/v1/instances")

            assert response.status_code == 500
            assert "Failed to retrieve instances" in response.json()["detail"]

    def test_update_instance_redis_error(self, client):
        """Test update instance when Redis fails."""
        with patch("redis_sre_agent.api.instances.get_instances_from_redis") as mock_get:
            mock_get.side_effect = Exception("Redis error")

            response = client.put(
                "/api/v1/instances/test-id",
                json={"name": "updated-name"},
            )

            assert response.status_code == 500
            assert "Failed to update instance" in response.json()["detail"]

    def test_delete_instance_redis_error(self, client):
        """Test delete instance when Redis fails."""
        with patch("redis_sre_agent.api.instances.get_instances_from_redis") as mock_get:
            mock_get.side_effect = Exception("Redis error")

            response = client.delete("/api/v1/instances/test-id")

            assert response.status_code == 500
            assert "Failed to delete instance" in response.json()["detail"]

    def test_get_instance_redis_error(self, client):
        """Test get instance when Redis fails."""
        with patch("redis_sre_agent.api.instances.get_instances_from_redis") as mock_get:
            mock_get.side_effect = Exception("Redis error")

            response = client.get("/api/v1/instances/test-id")

            assert response.status_code == 500
            assert "Failed to retrieve instance" in response.json()["detail"]


class TestConnectionTesting:
    """Test connection testing endpoints."""

    def test_test_connection_url_success(self, client):
        """Test connection URL testing with valid URL."""

        with patch("redis_sre_agent.core.redis.test_redis_connection") as mock_test:
            mock_test.return_value = True

            response = client.post(
                "/api/v1/instances/test-connection-url",
                json={"connection_url": "redis://localhost:6379"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert "host" in data
            assert "port" in data

    def test_test_connection_url_failure(self, client):
        """Test connection URL testing with invalid URL."""
        with patch("redis_sre_agent.core.redis.test_redis_connection") as mock_test:
            mock_test.return_value = False

            response = client.post(
                "/api/v1/instances/test-connection-url",
                json={"connection_url": "redis://invalid:9999"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is False
            assert "message" in data

    def test_test_instance_connection_success(self, client):
        """Test instance connection testing with valid instance."""
        from redis_sre_agent.api.instances import RedisInstance

        mock_instance = RedisInstance(
            id="test-id",
            name="test-redis",
            connection_url="redis://localhost:6379",
            environment="testing",
            usage="cache",
            description="Test instance",
            created_by="user",
        )

        with patch("redis_sre_agent.api.instances.get_instances_from_redis") as mock_get:
            mock_get.return_value = [mock_instance]

            with patch("redis_sre_agent.core.redis.test_redis_connection") as mock_test:
                mock_test.return_value = True

                response = client.post("/api/v1/instances/test-id/test-connection")

                assert response.status_code == 200
                data = response.json()
                assert data["success"] is True
                assert data["instance_id"] == "test-id"

    def test_test_instance_connection_not_found(self, client):
        """Test instance connection testing with non-existent instance."""
        with patch("redis_sre_agent.api.instances.get_instances_from_redis") as mock_get:
            mock_get.return_value = []

            response = client.post("/api/v1/instances/test-id/test-connection")

            assert response.status_code == 404
            assert "test-id" in response.json()["detail"]
            assert "not found" in response.json()["detail"].lower()


class TestRedisStorageHelpers:
    """Test Redis storage helper functions."""

    @pytest.mark.asyncio
    async def test_get_instances_from_redis_empty(self):
        """Test getting instances when Redis returns None."""
        from redis_sre_agent.api.instances import get_instances_from_redis

        with patch("redis_sre_agent.api.instances.get_redis_client") as mock_client:
            mock_redis = AsyncMock()
            mock_redis.get = AsyncMock(return_value=None)
            mock_client.return_value = mock_redis

            result = await get_instances_from_redis()

            assert result == []

    @pytest.mark.asyncio
    async def test_get_instances_from_redis_error(self):
        """Test getting instances when Redis raises an error."""
        from redis_sre_agent.api.instances import get_instances_from_redis

        with patch("redis_sre_agent.api.instances.get_redis_client") as mock_client:
            mock_redis = AsyncMock()
            mock_redis.get = AsyncMock(side_effect=Exception("Redis error"))
            mock_client.return_value = mock_redis

            result = await get_instances_from_redis()

            assert result == []

    @pytest.mark.asyncio
    async def test_get_instances_from_redis_json_error(self):
        """Test getting instances when JSON parsing fails."""
        from redis_sre_agent.api.instances import get_instances_from_redis

        with patch("redis_sre_agent.api.instances.get_redis_client") as mock_client:
            mock_redis = AsyncMock()
            mock_redis.get = AsyncMock(return_value="invalid json")
            mock_client.return_value = mock_redis

            result = await get_instances_from_redis()

            assert result == []

    @pytest.mark.asyncio
    async def test_save_instances_to_redis_success(self):
        """Test saving instances successfully."""
        from redis_sre_agent.api.instances import RedisInstance, save_instances_to_redis

        instance = RedisInstance(
            id="test-id",
            name="test-redis",
            connection_url="redis://localhost:6379",
            environment="testing",
            usage="cache",
            description="Test instance",
            created_by="user",
        )

        with patch("redis_sre_agent.api.instances.get_redis_client") as mock_client:
            mock_redis = AsyncMock()
            mock_redis.set = AsyncMock(return_value=True)
            mock_client.return_value = mock_redis

            result = await save_instances_to_redis([instance])

            assert result is True
            mock_redis.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_save_instances_to_redis_error(self):
        """Test saving instances when Redis raises an error."""
        from redis_sre_agent.api.instances import RedisInstance, save_instances_to_redis

        instance = RedisInstance(
            id="test-id",
            name="test-redis",
            connection_url="redis://localhost:6379",
            environment="testing",
            usage="cache",
            description="Test instance",
            created_by="user",
        )

        with patch("redis_sre_agent.api.instances.get_redis_client") as mock_client:
            mock_redis = AsyncMock()
            mock_redis.set = AsyncMock(side_effect=Exception("Redis error"))
            mock_client.return_value = mock_redis

            result = await save_instances_to_redis([instance])

            assert result is False


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

        with (
            patch("redis_sre_agent.api.instances.get_instances_from_redis") as mock_get,
            patch("redis_sre_agent.api.instances.save_instances_to_redis") as mock_save,
        ):
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

        with (
            patch("redis_sre_agent.api.instances.get_instances_from_redis") as mock_get,
            patch("redis_sre_agent.api.instances.save_instances_to_redis") as mock_save,
        ):
            mock_get.return_value = []
            mock_save.return_value = True

            response = client.post("/api/v1/instances", json=invalid_data)

            # Should return validation error
            assert response.status_code == 422

    def test_create_instance_with_created_by_agent(self, client):
        """Test instance creation with created_by='agent'."""
        create_data = {
            "name": "Agent Created Instance",
            "connection_url": "redis://dynamic:6379",
            "environment": "production",
            "usage": "cache",
            "description": "Dynamically created by agent",
            "created_by": "agent",
        }

        with (
            patch("redis_sre_agent.api.instances.get_instances_from_redis") as mock_get,
            patch("redis_sre_agent.api.instances.save_instances_to_redis") as mock_save,
        ):
            mock_get.return_value = []
            mock_save.return_value = True

            response = client.post("/api/v1/instances", json=create_data)

            assert response.status_code == 201
            data = response.json()
            assert data["created_by"] == "agent"

    def test_create_instance_with_user_id(self, client):
        """Test instance creation with user_id."""
        create_data = {
            "name": "User Instance",
            "connection_url": "redis://user-redis:6379",
            "environment": "production",
            "usage": "cache",
            "description": "User's Redis instance",
            "user_id": "user-123",
        }

        with (
            patch("redis_sre_agent.api.instances.get_instances_from_redis") as mock_get,
            patch("redis_sre_agent.api.instances.save_instances_to_redis") as mock_save,
        ):
            mock_get.return_value = []
            mock_save.return_value = True

            response = client.post("/api/v1/instances", json=create_data)

            assert response.status_code == 201
            data = response.json()
            assert data["user_id"] == "user-123"
