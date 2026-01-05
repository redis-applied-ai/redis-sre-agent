"""Support package extractor.

This module handles extracting and parsing Redis Enterprise support packages.
"""

from __future__ import annotations

import logging
import tarfile
from pathlib import Path
from typing import Optional

from .models import SupportPackage

logger = logging.getLogger(__name__)


class SupportPackageExtractionError(Exception):
    """Raised when support package extraction fails."""

    pass


class SupportPackageExtractor:
    """Extracts and parses Redis Enterprise support packages.

    Support packages are tar.gz archives containing diagnostic data.
    This class handles decompression and parsing into structured models.

    Example:
        extractor = SupportPackageExtractor(artifact_path=Path("/tmp/support_packages"))
        package = extractor.extract_and_parse(Path("debuginfo.tar.gz"))
        print(package.databases)
    """

    def __init__(self, artifact_path: Optional[Path] = None):
        """Initialize the extractor.

        Args:
            artifact_path: Base directory for extracted packages.
                          Defaults to system temp directory.
        """
        if artifact_path is None:
            import tempfile

            artifact_path = Path(tempfile.gettempdir()) / "support_packages"
        self.artifact_path = artifact_path

    def extract(self, archive_path: Path) -> Path:
        """Extract a support package archive.

        Args:
            archive_path: Path to the tar.gz archive

        Returns:
            Path to the extracted directory

        Raises:
            SupportPackageExtractionError: If extraction fails
        """
        if not archive_path.exists():
            raise SupportPackageExtractionError(f"Archive not found: {archive_path}")

        # Create output directory
        self.artifact_path.mkdir(parents=True, exist_ok=True)

        # Derive subdirectory name from archive name
        # e.g., "debuginfo.ABC123.tar.gz" -> "debuginfo.ABC123"
        subdir_name = archive_path.name
        for suffix in [".tar.gz", ".tgz", ".tar"]:
            if subdir_name.endswith(suffix):
                subdir_name = subdir_name[: -len(suffix)]
                break

        output_dir = self.artifact_path / subdir_name

        try:
            with tarfile.open(archive_path, "r:gz") as tar:
                # Security: Check for path traversal attacks
                for member in tar.getmembers():
                    if member.name.startswith("/") or ".." in member.name:
                        raise SupportPackageExtractionError(
                            f"Unsafe path in archive: {member.name}"
                        )

                # Extract to output directory
                output_dir.mkdir(parents=True, exist_ok=True)
                tar.extractall(path=output_dir, filter="data")

                logger.info(f"Extracted support package to: {output_dir}")

        except tarfile.TarError as e:
            raise SupportPackageExtractionError(f"Failed to extract archive: {e}") from e

        return output_dir

    def extract_and_parse(self, archive_path: Path) -> SupportPackage:
        """Extract and parse a support package archive.

        Args:
            archive_path: Path to the tar.gz archive

        Returns:
            Parsed SupportPackage model

        Raises:
            SupportPackageExtractionError: If extraction fails
        """
        output_dir = self.extract(archive_path)

        # Handle nested structure (archive may contain a top-level directory)
        # Look for database_* or node_* directories
        contents = list(output_dir.iterdir())
        if len(contents) == 1 and contents[0].is_dir():
            # Check if the single directory contains the expected structure
            subcontents = list(contents[0].iterdir())
            has_structure = any(
                d.name.startswith("database_") or d.name.startswith("node_")
                for d in subcontents
                if d.is_dir()
            )
            if has_structure:
                output_dir = contents[0]

        return SupportPackage.from_directory(output_dir)
