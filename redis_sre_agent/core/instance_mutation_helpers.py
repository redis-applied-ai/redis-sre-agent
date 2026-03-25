"""Shared helpers for MCP instance mutation tools."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from redis_sre_agent.core.clusters import get_cluster_by_id
from redis_sre_agent.core.instance_inspection_helpers import _mask_instance_payload
from redis_sre_agent.core.instances import (
    RedisInstance,
    RedisInstanceType,
    delete_instance_index_doc,
    get_instances,
    save_instances,
)


def _normalize_cluster_id(cluster_id: Optional[str]) -> Optional[str]:
    if cluster_id is None:
        return None
    normalized = cluster_id.strip()
    return normalized or None


async def _validate_instance_cluster_link(
    *,
    cluster_id: Optional[str],
    instance_type: Optional[str],
) -> Optional[str]:
    normalized_cluster_id = _normalize_cluster_id(cluster_id)
    if normalized_cluster_id is None:
        return None

    cluster = await get_cluster_by_id(normalized_cluster_id)
    if not cluster:
        raise RuntimeError(f"Cluster with ID '{normalized_cluster_id}' not found")

    normalized_instance_type = (instance_type or "unknown").strip().lower()
    cluster_type = (
        cluster.cluster_type.value
        if hasattr(cluster.cluster_type, "value")
        else str(cluster.cluster_type).strip().lower()
    )
    compatible_cluster_types = {
        "redis_enterprise": {"redis_enterprise"},
        "oss_cluster": {"oss_cluster"},
        "redis_cloud": {"redis_cloud"},
    }
    allowed_cluster_types = compatible_cluster_types.get(normalized_instance_type)
    if allowed_cluster_types and cluster_type not in allowed_cluster_types:
        allowed_list = ", ".join(sorted(allowed_cluster_types))
        raise RuntimeError(
            f"instance_type '{normalized_instance_type}' is incompatible with cluster_type "
            f"'{cluster_type}'. Allowed cluster_type(s): {allowed_list}"
        )

    return normalized_cluster_id


def _apply_extension_updates(
    current_extension_data: Optional[Dict[str, Any]],
    *,
    set_extensions: Optional[Dict[str, Any]],
    unset_extensions: Optional[List[str]],
) -> Optional[Dict[str, Any]]:
    extension_data = dict(current_extension_data or {})
    if set_extensions:
        extension_data.update(set_extensions)
    if unset_extensions:
        for key in unset_extensions:
            extension_data.pop(key, None)
    return extension_data or None


async def update_instance_helper(
    instance_id: str,
    *,
    name: Optional[str] = None,
    connection_url: Optional[str] = None,
    environment: Optional[str] = None,
    usage: Optional[str] = None,
    description: Optional[str] = None,
    repo_url: Optional[str] = None,
    notes: Optional[str] = None,
    monitoring_identifier: Optional[str] = None,
    logging_identifier: Optional[str] = None,
    instance_type: Optional[str] = None,
    admin_url: Optional[str] = None,
    admin_username: Optional[str] = None,
    admin_password: Optional[str] = None,
    cluster_id: Optional[str] = None,
    redis_cloud_subscription_id: Optional[int] = None,
    redis_cloud_database_id: Optional[int] = None,
    redis_cloud_subscription_type: Optional[str] = None,
    redis_cloud_database_name: Optional[str] = None,
    status: Optional[str] = None,
    version: Optional[str] = None,
    memory: Optional[str] = None,
    connections: Optional[int] = None,
    user_id: Optional[str] = None,
    set_extensions: Optional[Dict[str, Any]] = None,
    unset_extensions: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Update fields on an existing Redis instance and return a masked payload."""
    instances = await get_instances()
    instance_index = next((i for i, item in enumerate(instances) if item.id == instance_id), None)
    if instance_index is None:
        return {"error": "Instance not found", "id": instance_id}

    current = instances[instance_index]
    update_data: Dict[str, Any] = {}

    if name is not None:
        update_data["name"] = name
    if connection_url is not None:
        update_data["connection_url"] = connection_url
    if environment is not None:
        update_data["environment"] = environment.lower()
    if usage is not None:
        update_data["usage"] = usage.lower()
    if description is not None:
        update_data["description"] = description
    if repo_url is not None:
        update_data["repo_url"] = repo_url
    if notes is not None:
        update_data["notes"] = notes
    if monitoring_identifier is not None:
        update_data["monitoring_identifier"] = monitoring_identifier
    if logging_identifier is not None:
        update_data["logging_identifier"] = logging_identifier
    if instance_type is not None:
        update_data["instance_type"] = RedisInstanceType(instance_type.lower())
    if admin_url is not None:
        update_data["admin_url"] = admin_url
    if admin_username is not None:
        update_data["admin_username"] = admin_username
    if admin_password is not None:
        update_data["admin_password"] = admin_password
    if cluster_id is not None:
        update_data["cluster_id"] = _normalize_cluster_id(cluster_id)
    if redis_cloud_subscription_id is not None:
        update_data["redis_cloud_subscription_id"] = redis_cloud_subscription_id
    if redis_cloud_database_id is not None:
        update_data["redis_cloud_database_id"] = redis_cloud_database_id
    if redis_cloud_subscription_type is not None:
        update_data["redis_cloud_subscription_type"] = redis_cloud_subscription_type.lower()
    if redis_cloud_database_name is not None:
        update_data["redis_cloud_database_name"] = redis_cloud_database_name
    if status is not None:
        update_data["status"] = status
    if version is not None:
        update_data["version"] = version
    if memory is not None:
        update_data["memory"] = memory
    if connections is not None:
        update_data["connections"] = connections
    if user_id is not None:
        update_data["user_id"] = user_id

    effective_instance_type = update_data.get("instance_type", current.instance_type)
    effective_cluster_id = update_data.get("cluster_id", current.cluster_id)
    if "cluster_id" in update_data:
        update_data["cluster_id"] = await _validate_instance_cluster_link(
            cluster_id=effective_cluster_id,
            instance_type=effective_instance_type,
        )

    if set_extensions or unset_extensions:
        update_data["extension_data"] = _apply_extension_updates(
            current.extension_data,
            set_extensions=set_extensions,
            unset_extensions=unset_extensions,
        )

    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    updated = current.model_copy(update=update_data)
    validated = RedisInstance(**updated.model_dump(mode="json"))
    instances[instance_index] = validated

    if not await save_instances(instances):
        raise RuntimeError("Failed to save updated instance")

    payload = _mask_instance_payload(validated)
    payload["status"] = "updated"
    return payload


async def delete_instance_helper(instance_id: str, *, confirm: bool = False) -> Dict[str, Any]:
    """Delete a Redis instance after explicit confirmation."""
    if not confirm:
        return {
            "error": "Confirmation required",
            "id": instance_id,
            "status": "cancelled",
        }

    instances = await get_instances()
    remaining_instances = [instance for instance in instances if instance.id != instance_id]
    if len(remaining_instances) == len(instances):
        return {"error": "Instance not found", "id": instance_id}

    if not await save_instances(remaining_instances):
        raise RuntimeError("Failed to save after deletion")

    try:
        await delete_instance_index_doc(instance_id)
    except Exception:
        pass

    return {"id": instance_id, "status": "deleted"}
