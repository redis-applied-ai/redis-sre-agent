from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from redis_sre_agent.tools.cloud.redis_cloud.provider import (
    RedisCloudConfig,
    RedisCloudToolProvider,
)


@pytest.mark.asyncio
async def test_list_databases_parses_subscription_wrapper():
    # Configure provider with a redis_cloud instance and subscription id
    fake_instance = type(
        "Instance",
        (),
        {
            "instance_type": "redis_cloud",
            "redis_cloud_subscription_id": 999,
            "redis_cloud_subscription_type": "pro",
        },
    )()
    provider = RedisCloudToolProvider(
        redis_instance=fake_instance, config=RedisCloudConfig(api_key="k", api_secret_key="s")
    )

    # Simulate API returning subscription-wrapped databases payload (Pro)
    payload = {
        "accountId": 123,
        "subscription": [
            {
                "subscriptionId": 999,
                "databases": [
                    {"databaseId": 1, "name": "db1"},
                    {"databaseId": 2, "name": "db2"},
                ],
            }
        ],
    }

    # Patch the generated API function used by the provider
    with patch(
        "redis_sre_agent.tools.cloud.redis_cloud.provider.pro_get_subscription_databases.asyncio",
        new=AsyncMock(return_value=SimpleNamespace(to_dict=lambda: payload)),
    ):
        # Call the concrete method directly; tools() now wires tools to these
        # concrete async methods instead of using resolve_tool_call.
        result = await provider.list_databases()
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["databaseId"] == 1
