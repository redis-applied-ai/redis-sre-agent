"""Tests for support package storage backends."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestStorageProtocol:
    """Test that storage backends implement the protocol correctly."""

    def test_local_storage_implements_protocol(self, tmp_path: Path):
        """Test LocalStorage implements SupportPackageStorage protocol."""
        from redis_sre_agent.tools.support_package.storage import LocalStorage
        from redis_sre_agent.tools.support_package.storage.protocols import (
            SupportPackageStorage,
        )

        storage = LocalStorage(base_path=tmp_path)
        assert isinstance(storage, SupportPackageStorage)

    def test_s3_storage_implements_protocol(self):
        """Test S3Storage implements SupportPackageStorage protocol."""
        from redis_sre_agent.tools.support_package.storage import S3Storage
        from redis_sre_agent.tools.support_package.storage.protocols import (
            SupportPackageStorage,
        )

        storage = S3Storage(bucket="test-bucket", prefix="packages/")
        assert isinstance(storage, SupportPackageStorage)


class TestLocalStorage:
    """Test LocalStorage backend."""

    @pytest.fixture
    def storage(self, tmp_path: Path):
        """Create a LocalStorage instance for testing."""
        from redis_sre_agent.tools.support_package.storage import LocalStorage

        return LocalStorage(base_path=tmp_path)

    @pytest.fixture
    def sample_package(self, tmp_path: Path) -> Path:
        """Create a sample support package tar.gz file."""
        import tarfile

        package_dir = tmp_path / "sample_package"
        package_dir.mkdir()

        # Create sample database files
        db_dir = package_dir / "database_1"
        db_dir.mkdir()
        (db_dir / "database_1.info").write_text("# Redis Info\nredis_version:7.0.0")
        (db_dir / "database_1.slowlog").write_text("1) id=1\n   cmd=GET key")

        # Create sample node files
        node_dir = package_dir / "node_1"
        node_dir.mkdir()
        logs_dir = node_dir / "logs"
        logs_dir.mkdir()
        (logs_dir / "event_log.log").write_text("INFO: Node started")

        # Create tar.gz
        tar_path = tmp_path / "test_package.tar.gz"
        with tarfile.open(tar_path, "w:gz") as tar:
            tar.add(package_dir, arcname="sample_package")

        return tar_path

    async def test_upload_stores_file(self, storage, sample_package: Path):
        """Test that upload stores a file and returns package ID."""
        package_id = await storage.upload(sample_package)

        assert package_id is not None
        assert len(package_id) > 0

        # Verify file was stored in the package directory
        package_file = storage._package_file(package_id)
        assert package_file.exists()
        assert package_file.stat().st_size > 0

    async def test_upload_with_custom_id(self, storage, sample_package: Path):
        """Test upload with a custom package ID."""
        custom_id = "my-custom-package-id"
        package_id = await storage.upload(sample_package, package_id=custom_id)

        assert package_id == custom_id

    async def test_download_retrieves_file(self, storage, sample_package: Path, tmp_path: Path):
        """Test that download retrieves a previously uploaded file."""
        package_id = await storage.upload(sample_package)

        dest_path = tmp_path / "downloaded.tar.gz"
        result_path = await storage.download(package_id, dest_path)

        assert result_path == dest_path
        assert dest_path.exists()
        assert dest_path.stat().st_size > 0

    async def test_download_nonexistent_raises(self, storage, tmp_path: Path):
        """Test that downloading a nonexistent package raises an error."""
        from redis_sre_agent.tools.support_package.storage.protocols import (
            PackageNotFoundError,
        )

        with pytest.raises(PackageNotFoundError):
            await storage.download("nonexistent-id", tmp_path / "out.tar.gz")

    async def test_list_packages(self, storage, sample_package: Path):
        """Test listing all packages."""
        # Upload multiple packages
        id1 = await storage.upload(sample_package, package_id="pkg-1")
        id2 = await storage.upload(sample_package, package_id="pkg-2")

        packages = await storage.list_packages()

        assert len(packages) == 2
        package_ids = [p.package_id for p in packages]
        assert id1 in package_ids
        assert id2 in package_ids

    async def test_get_package_metadata(self, storage, sample_package: Path):
        """Test getting metadata for a specific package."""
        package_id = await storage.upload(sample_package)

        metadata = await storage.get_metadata(package_id)

        assert metadata is not None
        assert metadata.package_id == package_id
        assert metadata.filename is not None
        assert metadata.size_bytes > 0
        assert metadata.uploaded_at is not None

    async def test_delete_package(self, storage, sample_package: Path):
        """Test deleting a package."""
        package_id = await storage.upload(sample_package)

        # Verify it exists
        packages = await storage.list_packages()
        assert len(packages) == 1

        # Delete it
        await storage.delete(package_id)

        # Verify it's gone
        packages = await storage.list_packages()
        assert len(packages) == 0

    async def test_exists_returns_true_for_existing(self, storage, sample_package: Path):
        """Test exists() returns True for existing packages."""
        package_id = await storage.upload(sample_package)

        assert await storage.exists(package_id) is True

    async def test_exists_returns_false_for_nonexistent(self, storage):
        """Test exists() returns False for nonexistent packages."""
        assert await storage.exists("nonexistent-id") is False


class TestS3Storage:
    """Test S3Storage backend."""

    @pytest.fixture
    def mock_s3_client(self):
        """Create a mock boto3 S3 client."""
        with patch("boto3.client") as mock:
            client = MagicMock()
            mock.return_value = client
            yield client

    @pytest.fixture
    def storage(self, mock_s3_client):
        """Create an S3Storage instance with mocked client."""
        from redis_sre_agent.tools.support_package.storage import S3Storage

        storage = S3Storage(bucket="test-bucket", prefix="packages/")
        storage._client = mock_s3_client
        return storage

    @pytest.fixture
    def sample_package(self, tmp_path: Path) -> Path:
        """Create a sample package file."""
        package_path = tmp_path / "test_package.tar.gz"
        package_path.write_bytes(b"fake tar.gz content")
        return package_path

    async def test_upload_calls_s3_put_object(self, storage, sample_package: Path, mock_s3_client):
        """Test that upload calls S3 put_object."""
        package_id = await storage.upload(sample_package)

        mock_s3_client.upload_file.assert_called_once()
        call_args = mock_s3_client.upload_file.call_args
        assert call_args[1]["Bucket"] == "test-bucket"
        assert package_id in call_args[1]["Key"]

    async def test_download_calls_s3_download_file(self, storage, tmp_path: Path, mock_s3_client):
        """Test that download calls S3 download_file."""
        mock_s3_client.head_object.return_value = {}  # Package exists

        dest_path = tmp_path / "downloaded.tar.gz"
        await storage.download("test-package-id", dest_path)

        mock_s3_client.download_file.assert_called_once()

    async def test_list_packages_calls_s3_list_objects(self, storage, mock_s3_client):
        """Test that list_packages calls S3 list_objects_v2."""
        mock_s3_client.list_objects_v2.return_value = {
            "Contents": [
                {
                    "Key": "packages/pkg-1.tar.gz",
                    "Size": 1024,
                    "LastModified": "2024-01-01T00:00:00Z",
                },
                {
                    "Key": "packages/pkg-2.tar.gz",
                    "Size": 2048,
                    "LastModified": "2024-01-02T00:00:00Z",
                },
            ]
        }

        packages = await storage.list_packages()

        mock_s3_client.list_objects_v2.assert_called_once()
        assert len(packages) == 2
