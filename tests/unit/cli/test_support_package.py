"""Tests for support-package CLI commands."""

import json
import tarfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from click.testing import CliRunner


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


@pytest.fixture
def cli_runner():
    """Create a Click CLI runner."""
    return CliRunner()


class TestSupportPackageCLI:
    """Test support-package CLI commands."""

    def test_upload_command(self, cli_runner, sample_package_tarball: Path, tmp_path: Path):
        """Test uploading a support package via CLI."""
        from redis_sre_agent.cli.support_package import support_package

        with patch("redis_sre_agent.cli.support_package.get_manager") as mock_get_manager:
            mock_manager = AsyncMock()
            mock_manager.upload.return_value = "test-package-id"
            mock_get_manager.return_value = mock_manager

            result = cli_runner.invoke(
                support_package,
                ["upload", str(sample_package_tarball)],
            )

            assert result.exit_code == 0
            assert "test-package-id" in result.output

    def test_upload_with_custom_id(self, cli_runner, sample_package_tarball: Path, tmp_path: Path):
        """Test uploading with a custom package ID."""
        from redis_sre_agent.cli.support_package import support_package

        with patch("redis_sre_agent.cli.support_package.get_manager") as mock_get_manager:
            mock_manager = AsyncMock()
            mock_manager.upload.return_value = "my-custom-id"
            mock_get_manager.return_value = mock_manager

            result = cli_runner.invoke(
                support_package,
                ["upload", str(sample_package_tarball), "--id", "my-custom-id"],
            )

            assert result.exit_code == 0
            assert "my-custom-id" in result.output

    def test_upload_json_output(self, cli_runner, sample_package_tarball: Path, tmp_path: Path):
        """Test upload with JSON output."""
        from redis_sre_agent.cli.support_package import support_package

        with patch("redis_sre_agent.cli.support_package.get_manager") as mock_get_manager:
            mock_manager = AsyncMock()
            mock_manager.upload.return_value = "test-package-id"
            mock_get_manager.return_value = mock_manager

            result = cli_runner.invoke(
                support_package,
                ["upload", str(sample_package_tarball), "--json"],
            )

            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data["package_id"] == "test-package-id"
            assert data["status"] == "uploaded"

    def test_list_command(self, cli_runner, tmp_path: Path):
        """Test listing support packages."""
        from datetime import datetime, timezone

        from redis_sre_agent.cli.support_package import support_package
        from redis_sre_agent.tools.support_package.storage.protocols import (
            PackageMetadata,
        )

        with patch("redis_sre_agent.cli.support_package.get_manager") as mock_get_manager:
            mock_manager = AsyncMock()
            mock_manager.list_packages.return_value = [
                PackageMetadata(
                    package_id="pkg-1",
                    filename="package1.tar.gz",
                    size_bytes=1024,
                    uploaded_at=datetime.now(timezone.utc),
                ),
                PackageMetadata(
                    package_id="pkg-2",
                    filename="package2.tar.gz",
                    size_bytes=2048,
                    uploaded_at=datetime.now(timezone.utc),
                ),
            ]
            mock_get_manager.return_value = mock_manager

            result = cli_runner.invoke(support_package, ["list"])

            assert result.exit_code == 0
            assert "pkg-1" in result.output
            assert "pkg-2" in result.output

    def test_list_json_output(self, cli_runner, tmp_path: Path):
        """Test list with JSON output."""
        from datetime import datetime, timezone

        from redis_sre_agent.cli.support_package import support_package
        from redis_sre_agent.tools.support_package.storage.protocols import (
            PackageMetadata,
        )

        with patch("redis_sre_agent.cli.support_package.get_manager") as mock_get_manager:
            mock_manager = AsyncMock()
            mock_manager.list_packages.return_value = [
                PackageMetadata(
                    package_id="pkg-1",
                    filename="package1.tar.gz",
                    size_bytes=1024,
                    uploaded_at=datetime.now(timezone.utc),
                ),
            ]
            mock_get_manager.return_value = mock_manager

            result = cli_runner.invoke(support_package, ["list", "--json"])

            assert result.exit_code == 0
            data = json.loads(result.output)
            assert len(data) == 1
            assert data[0]["package_id"] == "pkg-1"

    def test_extract_command(self, cli_runner, tmp_path: Path):
        """Test extracting a support package."""
        from redis_sre_agent.cli.support_package import support_package

        with patch("redis_sre_agent.cli.support_package.get_manager") as mock_get_manager:
            mock_manager = AsyncMock()
            mock_manager.extract.return_value = tmp_path / "extracted"
            mock_get_manager.return_value = mock_manager

            result = cli_runner.invoke(support_package, ["extract", "pkg-1"])

            assert result.exit_code == 0
            assert "extracted" in result.output.lower() or "pkg-1" in result.output

    def test_delete_command(self, cli_runner, tmp_path: Path):
        """Test deleting a support package."""
        from redis_sre_agent.cli.support_package import support_package

        with patch("redis_sre_agent.cli.support_package.get_manager") as mock_get_manager:
            mock_manager = AsyncMock()
            mock_manager.delete.return_value = None
            mock_get_manager.return_value = mock_manager

            result = cli_runner.invoke(support_package, ["delete", "pkg-1", "--yes"])

            assert result.exit_code == 0
            mock_manager.delete.assert_called_once_with("pkg-1")

    def test_info_command(self, cli_runner, tmp_path: Path):
        """Test getting info about a support package."""
        from datetime import datetime, timezone

        from redis_sre_agent.cli.support_package import support_package
        from redis_sre_agent.tools.support_package.storage.protocols import (
            PackageMetadata,
        )

        with patch("redis_sre_agent.cli.support_package.get_manager") as mock_get_manager:
            mock_manager = AsyncMock()
            mock_manager.get_metadata.return_value = PackageMetadata(
                package_id="pkg-1",
                filename="package1.tar.gz",
                size_bytes=1024,
                uploaded_at=datetime.now(timezone.utc),
            )
            mock_manager.is_extracted.return_value = True
            mock_get_manager.return_value = mock_manager

            result = cli_runner.invoke(support_package, ["info", "pkg-1"])

            assert result.exit_code == 0
            assert "pkg-1" in result.output
