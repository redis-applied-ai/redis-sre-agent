"""Support package API endpoints."""

import logging
import tempfile
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from pydantic import BaseModel

from redis_sre_agent.core.config import settings
from redis_sre_agent.tools.support_package.manager import SupportPackageManager
from redis_sre_agent.tools.support_package.storage import LocalStorage, S3Storage

logger = logging.getLogger(__name__)

router = APIRouter()


def get_manager() -> SupportPackageManager:
    """Get a configured SupportPackageManager."""
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


# Response models
class PackageUploadResponse(BaseModel):
    """Response for package upload."""

    package_id: str
    status: str = "uploaded"
    filename: str


class PackageInfoResponse(BaseModel):
    """Response for package info."""

    package_id: str
    filename: str
    size_bytes: int
    uploaded_at: str
    is_extracted: bool
    storage_path: Optional[str] = None
    checksum: Optional[str] = None


class PackageListResponse(BaseModel):
    """Response for package list."""

    packages: List[PackageInfoResponse]
    total: int


class PackageExtractResponse(BaseModel):
    """Response for package extraction."""

    package_id: str
    status: str = "extracted"
    path: str


class PackageDeleteResponse(BaseModel):
    """Response for package deletion."""

    package_id: str
    status: str = "deleted"


@router.post(
    "/support-packages/upload",
    response_model=PackageUploadResponse,
    status_code=201,
)
async def upload_package(
    file: UploadFile = File(...),
    package_id: Optional[str] = Query(None, description="Custom package ID"),
):
    """Upload a support package."""
    try:
        manager = get_manager()

        # Save uploaded file to temp location
        with tempfile.NamedTemporaryFile(delete=False, suffix=".tar.gz") as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = Path(tmp.name)

        try:
            result_id = await manager.upload(tmp_path, package_id=package_id)
            return PackageUploadResponse(
                package_id=result_id,
                status="uploaded",
                filename=file.filename or "unknown",
            )
        finally:
            # Clean up temp file
            tmp_path.unlink(missing_ok=True)

    except Exception as e:
        logger.error(f"Failed to upload package: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/support-packages", response_model=PackageListResponse)
async def list_packages(
    limit: int = Query(100, ge=1, le=1000),
):
    """List uploaded support packages."""
    try:
        manager = get_manager()
        packages = await manager.list_packages()

        package_responses = []
        for pkg in packages[:limit]:
            is_extracted = await manager.is_extracted(pkg.package_id)
            package_responses.append(
                PackageInfoResponse(
                    package_id=pkg.package_id,
                    filename=pkg.filename,
                    size_bytes=pkg.size_bytes,
                    uploaded_at=pkg.uploaded_at.isoformat(),
                    is_extracted=is_extracted,
                    storage_path=pkg.storage_path,
                    checksum=pkg.checksum,
                )
            )

        return PackageListResponse(packages=package_responses, total=len(packages))

    except Exception as e:
        logger.error(f"Failed to list packages: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/support-packages/{package_id}", response_model=PackageInfoResponse)
async def get_package_info(package_id: str):
    """Get information about a support package."""
    try:
        manager = get_manager()
        metadata = await manager.get_metadata(package_id)

        if not metadata:
            raise HTTPException(status_code=404, detail=f"Package not found: {package_id}")

        is_extracted = await manager.is_extracted(package_id)

        return PackageInfoResponse(
            package_id=metadata.package_id,
            filename=metadata.filename,
            size_bytes=metadata.size_bytes,
            uploaded_at=metadata.uploaded_at.isoformat(),
            is_extracted=is_extracted,
            storage_path=metadata.storage_path,
            checksum=metadata.checksum,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get package info: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/support-packages/{package_id}/extract",
    response_model=PackageExtractResponse,
)
async def extract_package(package_id: str):
    """Extract a support package."""
    try:
        manager = get_manager()
        extract_path = await manager.extract(package_id)

        return PackageExtractResponse(
            package_id=package_id,
            status="extracted",
            path=str(extract_path),
        )

    except Exception as e:
        logger.error(f"Failed to extract package: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/support-packages/{package_id}", response_model=PackageDeleteResponse)
async def delete_package(package_id: str):
    """Delete a support package."""
    try:
        manager = get_manager()
        await manager.delete(package_id)

        return PackageDeleteResponse(
            package_id=package_id,
            status="deleted",
        )

    except Exception as e:
        logger.error(f"Failed to delete package: {e}")
        raise HTTPException(status_code=500, detail=str(e))
