"""US-005: provenance reverse index, side metadata, and tombstones (our Redis)."""

import fakeredis.aioredis
import pytest

from redis_sre_agent.core.keys import RedisKeys
from redis_sre_agent.core.semantic_cache.provenance import (
    ProvenanceStore,
    path_hash_for_source,
)


@pytest.fixture
def redis_client():
    return fakeredis.aioredis.FakeRedis()


def test_path_hash_matches_ingestion_algorithm():
    import hashlib

    source = "runbooks/memory.md"
    expected = hashlib.sha256(source.encode("utf-8")).hexdigest()[:16]
    assert path_hash_for_source(source) == expected
    assert len(path_hash_for_source(source)) == 16


@pytest.mark.asyncio
async def test_record_and_read_reverse_index(redis_client):
    store = ProvenanceStore(redis_client)
    ph = path_hash_for_source("a.md")

    assert await store.record_entry("entry-1", [ph], meta={"k": "v"}) is True
    assert await store.entries_for_path(ph) == ["entry-1"]
    # Side metadata persisted.
    assert await redis_client.get(RedisKeys.semantic_cache_meta("entry-1")) is not None


@pytest.mark.asyncio
async def test_remove_entry_undoes_index_and_meta(redis_client):
    store = ProvenanceStore(redis_client)
    ph = path_hash_for_source("a.md")
    await store.record_entry("entry-1", [ph], meta={"k": "v"})

    await store.remove_entry("entry-1", [ph])
    assert await store.entries_for_path(ph) == []
    assert await redis_client.get(RedisKeys.semantic_cache_meta("entry-1")) is None


@pytest.mark.asyncio
async def test_clear_path_drops_set_and_meta(redis_client):
    store = ProvenanceStore(redis_client)
    ph = path_hash_for_source("a.md")
    await store.record_entry("entry-1", [ph], meta={"k": "v"})
    await store.record_entry("entry-2", [ph], meta={"k": "v"})

    await store.clear_path(ph, ["entry-1", "entry-2"])
    assert await store.entries_for_path(ph) == []
    assert await redis_client.get(RedisKeys.semantic_cache_meta("entry-1")) is None


@pytest.mark.asyncio
async def test_tombstone_lifecycle(redis_client):
    store = ProvenanceStore(redis_client, tombstone_ttl_seconds=60)
    ph = path_hash_for_source("a.md")

    assert await store.has_fresh_tombstone([ph]) is False
    await store.write_tombstone(ph)
    assert await store.has_fresh_tombstone([ph]) is True
    # An unrelated path is unaffected.
    assert await store.has_fresh_tombstone([path_hash_for_source("b.md")]) is False
