"""Shared helpers for support-package management."""

from __future__ import annotations

from redis_sre_agent.core.config import settings
from redis_sre_agent.tools.support_package.manager import SupportPackageManager
from redis_sre_agent.tools.support_package.storage import LocalStorage, S3Storage


def get_support_package_manager() -> SupportPackageManager:
    """Return a configured support-package manager."""
    storage_type = getattr(settings, "support_package_storage_type", "local")

    if storage_type == "s3":
        storage = S3Storage(
            bucket=getattr(settings, "support_package_s3_bucket", ""),
            prefix=getattr(settings, "support_package_s3_prefix", "support-packages/"),
            region=getattr(settings, "support_package_s3_region", None),
            endpoint_url=getattr(settings, "support_package_s3_endpoint", None),
        )
    else:
        storage = LocalStorage(base_path=settings.support_package_artifacts_dir / "storage")

    return SupportPackageManager(
        storage=storage,
        extract_dir=settings.support_package_artifacts_dir / "extracted",
    )
