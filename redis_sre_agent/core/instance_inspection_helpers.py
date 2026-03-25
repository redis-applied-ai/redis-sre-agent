"""Shared helpers for MCP instance inspection tools."""

from __future__ import annotations

from typing import Any, Dict

from pydantic import SecretStr

from redis_sre_agent.core.instances import get_instance_by_id, mask_redis_url
from redis_sre_agent.core.redis import test_redis_connection


def _mask_instance_payload(instance: Any) -> Dict[str, Any]:
    payload = instance.model_dump(mode="json", exclude={"connection_url", "admin_password"})
    payload["connection_url"] = mask_redis_url(instance.connection_url)
    if instance.admin_password:
        payload["admin_password"] = "***"
    return payload


def _connection_url_value(connection_url: Any) -> str:
    if isinstance(connection_url, SecretStr):
        return connection_url.get_secret_value()
    return str(connection_url)


async def get_instance_helper(instance_id: str) -> Dict[str, Any]:
    """Get a masked payload for a configured instance."""
    instance = await get_instance_by_id(instance_id)
    if not instance:
        return {"error": "Instance not found", "id": instance_id}
    return _mask_instance_payload(instance)


async def check_redis_url_helper(connection_url: str) -> Dict[str, Any]:
    """Test a Redis URL without creating an instance."""
    success = await test_redis_connection(url=connection_url)
    return {
        "success": success,
        "message": "Successfully connected" if success else "Failed to connect",
        "url": mask_redis_url(connection_url),
    }


async def check_instance_helper(instance_id: str) -> Dict[str, Any]:
    """Test connectivity to a configured instance."""
    instance = await get_instance_by_id(instance_id)
    if not instance:
        return {"success": False, "error": "Instance not found", "id": instance_id}

    success = await test_redis_connection(url=_connection_url_value(instance.connection_url))
    return {
        "success": success,
        "message": "Successfully connected" if success else "Failed to connect",
        "instance_id": instance_id,
        "name": instance.name,
    }
