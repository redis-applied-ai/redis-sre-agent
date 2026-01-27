"""Integration test for thread deletion and Redis data layout.

This test exercises the new Threads API against a real Redis instance
(provided by the testcontainers-backed test_settings fixture).
It creates a thread via the HTTP API, attempts to delete it, and inspects
thread-related keys (including the search-index hash) before and after
deletion.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from redis_sre_agent.core.keys import RedisKeys
from redis_sre_agent.core.redis import SRE_THREADS_INDEX


@pytest.mark.integration
@pytest.mark.asyncio
async def test_thread_delete_integration(async_redis_client, test_settings):
    """Create a thread via API, delete it, and inspect Redis keys.

    This exercises the real delete path and asserts that it cleans up both
    the per-thread keys and the hash document backing the threads search
    index.
    """
    # Import the real FastAPI app - test_settings provides configuration
    from redis_sre_agent.api.app import app

    # ------------------------------------------------------------------
    # 1. Create a thread via the Threads API
    # ------------------------------------------------------------------
    create_payload = {
        "user_id": "test-user",
        "session_id": "test-session",
        "subject": "Delete me",
        "messages": [{"role": "user", "content": "Please investigate delete behaviour."}],
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        create_resp = await client.post("/api/v1/threads", json=create_payload)

    assert create_resp.status_code == 201
    create_body = create_resp.json()
    thread_id = create_body["thread_id"]

    # ------------------------------------------------------------------
    # 2. Inspect Redis keys before deletion
    # ------------------------------------------------------------------
    thread_key_pattern = f"sre:thread:{thread_id}:*"

    before_keys = set()
    cursor = 0
    while True:
        cursor, batch = await async_redis_client.scan(cursor=cursor, match=thread_key_pattern)
        if batch:
            before_keys.update(batch)
        if cursor == 0:
            break

    before_keys_str = {
        k.decode("utf-8") if isinstance(k, (bytes, bytearray)) else str(k) for k in before_keys
    }

    # We expect at least the metadata key to be present for a fresh thread.
    assert RedisKeys.thread_metadata(thread_id) in before_keys_str

    search_hash_key = f"{SRE_THREADS_INDEX}:{thread_id}"
    search_hash_exists_before = bool(await async_redis_client.exists(search_hash_key))
    # The search hash is written by ThreadManager._upsert_thread_search_doc during creation.
    assert search_hash_exists_before

    # ------------------------------------------------------------------
    # 3. Attempt to delete the thread via the API
    # ------------------------------------------------------------------
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        delete_resp = await client.delete(f"/api/v1/threads/{thread_id}")
        delete_resp_second = await client.delete(f"/api/v1/threads/{thread_id}")

    # Delete should now be idempotent and always return 204 even if the
    # underlying keys have already been removed.
    assert delete_resp.status_code == 204
    assert delete_resp_second.status_code == 204

    # ------------------------------------------------------------------
    # 4. Inspect Redis keys after deletion
    # ------------------------------------------------------------------
    after_keys = set()
    cursor = 0
    while True:
        cursor, batch = await async_redis_client.scan(cursor=cursor, match=thread_key_pattern)
        if batch:
            after_keys.update(batch)
        if cursor == 0:
            break

    after_keys_str = {
        k.decode("utf-8") if isinstance(k, (bytes, bytearray)) else str(k) for k in after_keys
    }

    # The per-thread metadata key is removed by the existing delete path.
    assert RedisKeys.thread_metadata(thread_id) not in after_keys_str

    # After deletion, the hash that backs the threads search index should also
    # be removed so the thread no longer appears in search results.
    search_hash_exists_after = bool(await async_redis_client.exists(search_hash_key))
    assert not search_hash_exists_after
