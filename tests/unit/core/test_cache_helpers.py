"""Tests for cache and version helpers."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from redis_sre_agent.core.cache_helpers import (
    cache_clear_helper,
    cache_stats_helper,
    get_tool_cache,
    version_helper,
)


class TestCacheStatsHelper:
    """Test cache statistics helper behavior."""

    def test_get_tool_cache_builds_all_instances_scope(self):
        """Tool-cache construction should default to the all-instances scope."""
        redis_client = object()

        with (
            patch("redis_sre_agent.core.cache_helpers.get_redis_client", return_value=redis_client),
            patch("redis_sre_agent.core.cache_helpers.ToolCache") as mock_tool_cache,
        ):
            cache = get_tool_cache()

        assert cache == mock_tool_cache.return_value
        mock_tool_cache.assert_called_once_with(
            redis_client=redis_client,
            instance_id="__all__",
        )

    @pytest.mark.asyncio
    async def test_cache_stats_helper_defaults_to_all_instances(self):
        """Stats without an instance should default to aggregate cache stats."""
        cache = MagicMock()
        cache.stats_all = AsyncMock(return_value={"total_keys": 7, "instances": ["redis-prod-1"]})

        with patch(
            "redis_sre_agent.core.cache_helpers.get_tool_cache",
            return_value=cache,
        ) as mock_get_cache:
            result = await cache_stats_helper()

        assert result == {"total_keys": 7, "instances": ["redis-prod-1"]}
        mock_get_cache.assert_called_once_with(None)
        cache.stats_all.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cache_stats_helper_returns_instance_stats(self):
        """Instance-specific stats should use the instance cache scope."""
        cache = MagicMock()
        cache.stats = AsyncMock(
            return_value={"instance_id": "redis-prod-1", "cached_keys": 3, "enabled": True}
        )

        with patch(
            "redis_sre_agent.core.cache_helpers.get_tool_cache",
            return_value=cache,
        ) as mock_get_cache:
            result = await cache_stats_helper(instance_id="redis-prod-1")

        assert result["instance_id"] == "redis-prod-1"
        assert result["cached_keys"] == 3
        mock_get_cache.assert_called_once_with("redis-prod-1")
        cache.stats.assert_awaited_once()


class TestCacheClearHelper:
    """Test cache clear helper behavior."""

    @pytest.mark.asyncio
    async def test_cache_clear_helper_requires_confirmation(self):
        """Cache clears should require explicit confirmation."""
        result = await cache_clear_helper(instance_id="redis-prod-1", confirm=False)

        assert result == {
            "error": "Confirmation required",
            "status": "cancelled",
            "instance_id": "redis-prod-1",
        }

    @pytest.mark.asyncio
    async def test_cache_clear_helper_requires_scope(self):
        """Cache clears should reject missing scope."""
        result = await cache_clear_helper(confirm=True)

        assert result == {
            "error": "Must specify instance_id or clear_all=True",
            "status": "failed",
        }

    @pytest.mark.asyncio
    async def test_cache_clear_helper_clears_all_instances(self):
        """Aggregate cache clears should call clear_all on the all-instances scope."""
        cache = MagicMock()
        cache.clear_all = AsyncMock(return_value=11)

        with patch(
            "redis_sre_agent.core.cache_helpers.get_tool_cache",
            return_value=cache,
        ) as mock_get_cache:
            result = await cache_clear_helper(clear_all=True, confirm=True)

        assert result == {"status": "cleared", "scope": "all", "deleted": 11}
        mock_get_cache.assert_called_once_with()
        cache.clear_all.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cache_clear_helper_clears_single_instance(self):
        """Instance-scoped cache clears should call clear on that instance."""
        cache = MagicMock()
        cache.clear = AsyncMock(return_value=4)

        with patch(
            "redis_sre_agent.core.cache_helpers.get_tool_cache",
            return_value=cache,
        ) as mock_get_cache:
            result = await cache_clear_helper(instance_id="redis-prod-1", confirm=True)

        assert result == {
            "status": "cleared",
            "scope": "instance",
            "instance_id": "redis-prod-1",
            "deleted": 4,
        }
        mock_get_cache.assert_called_once_with("redis-prod-1")
        cache.clear.assert_awaited_once()


class TestVersionHelper:
    """Test version metadata helper."""

    def test_version_helper_returns_package_metadata(self, monkeypatch):
        """Version helper should expose the installed package version."""
        monkeypatch.setattr("redis_sre_agent.core.cache_helpers.__version__", "0.0-test")
        assert version_helper() == {
            "name": "redis-sre-agent",
            "version": "0.0-test",
        }
