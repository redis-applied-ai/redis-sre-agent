"""S3-compatible storage backend for support packages."""

import hashlib
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import boto3
from botocore.exceptions import ClientError

from .protocols import PackageMetadata, PackageNotFoundError, SupportPackageStorage


class S3Storage(SupportPackageStorage):
    """S3-compatible storage backend for support packages.

    Stores packages in an S3 bucket with the structure:
        {prefix}{package_id}.tar.gz

    Metadata is stored as object tags and custom metadata.
    """

    def __init__(
        self,
        bucket: str,
        prefix: str = "",
        region: Optional[str] = None,
        endpoint_url: Optional[str] = None,
        aws_access_key_id: Optional[str] = None,
        aws_secret_access_key: Optional[str] = None,
    ):
        """Initialize S3 storage.

        Args:
            bucket: S3 bucket name
            prefix: Key prefix for packages (e.g., "support-packages/")
            region: AWS region (optional, uses default if not specified)
            endpoint_url: Custom endpoint URL for S3-compatible services
            aws_access_key_id: AWS access key (optional, uses default creds)
            aws_secret_access_key: AWS secret key (optional, uses default creds)
        """
        self.bucket = bucket
        self.prefix = prefix.rstrip("/") + "/" if prefix else ""

        client_kwargs: Dict[str, Any] = {}
        if region:
            client_kwargs["region_name"] = region
        if endpoint_url:
            client_kwargs["endpoint_url"] = endpoint_url
        if aws_access_key_id and aws_secret_access_key:
            client_kwargs["aws_access_key_id"] = aws_access_key_id
            client_kwargs["aws_secret_access_key"] = aws_secret_access_key

        self._client = boto3.client("s3", **client_kwargs)

    def _object_key(self, package_id: str) -> str:
        """Get the S3 object key for a package."""
        return f"{self.prefix}{package_id}.tar.gz"

    def _package_id_from_key(self, key: str) -> str:
        """Extract package ID from S3 object key."""
        # Remove prefix and .tar.gz extension
        name = key[len(self.prefix) :] if key.startswith(self.prefix) else key
        return name.rsplit(".tar.gz", 1)[0]

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
        """Upload a support package to S3."""
        if package_id is None:
            package_id = str(uuid.uuid4())

        key = self._object_key(package_id)
        checksum = self._compute_checksum(source_path)

        # Upload with metadata
        self._client.upload_file(
            Filename=str(source_path),
            Bucket=self.bucket,
            Key=key,
            ExtraArgs={
                "ContentType": "application/gzip",
                "Metadata": {
                    "original-filename": source_path.name,
                    "checksum-sha256": checksum,
                    "uploaded-at": datetime.now(timezone.utc).isoformat(),
                },
            },
        )

        return package_id

    async def download(
        self,
        package_id: str,
        dest_path: Path,
    ) -> Path:
        """Download a support package from S3."""
        key = self._object_key(package_id)

        try:
            # Check if object exists
            self._client.head_object(Bucket=self.bucket, Key=key)
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                raise PackageNotFoundError(package_id)
            raise

        # Download the file
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        self._client.download_file(
            Bucket=self.bucket,
            Key=key,
            Filename=str(dest_path),
        )

        return dest_path

    async def list_packages(self) -> List[PackageMetadata]:
        """List all support packages in S3."""
        packages = []

        response = self._client.list_objects_v2(
            Bucket=self.bucket,
            Prefix=self.prefix,
        )

        for obj in response.get("Contents", []):
            key = obj["Key"]
            if key.endswith(".tar.gz"):
                package_id = self._package_id_from_key(key)
                # Parse LastModified - handle both string and datetime
                last_modified = obj["LastModified"]
                if isinstance(last_modified, str):
                    uploaded_at = datetime.fromisoformat(last_modified.replace("Z", "+00:00"))
                else:
                    uploaded_at = last_modified

                packages.append(
                    PackageMetadata(
                        package_id=package_id,
                        filename=key.split("/")[-1],
                        size_bytes=obj["Size"],
                        uploaded_at=uploaded_at,
                        storage_path=key,
                    )
                )

        return packages

    async def get_metadata(self, package_id: str) -> Optional[PackageMetadata]:
        """Get metadata for a specific package from S3."""
        key = self._object_key(package_id)

        try:
            response = self._client.head_object(Bucket=self.bucket, Key=key)
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                return None
            raise

        # Get custom metadata
        metadata = response.get("Metadata", {})
        last_modified = response["LastModified"]
        if isinstance(last_modified, str):
            uploaded_at = datetime.fromisoformat(last_modified.replace("Z", "+00:00"))
        else:
            uploaded_at = last_modified

        return PackageMetadata(
            package_id=package_id,
            filename=metadata.get("original-filename", f"{package_id}.tar.gz"),
            size_bytes=response["ContentLength"],
            uploaded_at=uploaded_at,
            storage_path=key,
            checksum=metadata.get("checksum-sha256"),
        )

    async def delete(self, package_id: str) -> None:
        """Delete a support package from S3."""
        key = self._object_key(package_id)

        # Check if exists first
        if not await self.exists(package_id):
            raise PackageNotFoundError(package_id)

        self._client.delete_object(Bucket=self.bucket, Key=key)

    async def exists(self, package_id: str) -> bool:
        """Check if a package exists in S3."""
        key = self._object_key(package_id)

        try:
            self._client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                return False
            raise
