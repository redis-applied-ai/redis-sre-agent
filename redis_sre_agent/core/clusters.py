"""Redis cluster domain model and storage helpers.

Clusters are stored as Redis Hash documents with a RediSearch index for
efficient querying by environment, status, cluster_type, and user_id.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, SecretStr, field_serializer, field_validator, model_validator
from redisvl.query import CountQuery, FilterQuery
from redisvl.query.filter import FilterExpression, Tag

from .encryption import encrypt_secret, get_secret_value
from .redis import SRE_CLUSTERS_INDEX, get_clusters_index, get_redis_client

logger = logging.getLogger(__name__)


class RedisClusterType(str, Enum):
    """Supported cluster types."""

    oss_cluster = "oss_cluster"
    redis_enterprise = "redis_enterprise"
    redis_cloud = "redis_cloud"
    unknown = "unknown"


class RedisCluster(BaseModel):
    """Cluster-level configuration and metadata."""

    id: str
    name: str
    cluster_type: RedisClusterType = RedisClusterType.unknown
    environment: str = Field(..., description="Environment: development, staging, production, test")
    description: str
    notes: Optional[str] = None

    # Cluster-level enterprise admin credentials
    admin_url: Optional[str] = None
    admin_username: Optional[str] = None
    admin_password: Optional[SecretStr] = None

    status: Optional[str] = "unknown"
    version: Optional[str] = None
    last_checked: Optional[str] = None

    extension_data: Optional[Dict[str, Any]] = Field(
        default=None, description="Data storage for extensions, such as custom tool providers"
    )
    extension_secrets: Optional[Dict[str, SecretStr]] = Field(
        default=None, description="Secret storage for extensions, such as custom tool providers"
    )

    created_by: str = Field(
        default="user",
        description="Who created this cluster: 'user' (pre-configured) or 'agent' (dynamically created)",
    )
    user_id: Optional[str] = Field(
        default=None, description="User ID who owns this cluster (for pre-configured clusters)"
    )
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @field_serializer("admin_password", when_used="json")
    def dump_secret(self, v):
        if v is None:
            return None
        return v.get_secret_value() if isinstance(v, SecretStr) else v

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        value = (v or "").strip()
        if not value:
            raise ValueError("Cluster name cannot be empty")
        return value

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        allowed_environments = {"development", "staging", "production", "test"}
        normalized = (v or "").strip().lower()
        if normalized not in allowed_environments:
            raise ValueError("Environment must be one of: development, staging, production, test")
        return normalized

    @field_validator("created_by")
    @classmethod
    def validate_created_by(cls, v: str) -> str:
        if v not in {"user", "agent"}:
            raise ValueError(f"created_by must be 'user' or 'agent', got: {v}")
        return v

    @model_validator(mode="after")
    def validate_enterprise_admin_fields(self):
        has_url = bool((self.admin_url or "").strip())
        has_username = bool((self.admin_username or "").strip())
        has_password = bool(self.admin_password)

        if self.cluster_type == RedisClusterType.redis_enterprise:
            if not (has_url and has_username and has_password):
                raise ValueError(
                    "cluster_type=redis_enterprise requires admin_url, admin_username, "
                    "and admin_password"
                )
            return self

        if has_url or has_username or has_password:
            raise ValueError(
                "admin_url/admin_username/admin_password are only valid for "
                "cluster_type=redis_enterprise"
            )

        return self


@dataclass
class ClusterQueryResult:
    """Result of a cluster query with pagination info."""

    clusters: List[RedisCluster]
    total: int
    limit: int
    offset: int


async def _ensure_clusters_index_exists() -> None:
    try:
        index = await get_clusters_index()
        if not await index.exists():
            await index.create()
    except Exception:
        # Best-effort only; don't fail persistence on index errors
        return


def _to_epoch(ts: Optional[str]) -> float:
    if not ts:
        return 0.0
    try:
        if ts.endswith("Z"):
            ts = ts.replace("Z", "+00:00")
        return datetime.fromisoformat(ts).timestamp()
    except Exception:
        try:
            return float(ts)
        except Exception:
            return 0.0


async def get_clusters() -> List[RedisCluster]:
    """Load configured clusters using a single FT.SEARCH over the clusters index."""
    try:
        await _ensure_clusters_index_exists()
        index = await get_clusters_index()

        try:
            total = await index.query(CountQuery(filter_expression="*"))
        except Exception:
            total = 1000

        if not total:
            return []

        q = FilterQuery(
            filter_expression="*",
            return_fields=["data"],
            num_results=int(total) if isinstance(total, int) else 1000,
        )
        results = await index.query(q)

        out: List[RedisCluster] = []
        for doc in results or []:
            try:
                raw = doc.get("data")
                if not raw:
                    continue
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8")
                cluster_data = json.loads(raw)
                if cluster_data.get("admin_password"):
                    cluster_data["admin_password"] = get_secret_value(
                        cluster_data["admin_password"]
                    )
                out.append(RedisCluster(**cluster_data))
            except Exception as e:
                logger.exception("Failed to load cluster from search result: %s. Skipping.", e)
        return out
    except Exception as e:
        logger.exception("Failed to get clusters from Redis: %s", e)
        return []


async def query_clusters(
    *,
    environment: Optional[str] = None,
    status: Optional[str] = None,
    cluster_type: Optional[str] = None,
    user_id: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> ClusterQueryResult:
    """Query clusters with server-side filtering and pagination."""
    try:
        await _ensure_clusters_index_exists()
        index = await get_clusters_index()

        filter_expr = None

        if environment:
            env_filter = Tag("environment") == environment.lower()
            filter_expr = env_filter if filter_expr is None else (filter_expr & env_filter)

        if status:
            status_filter = Tag("status") == status.lower()
            filter_expr = status_filter if filter_expr is None else (filter_expr & status_filter)

        if cluster_type:
            type_filter = Tag("cluster_type") == cluster_type.lower()
            filter_expr = type_filter if filter_expr is None else (filter_expr & type_filter)

        if user_id:
            user_filter = Tag("user_id") == user_id
            filter_expr = user_filter if filter_expr is None else (filter_expr & user_filter)

        if search:
            name_filter = FilterExpression(f"@name:{{*{search}*}}")
            filter_expr = name_filter if filter_expr is None else (filter_expr & name_filter)

        count_expr = filter_expr if filter_expr is not None else "*"
        try:
            total = await index.query(CountQuery(filter_expression=count_expr))
            total = int(total) if isinstance(total, int) else 0
        except Exception:
            total = 0

        if total == 0:
            return ClusterQueryResult(clusters=[], total=0, limit=limit, offset=offset)

        limit = max(1, min(limit, 1000))
        offset = max(0, offset)

        fq = FilterQuery(return_fields=["data"], num_results=limit).sort_by("updated_at", asc=False)

        if filter_expr is not None:
            fq.set_filter(filter_expr)
        fq.paging(offset, limit)

        results = await index.query(fq)

        clusters: List[RedisCluster] = []
        for doc in results or []:
            try:
                raw = doc.get("data")
                if not raw:
                    continue
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8")
                cluster_data = json.loads(raw)
                if cluster_data.get("admin_password"):
                    cluster_data["admin_password"] = get_secret_value(
                        cluster_data["admin_password"]
                    )
                clusters.append(RedisCluster(**cluster_data))
            except Exception as e:
                logger.exception("Failed to load cluster from query result: %s. Skipping.", e)

        return ClusterQueryResult(clusters=clusters, total=total, limit=limit, offset=offset)

    except Exception as e:
        logger.exception("Failed to query clusters: %s", e)
        return ClusterQueryResult(clusters=[], total=0, limit=limit, offset=offset)


async def _upsert_cluster_index_doc(cluster: RedisCluster) -> bool:
    try:
        await _ensure_clusters_index_exists()
        client = get_redis_client()
        key = f"{SRE_CLUSTERS_INDEX}:{cluster.id}"

        cluster_dict = cluster.model_dump(mode="json")
        if cluster_dict.get("admin_password"):
            cluster_dict["admin_password"] = encrypt_secret(cluster_dict["admin_password"])

        created_ts = _to_epoch(cluster_dict.get("created_at"))
        updated_ts = _to_epoch(cluster_dict.get("updated_at"))
        if updated_ts <= 0:
            updated_ts = datetime.now(timezone.utc).timestamp()

        ctype = cluster.cluster_type
        try:
            ctype_val = ctype.value
        except Exception:
            ctype_val = str(ctype)

        await client.hset(
            key,
            mapping={
                "name": cluster.name or "",
                "environment": (cluster.environment or "").lower(),
                "cluster_type": ctype_val,
                "user_id": cluster.user_id or "",
                "status": (cluster.status or "unknown").lower(),
                "created_at": created_ts,
                "updated_at": updated_ts,
                "data": json.dumps(cluster_dict),
            },
        )
        return True
    except Exception:
        return False


async def _upsert_clusters_index_docs(clusters: List[RedisCluster]) -> bool:
    ok = True
    for cluster in clusters:
        ok = await _upsert_cluster_index_doc(cluster) and ok
    return ok


async def delete_cluster_index_doc(cluster_id: str) -> None:
    try:
        client = get_redis_client()
        await client.delete(f"{SRE_CLUSTERS_INDEX}:{cluster_id}")
    except Exception:
        return


async def save_clusters(clusters: List[RedisCluster]) -> bool:
    """Persist clusters using per-cluster hash docs + search index."""
    try:
        client = get_redis_client()
        await _ensure_clusters_index_exists()

        upsert_ok = await _upsert_clusters_index_docs(clusters)
        if not upsert_ok:
            return False

        keep_ids = {cluster.id for cluster in clusters}

        stale_ids: List[str] = []
        try:
            index = await get_clusters_index()
            try:
                total = await index.query(CountQuery(filter_expression="*"))
            except Exception:
                total = 1000

            if total:
                q = FilterQuery(
                    filter_expression="*",
                    return_fields=["data"],
                    num_results=int(total) if isinstance(total, int) else 1000,
                )
                results = await index.query(q)
                for doc in results or []:
                    try:
                        raw = doc.get("data")
                        if not raw:
                            continue
                        if isinstance(raw, bytes):
                            raw = raw.decode("utf-8")
                        d = json.loads(raw)
                        doc_id = d.get("id")
                        if doc_id and doc_id not in keep_ids:
                            stale_ids.append(doc_id)
                    except Exception:
                        continue
        except Exception:
            prefix = f"{SRE_CLUSTERS_INDEX}:"
            cursor: int = 0
            while True:
                cursor, batch = await client.scan(cursor=cursor, match=f"{prefix}*")
                if not batch:
                    if cursor == 0:
                        break
                    continue
                for key in batch:
                    try:
                        k = key.decode("utf-8") if isinstance(key, (bytes, bytearray)) else str(key)
                        cluster_id = k.split(":", 1)[1]
                        if cluster_id not in keep_ids:
                            stale_ids.append(cluster_id)
                    except Exception:
                        continue
                if cursor == 0:
                    break

        for stale_id in stale_ids:
            try:
                await client.delete(f"{SRE_CLUSTERS_INDEX}:{stale_id}")
            except Exception:
                pass

        # Best-effort rebuild of the unified discovery catalog, keeping cluster
        # CRUD and direct lookup semantics unchanged.
        try:
            from redis_sre_agent.core.targets import sync_target_catalog

            await sync_target_catalog(clusters=clusters)
        except Exception:
            logger.debug("Best-effort target catalog sync failed after saving clusters")
        return True
    except Exception as e:
        logger.exception("Failed to save clusters to Redis: %s", e)
        return False


async def get_cluster_by_id(cluster_id: str) -> Optional[RedisCluster]:
    """Get a single cluster by ID using direct key lookup."""
    try:
        client = get_redis_client()
        key = f"{SRE_CLUSTERS_INDEX}:{cluster_id}"
        data = await client.hget(key, "data")

        if not data:
            return None

        if isinstance(data, bytes):
            data = data.decode("utf-8")

        cluster_data = json.loads(data)
        if cluster_data.get("admin_password"):
            cluster_data["admin_password"] = get_secret_value(cluster_data["admin_password"])

        return RedisCluster(**cluster_data)
    except Exception as e:
        logger.exception("Failed to get cluster by ID %s: %s", cluster_id, e)
        return None
