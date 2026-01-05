"""Support package storage backends.

This module provides storage abstractions for support packages,
supporting both local filesystem and S3-compatible storage.
"""

from .local import LocalStorage
from .protocols import PackageMetadata, PackageNotFoundError, SupportPackageStorage
from .s3 import S3Storage

__all__ = [
    "SupportPackageStorage",
    "PackageMetadata",
    "PackageNotFoundError",
    "LocalStorage",
    "S3Storage",
]
