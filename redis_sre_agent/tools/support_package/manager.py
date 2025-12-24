"""Support Package Manager - coordinates storage, extraction, and tool providers."""

import shutil
import tarfile
from pathlib import Path
from typing import List, Optional

from .provider import SupportPackageToolProvider
from .storage.protocols import PackageMetadata, SupportPackageStorage


class SupportPackageManager:
    """Manager for support packages.

    Coordinates storage, extraction, and tool provider creation.
    Provides a high-level API for working with support packages.
    """

    def __init__(
        self,
        storage: SupportPackageStorage,
        extract_dir: Path,
    ):
        """Initialize the manager.

        Args:
            storage: Storage backend for packages
            extract_dir: Directory where packages are extracted
        """
        self.storage = storage
        self.extract_dir = Path(extract_dir)
        self.extract_dir.mkdir(parents=True, exist_ok=True)

    async def upload(
        self,
        source_path: Path,
        package_id: Optional[str] = None,
    ) -> str:
        """Upload a support package to storage.

        Args:
            source_path: Path to the support package file
            package_id: Optional custom package ID

        Returns:
            The package ID
        """
        return await self.storage.upload(source_path, package_id)

    async def list_packages(self) -> List[PackageMetadata]:
        """List all uploaded packages.

        Returns:
            List of package metadata
        """
        return await self.storage.list_packages()

    async def get_metadata(self, package_id: str) -> Optional[PackageMetadata]:
        """Get metadata for a specific package.

        Args:
            package_id: ID of the package

        Returns:
            Package metadata, or None if not found
        """
        return await self.storage.get_metadata(package_id)

    async def extract(self, package_id: str) -> Path:
        """Extract a package to the local filesystem.

        Downloads from storage if needed, then extracts.
        Returns cached path if already extracted.

        Args:
            package_id: ID of the package to extract

        Returns:
            Path to the extracted package directory
        """
        extract_path = self.extract_dir / package_id

        # Return cached if already extracted
        if extract_path.exists() and any(extract_path.iterdir()):
            return extract_path

        # Download from storage to temp location
        temp_download = self.extract_dir / f"{package_id}.tar.gz"
        try:
            await self.storage.download(package_id, temp_download)

            # Extract to package-specific directory
            extract_path.mkdir(parents=True, exist_ok=True)
            self._extract_tarball(temp_download, extract_path)

            return extract_path
        finally:
            # Clean up temp download
            if temp_download.exists():
                temp_download.unlink()

    def _extract_tarball(self, archive_path: Path, output_dir: Path) -> Path:
        """Extract a tarball to a directory.

        Handles nested structure where the archive may contain a top-level directory.

        Args:
            archive_path: Path to the tar.gz archive
            output_dir: Directory to extract to

        Returns:
            Path to the actual content directory (may be a subdirectory)
        """
        with tarfile.open(archive_path, "r:gz") as tar:
            # Security: Check for path traversal attacks
            for member in tar.getmembers():
                if member.name.startswith("/") or ".." in member.name:
                    raise ValueError(f"Unsafe path in archive: {member.name}")

            tar.extractall(path=output_dir, filter="data")

        # Handle nested structure (archive may contain a top-level directory)
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
                # Move contents up one level
                nested_dir = contents[0]
                for item in nested_dir.iterdir():
                    shutil.move(str(item), str(output_dir / item.name))
                nested_dir.rmdir()

        return output_dir

    async def delete(self, package_id: str) -> None:
        """Delete a package from storage and local extraction.

        Args:
            package_id: ID of the package to delete
        """
        # Remove extracted files if they exist
        extract_path = self.extract_dir / package_id
        if extract_path.exists():
            shutil.rmtree(extract_path)

        # Remove from storage
        await self.storage.delete(package_id)

    async def is_extracted(self, package_id: str) -> bool:
        """Check if a package is already extracted.

        Args:
            package_id: ID of the package

        Returns:
            True if extracted, False otherwise
        """
        extract_path = self.extract_dir / package_id
        return extract_path.exists() and any(extract_path.iterdir())

    async def get_tool_provider(self, package_id: str) -> SupportPackageToolProvider:
        """Get a tool provider for a package.

        Extracts the package if not already extracted.

        Args:
            package_id: ID of the package

        Returns:
            Tool provider for the package
        """
        extract_path = await self.extract(package_id)
        return SupportPackageToolProvider(package_path=extract_path)
