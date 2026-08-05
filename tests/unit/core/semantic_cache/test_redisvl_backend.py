"""RedisVLBackend: unit conversions, hit mapping, identifier shape, fail-open.

Drives the real backend against a stub standing in for redisvl's ``SemanticCache``,
so the mapping code runs for real with no Redis, no vectorizer and no network.
"""

import pytest

from redis_sre_agent.core.semantic_cache.backend import NO_ENTITY, CacheBackend
from redis_sre_agent.core.semantic_cache.redisvl_backend import (
    _FILTERABLE_FIELDS,
    RedisVLBackend,
    _distance_for,
    _entry_from_hit,
    _filter_for,
    _similarity_for,
    _ttl_seconds,
    get_redisvl_backend,
    reset_backend_cache,
)


class StubCache:
    """Stands in for redisvl's SemanticCache at its own API boundary."""

    def __init__(self, hits=None, store_key="sre_semantic_cache:abc123"):
        self.hits = hits if hits is not None else []
        self.store_key = store_key
        self.check_calls = []
        self.store_calls = []
        self.dropped = []
        self.check_exc = None
        self.store_exc = None
        self.drop_exc = None
        # Mirrors the real constructor: no cache-level TTL.
        self._ttl = None

    async def acheck(self, prompt, num_results=1, filter_expression=None, distance_threshold=None):
        self.check_calls.append(
            {
                "prompt": prompt,
                "num_results": num_results,
                "filter": filter_expression,
                "distance_threshold": distance_threshold,
            }
        )
        if self.check_exc is not None:
            raise self.check_exc
        return self.hits

    async def astore(self, prompt, response, filters=None, ttl=None):
        self.store_calls.append(
            {"prompt": prompt, "response": response, "filters": filters, "ttl": ttl}
        )
        if self.store_exc is not None:
            raise self.store_exc
        return self.store_key

    async def adrop(self, ids=None, keys=None):
        if self.drop_exc is not None:
            raise self.drop_exc
        self.dropped.append({"ids": ids, "keys": keys})


def _hit(**overrides):
    """A hit shaped the way redisvl returns them: filters flattened on top."""
    hit = {
        "key": "sre_semantic_cache:abc123",
        "entry_id": "abc123",
        "prompt": "how do I tune maxmemory",
        "response": '{"response": "answer"}',
        "vector_distance": 0.05,
        "version": "latest",
        "entity_id": NO_ENTITY,
        "cache_origin": "dynamic",
    }
    hit.update(overrides)
    return hit


# -- conversions -------------------------------------------------------------


def test_threshold_converts_similarity_to_cosine_distance():
    # Our setting is a similarity where higher is stricter; redisvl wants a
    # distance where lower is stricter.
    assert _distance_for(0.9) == pytest.approx(0.1)
    assert _distance_for(1.0) == pytest.approx(0.0)
    assert _distance_for(0.0) == pytest.approx(1.0)


def test_threshold_conversion_stays_in_cosine_range():
    # Redis rejects a COSINE distance outside [0, 2].
    assert _distance_for(-5.0) == 2.0
    assert _distance_for(5.0) == 0.0


def test_similarity_is_the_inverse_of_distance():
    for similarity in (0.9, 0.75, 1.0):
        assert _similarity_for(_distance_for(similarity)) == pytest.approx(similarity)


def test_similarity_treats_missing_distance_as_exact():
    assert _similarity_for(None) == 1.0


def test_ttl_converts_millis_to_seconds():
    assert _ttl_seconds(3_600_000) == 3600
    assert _ttl_seconds(86_400_000) == 86_400


def test_ttl_floors_at_one_second():
    # redisvl reads a TTL of 0 as "no TTL", so a sub-second TTL must not round
    # down into storing forever.
    assert _ttl_seconds(400) == 1
    assert _ttl_seconds(1) == 1


def test_ttl_passes_through_none():
    assert _ttl_seconds(None) is None


# -- schema / filters --------------------------------------------------------


def test_filterable_fields_are_dicts_not_filter_objects():
    # `filterable_fields` is typed list[dict]; passing Tag() objects raises
    # inside the constructor, which fail-open would hide as a dead cache.
    assert _FILTERABLE_FIELDS == [
        {"name": "version", "type": "tag"},
        {"name": "entity_id", "type": "tag"},
        {"name": "cache_origin", "type": "tag"},
    ]


def test_filter_builds_exact_tag_match_per_attribute():
    # RediSearch tag values are escaped by TokenEscaper, which escapes "." and
    # "-" -- so a version and a ticket id both come through backslashed.
    rendered = str(_filter_for({"version": "7.8", "entity_id": "RET-4421"}))
    assert rendered == r"(@version:{7\.8} @entity_id:{RET\-4421})"


def test_filter_includes_the_sentinel_rather_than_omitting_the_field():
    rendered = str(_filter_for({"version": "latest", "entity_id": NO_ENTITY}))
    # "_" is not a tag separator, so the sentinel survives unescaped and cannot
    # collide with a real entity id (extraction.py requires [A-Z]{2,}-\d+).
    assert rendered == "(@version:{latest} @entity_id:{_none})"


def test_filter_for_no_attributes_is_none_not_a_match_all_tag():
    # An empty Tag value renders as "*" (match everything). Returning None keeps
    # redisvl from applying a filter at all instead of applying a useless one.
    assert _filter_for(None) is None
    assert _filter_for({}) is None
    assert _filter_for({"version": ""}) is None


# -- hit mapping -------------------------------------------------------------


def test_hit_maps_all_six_entry_fields():
    entry = _entry_from_hit(_hit())
    assert entry.id == "sre_semantic_cache:abc123"
    assert entry.prompt == "how do I tune maxmemory"
    assert entry.response == '{"response": "answer"}'
    assert entry.similarity == pytest.approx(0.95)
    assert entry.attributes == {
        "version": "latest",
        "entity_id": NO_ENTITY,
        "cache_origin": "dynamic",
    }
    assert entry.search_strategy == "semantic"


def test_hit_id_is_the_full_key_not_the_bare_entry_id():
    # set_entry returns astore's full key and delete_entry passes it to
    # adrop(keys=...); search must use the same shape or invalidation breaks.
    entry = _entry_from_hit(_hit(key="sre_semantic_cache:xyz", entry_id="xyz"))
    assert entry.id == "sre_semantic_cache:xyz"


def test_hit_preserves_entity_attribute_for_the_scope_check():
    # An empty attributes dict here would make service.py reject every
    # entity-scoped hit while general queries kept working.
    entry = _entry_from_hit(_hit(entity_id="RET-4421"))
    assert entry.attributes["entity_id"] == "RET-4421"


def test_hit_tolerates_missing_optional_fields():
    entry = _entry_from_hit({"key": "k", "vector_distance": 0.0})
    assert entry.prompt == "" and entry.response == ""
    assert entry.attributes == {}


# -- transport ---------------------------------------------------------------


def test_backend_satisfies_the_protocol():
    assert isinstance(RedisVLBackend(cache=StubCache()), CacheBackend)


@pytest.mark.asyncio
async def test_search_passes_converted_threshold_and_filter():
    stub = StubCache(hits=[_hit()])
    backend = RedisVLBackend(cache=stub)

    entries = await backend.search(
        "q", similarity_threshold=0.9, attributes={"version": "latest", "entity_id": NO_ENTITY}
    )

    assert len(entries) == 1
    assert stub.check_calls[0]["distance_threshold"] == pytest.approx(0.1)
    assert stub.check_calls[0]["filter"] is not None


@pytest.mark.asyncio
async def test_search_requests_more_than_one_candidate():
    # service.py scans for the first in-scope entry, so give it room to scan.
    stub = StubCache()
    await RedisVLBackend(cache=stub).search("q", similarity_threshold=0.9)
    assert stub.check_calls[0]["num_results"] > 1


@pytest.mark.asyncio
async def test_search_fails_open_on_error():
    stub = StubCache()
    stub.check_exc = RuntimeError("redis down")
    assert await RedisVLBackend(cache=stub).search("q", similarity_threshold=0.9) == []


@pytest.mark.asyncio
async def test_search_handles_none_hits():
    stub = StubCache(hits=None)
    stub.hits = None
    assert await RedisVLBackend(cache=stub).search("q", similarity_threshold=0.9) == []


@pytest.mark.asyncio
async def test_set_entry_returns_the_full_key_and_converts_ttl():
    stub = StubCache(store_key="sre_semantic_cache:deadbeef")
    backend = RedisVLBackend(cache=stub)

    entry_id = await backend.set_entry(
        "q", "a", attributes={"version": "latest"}, ttl_millis=3_600_000
    )

    assert entry_id == "sre_semantic_cache:deadbeef"
    assert stub.store_calls[0]["ttl"] == 3600
    assert stub.store_calls[0]["filters"] == {"version": "latest"}


@pytest.mark.asyncio
async def test_set_entry_fails_open_on_error():
    stub = StubCache()
    stub.store_exc = RuntimeError("nope")
    assert await RedisVLBackend(cache=stub).set_entry("q", "a") is None


@pytest.mark.asyncio
async def test_delete_entry_drops_by_key_not_id():
    """Guards the bug this shape exists to prevent.

    ``adrop(ids=...)`` re-prefixes what it is given, so passing astore's already
    prefixed key as an id would delete nothing while returning success -- which
    makes invalidate() clear the provenance link for a live entry.
    """
    stub = StubCache()
    backend = RedisVLBackend(cache=stub)

    assert await backend.delete_entry("sre_semantic_cache:abc123") is True
    assert stub.dropped == [{"ids": None, "keys": ["sre_semantic_cache:abc123"]}]


@pytest.mark.asyncio
async def test_delete_entry_reports_failure_rather_than_false_success():
    # invalidate() keeps the provenance link when this is False so a later pass
    # can retry; a falsely-True return would strand the entry until TTL.
    stub = StubCache()
    stub.drop_exc = RuntimeError("connection reset")
    assert await RedisVLBackend(cache=stub).delete_entry("k") is False


@pytest.mark.asyncio
async def test_store_then_delete_round_trips_one_identifier_shape():
    stub = StubCache(store_key="sre_semantic_cache:rt")
    backend = RedisVLBackend(cache=stub)

    entry_id = await backend.set_entry("q", "a", attributes={"version": "latest"})
    assert await backend.delete_entry(entry_id) is True
    assert stub.dropped[0]["keys"] == [entry_id]


@pytest.mark.asyncio
async def test_aclose_is_a_noop_for_the_shared_instance():
    # service.py closes its backend every turn; a memoized transport must not
    # tear down connections the next turn still needs.
    stub = StubCache()
    await RedisVLBackend(cache=stub).aclose()
    assert stub.check_calls == [] and stub.store_calls == []


# -- construction / memoization ---------------------------------------------


def test_cache_is_built_without_a_ttl(monkeypatch):
    """acheck() refreshes the TTL of every hit it returns.

    A cache-level TTL would therefore turn our fixed store-time TTLs into a
    sliding window, so a popular "latest" answer -- deliberately short-lived
    because it tracks a moving pointer -- would never expire. This pins the
    invariant so adding ``ttl=`` fails here instead of silently in production.

    Exercises the real ``_build_cache`` with redisvl's constructor and the
    vectorizer patched out, so no Redis or OpenAI call happens.
    """
    import redisvl.extensions.cache.llm as llm_mod

    import redis_sre_agent.core.semantic_cache.redisvl_backend as mod

    captured = {}

    class FakeSemanticCache:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self._ttl = kwargs.get("ttl")

    monkeypatch.setattr(llm_mod, "SemanticCache", FakeSemanticCache)
    monkeypatch.setattr(
        "redis_sre_agent.core.vectorizer_helpers.create_vectorizer",
        lambda cfg: object(),
    )

    cache = mod._build_cache(mod.global_settings)

    assert "ttl" not in captured, "a cache-level TTL makes every read slide the TTL"
    assert cache._ttl is None
    # The filterable fields must reach the schema as plain dicts.
    assert captured["filterable_fields"] == _FILTERABLE_FIELDS
    assert captured["name"] == mod.INDEX_NAME


def test_backend_is_built_once_per_process(monkeypatch):
    """Construction is expensive and blocking, so it must be memoized.

    Patches the builder rather than the real constructor so this test makes no
    Redis or OpenAI call.
    """
    import redis_sre_agent.core.semantic_cache.redisvl_backend as mod

    calls = []

    def _fake_build(cfg):
        calls.append(cfg)
        return StubCache()

    monkeypatch.setattr(mod, "_build_cache", _fake_build)
    reset_backend_cache()

    first = get_redisvl_backend()
    second = get_redisvl_backend()

    assert first is second
    assert len(calls) == 1
    reset_backend_cache()


def test_distinct_settings_get_distinct_backends(monkeypatch):
    import redis_sre_agent.core.semantic_cache.redisvl_backend as mod
    from redis_sre_agent.core.config import settings as live_settings

    monkeypatch.setattr(mod, "_build_cache", lambda cfg: StubCache())
    reset_backend_cache()

    other = live_settings.model_copy(update={"embedding_model": "some-other-model"})
    assert get_redisvl_backend(live_settings) is not get_redisvl_backend(other)
    reset_backend_cache()


def test_construction_failure_degrades_to_no_cache_and_is_not_memoized(monkeypatch):
    import redis_sre_agent.core.semantic_cache.redisvl_backend as mod

    attempts = []

    def _boom(cfg):
        attempts.append(cfg)
        raise RuntimeError("no redis")

    monkeypatch.setattr(mod, "_build_cache", _boom)
    reset_backend_cache()

    assert get_redisvl_backend() is None
    # Not cached, so a transient failure is retried on the next turn.
    assert get_redisvl_backend() is None
    assert len(attempts) == 2
    reset_backend_cache()
