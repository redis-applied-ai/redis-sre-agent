"""Backfill migration from RedisInstance records to RedisCluster links.

Migration intent:
- For cluster-capable instance types with missing cluster_id, create/reuse a
  RedisCluster and set instance.cluster_id.
- Keep deprecated instance admin_* fields in place for compatibility mode.
- Be safe for startup automation (lock + completion marker).
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import socket
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import SecretStr

from redis_sre_agent.core import clusters as core_clusters
from redis_sre_agent.core import instances as core_instances
from redis_sre_agent.core.clusters import RedisCluster, RedisClusterType
from redis_sre_agent.core.instances import RedisInstance
from redis_sre_agent.core.redis import get_redis_client

logger = logging.getLogger(__name__)

MIGRATION_NAME = "instances_to_clusters_v1"
MIGRATION_VERSION = 1
MIGRATION_METADATA_KEY = "instance_cluster_migration"
MIGRATION_LOCK_KEY = "sre:migration:instances_to_clusters:v1:lock"
MIGRATION_DONE_KEY = "sre:migration:instances_to_clusters:v1:done"
MIGRATION_LOCK_TTL_SECONDS = 120

INSTANCE_TYPE_TO_CLUSTER_TYPE: Dict[str, RedisClusterType] = {
    "redis_enterprise": RedisClusterType.redis_enterprise,
    "oss_cluster": RedisClusterType.oss_cluster,
    "redis_cloud": RedisClusterType.redis_cloud,
}


@dataclass
class InstanceToClusterMigrationSummary:
    migration: str = MIGRATION_NAME
    version: int = MIGRATION_VERSION
    source: str = "startup"
    dry_run: bool = False
    force: bool = False
    run_id: str = ""
    started_at: str = ""
    finished_at: str = ""
    scanned: int = 0
    eligible: int = 0
    clusters_created: int = 0
    clusters_reused: int = 0
    instances_linked: int = 0
    skipped_existing_cluster_id: int = 0
    skipped_unsupported_type: int = 0
    skipped_missing_enterprise_admin: int = 0
    skipped_due_lock: bool = False
    skipped_due_marker: bool = False
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_optional_string(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = value.strip() if isinstance(value, str) else str(value).strip()
    return text or None


def _secret_to_string(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, SecretStr):
        text = value.get_secret_value()
        return text.strip() or None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    text = str(value).strip()
    return text or None


def _normalize_environment(value: Any) -> str:
    normalized = (_normalize_optional_string(value) or "").lower()
    aliases = {"dev": "development", "stage": "staging", "prod": "production", "qa": "test"}
    resolved = aliases.get(normalized, normalized)
    if resolved in {"development", "staging", "production", "test"}:
        return resolved
    return "development"


def _instance_type_value(value: Any) -> str:
    if hasattr(value, "value"):
        return str(value.value).strip().lower()
    return str(value or "").strip().lower()


def _merge_extension_metadata(
    extension_data: Optional[Dict[str, Any]],
    *,
    metadata: Dict[str, Any],
) -> Dict[str, Any]:
    merged = copy.deepcopy(extension_data) if isinstance(extension_data, dict) else {}
    current = merged.get(MIGRATION_METADATA_KEY)
    if isinstance(current, dict):
        out = copy.deepcopy(current)
        out.update(metadata)
        merged[MIGRATION_METADATA_KEY] = out
    else:
        merged[MIGRATION_METADATA_KEY] = metadata
    return merged


def _enterprise_fingerprint(
    *,
    admin_url: str,
    admin_username: str,
    admin_password: str,
    environment: str,
    user_id: Optional[str],
) -> str:
    material = "|".join(
        [
            admin_url.strip().lower(),
            admin_username.strip(),
            admin_password.strip(),
            environment.strip().lower(),
            (user_id or "").strip(),
        ]
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _generate_cluster_id(base: str, used_ids: set[str]) -> str:
    normalized = base.strip().lower().replace(" ", "-")
    candidate = normalized
    if candidate not in used_ids:
        return candidate
    suffix = 1
    while True:
        candidate = f"{normalized}-{suffix}"
        if candidate not in used_ids:
            return candidate
        suffix += 1


def _build_cluster_name(instance: RedisInstance, *, environment: str, cluster_type: str) -> str:
    base_name = _normalize_optional_string(instance.name) or instance.id
    prefix = "migrated-enterprise" if cluster_type == "redis_enterprise" else "migrated-cluster"
    return f"{prefix}-{environment}-{base_name}"[:120]


def _migration_metadata(
    *,
    run_id: str,
    source: str,
    migrated_at: str,
    created_from_instance_id: Optional[str] = None,
    linked_cluster_id: Optional[str] = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "migration": MIGRATION_NAME,
        "version": MIGRATION_VERSION,
        "run_id": run_id,
        "source": source,
        "migrated_at": migrated_at,
    }
    if created_from_instance_id:
        payload["created_from_instance_id"] = created_from_instance_id
    if linked_cluster_id:
        payload["linked_cluster_id"] = linked_cluster_id
    return payload


def _build_enterprise_lookup(
    clusters: List[RedisCluster],
) -> tuple[Dict[str, str], Dict[str, str], set[str]]:
    fingerprint_to_cluster_id: Dict[str, str] = {}
    created_from_instance_id_to_cluster_id: Dict[str, str] = {}
    used_ids: set[str] = set()

    for cluster in clusters:
        used_ids.add(cluster.id)

        ext_data = cluster.extension_data if isinstance(cluster.extension_data, dict) else {}
        migration_meta = ext_data.get(MIGRATION_METADATA_KEY)
        if isinstance(migration_meta, dict):
            created_from_id = _normalize_optional_string(migration_meta.get("created_from_instance_id"))
            if created_from_id:
                created_from_instance_id_to_cluster_id.setdefault(created_from_id, cluster.id)

        if cluster.cluster_type != RedisClusterType.redis_enterprise:
            continue

        admin_url = _normalize_optional_string(cluster.admin_url)
        admin_username = _normalize_optional_string(cluster.admin_username)
        admin_password = _secret_to_string(cluster.admin_password)
        if not (admin_url and admin_username and admin_password):
            continue

        fingerprint = _enterprise_fingerprint(
            admin_url=admin_url,
            admin_username=admin_username,
            admin_password=admin_password,
            environment=_normalize_environment(cluster.environment),
            user_id=_normalize_optional_string(cluster.user_id),
        )
        fingerprint_to_cluster_id.setdefault(fingerprint, cluster.id)

    return fingerprint_to_cluster_id, created_from_instance_id_to_cluster_id, used_ids


async def _release_lock(client, lock_token: str) -> None:
    try:
        await client.eval(
            "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end",
            1,
            MIGRATION_LOCK_KEY,
            lock_token,
        )
    except Exception:
        return


async def run_instances_to_clusters_migration(
    *,
    dry_run: bool = False,
    force: bool = False,
    source: str = "startup",
) -> InstanceToClusterMigrationSummary:
    """Backfill cluster links for existing cluster-capable RedisInstance records."""
    summary = InstanceToClusterMigrationSummary(
        source=source,
        dry_run=dry_run,
        force=force,
        run_id=str(uuid.uuid4()),
        started_at=_now_iso(),
    )
    client = get_redis_client()
    lock_token = f"{socket.gethostname()}:{summary.run_id}"
    lock_acquired = False

    try:
        lock_acquired = bool(
            await client.set(
                MIGRATION_LOCK_KEY,
                lock_token,
                nx=True,
                ex=MIGRATION_LOCK_TTL_SECONDS,
            )
        )
        if not lock_acquired:
            summary.skipped_due_lock = True
            summary.finished_at = _now_iso()
            return summary

        if not force:
            if bool(await client.exists(MIGRATION_DONE_KEY)):
                summary.skipped_due_marker = True
                summary.finished_at = _now_iso()
                return summary

        instances = await core_instances.get_instances()
        clusters = await core_clusters.get_clusters()
        summary.scanned = len(instances)

        fingerprint_to_cluster_id, created_from_instance_id_to_cluster_id, used_cluster_ids = (
            _build_enterprise_lookup(clusters)
        )

        updated_instances: List[RedisInstance] = list(instances)
        migrated_at = _now_iso()

        for idx, instance in enumerate(instances):
            if _normalize_optional_string(instance.cluster_id):
                summary.skipped_existing_cluster_id += 1
                continue

            instance_type = _instance_type_value(instance.instance_type)
            target_cluster_type = INSTANCE_TYPE_TO_CLUSTER_TYPE.get(instance_type)
            if target_cluster_type is None:
                summary.skipped_unsupported_type += 1
                continue

            summary.eligible += 1
            linked_cluster_id: Optional[str] = None
            reused = False

            if target_cluster_type == RedisClusterType.redis_enterprise:
                admin_url = _normalize_optional_string(instance.admin_url)
                admin_username = _normalize_optional_string(instance.admin_username)
                admin_password = _secret_to_string(instance.admin_password)

                if not (admin_url and admin_username and admin_password):
                    summary.skipped_missing_enterprise_admin += 1
                    continue

                fingerprint = _enterprise_fingerprint(
                    admin_url=admin_url,
                    admin_username=admin_username,
                    admin_password=admin_password,
                    environment=_normalize_environment(instance.environment),
                    user_id=_normalize_optional_string(instance.user_id),
                )
                linked_cluster_id = fingerprint_to_cluster_id.get(fingerprint)
                if linked_cluster_id:
                    reused = True
                else:
                    cluster_id = _generate_cluster_id(
                        f"cluster-migrated-{fingerprint[:12]}",
                        used_cluster_ids,
                    )
                    new_cluster = RedisCluster(
                        id=cluster_id,
                        name=_build_cluster_name(
                            instance,
                            environment=_normalize_environment(instance.environment),
                            cluster_type=target_cluster_type.value,
                        ),
                        cluster_type=target_cluster_type,
                        environment=_normalize_environment(instance.environment),
                        description=instance.description,
                        notes=instance.notes,
                        admin_url=admin_url,
                        admin_username=admin_username,
                        admin_password=SecretStr(admin_password),
                        status=instance.status,
                        version=instance.version,
                        last_checked=instance.last_checked,
                        created_by=instance.created_by,
                        user_id=instance.user_id,
                        created_at=instance.created_at,
                        updated_at=migrated_at,
                        extension_data=_merge_extension_metadata(
                            instance.extension_data,
                            metadata=_migration_metadata(
                                run_id=summary.run_id,
                                source=source,
                                migrated_at=migrated_at,
                                created_from_instance_id=instance.id,
                            ),
                        ),
                    )
                    clusters.append(new_cluster)
                    used_cluster_ids.add(cluster_id)
                    fingerprint_to_cluster_id[fingerprint] = cluster_id
                    created_from_instance_id_to_cluster_id.setdefault(instance.id, cluster_id)
                    linked_cluster_id = cluster_id
                    summary.clusters_created += 1
            else:
                # Conservative merge behavior for weak-identity types:
                # one cluster per source instance, with reuse only if previously migrated.
                linked_cluster_id = created_from_instance_id_to_cluster_id.get(instance.id)
                if linked_cluster_id:
                    reused = True
                else:
                    cluster_id = _generate_cluster_id(
                        f"cluster-migrated-{instance.id}",
                        used_cluster_ids,
                    )
                    new_cluster = RedisCluster(
                        id=cluster_id,
                        name=_build_cluster_name(
                            instance,
                            environment=_normalize_environment(instance.environment),
                            cluster_type=target_cluster_type.value,
                        ),
                        cluster_type=target_cluster_type,
                        environment=_normalize_environment(instance.environment),
                        description=instance.description,
                        notes=instance.notes,
                        status=instance.status,
                        version=instance.version,
                        last_checked=instance.last_checked,
                        created_by=instance.created_by,
                        user_id=instance.user_id,
                        created_at=instance.created_at,
                        updated_at=migrated_at,
                        extension_data=_merge_extension_metadata(
                            instance.extension_data,
                            metadata=_migration_metadata(
                                run_id=summary.run_id,
                                source=source,
                                migrated_at=migrated_at,
                                created_from_instance_id=instance.id,
                            ),
                        ),
                    )
                    clusters.append(new_cluster)
                    used_cluster_ids.add(cluster_id)
                    created_from_instance_id_to_cluster_id[instance.id] = cluster_id
                    linked_cluster_id = cluster_id
                    summary.clusters_created += 1

            if reused:
                summary.clusters_reused += 1

            if not linked_cluster_id:
                summary.errors.append(f"Failed to resolve cluster for instance '{instance.id}'")
                continue

            updated_instances[idx] = instance.model_copy(
                update={
                    "cluster_id": linked_cluster_id,
                    "updated_at": migrated_at,
                    "extension_data": _merge_extension_metadata(
                        instance.extension_data,
                        metadata=_migration_metadata(
                            run_id=summary.run_id,
                            source=source,
                            migrated_at=migrated_at,
                            linked_cluster_id=linked_cluster_id,
                        ),
                    ),
                }
            )
            summary.instances_linked += 1

        if not dry_run and not summary.errors:
            clusters_saved = await core_clusters.save_clusters(clusters)
            if not clusters_saved:
                summary.errors.append("Failed to persist migrated cluster records")
            else:
                instances_saved = await core_instances.save_instances(updated_instances)
                if not instances_saved:
                    summary.errors.append("Failed to persist migrated instance records")

        if not dry_run and not summary.errors:
            await client.set(
                MIGRATION_DONE_KEY,
                json.dumps(
                    {
                        "migration": MIGRATION_NAME,
                        "version": MIGRATION_VERSION,
                        "run_id": summary.run_id,
                        "source": source,
                        "finished_at": _now_iso(),
                        "scanned": summary.scanned,
                        "eligible": summary.eligible,
                        "clusters_created": summary.clusters_created,
                        "clusters_reused": summary.clusters_reused,
                        "instances_linked": summary.instances_linked,
                    }
                ),
            )

        summary.finished_at = _now_iso()
        return summary
    finally:
        if lock_acquired:
            await _release_lock(client, lock_token)
