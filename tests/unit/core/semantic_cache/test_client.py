"""US-003: LangCacheClient HTTP wrapper — payload shapes + fail-open behavior."""

import httpx
import pytest

from redis_sre_agent.core.semantic_cache.client import LangCacheClient


class _FakeResponse:
    def __init__(self, status_code=200, payload=None, raise_exc=None):
        self.status_code = status_code
        self._payload = payload or {}
        self._raise_exc = raise_exc

    def raise_for_status(self):
        if self._raise_exc is not None:
            raise self._raise_exc

    def json(self):
        return self._payload


class _FakeHTTPClient:
    """Records calls and returns queued responses (or raises)."""

    def __init__(self):
        self.calls = []
        self.responses = {}  # method -> _FakeResponse or Exception

    async def post(self, url, json=None, headers=None):
        return self._respond("post", url, json, headers)

    async def delete(self, url, headers=None):
        return self._respond("delete", url, None, headers)

    def _respond(self, method, url, json, headers):
        self.calls.append({"method": method, "url": url, "json": json, "headers": headers})
        result = self.responses.get(method)
        if isinstance(result, Exception):
            raise result
        return result if result is not None else _FakeResponse()

    async def aclose(self):
        pass


def _make_client(fake):
    return LangCacheClient(
        server_url="https://lc.example.com",
        cache_id="cache-1",
        api_key="secret",
        client=fake,
    )


@pytest.mark.asyncio
async def test_search_sends_strategies_and_attributes():
    fake = _FakeHTTPClient()
    fake.responses["post"] = _FakeResponse(
        payload={
            "data": [
                {
                    "id": "a" * 32,
                    "prompt": "q",
                    "response": "r",
                    "similarity": 0.97,
                    "attributes": {"version": "latest"},
                    "searchStrategy": "semantic",
                }
            ]
        }
    )
    client = _make_client(fake)
    entries = await client.search("q", similarity_threshold=0.9, attributes={"version": "latest"})

    call = fake.calls[0]
    assert call["url"] == "https://lc.example.com/v1/caches/cache-1/entries/search"
    assert call["json"]["searchStrategies"] == ["exact", "semantic"]
    assert call["json"]["similarityThreshold"] == 0.9
    assert call["json"]["attributes"] == {"version": "latest"}
    assert call["headers"]["Authorization"] == "Bearer secret"
    assert len(entries) == 1
    assert entries[0].similarity == 0.97
    assert entries[0].search_strategy == "semantic"


@pytest.mark.asyncio
async def test_search_fails_open_to_empty_list():
    fake = _FakeHTTPClient()
    fake.responses["post"] = httpx.ConnectError("boom")
    client = _make_client(fake)
    assert await client.search("q", similarity_threshold=0.9) == []


@pytest.mark.asyncio
async def test_set_entry_returns_entry_id_with_ttl():
    fake = _FakeHTTPClient()
    fake.responses["post"] = _FakeResponse(status_code=201, payload={"entryId": "e" * 32})
    client = _make_client(fake)
    entry_id = await client.set_entry(
        "prompt", "response", attributes={"version": "7.8"}, ttl_millis=1000
    )

    assert entry_id == "e" * 32
    body = fake.calls[0]["json"]
    assert body["prompt"] == "prompt"
    assert body["response"] == "response"
    assert body["attributes"] == {"version": "7.8"}
    assert body["ttlMillis"] == 1000


@pytest.mark.asyncio
async def test_set_entry_fails_open_to_none():
    fake = _FakeHTTPClient()
    fake.responses["post"] = RuntimeError("nope")
    client = _make_client(fake)
    assert await client.set_entry("p", "r") is None


@pytest.mark.asyncio
async def test_delete_entry_success_and_failure():
    fake = _FakeHTTPClient()
    fake.responses["delete"] = _FakeResponse(status_code=204)
    client = _make_client(fake)
    assert await client.delete_entry("e" * 32) is True
    assert fake.calls[0]["url"] == "https://lc.example.com/v1/caches/cache-1/entries/" + "e" * 32

    fake.responses["delete"] = httpx.ConnectError("down")
    assert await client.delete_entry("e" * 32) is False
