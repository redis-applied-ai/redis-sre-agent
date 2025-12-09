"""Redis Cloud Management API tool provider.

This module provides tools for managing Redis Cloud resources through the
Redis Cloud Management API.

Example usage:
    from redis_sre_agent.tools.cloud.redis_cloud import RedisCloudConfig, RedisCloudToolProvider

    provider = RedisCloudToolProvider(config=RedisCloudConfig())
    async with provider:
        # Call the concrete async methods directly; ToolProvider.tools() wires
        # tools for LLM use on top of these methods.
        result = await provider.list_subscriptions()
"""

from .provider import RedisCloudConfig, RedisCloudToolProvider

__all__ = [
    "RedisCloudToolProvider",
    "RedisCloudConfig",
]
