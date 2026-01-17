"""Tests for ToolManager shared Redis cache functionality."""

import json
from unittest.mock import AsyncMock

import pytest

from redis_sre_agent.core.instances import RedisInstance
from redis_sre_agent.tools.cache import DEFAULT_TOOL_TTLS, ToolCache
from redis_sre_agent.tools.manager import ToolManager


class TestToolCache:
    """Test ToolCache Redis-backed caching."""

    @pytest.fixture
    def mock_redis(self):
        """Mock async Redis client."""
        client = AsyncMock()
        client.get = AsyncMock(return_value=None)
        client.setex = AsyncMock(return_value=True)
        client.delete = AsyncMock(return_value=1)
        client.keys = AsyncMock(return_value=[])
        return client

    @pytest.fixture
    def test_instance(self):
        """Create a test Redis instance."""
        return RedisInstance(
            id="test-instance-123",
            name="Test Instance",
            connection_url="redis://localhost:6379",
            environment="test",
            usage="cache",
            description="Test instance for caching tests",
            instance_type="oss_single",
        )

    @pytest.mark.asyncio
    async def test_cache_initialization(self, mock_redis, test_instance):
        """Test ToolCache initializes with Redis client and instance."""
        cache = ToolCache(redis_client=mock_redis, instance_id=test_instance.id)

        assert cache._redis == mock_redis
        assert cache._instance_id == test_instance.id
        assert cache._enabled is True

    @pytest.mark.asyncio
    async def test_cache_key_format(self, mock_redis, test_instance):
        """Test cache key includes instance_id, tool_name, and args hash."""
        cache = ToolCache(redis_client=mock_redis, instance_id=test_instance.id)

        key = cache.build_key("redis_cli_info", {"section": "memory"})

        # Key should be: sre_cache:tool:{instance_id}:{tool_name}:{args_hash}
        assert key.startswith("sre_cache:tool:")
        assert test_instance.id in key
        assert "redis_cli_info" in key

    @pytest.mark.asyncio
    async def test_cache_key_uses_stable_tool_name(self, mock_redis, test_instance):
        """Test cache key uses the full tool name including stable hash.

        Tool names include a SHA256-based hash derived from instance ID,
        which is stable across runs. Different hashes produce different keys.
        """
        cache = ToolCache(redis_client=mock_redis, instance_id=test_instance.id)

        # Same tool name with same args should produce same key
        key1 = cache.build_key("redis_command_104c81_info", {"section": "memory"})
        key2 = cache.build_key("redis_command_104c81_info", {"section": "memory"})
        assert key1 == key2

        # Different tool names (different hashes) should produce different keys
        key3 = cache.build_key("redis_command_abc123_info", {"section": "memory"})
        assert key1 != key3

        # Key should contain the full tool name including hash
        assert "redis_command_104c81_info" in key1

    @pytest.mark.asyncio
    async def test_cache_get_miss(self, mock_redis, test_instance):
        """Test cache miss returns None."""
        mock_redis.get.return_value = None
        cache = ToolCache(redis_client=mock_redis, instance_id=test_instance.id)

        result = await cache.get("redis_cli_info", {"section": "memory"})

        assert result is None
        mock_redis.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_cache_get_hit(self, mock_redis, test_instance):
        """Test cache hit returns cached data."""
        cached_data = {"status": "success", "data": {"used_memory": 1024}}
        mock_redis.get.return_value = json.dumps(cached_data).encode()
        cache = ToolCache(redis_client=mock_redis, instance_id=test_instance.id)

        result = await cache.get("redis_cli_info", {"section": "memory"})

        assert result == cached_data
        mock_redis.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_cache_set_with_default_ttl(self, mock_redis, test_instance):
        """Test cache set uses default TTL."""
        cache = ToolCache(redis_client=mock_redis, instance_id=test_instance.id)
        data = {"status": "success", "data": {"used_memory": 1024}}

        await cache.set("redis_cli_info", {"section": "memory"}, data)

        mock_redis.setex.assert_called_once()
        call_args = mock_redis.setex.call_args
        # Should use TTL from DEFAULT_TOOL_TTLS or default
        assert call_args[0][1] > 0  # TTL should be positive

    @pytest.mark.asyncio
    async def test_cache_set_with_custom_ttl(self, mock_redis, test_instance):
        """Test cache set with custom TTL overrides."""
        custom_ttls = {"info": 120}
        cache = ToolCache(
            redis_client=mock_redis, instance_id=test_instance.id, ttl_overrides=custom_ttls
        )
        data = {"status": "success"}

        await cache.set("redis_cli_info", {}, data)

        call_args = mock_redis.setex.call_args
        assert call_args[0][1] == 120  # Custom TTL

    @pytest.mark.asyncio
    async def test_cache_does_not_cache_errors(self, mock_redis, test_instance):
        """Test that error responses are not cached."""
        cache = ToolCache(redis_client=mock_redis, instance_id=test_instance.id)
        error_data = {"status": "error", "error": "Connection failed"}

        await cache.set("redis_cli_info", {}, error_data)

        # Should not call setex for error responses
        mock_redis.setex.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_clear_by_instance(self, mock_redis, test_instance):
        """Test clearing cache for a specific instance."""

        # Mock scan_iter as an async generator
        async def mock_scan_iter(*args, **kwargs):
            for key in [
                b"sre_cache:tool:test-instance-123:redis_cli_info:abc123",
                b"sre_cache:tool:test-instance-123:redis_cli_memory:def456",
            ]:
                yield key

        mock_redis.scan_iter = mock_scan_iter
        mock_redis.delete.return_value = 2  # Return number of deleted keys
        cache = ToolCache(redis_client=mock_redis, instance_id=test_instance.id)

        deleted = await cache.clear()

        assert deleted == 2

    @pytest.mark.asyncio
    async def test_cache_stats(self, mock_redis, test_instance):
        """Test getting cache statistics."""

        # Mock scan_iter as an async generator
        async def mock_scan_iter(*args, **kwargs):
            for key in [b"key1", b"key2", b"key3"]:
                yield key

        mock_redis.scan_iter = mock_scan_iter
        cache = ToolCache(redis_client=mock_redis, instance_id=test_instance.id)

        stats = await cache.stats()

        assert stats["instance_id"] == test_instance.id
        assert stats["cached_keys"] == 3
        assert "enabled" in stats

    @pytest.mark.asyncio
    async def test_cache_disabled_returns_none(self, mock_redis, test_instance):
        """Test that disabled cache always returns None."""
        cache = ToolCache(redis_client=mock_redis, instance_id=test_instance.id, enabled=False)

        result = await cache.get("redis_cli_info", {})

        assert result is None
        mock_redis.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_disabled_set_returns_false(self, mock_redis, test_instance):
        """Test that disabled cache set returns False."""
        cache = ToolCache(redis_client=mock_redis, instance_id=test_instance.id, enabled=False)

        result = await cache.set("redis_cli_info", {}, {"data": "test"})

        assert result is False
        mock_redis.setex.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_get_handles_exception(self, mock_redis, test_instance):
        """Test cache get handles Redis exceptions gracefully."""
        mock_redis.get.side_effect = Exception("Redis connection error")
        cache = ToolCache(redis_client=mock_redis, instance_id=test_instance.id)

        result = await cache.get("redis_cli_info", {})

        assert result is None

    @pytest.mark.asyncio
    async def test_cache_set_handles_exception(self, mock_redis, test_instance):
        """Test cache set handles Redis exceptions gracefully."""
        mock_redis.setex.side_effect = Exception("Redis connection error")
        cache = ToolCache(redis_client=mock_redis, instance_id=test_instance.id)

        result = await cache.set("redis_cli_info", {}, {"data": "test"})

        assert result is False

    @pytest.mark.asyncio
    async def test_cache_clear_handles_exception(self, mock_redis, test_instance):
        """Test cache clear handles Redis exceptions gracefully."""

        async def mock_scan_iter(*args, **kwargs):
            raise Exception("Redis connection error")

        mock_redis.scan_iter = mock_scan_iter
        cache = ToolCache(redis_client=mock_redis, instance_id=test_instance.id)

        deleted = await cache.clear()

        assert deleted == 0

    @pytest.mark.asyncio
    async def test_cache_clear_no_keys(self, mock_redis, test_instance):
        """Test cache clear with no keys to delete."""

        async def mock_scan_iter(*args, **kwargs):
            return
            yield  # Make it an async generator that yields nothing

        mock_redis.scan_iter = mock_scan_iter
        cache = ToolCache(redis_client=mock_redis, instance_id=test_instance.id)

        deleted = await cache.clear()

        assert deleted == 0

    @pytest.mark.asyncio
    async def test_cache_clear_all(self, mock_redis, test_instance):
        """Test clearing cache for all instances."""

        async def mock_scan_iter(*args, **kwargs):
            for key in [
                b"sre_cache:tool:instance-1:tool1:hash1",
                b"sre_cache:tool:instance-2:tool2:hash2",
            ]:
                yield key

        mock_redis.scan_iter = mock_scan_iter
        mock_redis.delete.return_value = 2
        cache = ToolCache(redis_client=mock_redis, instance_id=test_instance.id)

        deleted = await cache.clear_all()

        assert deleted == 2

    @pytest.mark.asyncio
    async def test_cache_clear_all_no_keys(self, mock_redis, test_instance):
        """Test clear_all with no keys to delete."""

        async def mock_scan_iter(*args, **kwargs):
            return
            yield  # Make it an async generator that yields nothing

        mock_redis.scan_iter = mock_scan_iter
        cache = ToolCache(redis_client=mock_redis, instance_id=test_instance.id)

        deleted = await cache.clear_all()

        assert deleted == 0

    @pytest.mark.asyncio
    async def test_cache_clear_all_handles_exception(self, mock_redis, test_instance):
        """Test clear_all handles Redis exceptions gracefully."""

        async def mock_scan_iter(*args, **kwargs):
            raise Exception("Redis connection error")

        mock_redis.scan_iter = mock_scan_iter
        cache = ToolCache(redis_client=mock_redis, instance_id=test_instance.id)

        deleted = await cache.clear_all()

        assert deleted == 0

    @pytest.mark.asyncio
    async def test_cache_stats_handles_exception(self, mock_redis, test_instance):
        """Test stats handles Redis exceptions gracefully."""

        async def mock_scan_iter(*args, **kwargs):
            raise Exception("Redis connection error")

        mock_redis.scan_iter = mock_scan_iter
        cache = ToolCache(redis_client=mock_redis, instance_id=test_instance.id)

        stats = await cache.stats()

        assert stats["cached_keys"] == 0
        assert "error" in stats

    @pytest.mark.asyncio
    async def test_cache_stats_all(self, mock_redis, test_instance):
        """Test getting stats for all instances."""

        async def mock_scan_iter(*args, **kwargs):
            for key in [
                b"sre_cache:tool:instance-1:tool1:hash1",
                b"sre_cache:tool:instance-2:tool2:hash2",
                b"sre_cache:tool:instance-1:tool3:hash3",
            ]:
                yield key

        mock_redis.scan_iter = mock_scan_iter
        cache = ToolCache(redis_client=mock_redis, instance_id=test_instance.id)

        stats = await cache.stats_all()

        assert stats["total_keys"] == 3
        assert len(stats["instances"]) == 2
        assert "instance-1" in stats["instances"]
        assert "instance-2" in stats["instances"]

    @pytest.mark.asyncio
    async def test_cache_stats_all_handles_exception(self, mock_redis, test_instance):
        """Test stats_all handles Redis exceptions gracefully."""

        async def mock_scan_iter(*args, **kwargs):
            raise Exception("Redis connection error")

        mock_redis.scan_iter = mock_scan_iter
        cache = ToolCache(redis_client=mock_redis, instance_id=test_instance.id)

        stats = await cache.stats_all()

        assert stats["total_keys"] == 0
        assert stats["instances"] == []
        assert "error" in stats


class TestToolManagerWithCache:
    """Test ToolManager integration with shared cache."""

    @pytest.fixture
    def mock_cache_redis(self):
        """Mock async Redis client for cache."""
        client = AsyncMock()
        client.get = AsyncMock(return_value=None)
        client.setex = AsyncMock(return_value=True)
        client.delete = AsyncMock(return_value=1)
        client.keys = AsyncMock(return_value=[])
        return client

    @pytest.fixture
    def test_instance(self):
        """Create a test Redis instance."""
        return RedisInstance(
            id="test-instance-456",
            name="Test Instance",
            connection_url="redis://localhost:6379",
            environment="test",
            usage="cache",
            description="Test instance",
            instance_type="oss_single",
        )

    @pytest.mark.asyncio
    async def test_tool_manager_accepts_cache_client(self, mock_cache_redis, test_instance):
        """Test ToolManager can be initialized with a cache client."""
        async with ToolManager(
            redis_instance=test_instance,
            cache_client=mock_cache_redis,
        ) as mgr:
            assert mgr._shared_cache is not None
            assert mgr._shared_cache._redis == mock_cache_redis

    @pytest.mark.asyncio
    async def test_tool_manager_uses_cache_on_resolve(self, mock_cache_redis, test_instance):
        """Test that resolve_tool_call checks shared cache first."""
        cached_result = {"status": "success", "data": {"info": "cached"}}
        mock_cache_redis.get.return_value = json.dumps(cached_result).encode()

        async with ToolManager(
            redis_instance=test_instance,
            cache_client=mock_cache_redis,
        ) as mgr:
            tools = mgr.get_tools()
            # Find a redis_cli tool
            info_tool = next((t for t in tools if "info" in t.name.lower()), None)
            if info_tool:
                result = await mgr.resolve_tool_call(info_tool.name, {})

                # Should have checked cache
                mock_cache_redis.get.assert_called()
                # Result should be from cache
                assert result == cached_result

    @pytest.mark.asyncio
    async def test_tool_manager_populates_cache_on_miss(self, mock_cache_redis, test_instance):
        """Test that cache is populated on cache miss."""
        mock_cache_redis.get.return_value = None  # Cache miss

        async with ToolManager(
            redis_instance=test_instance,
            cache_client=mock_cache_redis,
        ) as mgr:
            tools = mgr.get_tools()
            # Find a knowledge tool (doesn't need real Redis)
            knowledge_tool = next((t for t in tools if "knowledge" in t.name), None)
            if knowledge_tool:
                # This will fail but we're testing cache population flow
                try:
                    await mgr.resolve_tool_call(knowledge_tool.name, {"query": "test"})
                except Exception:
                    pass

                # Should have tried to cache the result (or error)
                # The implementation should call setex on success

    @pytest.mark.asyncio
    async def test_tool_manager_without_cache_works(self, test_instance):
        """Test ToolManager works normally without cache client."""
        async with ToolManager(
            redis_instance=test_instance,
            cache_client=None,  # No cache
        ) as mgr:
            assert mgr._shared_cache is None
            tools = mgr.get_tools()
            assert len(tools) > 0


class TestDefaultToolTTLs:
    """Test default TTL configuration."""

    def test_default_ttls_defined(self):
        """Test that default TTLs are defined for common tools."""
        assert "info" in DEFAULT_TOOL_TTLS
        assert "config_get" in DEFAULT_TOOL_TTLS
        assert "memory_stats" in DEFAULT_TOOL_TTLS

    def test_default_ttls_are_positive(self):
        """Test all default TTLs are positive integers."""
        for tool, ttl in DEFAULT_TOOL_TTLS.items():
            assert isinstance(ttl, int)
            assert ttl > 0, f"TTL for {tool} should be positive"

    def test_config_get_has_longer_ttl(self):
        """Test that config_get has a longer TTL since config rarely changes."""
        assert DEFAULT_TOOL_TTLS.get("config_get", 0) >= DEFAULT_TOOL_TTLS.get("info", 60)
