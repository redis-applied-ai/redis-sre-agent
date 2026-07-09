"""Async HTTP client for the managed Redis LangCache service.

Wraps the REST endpoints verified in
``redis-docs/content/develop/ai/langcache/api-reference/api.yaml``:

* ``POST /v1/caches/{cacheId}/entries/search`` — search (exact then semantic)
* ``POST /v1/caches/{cacheId}/entries``        — set (returns ``entryId``)
* ``DELETE /v1/caches/{cacheId}/entries/{id}`` — delete a single entry
* ``DELETE /v1/caches/{cacheId}/entries``      — delete by attributes (deleteQuery)
* ``POST /v1/caches/{cacheId}/flush``          — flush all entries

Every method **fails open**: transport/HTTP errors are logged and converted to a
miss/no-op return value so the cache is transparent to the agent.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

import httpx

logger = logging.getLogger(__name__)

# LangCache search strategies (api.yaml SearchStrategy enum), ordered by priority.
DEFAULT_SEARCH_STRATEGIES: Sequence[str] = ("exact", "semantic")


@dataclass(frozen=True)
class LangCacheEntry:
    """A single cache entry returned by a search (api.yaml ``CacheEntry``)."""

    id: str
    prompt: str
    response: str
    similarity: float
    attributes: Dict[str, str]
    search_strategy: str

    @classmethod
    def from_payload(cls, payload: Dict[str, Any]) -> "LangCacheEntry":
        return cls(
            id=str(payload.get("id", "")),
            prompt=str(payload.get("prompt", "")),
            response=str(payload.get("response", "")),
            similarity=float(payload.get("similarity", 0.0) or 0.0),
            attributes=dict(payload.get("attributes") or {}),
            search_strategy=str(payload.get("searchStrategy", "")),
        )


class LangCacheClient:
    """Thin async wrapper around the LangCache REST API.

    Args:
        server_url: Base URL of the LangCache service.
        cache_id: The cache identifier (path segment).
        api_key: Bearer token for the ``Authorization`` header.
        timeout: Per-request timeout in seconds.
        client: Optional injected ``httpx.AsyncClient`` (for tests).
    """

    def __init__(
        self,
        *,
        server_url: str,
        cache_id: str,
        api_key: str,
        timeout: float = 5.0,
        client: Optional[httpx.AsyncClient] = None,
    ):
        self._base = server_url.rstrip("/")
        self._cache_id = cache_id
        self._timeout = timeout
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        self._client = client
        self._owns_client = client is None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    async def aclose(self) -> None:
        if self._client is not None and self._owns_client:
            await self._client.aclose()
            self._client = None

    def _url(self, suffix: str) -> str:
        return f"{self._base}/v1/caches/{self._cache_id}{suffix}"

    async def search(
        self,
        prompt: str,
        *,
        similarity_threshold: float,
        attributes: Optional[Dict[str, str]] = None,
        search_strategies: Sequence[str] = DEFAULT_SEARCH_STRATEGIES,
    ) -> List[LangCacheEntry]:
        """Search the cache. Returns matching entries (possibly empty) or [] on error."""
        body: Dict[str, Any] = {
            "prompt": prompt,
            "similarityThreshold": similarity_threshold,
            "searchStrategies": list(search_strategies),
        }
        if attributes:
            body["attributes"] = attributes
        try:
            client = await self._get_client()
            resp = await client.post(self._url("/entries/search"), json=body, headers=self._headers)
            resp.raise_for_status()
            data = resp.json().get("data") or []
            return [LangCacheEntry.from_payload(item) for item in data]
        except Exception as exc:
            logger.warning("LangCache search failed (fail-open miss): %s", exc)
            return []

    async def set_entry(
        self,
        prompt: str,
        response: str,
        *,
        attributes: Optional[Dict[str, str]] = None,
        ttl_millis: Optional[int] = None,
    ) -> Optional[str]:
        """Store an entry. Returns the new ``entry_id`` or None on error."""
        body: Dict[str, Any] = {"prompt": prompt, "response": response}
        if attributes:
            body["attributes"] = attributes
        if ttl_millis is not None:
            body["ttlMillis"] = ttl_millis
        try:
            client = await self._get_client()
            resp = await client.post(self._url("/entries"), json=body, headers=self._headers)
            resp.raise_for_status()
            return resp.json().get("entryId")
        except Exception as exc:
            logger.warning("LangCache set failed (fail-open no-op): %s", exc)
            return None

    async def delete_entry(self, entry_id: str) -> bool:
        """Delete a single entry by id. Returns True on success, False on error."""
        try:
            client = await self._get_client()
            resp = await client.delete(self._url(f"/entries/{entry_id}"), headers=self._headers)
            resp.raise_for_status()
            return True
        except Exception as exc:
            logger.warning("LangCache delete_entry failed: %s", exc)
            return False

    # Only per-entry delete is wired (the sole v1 caller is push invalidation).
    # LangCache also exposes deleteQuery (by attributes) and flush (full clear) —
    # add those wrappers if/when a break-glass caller needs them.
