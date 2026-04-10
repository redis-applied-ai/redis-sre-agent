"""Redis cluster management API endpoints."""

import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import (
    BaseModel,
    Field,
    SecretStr,
    ValidationError,
    field_serializer,
    field_validator,
)
from ulid import ULID

from redis_sre_agent.core import clusters as core_clusters
from redis_sre_agent.core.cluster_admin_defaults import (
    build_enterprise_admin_missing_fields_error,
    missing_enterprise_admin_fields,
    resolve_enterprise_admin_fields,
)

logger = logging.getLogger(__name__)

router = APIRouter()

_ALLOWED_ENVIRONMENTS = {"development", "staging", "production", "test"}
_ALLOWED_CLUSTER_TYPES = {"oss_cluster", "redis_enterprise", "redis_cloud", "unknown"}
_ALLOWED_CREATED_BY = {"user", "agent"}


def to_response(cluster: "core_clusters.RedisCluster") -> "RedisClusterResponse":
    """Convert domain cluster to API-safe response with masked credentials."""
    admin_pwd = (
        cluster.admin_password.get_secret_value()
        if cluster.admin_password and isinstance(cluster.admin_password, SecretStr)
        else cluster.admin_password
    )
    return RedisClusterResponse(
        id=cluster.id,
        name=cluster.name,
        cluster_type=cluster.cluster_type,
        environment=cluster.environment,
        description=cluster.description,
        notes=cluster.notes,
        admin_url=cluster.admin_url,
        admin_username=cluster.admin_username,
        admin_password="***" if admin_pwd else None,
        status=cluster.status,
        version=cluster.version,
        last_checked=cluster.last_checked,
        created_at=cluster.created_at,
        updated_at=cluster.updated_at,
        created_by=cluster.created_by,
        user_id=cluster.user_id,
    )


class RedisClusterResponse(BaseModel):
    """Response model for Redis cluster with masked credentials."""

    id: str
    name: str
    cluster_type: str = "unknown"
    environment: str
    description: str
    notes: Optional[str] = None
    admin_url: Optional[str] = None
    admin_username: Optional[str] = None
    admin_password: Optional[str] = None  # Always masked as "***"
    status: Optional[str] = "unknown"
    version: Optional[str] = None
    last_checked: Optional[str] = None
    created_at: str
    updated_at: str
    created_by: str = "user"
    user_id: Optional[str] = None


class ClusterListResponse(BaseModel):
    """Response model for paginated cluster list with filtering."""

    clusters: List[RedisClusterResponse]
    total: int = Field(..., description="Total number of clusters matching the filter")
    limit: int = Field(..., description="Maximum number of results returned")
    offset: int = Field(..., description="Number of results skipped")


class CreateClusterRequest(BaseModel):
    """Request model for creating a Redis cluster."""

    name: str
    cluster_type: str = Field(
        "unknown",
        description="Redis cluster type: oss_cluster, redis_enterprise, redis_cloud, unknown",
    )
    environment: str
    description: str
    notes: Optional[str] = None

    admin_url: Optional[str] = Field(
        None,
        description="Redis Enterprise admin API URL. Required for cluster_type='redis_enterprise'.",
    )
    admin_username: Optional[str] = Field(
        None,
        description="Redis Enterprise admin API username. Required for cluster_type='redis_enterprise'.",
    )
    admin_password: Optional[SecretStr] = Field(
        None,
        description="Redis Enterprise admin API password. Required for cluster_type='redis_enterprise'.",
    )

    status: Optional[str] = "unknown"
    version: Optional[str] = None
    last_checked: Optional[str] = None
    created_by: str = Field(
        default="user", description="Who created this cluster: 'user' or 'agent'"
    )
    user_id: Optional[str] = Field(default=None, description="User ID who owns this cluster")

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        normalized = (v or "").strip().lower()
        if normalized not in _ALLOWED_ENVIRONMENTS:
            raise ValueError("Environment must be one of: development, staging, production, test")
        return normalized

    @field_validator("cluster_type")
    @classmethod
    def validate_cluster_type(cls, v: str) -> str:
        normalized = (v or "").strip().lower()
        if normalized not in _ALLOWED_CLUSTER_TYPES:
            raise ValueError(
                "cluster_type must be one of: oss_cluster, redis_enterprise, redis_cloud, unknown"
            )
        return normalized

    @field_validator("created_by")
    @classmethod
    def validate_created_by(cls, v: str) -> str:
        normalized = (v or "").strip().lower()
        if normalized not in _ALLOWED_CREATED_BY:
            raise ValueError("created_by must be 'user' or 'agent'")
        return normalized

    @field_serializer("admin_password", when_used="json")
    def dump_secret(self, v):
        if v is None:
            return None
        return v.get_secret_value() if isinstance(v, SecretStr) else v


class UpdateClusterRequest(BaseModel):
    """Request model for updating a Redis cluster."""

    name: Optional[str] = None
    cluster_type: Optional[str] = Field(
        None,
        description="Redis cluster type: oss_cluster, redis_enterprise, redis_cloud, unknown",
    )
    environment: Optional[str] = None
    description: Optional[str] = None
    notes: Optional[str] = None
    admin_url: Optional[str] = None
    admin_username: Optional[str] = None
    admin_password: Optional[SecretStr] = None
    status: Optional[str] = None
    version: Optional[str] = None
    last_checked: Optional[str] = None
    created_by: Optional[str] = None
    user_id: Optional[str] = None

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        normalized = (v or "").strip().lower()
        if normalized not in _ALLOWED_ENVIRONMENTS:
            raise ValueError("Environment must be one of: development, staging, production, test")
        return normalized

    @field_validator("cluster_type")
    @classmethod
    def validate_cluster_type(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        normalized = (v or "").strip().lower()
        if normalized not in _ALLOWED_CLUSTER_TYPES:
            raise ValueError(
                "cluster_type must be one of: oss_cluster, redis_enterprise, redis_cloud, unknown"
            )
        return normalized

    @field_validator("created_by")
    @classmethod
    def validate_created_by(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        normalized = (v or "").strip().lower()
        if normalized not in _ALLOWED_CREATED_BY:
            raise ValueError("created_by must be 'user' or 'agent'")
        return normalized

    @field_serializer("admin_password", when_used="json")
    def dump_secret(self, v):
        if v is None:
            return None
        return v.get_secret_value() if isinstance(v, SecretStr) else v


@router.get("/clusters", response_model=ClusterListResponse)
async def list_clusters(
    environment: Optional[str] = Query(None, description="Filter by environment"),
    status: Optional[str] = Query(None, description="Filter by status"),
    cluster_type: Optional[str] = Query(None, description="Filter by cluster type"),
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    search: Optional[str] = Query(None, description="Search by cluster name"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of results"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
):
    """List Redis clusters with server-side filtering and pagination."""
    try:
        result = await core_clusters.query_clusters(
            environment=environment,
            status=status,
            cluster_type=cluster_type,
            user_id=user_id,
            search=search,
            limit=limit,
            offset=offset,
        )
        return ClusterListResponse(
            clusters=[to_response(cluster) for cluster in result.clusters],
            total=result.total,
            limit=result.limit,
            offset=result.offset,
        )
    except Exception as e:
        logger.error(f"Failed to list clusters: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve clusters")


@router.post("/clusters", response_model=RedisClusterResponse, status_code=201)
async def create_cluster(request: CreateClusterRequest):
    """Create a new Redis cluster."""
    try:
        clusters = await core_clusters.get_clusters()

        if any(cluster.name == request.name for cluster in clusters):
            raise HTTPException(
                status_code=400, detail=f"Cluster with name '{request.name}' already exists"
            )

        resolved_admin = resolve_enterprise_admin_fields(
            cluster_type=request.cluster_type,
            admin_url=request.admin_url,
            admin_username=request.admin_username,
            admin_password=request.admin_password,
        )
        if request.cluster_type == "redis_enterprise":
            missing_fields = missing_enterprise_admin_fields(
                admin_url=resolved_admin.admin_url,
                admin_username=resolved_admin.admin_username,
                admin_password=resolved_admin.admin_password,
            )
            if missing_fields:
                raise HTTPException(
                    status_code=400,
                    detail=build_enterprise_admin_missing_fields_error(missing_fields),
                )
        elif any(
            (
                resolved_admin.admin_url,
                resolved_admin.admin_username,
                resolved_admin.admin_password,
            )
        ):
            raise HTTPException(
                status_code=400,
                detail=(
                    "admin_url/admin_username/admin_password are only valid for "
                    "cluster_type=redis_enterprise"
                ),
            )

        cluster_id = f"cluster-{request.environment}-{ULID()}"
        new_cluster = core_clusters.RedisCluster(
            id=cluster_id,
            name=request.name,
            cluster_type=request.cluster_type,
            environment=request.environment,
            description=request.description,
            notes=request.notes,
            admin_url=resolved_admin.admin_url,
            admin_username=resolved_admin.admin_username,
            admin_password=resolved_admin.admin_password,
            status=request.status,
            version=request.version,
            last_checked=request.last_checked,
            created_by=request.created_by,
            user_id=request.user_id,
        )

        clusters.append(new_cluster)
        if not await core_clusters.save_clusters(clusters):
            raise HTTPException(status_code=500, detail="Failed to save cluster")

        logger.info(f"Created Redis cluster: {new_cluster.name} ({new_cluster.id})")
        return to_response(new_cluster)

    except HTTPException:
        raise
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to create cluster: {e}")
        raise HTTPException(status_code=500, detail="Failed to create cluster")


@router.get("/clusters/{cluster_id}", response_model=RedisClusterResponse)
async def get_cluster(cluster_id: str):
    """Get a specific Redis cluster by ID with masked credentials."""
    try:
        cluster = await core_clusters.get_cluster_by_id(cluster_id)
        if not cluster:
            raise HTTPException(status_code=404, detail=f"Cluster with ID '{cluster_id}' not found")
        return to_response(cluster)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get cluster {cluster_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve cluster")


@router.put("/clusters/{cluster_id}", response_model=RedisClusterResponse)
async def update_cluster(cluster_id: str, request: UpdateClusterRequest):
    """Update a Redis cluster."""
    try:
        clusters = await core_clusters.get_clusters()

        cluster_index = None
        for i, cluster in enumerate(clusters):
            if cluster.id == cluster_id:
                cluster_index = i
                break

        if cluster_index is None:
            raise HTTPException(status_code=404, detail=f"Cluster with ID '{cluster_id}' not found")

        current_cluster = clusters[cluster_index]
        update_data = request.model_dump(exclude_unset=True, mode="json")
        update_data["updated_at"] = datetime.now(timezone.utc).isoformat()

        # Preserve existing secret when UI submits masked value
        if "admin_password" in update_data:
            pwd_str = update_data["admin_password"]
            if pwd_str and ("***" in pwd_str or pwd_str == "***"):
                del update_data["admin_password"]

        if "name" in update_data and update_data["name"] != current_cluster.name:
            if any(c.id != cluster_id and c.name == update_data["name"] for c in clusters):
                raise HTTPException(
                    status_code=400,
                    detail=f"Cluster with name '{update_data['name']}' already exists",
                )

        updated_cluster = current_cluster.model_copy(update=update_data)

        # Enforce final validation against domain model rules after merge
        try:
            validated_cluster = core_clusters.RedisCluster(
                **updated_cluster.model_dump(mode="json")
            )
        except ValidationError as e:
            raise HTTPException(status_code=400, detail=str(e))

        clusters[cluster_index] = validated_cluster
        if not await core_clusters.save_clusters(clusters):
            raise HTTPException(status_code=500, detail="Failed to save updated cluster")

        logger.info(f"Updated Redis cluster: {validated_cluster.name} ({validated_cluster.id})")
        return to_response(validated_cluster)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update cluster {cluster_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to update cluster")


@router.delete("/clusters/{cluster_id}")
async def delete_cluster(cluster_id: str):
    """Delete a Redis cluster."""
    try:
        clusters = await core_clusters.get_clusters()

        original_count = len(clusters)
        clusters = [cluster for cluster in clusters if cluster.id != cluster_id]
        if len(clusters) == original_count:
            raise HTTPException(status_code=404, detail=f"Cluster with ID '{cluster_id}' not found")

        if not await core_clusters.save_clusters(clusters):
            raise HTTPException(status_code=500, detail="Failed to save after deletion")

        try:
            await core_clusters.delete_cluster_index_doc(cluster_id)
        except Exception:
            pass

        logger.info(f"Deleted Redis cluster: {cluster_id}")
        return {"message": f"Cluster {cluster_id} deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete cluster {cluster_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete cluster")
