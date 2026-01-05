"""Protocol definitions for support package storage."""

from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field


class PackageNotFoundError(Exception):
    """Raised when a support package is not found in storage."""

    def __init__(self, package_id: str):
        self.package_id = package_id
        super().__init__(f"Support package not found: {package_id}")


class PackageMetadata(BaseModel):
    """Metadata for a stored support package."""

    package_id: str = Field(..., description="Unique identifier for the package")
    filename: str = Field(..., description="Original filename of the package")
    size_bytes: int = Field(..., description="Size of the package in bytes")
    uploaded_at: datetime = Field(..., description="When the package was uploaded")
    storage_path: Optional[str] = Field(
        default=None, description="Path in storage (local path or S3 key)"
    )
    content_type: str = Field(default="application/gzip", description="MIME type of the package")
    checksum: Optional[str] = Field(default=None, description="SHA-256 checksum of the package")


class SupportPackageStorage(ABC):
    """Abstract base class for support package storage backends.

    Implementations must provide methods for uploading, downloading,
    listing, and deleting support packages.
    """

    @abstractmethod
    async def upload(
        self,
        source_path: Path,
        package_id: Optional[str] = None,
    ) -> str:
        """Upload a support package to storage.

        Args:
            source_path: Path to the support package file to upload
            package_id: Optional custom package ID. If not provided,
                one will be generated.

        Returns:
            The package ID (generated or provided)
        """
        ...

    @abstractmethod
    async def download(
        self,
        package_id: str,
        dest_path: Path,
    ) -> Path:
        """Download a support package from storage.

        Args:
            package_id: ID of the package to download
            dest_path: Path where the package should be saved

        Returns:
            The path where the package was saved

        Raises:
            PackageNotFoundError: If the package doesn't exist
        """
        ...

    @abstractmethod
    async def list_packages(self) -> List[PackageMetadata]:
        """List all support packages in storage.

        Returns:
            List of package metadata for all stored packages
        """
        ...

    @abstractmethod
    async def get_metadata(self, package_id: str) -> Optional[PackageMetadata]:
        """Get metadata for a specific package.

        Args:
            package_id: ID of the package

        Returns:
            Package metadata, or None if not found
        """
        ...

    @abstractmethod
    async def delete(self, package_id: str) -> None:
        """Delete a support package from storage.

        Args:
            package_id: ID of the package to delete

        Raises:
            PackageNotFoundError: If the package doesn't exist
        """
        ...

    @abstractmethod
    async def exists(self, package_id: str) -> bool:
        """Check if a package exists in storage.

        Args:
            package_id: ID of the package to check

        Returns:
            True if the package exists, False otherwise
        """
        ...
