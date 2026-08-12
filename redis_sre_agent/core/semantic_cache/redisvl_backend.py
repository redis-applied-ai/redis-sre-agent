"""``redisvl``-backed transport for the semantic answer cache.

Same strategy as the LangCache transport, different tool: ``redisvl``'s
``SemanticCache`` runs on the plain Redis this service already uses, so the cache
works with no external provisioning.

The one real operational difference is that embeddings are computed
**client-side** here, where LangCache computes them server-side. A repeated query
is free (``create_vectorizer`` attaches an ``EmbeddingsCache``), but a *novel*
query pays an embedding round trip before the miss is even known.

Two unit conversions live here so the strategy layer never learns them:

* **Threshold** -- ``distance_threshold`` is Redis COSINE distance in ``[0, 2]``
  where *lower* is stricter, the inverse of our similarity setting.
* **TTL** -- ``astore`` takes seconds; ``semantic_cache_ttl_*_ms`` are millis.

**Identifier shape.** ``astore`` returns the *full prefixed Redis key*, while
``adrop(ids=...)`` expects an unprefixed id and re-prefixes it itself. Passing
one to the other deletes nothing while appearing to succeed -- which would make
``invalidate`` clear the provenance link for a live entry and strand it past its
own retry path. So the full key is the single identifier used everywhere: what
``set_entry`` returns, what ``search`` reads from ``hit["key"]``, and what goes
to ``adrop(keys=...)``.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from redisvl.query.filter import Tag

from redis_sre_agent.core.config import Settings
from redis_sre_agent.core.config import settings as global_settings
from redis_sre_agent.core.semantic_cache.client import CacheEntry

logger = logging.getLogger(__name__)

# Index name for the cache's own RediSearch index, in the service's own Redis.
# Changing this (or the fields/embedding model below) orphans existing entries;
# they expire on their own TTL.
INDEX_NAME = "sre_semantic_cache"

# Declared up front: redisvl bakes filterable fields into the index schema, so
# they must exist before the first store. These are plain dicts -- the
# `filterable_fields` parameter is typed `list[dict]`, NOT a list of query-filter
# objects, and passing `Tag(...)` objects raises inside the constructor (which
# service.py's fail-open would then swallow into a permanently dead cache).
_FILTERABLE_FIELDS: List[Dict[str, Any]] = [
    {"name": "version", "type": "tag"},
    {"name": "entity_id", "type": "tag"},
    {"name": "cache_origin", "type": "tag"},
]
_ATTRIBUTE_FIELDS = tuple(str(field["name"]) for field in _FILTERABLE_FIELDS)

# The attribute pre-filter is exact, so one hit is normally enough. A few extra
# cost almost nothing and give service.py's in-scope scan something to work with
# if a filter ever fails to apply.
_NUM_RESULTS = 4


def _distance_for(similarity_threshold: float) -> float:
    """Similarity (higher is stricter) -> COSINE distance (lower is stricter)."""
    return max(0.0, min(2.0, 1.0 - float(similarity_threshold)))


def _similarity_for(vector_distance: Any) -> float:
    """COSINE distance -> similarity, the inverse of :func:`_distance_for`."""
    return 1.0 - float(vector_distance or 0.0)


def _ttl_seconds(ttl_millis: Optional[int]) -> Optional[int]:
    """Milliseconds -> whole seconds, floored at 1.

    Flooring matters: redisvl treats a TTL of 0 as "no TTL" (store forever), so a
    sub-second TTL must not round down to it.
    """
    if ttl_millis is None:
        return None
    return max(1, round(int(ttl_millis) / 1000))


def _filter_for(attributes: Optional[Dict[str, str]]) -> Any:
    """AND together an exact tag match per supplied attribute.

    Fields with no value are skipped rather than filtered on, because an empty
    ``Tag`` value renders as ``*`` -- match everything -- which would silently
    widen the query instead of narrowing it.
    """
    expression = None
    for name in _ATTRIBUTE_FIELDS:
        value = (attributes or {}).get(name)
        if not value:
            continue
        clause = Tag(name) == value
        expression = clause if expression is None else expression & clause
    return expression


def _entry_from_hit(hit: Dict[str, Any]) -> CacheEntry:
    """Map a redisvl hit onto the backend-neutral :class:`CacheEntry`.

    All six fields matter. ``attributes`` especially: redisvl calls these
    "filters" and returns them flattened onto the hit, so leaving them out would
    make service.py's scope check reject every entity-scoped hit while general
    queries kept working -- a partial failure hidden behind fail-open.
    """
    return CacheEntry(
        # The full Redis key, not the bare entry_id -- see the module docstring.
        id=str(hit.get("key", "")),
        prompt=str(hit.get("prompt", "")),
        response=str(hit.get("response", "")),
        similarity=_similarity_for(hit.get("vector_distance")),
        attributes={name: str(hit[name]) for name in _ATTRIBUTE_FIELDS if hit.get(name)},
        # redisvl has no server-side exact-match tier; every hit is a vector hit.
        search_strategy="semantic",
    )


class RedisVLBackend:
    """A :class:`CacheBackend` over ``redisvl``'s ``SemanticCache``.

    Accepts the underlying cache by injection so tests can drive the real mapping
    logic against a stub with no Redis, no vectorizer and no network.
    """

    def __init__(self, cache: Any):
        self._cache = cache

    async def search(
        self,
        prompt: str,
        *,
        similarity_threshold: float,
        attributes: Optional[Dict[str, str]] = None,
    ) -> List[CacheEntry]:
        """Search the cache. Returns matching entries (possibly empty) or [] on error."""
        try:
            hits = await self._cache.acheck(
                prompt,
                num_results=_NUM_RESULTS,
                filter_expression=_filter_for(attributes),
                distance_threshold=_distance_for(similarity_threshold),
            )
            return [_entry_from_hit(hit) for hit in hits or []]
        except Exception as exc:
            logger.warning("redisvl cache search failed (fail-open miss): %s", exc)
            return []

    async def set_entry(
        self,
        prompt: str,
        response: str,
        *,
        attributes: Optional[Dict[str, str]] = None,
        ttl_millis: Optional[int] = None,
    ) -> Optional[str]:
        """Store an entry. Returns the full Redis key, or None on error."""
        try:
            return await self._cache.astore(
                prompt,
                response,
                filters=dict(attributes or {}),
                ttl=_ttl_seconds(ttl_millis),
            )
        except Exception as exc:
            logger.warning("redisvl cache set failed (fail-open no-op): %s", exc)
            return None

    async def delete_entry(self, entry_id: str) -> bool:
        """Delete one entry by the key ``set_entry``/``search`` returned.

        Uses ``keys=`` rather than ``ids=`` because ``entry_id`` is already the
        full prefixed key; ``ids=`` would prefix it a second time and delete
        nothing. Returns True only if the drop did not raise -- an
        already-absent key counts as gone, which is what ``invalidate`` asks.
        """
        try:
            await self._cache.adrop(keys=[entry_id])
            return True
        except Exception as exc:
            logger.warning("redisvl cache delete_entry failed: %s", exc)
            return False

    async def aclose(self) -> None:
        """No-op: this instance is process-wide and shared across turns.

        service.py closes its backend in a ``finally`` on every turn. For a
        memoized transport that must not tear anything down, or the next turn
        would find dead connections. See :func:`get_redisvl_backend`.
        """
        return None


# Built once per process. Construction is expensive AND blocking:
# `SemanticCache.__init__` does a synchronous Redis round trip, and
# `create_vectorizer()` makes an *uncached* synchronous OpenAI call to discover
# embedding dimensions (redisvl's `_set_model_dims` calls the private `_embed`,
# bypassing its own EmbeddingsCache despite a comment claiming otherwise).
# service.py builds a cache twice per turn, so without this every turn would pay
# both costs twice.
#
# Not keyed on settings: `from_settings` uses global settings on every production
# path, so one instance per process is the only shape that occurs. Tests that vary
# settings call `reset_backend_cache`.
_BACKEND: Optional["RedisVLBackend"] = None
_BUILD_FAILED = False


def _build_cache(cfg: Settings) -> Any:
    """Construct the underlying ``redisvl`` cache. Blocking; call once."""
    from redisvl.extensions.cache.llm import SemanticCache

    from redis_sre_agent.core.vectorizer_helpers import create_vectorizer

    return SemanticCache(
        name=INDEX_NAME,
        vectorizer=create_vectorizer(cfg),
        filterable_fields=_FILTERABLE_FIELDS,
        redis_url=cfg.redis_url.get_secret_value(),
        # Deliberately no `ttl=`. `acheck()` refreshes the TTL of every hit it
        # returns, so a cache-level TTL would turn our fixed store-time TTLs into
        # a sliding window -- and a popular "latest" answer, which is short-lived
        # precisely because it tracks a moving pointer, would never expire.
        # Per-entry TTLs passed to `astore(ttl=...)` are unaffected by reads.
    )


def get_redisvl_backend(settings: Optional[Settings] = None) -> Optional[RedisVLBackend]:
    """Return the process-wide backend, building it at most once.

    Deliberately synchronous. A plain function called from a coroutine has no
    await point inside it, so two concurrent turns cannot interleave through it
    and no lock is needed. Wrapping the build in ``asyncio.to_thread`` would
    *introduce* the double-construction race that a lock would then have to
    guard, to avoid a single once-per-process stall that is smaller than what the
    knowledge-search path already takes on the loop today.

    Returns None (and logs) if construction fails, so a misconfigured cache
    degrades to "no cache" instead of breaking the agent.

    A failure is remembered, deliberately. The realistic failure is *permanent* --
    an index-schema mismatch after changing ``filterable_fields`` or
    ``embedding_model`` -- and every retry pays the uncached blocking OpenAI
    dimension probe again, twice per turn, on the event loop. So a broken cache
    would not just be dead, it would actively slow every request. Trading
    recovery-without-restart for that is worth it: this cache is a non-essential
    optimization that already fails open, and a worker restart clears the flag.
    """
    global _BACKEND, _BUILD_FAILED
    if _BACKEND is not None or _BUILD_FAILED:
        return _BACKEND
    try:
        _BACKEND = RedisVLBackend(_build_cache(settings or global_settings))
    except Exception as exc:
        _BUILD_FAILED = True
        logger.warning("redisvl semantic cache unavailable (disabling): %s", exc)
    return _BACKEND


def reset_backend_cache() -> None:
    """Forget the memoized backend and any remembered failure.

    Used by tests, and by ``set_vectorizer_factory`` since a module-global factory
    override cannot be detected from settings.
    """
    global _BACKEND, _BUILD_FAILED
    _BACKEND = None
    _BUILD_FAILED = False
