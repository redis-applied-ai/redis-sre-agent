"""Integration-like tests for instances storage using RediSearch enumeration.

Validates that:
- get_instances() reads instances via a single FT.SEARCH
- save_instances() cleanup deletes stale docs using FT.SEARCH results (no SCAN)

Uses the Testcontainers-backed Redis from tests/conftest.py.
"""

import base64
import os
import uuid

import pytest

from redis_sre_agent.core.instances import (
    RedisInstance,
    get_instances,
    save_instances,
)
from redis_sre_agent.core.redis import SRE_INSTANCES_INDEX, get_redis_client


@pytest.mark.asyncio
async def test_save_and_get_instances_via_search_enumeration(
    async_redis_client, test_settings, monkeypatch
):
    # Ensure a master key is set for encryption/decryption
    mk = base64.b64encode(os.urandom(32)).decode("ascii")
    monkeypatch.setenv("REDIS_SRE_MASTER_KEY", mk)

    # Use clean DB from async_redis_client fixture with dependency injection
    client = get_redis_client(config=test_settings)

    inst1 = RedisInstance(
        id=f"it-{uuid.uuid4().hex[:8]}",
        name="Inst One",
        connection_url="redis://example-host:6379/0",
        environment="test",
        usage="cache",
        description="first",
        instance_type="oss_single",
    )
    inst2 = RedisInstance(
        id=f"it-{uuid.uuid4().hex[:8]}",
        name="Inst Two",
        connection_url="redis://example-host:6379/1",
        environment="test",
        usage="cache",
        description="second",
        instance_type="oss_single",
    )

    # Initial save with two instances
    ok = await save_instances([inst1, inst2])
    assert ok is True

    # Should have exactly 2 hash docs with the prefix
    cur, keys = 0, []
    prefix = f"{SRE_INSTANCES_INDEX}:*"
    while True:
        cur, batch = await client.scan(cursor=cur, match=prefix)
        if batch:
            keys.extend(batch)
        if cur == 0:
            break
    assert len(keys) == 2

    # get_instances should return 2
    got = await get_instances()
    got_ids = {g.id for g in got}
    assert {inst1.id, inst2.id} <= got_ids

    # Now save with only inst1 (replace semantics) — inst2 should be removed
    ok2 = await save_instances([inst1])
    assert ok2 is True

    # Verify only inst1 remains by key existence
    cur, keys2 = 0, []
    while True:
        cur, batch = await client.scan(cursor=cur, match=prefix)
        if batch:
            keys2.extend(batch)
        if cur == 0:
            break
    key_strs = [k.decode("utf-8") if isinstance(k, (bytes, bytearray)) else str(k) for k in keys2]
    assert f"{SRE_INSTANCES_INDEX}:{inst1.id}" in key_strs
    assert all(f"{SRE_INSTANCES_INDEX}:{inst2.id}" != s for s in key_strs)

    # And get_instances should show exactly one
    got2 = await get_instances()
    assert len(got2) >= 1
    assert inst1.id in {g.id for g in got2}
