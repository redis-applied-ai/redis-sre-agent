"""Unit tests for clusters API endpoints."""

import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from redis_sre_agent.api.app import app
from redis_sre_agent.core.clusters import ClusterQueryResult, RedisCluster


@pytest.fixture
def client():
    """Test client for FastAPI app."""
    return TestClient(app)


@pytest.fixture
def sample_cluster():
    """Sample Redis cluster data."""
    return RedisCluster(
        id="test-cluster-123",
        name="Test Redis Enterprise Cluster",
        cluster_type="redis_enterprise",
        environment="test",
        description="Test Redis Enterprise cluster",
        admin_url="https://cluster.example.com:9443",
        admin_username="admin@example.com",
        admin_password="cluster-secret",
        status="active",
        created_at="2025-09-19T10:00:00Z",
        updated_at="2025-09-19T10:00:00Z",
    )


class TestClustersAPI:
    """Test clusters API endpoints."""

    def test_list_clusters_success(self, client, sample_cluster):
        """Test successful cluster listing."""
        mock_result = ClusterQueryResult(
            clusters=[sample_cluster],
            total=1,
            limit=100,
            offset=0,
        )

        with patch("redis_sre_agent.core.clusters.query_clusters") as mock_query:
            mock_query.return_value = mock_result

            response = client.get("/api/v1/clusters")

            assert response.status_code == 200
            data = response.json()
            assert data["total"] == 1
            assert len(data["clusters"]) == 1
            assert data["clusters"][0]["id"] == "test-cluster-123"
            assert data["clusters"][0]["admin_password"] == "***"

    def test_get_cluster_success(self, client, sample_cluster):
        """Test successful cluster retrieval."""
        with patch("redis_sre_agent.core.clusters.get_cluster_by_id") as mock_get:
            mock_get.return_value = sample_cluster

            response = client.get("/api/v1/clusters/test-cluster-123")

            assert response.status_code == 200
            data = response.json()
            assert data["id"] == "test-cluster-123"
            assert data["name"] == "Test Redis Enterprise Cluster"
            assert data["admin_password"] == "***"

    def test_get_cluster_not_found(self, client):
        """Test cluster retrieval when not found."""
        with patch("redis_sre_agent.core.clusters.get_cluster_by_id") as mock_get:
            mock_get.return_value = None

            response = client.get("/api/v1/clusters/nonexistent")

            assert response.status_code == 404

    def test_create_cluster_success(self, client):
        """Test successful cluster creation."""
        create_data = {
            "name": "New Enterprise Cluster",
            "cluster_type": "redis_enterprise",
            "environment": "development",
            "description": "New test enterprise cluster",
            "admin_url": "https://new-cluster.example.com:9443",
            "admin_username": "admin@example.com",
            "admin_password": "secret",
        }

        with (
            patch("redis_sre_agent.core.clusters.get_clusters") as mock_get,
            patch("redis_sre_agent.core.clusters.save_clusters") as mock_save,
        ):
            mock_get.return_value = []
            mock_save.return_value = True

            response = client.post("/api/v1/clusters", json=create_data)

            assert response.status_code == 201
            data = response.json()
            assert data["name"] == "New Enterprise Cluster"
            assert data["admin_password"] == "***"

    def test_create_cluster_success_with_env_defaults(self, client):
        """Enterprise create should use REDIS_ENTERPRISE_ADMIN_* defaults."""
        create_data = {
            "name": "New Enterprise Cluster",
            "cluster_type": "redis_enterprise",
            "environment": "development",
            "description": "New test enterprise cluster",
        }

        with (
            patch.dict(
                os.environ,
                {
                    "REDIS_ENTERPRISE_ADMIN_URL": "https://env-cluster.example.com:9443",
                    "REDIS_ENTERPRISE_ADMIN_USERNAME": "env-admin@example.com",
                    "REDIS_ENTERPRISE_ADMIN_PASSWORD": "env-secret",
                },
                clear=False,
            ),
            patch("redis_sre_agent.core.clusters.get_clusters") as mock_get,
            patch("redis_sre_agent.core.clusters.save_clusters") as mock_save,
        ):
            mock_get.return_value = []
            mock_save.return_value = True

            response = client.post("/api/v1/clusters", json=create_data)

            assert response.status_code == 201
            data = response.json()
            assert data["admin_url"] == "https://env-cluster.example.com:9443"
            assert data["admin_username"] == "env-admin@example.com"
            assert data["admin_password"] == "***"

    def test_create_cluster_success_with_mixed_explicit_and_env(self, client):
        """Explicit request values should override env defaults per field."""
        create_data = {
            "name": "New Enterprise Cluster",
            "cluster_type": "redis_enterprise",
            "environment": "development",
            "description": "New test enterprise cluster",
            "admin_url": "https://explicit-cluster.example.com:9443",
        }

        with (
            patch.dict(
                os.environ,
                {
                    "REDIS_ENTERPRISE_ADMIN_URL": "https://env-cluster.example.com:9443",
                    "REDIS_ENTERPRISE_ADMIN_USERNAME": "env-admin@example.com",
                    "REDIS_ENTERPRISE_ADMIN_PASSWORD": "env-secret",
                },
                clear=False,
            ),
            patch("redis_sre_agent.core.clusters.get_clusters") as mock_get,
            patch("redis_sre_agent.core.clusters.save_clusters") as mock_save,
        ):
            mock_get.return_value = []
            mock_save.return_value = True

            response = client.post("/api/v1/clusters", json=create_data)

            assert response.status_code == 201
            data = response.json()
            assert data["admin_url"] == "https://explicit-cluster.example.com:9443"
            assert data["admin_username"] == "env-admin@example.com"
            assert data["admin_password"] == "***"

    def test_create_cluster_missing_enterprise_admin_fields(self, client):
        """Test enterprise cluster create validation."""
        invalid_data = {
            "name": "Bad Enterprise Cluster",
            "cluster_type": "redis_enterprise",
            "environment": "development",
            "description": "Missing enterprise admin fields",
            "admin_url": "https://new-cluster.example.com:9443",
            # Missing admin_username/admin_password
        }

        with patch.dict(
            os.environ,
            {
                "REDIS_ENTERPRISE_ADMIN_URL": "",
                "REDIS_ENTERPRISE_ADMIN_USERNAME": "",
                "REDIS_ENTERPRISE_ADMIN_PASSWORD": "",
            },
            clear=False,
        ):
            response = client.post("/api/v1/clusters", json=invalid_data)

        assert response.status_code == 400
        assert "requires admin_url, admin_username, and admin_password" in response.json()["detail"]
        assert "REDIS_ENTERPRISE_ADMIN_URL" in response.json()["detail"]

    def test_create_cluster_non_enterprise_rejects_admin_fields(self, client):
        """Test non-enterprise cluster rejects admin fields."""
        invalid_data = {
            "name": "Bad OSS Cluster",
            "cluster_type": "oss_cluster",
            "environment": "development",
            "description": "OSS cluster with invalid admin fields",
            "admin_url": "https://new-cluster.example.com:9443",
            "admin_username": "admin@example.com",
            "admin_password": "secret",
        }

        response = client.post("/api/v1/clusters", json=invalid_data)

        assert response.status_code == 400
        assert "admin_url/admin_username/admin_password are only valid" in response.json()["detail"]

    def test_update_cluster_success(self, client, sample_cluster):
        """Test successful cluster update."""
        update_data = {
            "description": "Updated description",
            "status": "maintenance",
        }

        with (
            patch("redis_sre_agent.core.clusters.get_clusters") as mock_get,
            patch("redis_sre_agent.core.clusters.save_clusters") as mock_save,
        ):
            mock_get.return_value = [sample_cluster]
            mock_save.return_value = True

            response = client.put("/api/v1/clusters/test-cluster-123", json=update_data)

            assert response.status_code == 200
            data = response.json()
            assert data["description"] == "Updated description"
            assert data["status"] == "maintenance"

    def test_update_cluster_rejects_invalid_merged_state(self, client, sample_cluster):
        """Changing enterprise cluster_type to non-enterprise should fail validation."""
        update_data = {"cluster_type": "oss_cluster"}

        with patch("redis_sre_agent.core.clusters.get_clusters") as mock_get:
            mock_get.return_value = [sample_cluster]

            response = client.put("/api/v1/clusters/test-cluster-123", json=update_data)

            assert response.status_code == 400
            assert (
                "admin_url/admin_username/admin_password are only valid"
                in response.json()["detail"]
            )

    def test_update_cluster_not_found(self, client):
        """Test cluster update when not found."""
        update_data = {"description": "Updated description"}

        with patch("redis_sre_agent.core.clusters.get_clusters") as mock_get:
            mock_get.return_value = []

            response = client.put("/api/v1/clusters/nonexistent", json=update_data)

            assert response.status_code == 404

    def test_delete_cluster_success(self, client, sample_cluster):
        """Test successful cluster deletion."""
        with (
            patch("redis_sre_agent.core.clusters.get_clusters") as mock_get,
            patch("redis_sre_agent.core.clusters.save_clusters") as mock_save,
            patch("redis_sre_agent.core.clusters.delete_cluster_index_doc") as mock_delete_doc,
        ):
            mock_get.return_value = [sample_cluster]
            mock_save.return_value = True
            mock_delete_doc.return_value = None

            response = client.delete("/api/v1/clusters/test-cluster-123")

            assert response.status_code == 200
            data = response.json()
            assert "message" in data

    def test_delete_cluster_not_found(self, client):
        """Test cluster deletion when not found."""
        with patch("redis_sre_agent.core.clusters.get_clusters") as mock_get:
            mock_get.return_value = []

            response = client.delete("/api/v1/clusters/nonexistent")

            assert response.status_code == 404


class TestClustersAPIErrorHandling:
    """Test error handling in clusters API."""

    def test_list_clusters_error(self, client):
        """Test list clusters when backend fails."""
        with patch("redis_sre_agent.core.clusters.query_clusters") as mock_query:
            mock_query.side_effect = Exception("Redis failure")

            response = client.get("/api/v1/clusters")

            assert response.status_code == 500
            assert "Failed to retrieve clusters" in response.json()["detail"]

    def test_get_cluster_error(self, client):
        """Test get cluster when backend fails."""
        with patch("redis_sre_agent.core.clusters.get_cluster_by_id") as mock_get:
            mock_get.side_effect = Exception("Redis failure")

            response = client.get("/api/v1/clusters/test-cluster-123")

            assert response.status_code == 500
            assert "Failed to retrieve cluster" in response.json()["detail"]
