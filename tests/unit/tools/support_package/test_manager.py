"""Tests for SupportPackageManager."""

import tarfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def sample_package_tarball(tmp_path: Path) -> Path:
    """Create a sample support package tar.gz file."""
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


class TestSupportPackageManager:
    """Test SupportPackageManager class."""

    @pytest.fixture
    def manager(self, tmp_path: Path):
        """Create a SupportPackageManager with local storage."""
        from redis_sre_agent.tools.support_package.manager import (
            SupportPackageManager,
        )
        from redis_sre_agent.tools.support_package.storage import LocalStorage

        storage = LocalStorage(base_path=tmp_path / "storage")
        extract_dir = tmp_path / "extracted"
        return SupportPackageManager(storage=storage, extract_dir=extract_dir)

    async def test_upload_package(self, manager, sample_package_tarball: Path):
        """Test uploading a support package."""
        package_id = await manager.upload(sample_package_tarball)

        assert package_id is not None
        assert len(package_id) > 0

    async def test_upload_with_custom_id(self, manager, sample_package_tarball: Path):
        """Test uploading with a custom package ID."""
        custom_id = "my-custom-id"
        package_id = await manager.upload(sample_package_tarball, package_id=custom_id)

        assert package_id == custom_id

    async def test_list_packages(self, manager, sample_package_tarball: Path):
        """Test listing uploaded packages."""
        await manager.upload(sample_package_tarball, package_id="pkg-1")
        await manager.upload(sample_package_tarball, package_id="pkg-2")

        packages = await manager.list_packages()

        assert len(packages) == 2
        package_ids = [p.package_id for p in packages]
        assert "pkg-1" in package_ids
        assert "pkg-2" in package_ids

    async def test_get_package_metadata(self, manager, sample_package_tarball: Path):
        """Test getting package metadata."""
        package_id = await manager.upload(sample_package_tarball)

        metadata = await manager.get_metadata(package_id)

        assert metadata is not None
        assert metadata.package_id == package_id
        assert metadata.size_bytes > 0

    async def test_extract_package(self, manager, sample_package_tarball: Path):
        """Test extracting a package."""
        package_id = await manager.upload(sample_package_tarball)

        extract_path = await manager.extract(package_id)

        assert extract_path.exists()
        assert extract_path.is_dir()
        # Should contain the extracted content
        assert (extract_path / "database_1").exists() or any(
            d.name.startswith("database_") for d in extract_path.iterdir()
        )

    async def test_extract_returns_cached_path(self, manager, sample_package_tarball: Path):
        """Test that extract returns cached path if already extracted."""
        package_id = await manager.upload(sample_package_tarball)

        path1 = await manager.extract(package_id)
        path2 = await manager.extract(package_id)

        assert path1 == path2

    async def test_delete_package(self, manager, sample_package_tarball: Path):
        """Test deleting a package."""
        package_id = await manager.upload(sample_package_tarball)

        await manager.delete(package_id)

        packages = await manager.list_packages()
        assert len(packages) == 0

    async def test_delete_also_removes_extracted(self, manager, sample_package_tarball: Path):
        """Test that delete also removes extracted files."""
        package_id = await manager.upload(sample_package_tarball)
        extract_path = await manager.extract(package_id)

        assert extract_path.exists()

        await manager.delete(package_id)

        assert not extract_path.exists()

    async def test_get_tool_provider(self, manager, sample_package_tarball: Path):
        """Test getting a tool provider for a package."""
        from redis_sre_agent.tools.support_package.provider import (
            SupportPackageToolProvider,
        )

        package_id = await manager.upload(sample_package_tarball)

        provider = await manager.get_tool_provider(package_id)

        assert provider is not None
        assert isinstance(provider, SupportPackageToolProvider)

    async def test_get_tool_provider_extracts_if_needed(
        self, manager, sample_package_tarball: Path
    ):
        """Test that get_tool_provider extracts the package if not already extracted."""
        package_id = await manager.upload(sample_package_tarball)

        # Should not be extracted yet
        extract_path = manager.extract_dir / package_id
        assert not extract_path.exists()

        # Get provider should trigger extraction
        provider = await manager.get_tool_provider(package_id)

        assert provider is not None
        # Now it should be extracted
        assert extract_path.exists()

    async def test_is_extracted(self, manager, sample_package_tarball: Path):
        """Test checking if a package is extracted."""
        package_id = await manager.upload(sample_package_tarball)

        assert await manager.is_extracted(package_id) is False

        await manager.extract(package_id)

        assert await manager.is_extracted(package_id) is True
