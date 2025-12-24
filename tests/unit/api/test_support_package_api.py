"""Unit tests for support package API endpoints."""

import io
import tarfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from redis_sre_agent.api.app import app


@pytest.fixture
def client():
    """Test client for FastAPI app."""
    return TestClient(app)


@pytest.fixture
def sample_package_bytes() -> bytes:
    """Create a sample support package tar.gz in memory."""
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        # Add a sample file
        data = b"# Redis Info\nredis_version:7.0.0"
        info = tarfile.TarInfo(name="sample_package/database_1/database_1.info")
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    buffer.seek(0)
    return buffer.read()


@pytest.fixture
def sample_metadata():
    """Sample package metadata."""
    from redis_sre_agent.tools.support_package.storage.protocols import PackageMetadata

    return PackageMetadata(
        package_id="test-pkg-123",
        filename="test_package.tar.gz",
        size_bytes=1024,
        uploaded_at=datetime.now(timezone.utc),
    )


class TestSupportPackageAPI:
    """Test support package API endpoints."""

    def test_upload_package(self, client, sample_package_bytes):
        """Test uploading a support package."""
        with patch("redis_sre_agent.api.support_package.get_manager") as mock_get_manager:
            mock_manager = AsyncMock()
            mock_manager.upload.return_value = "test-pkg-123"
            mock_get_manager.return_value = mock_manager

            response = client.post(
                "/api/v1/support-packages/upload",
                files={"file": ("test.tar.gz", sample_package_bytes, "application/gzip")},
            )

            assert response.status_code == 201
            data = response.json()
            assert data["package_id"] == "test-pkg-123"
            assert data["status"] == "uploaded"

    def test_upload_package_with_custom_id(self, client, sample_package_bytes):
        """Test uploading with a custom package ID."""
        with patch("redis_sre_agent.api.support_package.get_manager") as mock_get_manager:
            mock_manager = AsyncMock()
            mock_manager.upload.return_value = "my-custom-id"
            mock_get_manager.return_value = mock_manager

            response = client.post(
                "/api/v1/support-packages/upload?package_id=my-custom-id",
                files={"file": ("test.tar.gz", sample_package_bytes, "application/gzip")},
            )

            assert response.status_code == 201
            data = response.json()
            assert data["package_id"] == "my-custom-id"

    def test_list_packages(self, client, sample_metadata):
        """Test listing support packages."""
        with patch("redis_sre_agent.api.support_package.get_manager") as mock_get_manager:
            mock_manager = AsyncMock()
            mock_manager.list_packages.return_value = [sample_metadata]
            mock_get_manager.return_value = mock_manager

            response = client.get("/api/v1/support-packages")

            assert response.status_code == 200
            data = response.json()
            assert len(data["packages"]) == 1
            assert data["packages"][0]["package_id"] == "test-pkg-123"

    def test_list_packages_empty(self, client):
        """Test listing when no packages exist."""
        with patch("redis_sre_agent.api.support_package.get_manager") as mock_get_manager:
            mock_manager = AsyncMock()
            mock_manager.list_packages.return_value = []
            mock_get_manager.return_value = mock_manager

            response = client.get("/api/v1/support-packages")

            assert response.status_code == 200
            data = response.json()
            assert len(data["packages"]) == 0

    def test_get_package_info(self, client, sample_metadata):
        """Test getting package info."""
        with patch("redis_sre_agent.api.support_package.get_manager") as mock_get_manager:
            mock_manager = AsyncMock()
            mock_manager.get_metadata.return_value = sample_metadata
            mock_manager.is_extracted.return_value = False
            mock_get_manager.return_value = mock_manager

            response = client.get("/api/v1/support-packages/test-pkg-123")

            assert response.status_code == 200
            data = response.json()
            assert data["package_id"] == "test-pkg-123"
            assert data["is_extracted"] is False

    def test_get_package_not_found(self, client):
        """Test getting non-existent package."""
        with patch("redis_sre_agent.api.support_package.get_manager") as mock_get_manager:
            mock_manager = AsyncMock()
            mock_manager.get_metadata.return_value = None
            mock_get_manager.return_value = mock_manager

            response = client.get("/api/v1/support-packages/nonexistent")

            assert response.status_code == 404

    def test_extract_package(self, client, tmp_path: Path):
        """Test extracting a package."""
        with patch("redis_sre_agent.api.support_package.get_manager") as mock_get_manager:
            mock_manager = AsyncMock()
            mock_manager.extract.return_value = tmp_path / "extracted"
            mock_get_manager.return_value = mock_manager

            response = client.post("/api/v1/support-packages/test-pkg-123/extract")

            assert response.status_code == 200
            data = response.json()
            assert data["package_id"] == "test-pkg-123"
            assert data["status"] == "extracted"

    def test_delete_package(self, client):
        """Test deleting a package."""
        with patch("redis_sre_agent.api.support_package.get_manager") as mock_get_manager:
            mock_manager = AsyncMock()
            mock_manager.delete.return_value = None
            mock_get_manager.return_value = mock_manager

            response = client.delete("/api/v1/support-packages/test-pkg-123")

            assert response.status_code == 200
            mock_manager.delete.assert_called_once_with("test-pkg-123")
