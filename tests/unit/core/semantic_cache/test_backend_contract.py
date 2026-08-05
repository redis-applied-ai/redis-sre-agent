"""The backend-parametrized contract suite: one matrix, both REAL backends.

``test_service.py`` proves the *strategy* layer is transport-agnostic by driving
it through a Protocol-shaped fake. This file proves the other half: that each
real transport actually honours the contract that layer depends on -- unit
conversions, the attribute round trip, and the identifier shape.

Both backends run their real mapping code here. Only the outermost boundary is
faked, at the last line of code we own:

* LangCache -- an ``httpx.MockTransport``, so request construction and JSON
  parsing are exercised for real.
* redisvl -- a stub with ``acheck``/``astore``/``adrop``, since redisvl's own
  internals (vectorizer, index, Redis) are not ours to test.

Consequence: zero network calls and zero embedding calls. The memoized factory is
deliberately bypassed -- backends are constructed directly.
"""

import json

import httpx
import pytest

from redis_sre_agent.core.semantic_cache.backend import NO_ENTITY, CacheBackend
from redis_sre_agent.core.semantic_cache.client import LangCacheClient
from redis_sre_agent.core.semantic_cache.redisvl_backend import RedisVLBackend

# Tripwire: adding a method to CacheBackend must come with a contract case here.
# Without this, a new method silently gets no cross-backend coverage, and a
# missing implementation surfaces only as an AttributeError that service.py's
# fail-open swallows.
_COVERED_METHODS = {"search", "set_entry", "delete_entry", "aclose"}

_STORED_KEY = "sre_semantic_cache:contract"


def test_contract_covers_every_protocol_method():
    assert set(CacheBackend.__protocol_attrs__) == _COVERED_METHODS


# -- backend construction ----------------------------------------------------


class _RedisVLStub:
    """redisvl's SemanticCache surface, backed by an in-memory dict."""

    def __init__(self):
        self.entries = {}
        self.last_check = None

    async def acheck(self, prompt, num_results=1, filter_expression=None, distance_threshold=None):
        self.last_check = {
            "filter": str(filter_expression) if filter_expression is not None else None,
            "distance_threshold": distance_threshold,
        }
        # Return everything; the contract asserts on mapping, and service.py owns
        # scope selection. Shape mirrors redisvl: filters flattened onto the hit.
        return list(self.entries.values())

    async def astore(self, prompt, response, filters=None, ttl=None):
        hit = {
            "key": _STORED_KEY,
            "entry_id": "contract",
            "prompt": prompt,
            "response": response,
            "vector_distance": 0.02,
            **(filters or {}),
        }
        self.entries[_STORED_KEY] = hit
        return _STORED_KEY

    async def adrop(self, ids=None, keys=None):
        if ids is not None:
            # Mirrors the real re-prefixing, so passing a full key as an id
            # resolves to a name that does not exist and deletes nothing.
            for entry_id in ids:
                self.entries.pop(f"sre_semantic_cache:{entry_id}", None)
        for key in keys or []:
            self.entries.pop(key, None)


def _make_langcache():
    """Real LangCacheClient over an in-memory MockTransport LangCache."""
    store = {}

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content or b"{}")
        path = request.url.path
        if path.endswith("/entries/search"):
            wanted = body.get("attributes") or {}
            data = [
                entry
                for entry in store.values()
                if all(entry["attributes"].get(k) == v for k, v in wanted.items())
            ]
            return httpx.Response(200, json={"data": data})
        if path.endswith("/entries"):
            store[_STORED_KEY] = {
                "id": _STORED_KEY,
                "prompt": body["prompt"],
                "response": body["response"],
                "similarity": 0.98,
                "attributes": body.get("attributes") or {},
                "searchStrategy": "semantic",
            }
            return httpx.Response(200, json={"entryId": _STORED_KEY})
        if request.method == "DELETE":
            existed = store.pop(path.rsplit("/", 1)[-1], None)
            return httpx.Response(200 if existed else 404, json={})
        return httpx.Response(404, json={})

    return LangCacheClient(
        server_url="https://langcache.test",
        cache_id="cache-1",
        api_key="key-1",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    ), store


@pytest.fixture(params=["langcache", "redisvl"])
def backend(request):
    if request.param == "langcache":
        client, _ = _make_langcache()
        return client
    return RedisVLBackend(cache=_RedisVLStub())


# -- the contract ------------------------------------------------------------


def test_backend_satisfies_the_protocol(backend):
    assert isinstance(backend, CacheBackend)


@pytest.mark.asyncio
async def test_store_returns_an_id_that_search_reports_back(backend):
    """The identifier shape must be one thing across store, search and delete."""
    entry_id = await backend.set_entry(
        "how do I tune maxmemory",
        json.dumps({"response": "answer"}),
        attributes={"version": "latest", "entity_id": NO_ENTITY, "cache_origin": "dynamic"},
        ttl_millis=3_600_000,
    )
    assert entry_id

    entries = await backend.search(
        "how do I tune maxmemory",
        similarity_threshold=0.9,
        attributes={"version": "latest", "entity_id": NO_ENTITY},
    )
    assert [e.id for e in entries] == [entry_id]


@pytest.mark.asyncio
async def test_stored_attributes_survive_the_round_trip(backend):
    """service.py's scope check reads ``attributes``; an empty dict breaks it.

    With attributes dropped, general queries would keep working while every
    entity-scoped lookup silently missed -- so assert a ticket-scoped value
    positively, not just that rejection happens.
    """
    await backend.set_entry(
        "status of RET-4421",
        json.dumps({"response": "ticket answer"}),
        attributes={"version": "7.8", "entity_id": "RET-4421", "cache_origin": "dynamic"},
        ttl_millis=86_400_000,
    )

    entries = await backend.search(
        "status of RET-4421",
        similarity_threshold=0.9,
        attributes={"version": "7.8", "entity_id": "RET-4421"},
    )

    assert entries, "a stored entry must be findable"
    assert entries[0].attributes["entity_id"] == "RET-4421"
    assert entries[0].attributes["version"] == "7.8"


@pytest.mark.asyncio
async def test_response_survives_the_round_trip(backend):
    payload = json.dumps({"response": "answer", "search_results": [{"title": "Doc"}]})
    await backend.set_entry("q", payload, attributes={"version": "latest", "entity_id": NO_ENTITY})

    entries = await backend.search(
        "q", similarity_threshold=0.9, attributes={"version": "latest", "entity_id": NO_ENTITY}
    )
    assert entries[0].response == payload


@pytest.mark.asyncio
async def test_similarity_is_reported_as_similarity_not_distance(backend):
    await backend.set_entry("q", "a", attributes={"version": "latest", "entity_id": NO_ENTITY})
    entries = await backend.search(
        "q", similarity_threshold=0.9, attributes={"version": "latest", "entity_id": NO_ENTITY}
    )
    # Both backends must express a close match as a HIGH number, whatever their
    # library speaks internally.
    assert entries[0].similarity >= 0.9


@pytest.mark.asyncio
async def test_delete_removes_the_entry_it_names(backend):
    """The bug this shape exists to prevent: a delete that reports success and
    leaves the entry live makes invalidate() drop its provenance link, so no
    later pass can ever reach it."""
    entry_id = await backend.set_entry(
        "q", "a", attributes={"version": "latest", "entity_id": NO_ENTITY}
    )

    assert await backend.delete_entry(entry_id) is True

    entries = await backend.search(
        "q", similarity_threshold=0.9, attributes={"version": "latest", "entity_id": NO_ENTITY}
    )
    assert entries == [], "delete_entry returned True but the entry is still served"


@pytest.mark.asyncio
async def test_search_miss_returns_empty_list(backend):
    assert (
        await backend.search(
            "never stored", similarity_threshold=0.9, attributes={"version": "latest"}
        )
        == []
    )


@pytest.mark.asyncio
async def test_aclose_is_safe_to_call(backend):
    # Per-turn transports close their own client; shared ones no-op. Either way
    # service.py's `finally: aclose()` must never raise.
    await backend.aclose()


# -- fail-open ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_fails_open_when_the_transport_breaks():
    def exploding(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host")

    langcache = LangCacheClient(
        server_url="https://langcache.test",
        cache_id="c",
        api_key="k",
        client=httpx.AsyncClient(transport=httpx.MockTransport(exploding)),
    )

    class Broken:
        async def acheck(self, *a, **k):
            raise RuntimeError("redis down")

    for candidate in (langcache, RedisVLBackend(cache=Broken())):
        assert await candidate.search("q", similarity_threshold=0.9) == []


@pytest.mark.asyncio
async def test_set_entry_fails_open_when_the_transport_breaks():
    def exploding(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host")

    langcache = LangCacheClient(
        server_url="https://langcache.test",
        cache_id="c",
        api_key="k",
        client=httpx.AsyncClient(transport=httpx.MockTransport(exploding)),
    )

    class Broken:
        async def astore(self, *a, **k):
            raise RuntimeError("redis down")

    for candidate in (langcache, RedisVLBackend(cache=Broken())):
        assert await candidate.set_entry("q", "a") is None


@pytest.mark.asyncio
async def test_redisvl_delete_by_id_would_not_remove_the_entry():
    """Documents why ``delete_entry`` uses ``keys=`` and not ``ids=``.

    ``adrop(ids=...)`` prefixes what it receives, so handing it the already
    prefixed key that ``astore`` returned resolves to a nonexistent name.
    """
    stub = _RedisVLStub()
    backend = RedisVLBackend(cache=stub)
    entry_id = await backend.set_entry("q", "a", attributes={"version": "latest"})

    await stub.adrop(ids=[entry_id])  # the wrong call
    assert entry_id in stub.entries, "sanity check: ids= double-prefixes"

    await backend.delete_entry(entry_id)  # what the backend actually does
    assert entry_id not in stub.entries
