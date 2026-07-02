"""US-007/US-009: SemanticCache lookup, store (race guard), and invalidation."""

import json

import fakeredis.aioredis
import pytest

from redis_sre_agent.core.semantic_cache.client import LangCacheEntry
from redis_sre_agent.core.semantic_cache.provenance import ProvenanceStore, path_hash_for_source
from redis_sre_agent.core.semantic_cache.service import (
    SemanticCache,
    _changed_source_paths,
    invalidate_changed_sources,
)


class FakeLangCache:
    def __init__(self):
        self.search_result = []
        self.search_exc = None
        self.set_result = "entry-xyz"
        self.search_calls = []
        self.set_calls = []
        self.deleted = []
        self.delete_fail = set()  # entry_ids for which delete_entry returns False

    async def search(
        self, prompt, *, similarity_threshold, attributes=None, search_strategies=None
    ):
        self.search_calls.append(
            {"prompt": prompt, "threshold": similarity_threshold, "attributes": attributes}
        )
        if self.search_exc is not None:
            raise self.search_exc
        return self.search_result

    async def set_entry(self, prompt, response, *, attributes=None, ttl_millis=None):
        self.set_calls.append(
            {"prompt": prompt, "response": response, "attributes": attributes, "ttl": ttl_millis}
        )
        return self.set_result

    async def delete_entry(self, entry_id):
        self.deleted.append(entry_id)
        return entry_id not in self.delete_fail

    async def aclose(self):
        pass


class FakeProvenance:
    """Provenance double with programmable tombstone responses."""

    def __init__(self, tombstone_sequence=None, record_ok=True):
        self.records = []
        self.removed = []
        self.tombstones_written = []
        self._tombstone_sequence = list(tombstone_sequence or [])
        self._record_ok = record_ok
        self.entries = {}

    async def has_fresh_tombstone(self, path_hashes):
        if self._tombstone_sequence:
            return self._tombstone_sequence.pop(0)
        return False

    async def record_entry(self, entry_id, path_hashes, *, meta=None):
        self.records.append((entry_id, list(path_hashes), meta))
        return self._record_ok

    async def remove_entry(self, entry_id, path_hashes):
        self.removed.append((entry_id, list(path_hashes)))

    async def entries_for_path(self, path_hash):
        return self.entries.get(path_hash, [])

    async def clear_path(self, path_hash, entry_ids):
        self.entries.pop(path_hash, None)

    async def write_tombstone(self, path_hash):
        self.tombstones_written.append(path_hash)


def _make_cache(client, provenance):
    return SemanticCache(
        client=client,
        provenance=provenance,
        similarity_threshold=0.9,
        ttl_latest_ms=3600_000,
        ttl_pinned_ms=86_400_000,
    )


def _entry(response_payload, *, similarity=0.97, attributes=None, strategy="semantic"):
    return LangCacheEntry(
        id="a" * 32,
        prompt="q",
        response=json.dumps(response_payload),
        similarity=similarity,
        attributes=attributes or {},
        search_strategy=strategy,
    )


# -- lookup -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_lookup_hit_reconstructs_response_and_sources():
    client = FakeLangCache()
    client.search_result = [
        _entry({"response": "cached answer", "search_results": [{"title": "Doc"}]})
    ]
    cache = _make_cache(client, FakeProvenance())

    result = await cache.lookup("how do I tune maxmemory?")
    assert result is not None
    assert result.response == "cached answer"
    assert result.search_results == [{"title": "Doc"}]


@pytest.mark.asyncio
async def test_lookup_miss_returns_none():
    client = FakeLangCache()
    client.search_result = []
    cache = _make_cache(client, FakeProvenance())
    assert await cache.lookup("anything") is None


@pytest.mark.asyncio
async def test_lookup_below_threshold_rejected():
    client = FakeLangCache()
    client.search_result = [_entry({"response": "x"}, similarity=0.5)]
    cache = _make_cache(client, FakeProvenance())
    assert await cache.lookup("anything") is None


@pytest.mark.asyncio
async def test_lookup_post_filter_rejects_entity_mismatch():
    client = FakeLangCache()
    # Candidate is for RET-9999 but query asks about RET-4421.
    client.search_result = [
        _entry({"response": "wrong ticket"}, attributes={"entity_id": "RET-9999"})
    ]
    cache = _make_cache(client, FakeProvenance())

    result = await cache.lookup("status of RET-4421")
    assert result is None
    # The lookup did scope by entity_id in the request attributes.
    assert client.search_calls[0]["attributes"].get("entity_id") == "RET-4421"


@pytest.mark.asyncio
async def test_lookup_post_filter_accepts_entity_match():
    client = FakeLangCache()
    client.search_result = [
        _entry({"response": "right ticket"}, attributes={"entity_id": "RET-4421"})
    ]
    cache = _make_cache(client, FakeProvenance())
    result = await cache.lookup("status of RET-4421")
    assert result is not None and result.response == "right ticket"


@pytest.mark.asyncio
async def test_lookup_fails_open_on_client_error():
    client = FakeLangCache()
    client.search_exc = RuntimeError("langcache down")
    cache = _make_cache(client, FakeProvenance())
    assert await cache.lookup("anything") is None


# -- store ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_store_grounded_writes_entry_and_index():
    client = FakeLangCache()
    prov = FakeProvenance()
    cache = _make_cache(client, prov)

    entry_id = await cache.store(
        "how do I tune maxmemory?",
        "the answer",
        [{"source_document_path": "runbooks/mem.md", "title": "Mem"}],
    )
    assert entry_id == "entry-xyz"
    assert len(client.set_calls) == 1
    # Canonical-key invariant: first-turn store key == raw query == lookup key.
    assert client.set_calls[0]["prompt"] == "how do I tune maxmemory?"
    assert client.set_calls[0]["attributes"]["cache_origin"] == "dynamic"
    assert client.set_calls[0]["attributes"]["version"] == "latest"
    # Reverse index recorded against the cited source's path_hash.
    recorded_entry, recorded_hashes, _meta = prov.records[0]
    assert recorded_entry == "entry-xyz"
    assert recorded_hashes == [path_hash_for_source("runbooks/mem.md")]


@pytest.mark.asyncio
async def test_store_reuses_supplied_rewritten_key_without_calling_nano(monkeypatch):
    """When the caller supplies the canonical key (§F), store must not rewrite again."""
    import redis_sre_agent.core.semantic_cache.service as service_mod

    def _boom(*args, **kwargs):
        raise AssertionError("rewrite_query must not be called when key is supplied")

    monkeypatch.setattr(service_mod, "rewrite_query", _boom)

    client = FakeLangCache()
    cache = _make_cache(client, FakeProvenance())
    entry_id = await cache.store(
        "follow up?",
        "answer",
        [{"source_document_path": "a.md"}],
        conversation_history=[object()],
        rewritten_query="precomputed standalone question",
    )
    assert entry_id == "entry-xyz"
    assert client.set_calls[0]["prompt"] == "precomputed standalone question"


@pytest.mark.asyncio
async def test_canonical_key_truncates_to_prompt_limit():
    client = FakeLangCache()
    cache = _make_cache(client, FakeProvenance())
    key = await cache.canonical_key("x" * 5000, conversation_history=None)
    assert key == "x" * 1024


@pytest.mark.asyncio
async def test_store_ungrounded_skipped():
    client = FakeLangCache()
    cache = _make_cache(client, FakeProvenance())
    entry_id = await cache.store("q", "answer", [])
    assert entry_id is None
    assert client.set_calls == []


@pytest.mark.asyncio
async def test_store_skipped_when_tombstone_present_before_write():
    client = FakeLangCache()
    prov = FakeProvenance(tombstone_sequence=[True])  # fresh tombstone before store
    cache = _make_cache(client, prov)
    entry_id = await cache.store("q", "answer", [{"source_document_path": "a.md"}])
    assert entry_id is None
    assert client.set_calls == []


@pytest.mark.asyncio
async def test_store_undone_when_tombstone_appears_during_write():
    client = FakeLangCache()
    # False before write, True on the post-SADD recheck.
    prov = FakeProvenance(tombstone_sequence=[False, True])
    cache = _make_cache(client, prov)

    entry_id = await cache.store("q", "answer", [{"source_document_path": "a.md"}])
    assert entry_id is None
    assert len(client.set_calls) == 1  # it was stored...
    assert client.deleted == ["entry-xyz"]  # ...then undone
    assert prov.removed and prov.removed[0][0] == "entry-xyz"


@pytest.mark.asyncio
async def test_store_pinned_version_uses_longer_ttl():
    client = FakeLangCache()
    cache = _make_cache(client, FakeProvenance())
    await cache.store("what changed in 7.8?", "answer", [{"source_document_path": "a.md"}])
    assert client.set_calls[0]["ttl"] == 86_400_000
    assert client.set_calls[0]["attributes"]["version"] == "7.8"


# -- invalidation -----------------------------------------------------------


@pytest.mark.asyncio
async def test_invalidate_deletes_entries_and_writes_tombstone():
    client = FakeLangCache()
    redis_client = fakeredis.aioredis.FakeRedis()
    store = ProvenanceStore(redis_client)
    cache = _make_cache(client, store)

    ph = path_hash_for_source("changed.md")
    await store.record_entry("e1", [ph], meta={})
    await store.record_entry("e2", [ph], meta={})

    deleted = await cache.invalidate(["changed.md"])
    assert deleted == 2
    assert set(client.deleted) == {"e1", "e2"}
    assert await store.entries_for_path(ph) == []
    assert await store.has_fresh_tombstone([ph]) is True


def test_changed_source_paths_filters_to_replaced_or_removed():
    summary = {
        "files": [
            {"path": "a.md", "action": "update"},
            {"path": "b.md", "action": "add"},
            {"path": "c.md", "action": "delete"},
            {"path": "d.md", "action": "unchanged"},
        ]
    }
    assert _changed_source_paths(summary) == ["a.md", "c.md"]
    # Also supports the workflow-mixin "file" key shape.
    assert _changed_source_paths([{"file": "x.md", "action": "updated"}]) == ["x.md"]


@pytest.mark.asyncio
async def test_invalidate_changed_sources_noop_without_credentials():
    # Default settings have no LangCache credentials => no-op, returns 0.
    deleted = await invalidate_changed_sources({"files": [{"path": "a.md", "action": "update"}]})
    assert deleted == 0


@pytest.mark.asyncio
async def test_invalidate_changed_sources_noop_for_pure_adds():
    deleted = await invalidate_changed_sources([{"file": "a.md", "action": "add"}])
    assert deleted == 0


# -- regression coverage for PR review findings ------------------------------


@pytest.mark.asyncio
async def test_store_version_resolved_from_rewritten_key_not_raw_query():
    """Version/entity are tagged from the canonical key, not the raw query.

    A referential mid-conversation turn ("what about that version?") has no
    version in the raw text, but the nano rewrite resolves it (e.g. 7.2). The
    stored entry must carry version=7.2 (+ pinned TTL), not latest.
    """
    client = FakeLangCache()
    cache = _make_cache(client, FakeProvenance())
    await cache.store(
        "what about that version?",
        "answer",
        [{"source_document_path": "a.md"}],
        conversation_history=[object()],
        rewritten_query="How do I configure clustering in Redis 7.2?",
    )
    assert client.set_calls[0]["attributes"]["version"] == "7.2"
    assert client.set_calls[0]["ttl"] == 86_400_000  # pinned TTL, not latest


@pytest.mark.asyncio
async def test_lookup_version_resolved_from_rewritten_key():
    client = FakeLangCache()
    client.search_result = []
    cache = _make_cache(client, FakeProvenance())
    await cache.lookup(
        "what about that version?",
        conversation_history=[object()],
        rewritten_query="How do I configure clustering in Redis 7.2?",
    )
    assert client.search_calls[0]["attributes"]["version"] == "7.2"


def test_path_hashes_ignores_source_fallback():
    """Only source_document_path is hashed; `source` is not a fallback (would
    mint a hash ingestion never emits -> un-invalidatable entries)."""
    assert SemanticCache._path_hashes([{"source": "configuration"}]) == []
    assert SemanticCache._path_hashes([{"source_document_path": "runbooks/x.md"}]) == [
        path_hash_for_source("runbooks/x.md")
    ]


@pytest.mark.asyncio
async def test_store_without_source_document_path_records_no_reverse_index():
    client = FakeLangCache()
    prov = FakeProvenance()
    cache = _make_cache(client, prov)
    entry_id = await cache.store("q", "answer", [{"source": "configuration", "title": "X"}])
    assert entry_id == "entry-xyz"  # still stored (grounded)
    assert prov.records[0][1] == []  # ...but no path_hashes -> no reverse index


@pytest.mark.asyncio
async def test_lookup_rejects_ticket_entry_for_general_query():
    """A general query (no entity_id) must not be served a ticket-scoped entry."""
    client = FakeLangCache()
    client.search_result = [
        _entry({"response": "ticket-scoped answer"}, attributes={"entity_id": "RET-4421"})
    ]
    cache = _make_cache(client, FakeProvenance())
    result = await cache.lookup("how do I tune maxmemory?")  # no entity_id
    assert result is None


@pytest.mark.asyncio
async def test_meta_provenance_path_hashes_align_with_mixed_citations():
    """cache_meta provenance must pair each result with ITS OWN path_hash, even
    when some cited rows lack source_document_path (would misalign under zip)."""
    client = FakeLangCache()
    prov = FakeProvenance()
    cache = _make_cache(client, prov)
    await cache.store(
        "q",
        "answer",
        [
            {"source_document_path": "a.md", "title": "A"},
            {"source": "configuration", "title": "no-path"},  # no source_document_path
            {"source_document_path": "b.md", "title": "B"},
        ],
    )
    meta = prov.records[0][2]
    prov_list = meta["provenance"]
    assert prov_list[0]["path_hash"] == path_hash_for_source("a.md")
    assert prov_list[1]["path_hash"] is None  # row without a path stays None
    assert prov_list[2]["path_hash"] == path_hash_for_source("b.md")
    # Reverse index still only carries the two real paths.
    assert prov.records[0][1] == [path_hash_for_source("a.md"), path_hash_for_source("b.md")]


@pytest.mark.asyncio
async def test_store_rolls_back_when_provenance_recording_fails():
    """If reverse-index recording fails, the LangCache entry must be rolled back
    so it can't linger un-invalidatable (only TTL would reach it)."""
    client = FakeLangCache()
    prov = FakeProvenance(record_ok=False)
    cache = _make_cache(client, prov)
    entry_id = await cache.store("q", "answer", [{"source_document_path": "a.md"}])
    assert entry_id is None
    assert client.set_calls and client.deleted == ["entry-xyz"]  # stored then undone
    assert prov.removed and prov.removed[0][0] == "entry-xyz"


@pytest.mark.asyncio
async def test_store_no_paths_not_rolled_back_on_meta_only_failure():
    """An entry with no source paths is TTL-only by design; a meta-only record
    failure should NOT delete an otherwise-servable entry."""
    client = FakeLangCache()
    prov = FakeProvenance(record_ok=False)
    cache = _make_cache(client, prov)
    entry_id = await cache.store("q", "answer", [{"source": "configuration"}])
    assert entry_id == "entry-xyz"
    assert client.deleted == []  # not rolled back (no reverse index was expected)


@pytest.mark.asyncio
async def test_invalidate_keeps_reverse_index_for_failed_deletes():
    """A failed LangCache delete must NOT drop its reverse-index link — the row
    may still exist and needs to stay invalidatable on a later retry."""
    client = FakeLangCache()
    client.delete_fail = {"e_fail"}
    redis_client = fakeredis.aioredis.FakeRedis()
    store = ProvenanceStore(redis_client)
    cache = _make_cache(client, store)

    ph = path_hash_for_source("changed.md")
    await store.record_entry("e_ok", [ph], meta={})
    await store.record_entry("e_fail", [ph], meta={})

    deleted = await cache.invalidate(["changed.md"])
    assert deleted == 1  # only e_ok
    remaining = await store.entries_for_path(ph)
    assert remaining == ["e_fail"]  # failed delete kept for retry; e_ok removed


@pytest.mark.asyncio
async def test_aclose_never_raises():
    """Cleanup must be exception-safe so a failed close in a finally can't
    discard an already-computed lookup result/key."""

    class _BoomClient:
        async def aclose(self):
            raise RuntimeError("close boom")

    cache = SemanticCache(
        client=_BoomClient(),
        provenance=FakeProvenance(),
        similarity_threshold=0.9,
        ttl_latest_ms=1,
        ttl_pinned_ms=1,
    )
    await cache.aclose()  # must not raise
