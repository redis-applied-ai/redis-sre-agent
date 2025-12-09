"""
Redis instance domain model and storage helpers.

TODO: Use a better persistence structure than serializing a list of JSON
      objects into a string.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, SecretStr, field_serializer, field_validator
from redisvl.query import CountQuery, FilterQuery

from .encryption import encrypt_secret, get_secret_value
from .keys import RedisKeys
from .redis import (
    SRE_INSTANCES_INDEX,
    get_instances_index,
    get_redis_client,  # noqa: F401  # Expose for tests that patch via this module path
)

logger = logging.getLogger(__name__)


def mask_redis_url(url: Any) -> str:
    """Mask username and password in a Redis URL for safe display/logging.

    Accepts a plain string or a SecretStr. The function will unwrap SecretStr
    internally to avoid callers needing to access secret values directly.

    Args:
        url: Redis connection URL (e.g., redis://user:pass@host:port/db) or SecretStr

    Returns:
        Masked URL (e.g., redis://***:***@host:port/db)
    """
    try:
        # Avoid exposing secrets to callers: unwrap here if needed
        if isinstance(url, SecretStr):
            url = url.get_secret_value()
        elif not isinstance(url, str):
            url = str(url)

        from urllib.parse import urlparse

        parsed = urlparse(url)
        if parsed.username or parsed.password:
            # Reconstruct URL with masked credentials
            masked_netloc = parsed.hostname or ""
            if parsed.port:
                masked_netloc += f":{parsed.port}"
            if parsed.username or parsed.password:
                masked_netloc = f"***:***@{masked_netloc}"

            masked_url = f"{parsed.scheme}://{masked_netloc}{parsed.path}"
            if parsed.query:
                masked_url += f"?{parsed.query}"
            if parsed.fragment:
                masked_url += f"#{parsed.fragment}"
            return masked_url
        # No credentials present, return as-is
        return url
    except Exception as e:
        logger.warning(f"Failed to mask URL credentials: {e}")
        # Generic masked placeholder without revealing host or port
        return "redis://***:***@<host>:<port>"


class RedisInstanceType(str, Enum):
    oss_single = "oss_single"
    oss_cluster = "oss_cluster"
    redis_enterprise = "redis_enterprise"
    redis_cloud = "redis_cloud"
    unknown = "unknown"


class RedisInstance(BaseModel):
    """Redis instance configuration (domain model).

    Validation allows loading instances with invalid URLs from storage so they
    can be fixed later by callers. Input validation should be enforced at API edges.
    """

    id: str
    name: str
    connection_url: SecretStr = Field(
        ..., description="Redis connection URL (e.g., redis://localhost:6379)"
    )
    environment: str = Field(..., description="Environment: development, staging, production")

    @field_serializer("connection_url", "admin_password", when_used="json")
    def dump_secret(self, v):
        if v is None:
            return None
        return v.get_secret_value() if isinstance(v, SecretStr) else v

    usage: str = Field(..., description="Usage type: cache, analytics, session, queue, or custom")
    description: str
    repo_url: Optional[str] = None
    notes: Optional[str] = None
    monitoring_identifier: Optional[str] = Field(
        None, description="Name used in monitoring systems (defaults to instance name)"
    )
    logging_identifier: Optional[str] = Field(
        None, description="Name used in logging systems (defaults to instance name)"
    )
    instance_type: "RedisInstanceType" = Field(
        ...,
        description="Redis instance type: oss_single, oss_cluster, redis_enterprise, redis_cloud, unknown",
    )
    admin_url: Optional[str] = Field(
        None,
        description="Redis Enterprise admin API URL (e.g., https://cluster.example.com:9443). Only for instance_type='redis_enterprise'.",
    )
    admin_username: Optional[str] = Field(
        None,
        description="Redis Enterprise admin API username. Only for instance_type='redis_enterprise'.",
    )
    admin_password: Optional[SecretStr] = Field(
        None,
        description="Redis Enterprise admin API password. Only for instance_type='redis_enterprise'.",
    )
    # Redis Cloud identifiers
    redis_cloud_subscription_id: Optional[int] = Field(
        None, description="Redis Cloud subscription ID. Only for instance_type='redis_cloud'."
    )
    redis_cloud_database_id: Optional[int] = Field(
        None, description="Redis Cloud database ID. Only for instance_type='redis_cloud'."
    )
    # Redis Cloud metadata for routing
    redis_cloud_subscription_type: Optional[str] = Field(
        default=None,
        description="Redis Cloud subscription type: 'pro' or 'essentials' (aka 'fixed'). Only for instance_type='redis_cloud'.",
    )
    redis_cloud_database_name: Optional[str] = Field(
        default=None,
        description="Redis Cloud database name (used when ID is not available). Only for instance_type='redis_cloud'.",
    )
    status: Optional[str] = "unknown"
    version: Optional[str] = None
    memory: Optional[str] = None
    connections: Optional[int] = None
    last_checked: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    extension_data: Optional[Dict[str, Any]] = Field(
        default=None, description="Data storage for extensions, such as custom tool providers"
    )
    extension_secrets: Optional[Dict[str, SecretStr]] = Field(
        default=None, description="Secret storage for extensions, such as custom tool providers"
    )
    created_by: str = Field(
        default="user",
        description="Who created this instance: 'user' (pre-configured) or 'agent' (dynamically created)",
    )
    user_id: Optional[str] = Field(
        default=None, description="User ID who owns this instance (for pre-configured instances)"
    )

    @field_validator("connection_url")
    @classmethod
    def validate_not_app_redis(cls, v: SecretStr) -> SecretStr:
        """Ensure this is not the application's own Redis database."""
        try:
            from redis_sre_agent.core.config import settings

            url_value = v.get_secret_value() if isinstance(v, SecretStr) else v
            settings_url = (
                settings.redis_url.get_secret_value()
                if isinstance(settings.redis_url, SecretStr)
                else settings.redis_url
            )
            if url_value == settings_url:
                raise ValueError("Cannot create instance for application's own Redis database.")
        except Exception:
            pass
        return v

    @field_validator("created_by")
    @classmethod
    def validate_created_by(cls, v: str) -> str:
        if v not in ["user", "agent"]:
            raise ValueError(f"created_by must be 'user' or 'agent', got: {v}")
        return v

    async def get_bdb_uid(
        self,
        *,
        redis_url: Optional[str] = None,
        bdb_name: Optional[str] = None,
        verify_ssl: Optional[bool] = None,
        timeout: float = 10.0,
    ) -> Optional[int]:
        """Discover the Redis Enterprise database UID (BDB ID) for this instance.

        Strategy:
        - If bdb_name is provided: fetch /v1/bdbs and return the uid for an exact name match.
        - Else: parse the port from redis_url or this instance's connection_url and match
                against 'port' (non-TLS) or 'ssl_port' (TLS/rediss), falling back to
                scanning 'endpoints' if present.

        Returns:
            UID as int if found, else None.
        """
        try:
            # Require Redis Enterprise for BDB discovery
            if self.instance_type != RedisInstanceType.redis_enterprise:
                return None
            if not self.admin_url:
                return None

            # Extract credentials
            admin_username = self.admin_username or ""
            admin_password = (
                self.admin_password.get_secret_value()
                if isinstance(self.admin_password, SecretStr)
                else (self.admin_password or "")
            )

            # Compute TLS verify flag from param or env
            import os

            if verify_ssl is not None:
                verify_flag = bool(verify_ssl)
            else:
                env_val = os.getenv("TOOLS_REDIS_ENTERPRISE_ADMIN_VERIFY_SSL", "true").lower()
                verify_flag = env_val not in ("0", "false", "no", "off")

            # Determine target port and whether TLS is used
            from urllib.parse import urlparse

            target_port: Optional[int] = None
            use_tls = False
            try:
                url_to_parse = redis_url or (
                    self.connection_url.get_secret_value()
                    if isinstance(self.connection_url, SecretStr)
                    else str(self.connection_url)
                )
                parsed = urlparse(url_to_parse) if url_to_parse else None
                if parsed and parsed.port:
                    target_port = int(parsed.port)
                scheme = (parsed.scheme or "").lower() if parsed else ""
                use_tls = scheme in ("rediss", "redis+ssl", "redis+tls")
            except Exception:
                pass

            import httpx

            auth = (admin_username, admin_password) if admin_username else None
            async with httpx.AsyncClient(
                base_url=self.admin_url,
                auth=auth,
                verify=verify_flag,
                timeout=timeout,
                headers={"Accept": "application/json"},
            ) as client:
                resp = await client.get("/v1/bdbs")
                resp.raise_for_status()
                bdbs = resp.json()
                if not isinstance(bdbs, list):
                    # Some versions may return {"bdbs": [...]} instead
                    bdbs = bdbs.get("bdbs", []) if isinstance(bdbs, dict) else []

                # Name preference
                if bdb_name:
                    for b in bdbs:
                        try:
                            if (b.get("name") or "") == bdb_name:
                                return int(b.get("uid"))
                        except Exception:
                            continue

                # Port matching
                if target_port is not None:
                    for b in bdbs:
                        try:
                            port = b.get("ssl_port") if use_tls else b.get("port")
                            if port is None:
                                # Fallback to endpoints array
                                eps = b.get("endpoints") or []
                                # endpoints may be list of dicts with {"port": ..., "tls": bool}
                                for ep in eps:
                                    ep_port = ep.get("port")
                                    ep_tls = bool(ep.get("tls")) if "tls" in ep else None
                                    if ep_port == target_port and (
                                        ep_tls is None or ep_tls == use_tls
                                    ):
                                        return int(b.get("uid"))
                                continue
                            if int(port) == target_port:
                                return int(b.get("uid"))
                        except Exception:
                            continue
                return None
        except Exception as e:
            logger.debug(f"get_bdb_uid error: {e}")
            return None


async def get_instances() -> List[RedisInstance]:
    """Load configured instances using a single FT.SEARCH over the instances index."""
    try:
        # Ensure index exists (best-effort) and read instance docs from RediSearch
        await _ensure_instances_index_exists()
        index = await get_instances_index()

        # Determine how many docs exist, then fetch them in one search call
        try:
            total = await index.query(CountQuery(filter_expression="*"))
        except Exception:
            total = 1000  # sensible fallback

        if not total:
            return []

        q = FilterQuery(
            filter_expression="*",
            return_fields=["data"],  # full JSON payload is stored under 'data'
            num_results=int(total) if isinstance(total, int) else 1000,
        )
        results = await index.query(q)

        out: List[RedisInstance] = []
        for doc in results or []:
            try:
                raw = doc.get("data")
                if not raw:
                    continue
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8")
                inst_data = json.loads(raw)
                if inst_data.get("connection_url"):
                    inst_data["connection_url"] = get_secret_value(inst_data["connection_url"])
                if inst_data.get("admin_password"):
                    inst_data["admin_password"] = get_secret_value(inst_data["admin_password"])
                out.append(RedisInstance(**inst_data))
            except Exception as e:
                logger.error("Failed to load instance from search result: %s. Skipping.", e)
        return out
    except Exception as e:
        logger.error("Failed to get instances from Redis: %s", e)
        return []


# --- Instances search index helpers (non-breaking integration) ---
async def _ensure_instances_index_exists() -> None:
    try:
        index = await get_instances_index()
        if not await index.exists():
            await index.create()
    except Exception:
        # Best-effort only; don't fail persistence on index errors
        return


def _to_epoch(ts: Optional[str]) -> float:
    if not ts:
        return 0.0
    try:
        # Handle Z suffix
        if ts.endswith("Z"):
            ts = ts.replace("Z", "+00:00")
        return datetime.fromisoformat(ts).timestamp()
    except Exception:
        try:
            return float(ts)
        except Exception:
            return 0.0


async def _upsert_instance_index_doc(instance: "RedisInstance") -> bool:
    try:
        await _ensure_instances_index_exists()
        client = get_redis_client()
        key = f"{SRE_INSTANCES_INDEX}:{instance.id}"

        # Serialize full instance data (with encrypted secrets) into 'data'
        inst_dict = instance.model_dump(mode="json")
        if inst_dict.get("connection_url"):
            inst_dict["connection_url"] = encrypt_secret(inst_dict["connection_url"])
        if inst_dict.get("admin_password"):
            inst_dict["admin_password"] = encrypt_secret(inst_dict["admin_password"])

        # Index timestamps (numeric) but keep ISO strings inside 'data'
        created_ts = _to_epoch(inst_dict.get("created_at"))
        updated_ts = _to_epoch(inst_dict.get("updated_at"))
        if updated_ts <= 0:
            updated_ts = datetime.now(timezone.utc).timestamp()

        # Normalize instance_type to value when Enum
        itype = instance.instance_type
        try:
            itype_val = itype.value  # Enum
        except Exception:
            itype_val = str(itype)

        await client.hset(
            key,
            mapping={
                "name": instance.name or "",
                "environment": (instance.environment or "").lower(),
                "usage": (instance.usage or "").lower(),
                "instance_type": itype_val,
                "user_id": instance.user_id or "",
                "status": (instance.status or "unknown").lower(),
                "created_at": created_ts,
                "updated_at": updated_ts,
                "data": json.dumps(inst_dict),
            },
        )
        return True
    except Exception:
        return False


async def _upsert_instances_index_docs(instances: List["RedisInstance"]) -> bool:
    ok = True
    for inst in instances:
        ok = await _upsert_instance_index_doc(inst) and ok
    return ok


async def delete_instance_index_doc(instance_id: str) -> None:
    try:
        client = get_redis_client()
        await client.delete(f"{SRE_INSTANCES_INDEX}:{instance_id}")
    except Exception:
        return


async def save_instances(instances: List[RedisInstance]) -> bool:
    """Persist instances using per-instance hash docs + search index (no legacy list)."""
    try:
        client = get_redis_client()
        await _ensure_instances_index_exists()

        # Upsert all provided instances
        upsert_ok = await _upsert_instances_index_docs(instances)
        if not upsert_ok:
            return False

        # Replace semantics: delete any stored docs not in the provided set
        keep_ids = {inst.id for inst in instances}

        # Prefer RediSearch enumeration (single FT.SEARCH) and fall back to SCAN if needed
        stale_ids: List[str] = []
        try:
            index = await get_instances_index()
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
            # Fallback: SCAN keys by prefix
            prefix = f"{SRE_INSTANCES_INDEX}:"
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
                        instance_id = k.split(":", 1)[1]
                        if instance_id not in keep_ids:
                            stale_ids.append(instance_id)
                    except Exception:
                        continue
                if cursor == 0:
                    break

        # Delete stale docs
        for sid in stale_ids:
            try:
                await client.delete(f"{SRE_INSTANCES_INDEX}:{sid}")
            except Exception:
                pass
        return True
    except Exception as e:
        logger.exception("Failed to save instances to Redis: %s", e)
        return False


async def get_session_instances(thread_id: str) -> List[RedisInstance]:
    """Get per-thread dynamically created instances from Redis (TTL-backed)."""
    try:
        redis_client = get_redis_client()
        key = RedisKeys.thread_instances(thread_id)
        raw = await redis_client.get(key)
        if not raw:
            return []
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        data = json.loads(raw)
        out: List[RedisInstance] = []
        for inst_data in data:
            if inst_data.get("connection_url"):
                inst_data["connection_url"] = get_secret_value(inst_data["connection_url"])
            if inst_data.get("admin_password"):
                inst_data["admin_password"] = get_secret_value(inst_data["admin_password"])
            out.append(RedisInstance(**inst_data))
        return out
    except Exception as e:
        logger.error("Failed to get session instances for %s: %s", thread_id, e)
        return []


async def add_session_instance(thread_id: str, instance: RedisInstance) -> bool:
    """Append an instance to session memory (dedupe by name or URL)."""
    try:
        redis_client = get_redis_client()
        existing = await get_session_instances(thread_id)
        for ex in existing:
            ex_url = ex.connection_url.get_secret_value()
            in_url = instance.connection_url.get_secret_value()
            if ex.name == instance.name or ex_url == in_url:
                return True
        # Serialize + encrypt
        items = []
        for inst in existing + [instance]:
            d = inst.model_dump(mode="json")
            if d.get("connection_url"):
                d["connection_url"] = encrypt_secret(d["connection_url"])
            if d.get("admin_password"):
                d["admin_password"] = encrypt_secret(d["admin_password"])
            items.append(d)
        await redis_client.set(RedisKeys.thread_instances(thread_id), json.dumps(items), ex=3600)
        return True
    except Exception as e:
        logger.error("Failed to add session instance for %s: %s", thread_id, e)
        return False


async def get_all_instances(
    user_id: Optional[str] = None, thread_id: Optional[str] = None
) -> List[RedisInstance]:
    configured = await get_instances()
    if user_id:
        configured = [
            inst for inst in configured if inst.user_id == user_id or inst.user_id is None
        ]
    session_instances: List[RedisInstance] = []
    if thread_id:
        session_instances = await get_session_instances(thread_id)
    urls = {i.connection_url.get_secret_value() for i in configured}
    out = list(configured)
    for s in session_instances:
        if s.connection_url.get_secret_value() not in urls:
            out.append(s)
    return out


async def create_instance(
    *,
    name: str,
    connection_url: str,
    environment: str,
    usage: str,
    description: str,
    created_by: str = "agent",
    user_id: Optional[str] = None,
    repo_url: Optional[str] = None,
    notes: Optional[str] = None,
    instance_type: "RedisInstanceType" = RedisInstanceType.unknown,
) -> RedisInstance:
    """Create and persist a new instance for dynamic agent flows."""
    try:
        instances = await get_instances()
        if any(inst.name == name for inst in instances):
            raise ValueError(f"Instance with name '{name}' already exists")
        instance_id = f"redis-{environment}-{int(datetime.now().timestamp())}"
        new_inst = RedisInstance(
            id=instance_id,
            name=name,
            connection_url=connection_url,
            environment=environment,
            usage=usage,
            description=description,
            repo_url=repo_url,
            notes=notes,
            created_by=created_by,
            user_id=user_id,
            instance_type=instance_type,
        )
        instances.append(new_inst)
        if not await save_instances(instances):
            raise ValueError("Failed to save instance to storage")
        return new_inst
    except Exception as e:
        logger.error("Failed to create instance programmatically: %s", e)
        raise


# Convenience lookups
async def get_instance_by_id(instance_id: str) -> Optional[RedisInstance]:
    for inst in await get_instances():
        if inst.id == instance_id:
            return inst
    return None


async def get_instance_by_name(instance_name: str) -> Optional[RedisInstance]:
    for inst in await get_instances():
        if inst.name == instance_name:
            return inst
    return None


async def get_instance_map() -> Dict[str, RedisInstance]:
    return {inst.id: inst for inst in await get_instances()}


async def get_instance_name(instance_id: str) -> Optional[str]:
    inst = await get_instance_by_id(instance_id)
    return inst.name if inst else None
