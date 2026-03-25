"""Tests for instance inspection helpers."""

from unittest.mock import AsyncMock, patch

import pytest
from pydantic import SecretStr

from redis_sre_agent.core.instance_inspection_helpers import (
    _connection_url_value,
    check_instance_helper,
    check_redis_url_helper,
    get_instance_helper,
)
from redis_sre_agent.core.instances import RedisInstance, RedisInstanceType


def _build_instance() -> RedisInstance:
    return RedisInstance(
        id="redis-prod-1",
        name="Production Redis",
        connection_url=SecretStr("redis://user:pass@redis.example.com:6379/0"),
        environment="production",
        usage="cache",
        description="Primary cache",
        instance_type=RedisInstanceType.redis_cloud,
        admin_url="https://admin.example.com",
        admin_username="admin",
        admin_password=SecretStr("super-secret"),
        cluster_id="cluster-123",
    )


class TestGetInstanceHelper:
    """Test shared helpers for instance inspection."""

    @pytest.mark.asyncio
    async def test_get_instance_helper_returns_masked_payload(self):
        """Instance retrieval should return a masked, machine-friendly payload."""
        with patch(
            "redis_sre_agent.core.instance_inspection_helpers.get_instance_by_id",
            new_callable=AsyncMock,
            return_value=_build_instance(),
        ):
            result = await get_instance_helper("redis-prod-1")

        assert result["id"] == "redis-prod-1"
        assert result["name"] == "Production Redis"
        assert result["connection_url"] == "redis://***:***@redis.example.com:6379/0"
        assert result["admin_password"] == "***"
        assert result["cluster_id"] == "cluster-123"

    @pytest.mark.asyncio
    async def test_get_instance_helper_returns_not_found_payload(self):
        """Missing instances should return an error payload."""
        with patch(
            "redis_sre_agent.core.instance_inspection_helpers.get_instance_by_id",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await get_instance_helper("missing")

        assert result == {"error": "Instance not found", "id": "missing"}


class TestConnectionHelpers:
    """Test shared helpers for instance and URL connectivity checks."""

    def test_connection_url_value_accepts_plain_strings(self):
        """Plain-string URLs should pass through unchanged."""
        assert _connection_url_value("redis://plain-host:6379/0") == "redis://plain-host:6379/0"

    @pytest.mark.asyncio
    async def test_test_redis_url_helper_masks_url(self):
        """URL tests should mask credentials in the returned payload."""
        with patch(
            "redis_sre_agent.core.instance_inspection_helpers.test_redis_connection",
            new_callable=AsyncMock,
            return_value=True,
        ) as mock_test:
            result = await check_redis_url_helper("redis://user:pass@redis.example.com:6379/0")

        assert result == {
            "success": True,
            "message": "Successfully connected",
            "url": "redis://***:***@redis.example.com:6379/0",
        }
        mock_test.assert_awaited_once_with(url="redis://user:pass@redis.example.com:6379/0")

    @pytest.mark.asyncio
    async def test_test_instance_helper_success(self):
        """Instance tests should resolve the instance and check its connection URL."""
        with (
            patch(
                "redis_sre_agent.core.instance_inspection_helpers.get_instance_by_id",
                new_callable=AsyncMock,
                return_value=_build_instance(),
            ),
            patch(
                "redis_sre_agent.core.instance_inspection_helpers.test_redis_connection",
                new_callable=AsyncMock,
                return_value=False,
            ) as mock_test,
        ):
            result = await check_instance_helper("redis-prod-1")

        assert result == {
            "success": False,
            "message": "Failed to connect",
            "instance_id": "redis-prod-1",
            "name": "Production Redis",
        }
        mock_test.assert_awaited_once_with(url="redis://user:pass@redis.example.com:6379/0")

    @pytest.mark.asyncio
    async def test_test_instance_helper_not_found(self):
        """Missing instances should return an error payload without probing Redis."""
        with (
            patch(
                "redis_sre_agent.core.instance_inspection_helpers.get_instance_by_id",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "redis_sre_agent.core.instance_inspection_helpers.test_redis_connection",
                new_callable=AsyncMock,
            ) as mock_test,
        ):
            result = await check_instance_helper("missing")

        assert result == {
            "success": False,
            "error": "Instance not found",
            "id": "missing",
        }
        mock_test.assert_not_awaited()
