"""Shared helpers for cache and version MCP tools."""

from __future__ import annotations

from typing import Any, Dict, Optional

from redis_sre_agent import __version__
from redis_sre_agent.core.redis import get_redis_client
from redis_sre_agent.tools.cache import ToolCache


def get_tool_cache(instance_id: Optional[str] = None) -> ToolCache:
    """Build a tool cache scoped to one instance or all instances."""
    return ToolCache(
        redis_client=get_redis_client(),
        instance_id=instance_id or "__all__",
    )


async def cache_stats_helper(instance_id: Optional[str] = None) -> Dict[str, Any]:
    """Return cache statistics for one instance or all instances."""
    cache = get_tool_cache(instance_id if instance_id else "__all__")
    if instance_id:
        return await cache.stats()
    return await cache.stats_all()


async def cache_clear_helper(
    *,
    instance_id: Optional[str] = None,
    clear_all: bool = False,
    confirm: bool = False,
) -> Dict[str, Any]:
    """Clear cached tool outputs with explicit confirmation."""
    if not confirm:
        return {
            "error": "Confirmation required",
            "status": "cancelled",
            "instance_id": instance_id,
        }

    if not instance_id and not clear_all:
        return {
            "error": "Must specify instance_id or clear_all=True",
            "status": "failed",
        }

    if clear_all:
        cache = get_tool_cache("__all__")
        deleted = await cache.clear_all()
        return {
            "status": "cleared",
            "scope": "all",
            "deleted": deleted,
        }

    cache = get_tool_cache(instance_id)
    deleted = await cache.clear()
    return {
        "status": "cleared",
        "scope": "instance",
        "instance_id": instance_id,
        "deleted": deleted,
    }


def version_helper() -> Dict[str, str]:
    """Return package version metadata."""
    return {
        "name": "redis-sre-agent",
        "version": __version__,
    }
