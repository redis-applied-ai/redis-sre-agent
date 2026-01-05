"""Local filesystem storage backend for support packages."""

import hashlib
import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from .protocols import PackageMetadata, PackageNotFoundError, SupportPackageStorage


class LocalStorage(SupportPackageStorage):
    """Local filesystem storage backend for support packages.

    Stores packages in a directory structure:
        base_path/
            {package_id}/
                package.tar.gz
                metadata.json
    """

    def __init__(self, base_path: Path):
        """Initialize local storage.

        Args:
            base_path: Base directory for storing packages
        """
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _package_dir(self, package_id: str) -> Path:
        """Get the directory for a specific package."""
        return self.base_path / package_id

    def _package_file(self, package_id: str) -> Path:
        """Get the path to the package file."""
        return self._package_dir(package_id) / "package.tar.gz"

    def _metadata_file(self, package_id: str) -> Path:
        """Get the path to the metadata file."""
        return self._package_dir(package_id) / "metadata.json"

    def _compute_checksum(self, file_path: Path) -> str:
        """Compute SHA-256 checksum of a file."""
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    async def upload(
        self,
        source_path: Path,
        package_id: Optional[str] = None,
    ) -> str:
        """Upload a support package to local storage."""
        if package_id is None:
            package_id = str(uuid.uuid4())

        package_dir = self._package_dir(package_id)
        package_dir.mkdir(parents=True, exist_ok=True)

        # Copy the file
        dest_file = self._package_file(package_id)
        shutil.copy2(source_path, dest_file)

        # Compute checksum and create metadata
        checksum = self._compute_checksum(dest_file)
        metadata = PackageMetadata(
            package_id=package_id,
            filename=source_path.name,
            size_bytes=dest_file.stat().st_size,
            uploaded_at=datetime.now(timezone.utc),
            storage_path=str(dest_file),
            checksum=checksum,
        )

        # Save metadata
        metadata_file = self._metadata_file(package_id)
        metadata_file.write_text(metadata.model_dump_json(indent=2))

        return package_id

    async def download(
        self,
        package_id: str,
        dest_path: Path,
    ) -> Path:
        """Download a support package from local storage."""
        package_file = self._package_file(package_id)

        if not package_file.exists():
            raise PackageNotFoundError(package_id)

        # Copy to destination
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(package_file, dest_path)

        return dest_path

    async def list_packages(self) -> List[PackageMetadata]:
        """List all support packages in local storage."""
        packages = []

        for package_dir in self.base_path.iterdir():
            if package_dir.is_dir():
                metadata = await self.get_metadata(package_dir.name)
                if metadata:
                    packages.append(metadata)

        return packages

    async def get_metadata(self, package_id: str) -> Optional[PackageMetadata]:
        """Get metadata for a specific package."""
        metadata_file = self._metadata_file(package_id)

        if not metadata_file.exists():
            return None

        data = json.loads(metadata_file.read_text())
        return PackageMetadata(**data)

    async def delete(self, package_id: str) -> None:
        """Delete a support package from local storage."""
        package_dir = self._package_dir(package_id)

        if not package_dir.exists():
            raise PackageNotFoundError(package_id)

        shutil.rmtree(package_dir)

    async def exists(self, package_id: str) -> bool:
        """Check if a package exists in local storage."""
        return self._package_file(package_id).exists()
