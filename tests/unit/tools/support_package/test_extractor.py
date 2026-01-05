"""Tests for support package extractor."""

import tarfile
from pathlib import Path

import pytest


class TestSupportPackageExtractor:
    """Tests for SupportPackageExtractor."""

    def test_extract_creates_output_directory(self, tmp_path: Path):
        """Test that extraction creates the output directory if needed."""
        from redis_sre_agent.tools.support_package.extractor import SupportPackageExtractor

        # Create a minimal tar.gz file
        archive_path = tmp_path / "test.tar.gz"
        content_dir = tmp_path / "content"
        content_dir.mkdir()
        (content_dir / "test.txt").write_text("test content")

        with tarfile.open(archive_path, "w:gz") as tar:
            tar.add(content_dir / "test.txt", arcname="test.txt")

        output_dir = tmp_path / "output"
        extractor = SupportPackageExtractor(artifact_path=output_dir)
        result = extractor.extract(archive_path)

        assert output_dir.exists()
        assert result.exists()

    def test_extract_decompresses_tar_gz(self, tmp_path: Path):
        """Test that tar.gz files are properly decompressed."""
        from redis_sre_agent.tools.support_package.extractor import SupportPackageExtractor

        # Create a tar.gz with database structure
        archive_path = tmp_path / "debuginfo.tar.gz"
        content_dir = tmp_path / "content"
        db_dir = content_dir / "database_1"
        db_dir.mkdir(parents=True)
        (db_dir / "database_1.info").write_text("# Server\nredis_version:8.4.0")

        with tarfile.open(archive_path, "w:gz") as tar:
            tar.add(db_dir, arcname="database_1")

        output_dir = tmp_path / "output"
        extractor = SupportPackageExtractor(artifact_path=output_dir)
        result = extractor.extract(archive_path)

        # Verify extraction
        assert (result / "database_1" / "database_1.info").exists()

    def test_extract_returns_support_package(self, tmp_path: Path):
        """Test that extract returns a SupportPackage model."""
        from redis_sre_agent.tools.support_package.extractor import SupportPackageExtractor
        from redis_sre_agent.tools.support_package.models import SupportPackage

        # Create a tar.gz with database structure
        archive_path = tmp_path / "debuginfo.tar.gz"
        content_dir = tmp_path / "content"
        db_dir = content_dir / "database_1"
        db_dir.mkdir(parents=True)
        (db_dir / "database_1.info").write_text("# Server\n")

        with tarfile.open(archive_path, "w:gz") as tar:
            tar.add(db_dir, arcname="database_1")

        output_dir = tmp_path / "output"
        extractor = SupportPackageExtractor(artifact_path=output_dir)
        pkg = extractor.extract_and_parse(archive_path)

        assert isinstance(pkg, SupportPackage)
        assert len(pkg.databases) == 1

    def test_extract_uses_archive_name_for_subdir(self, tmp_path: Path):
        """Test that each archive is extracted to a uniquely named subdirectory."""
        from redis_sre_agent.tools.support_package.extractor import SupportPackageExtractor

        archive_path = tmp_path / "debuginfo.ABC123.tar.gz"
        content_dir = tmp_path / "content"
        content_dir.mkdir()
        (content_dir / "test.txt").write_text("test")

        with tarfile.open(archive_path, "w:gz") as tar:
            tar.add(content_dir / "test.txt", arcname="test.txt")

        output_dir = tmp_path / "output"
        extractor = SupportPackageExtractor(artifact_path=output_dir)
        result = extractor.extract(archive_path)

        # Should extract to a subdirectory named after the archive
        assert "debuginfo.ABC123" in str(result)

    def test_extract_handles_nested_tar_structure(self, tmp_path: Path):
        """Test extraction when tar contains a top-level directory."""
        from redis_sre_agent.tools.support_package.extractor import SupportPackageExtractor

        archive_path = tmp_path / "package.tar.gz"
        content_dir = tmp_path / "content" / "toplevel"
        db_dir = content_dir / "database_1"
        db_dir.mkdir(parents=True)
        (db_dir / "database_1.info").write_text("# Server\n")

        with tarfile.open(archive_path, "w:gz") as tar:
            tar.add(content_dir, arcname="toplevel")

        output_dir = tmp_path / "output"
        extractor = SupportPackageExtractor(artifact_path=output_dir)
        result = extractor.extract(archive_path)

        # The extractor should handle nested structure
        assert result.exists()

    def test_extract_raises_on_invalid_archive(self, tmp_path: Path):
        """Test that invalid archives raise appropriate errors."""
        from redis_sre_agent.tools.support_package.extractor import (
            SupportPackageExtractionError,
            SupportPackageExtractor,
        )

        invalid_file = tmp_path / "invalid.tar.gz"
        invalid_file.write_text("not a valid tar file")

        output_dir = tmp_path / "output"
        extractor = SupportPackageExtractor(artifact_path=output_dir)

        with pytest.raises(SupportPackageExtractionError):
            extractor.extract(invalid_file)

    def test_extract_raises_on_missing_file(self, tmp_path: Path):
        """Test that missing files raise appropriate errors."""
        from redis_sre_agent.tools.support_package.extractor import (
            SupportPackageExtractionError,
            SupportPackageExtractor,
        )

        output_dir = tmp_path / "output"
        extractor = SupportPackageExtractor(artifact_path=output_dir)

        with pytest.raises(SupportPackageExtractionError):
            extractor.extract(tmp_path / "nonexistent.tar.gz")
