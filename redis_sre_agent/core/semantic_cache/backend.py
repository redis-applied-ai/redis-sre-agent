"""Backend seam for the semantic answer cache.

``SemanticCache`` (service.py) owns all cache *strategy* -- query rewrite, scope
extraction, cacheability, provenance, tombstones, invalidation -- and reaches its
transport through exactly the four methods declared here. Two transports exist:

* :class:`~redis_sre_agent.core.semantic_cache.client.LangCacheClient` -- the
  managed LangCache REST service, which embeds server-side.
* :class:`~redis_sre_agent.core.semantic_cache.redisvl_backend.RedisVLBackend`
  -- ``redisvl``'s ``SemanticCache`` on plain Redis, which embeds client-side.

The contract deliberately speaks LangCache's units -- **similarity** (higher is
stricter) and **milliseconds** -- because those are the units the existing
``semantic_cache_*`` settings already use. A backend whose library speaks other
units converts at its own boundary so the strategy layer never learns them.

Nothing in this repo type-checks (``make lint`` is ruff-only and mypy is not
wired into any gate), so conformance is asserted at runtime instead: the Protocol
is ``runtime_checkable`` and the tests assert ``isinstance`` for every backend.
That catches a method added here but missed in one implementation, which would
otherwise surface only as an ``AttributeError`` swallowed by service.py's
fail-open handlers.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Protocol, runtime_checkable

from redis_sre_agent.core.semantic_cache.client import CacheEntry

# Sentinel for "this query names no entity".
#
# A tag filter cannot express "field is absent", and redisvl's ``Tag`` renders an
# empty value as ``*`` -- match EVERYTHING, not nothing -- so omitting entity_id
# would let a general query match ticket-scoped entries. Writing an explicit
# value keeps the filter an exact equality match on either backend.
#
# Collision-free by construction: extraction.py only ever produces entity ids
# matching ``[A-Z]{2,}-\d+``, which this cannot match.
NO_ENTITY = "_none"


@runtime_checkable
class CacheBackend(Protocol):
    """The transport surface ``SemanticCache`` depends on.

    Every method **fails open**: transport errors are logged and converted to a
    miss/no-op return value so the cache stays transparent to the agent.
    """

    async def search(
        self,
        prompt: str,
        *,
        similarity_threshold: float,
        attributes: Optional[Dict[str, str]] = None,
    ) -> List[CacheEntry]:
        """Return candidate entries ordered best-first, or ``[]`` on any error.

        ``similarity_threshold`` is a similarity, where higher is stricter.
        """
        ...

    async def set_entry(
        self,
        prompt: str,
        response: str,
        *,
        attributes: Optional[Dict[str, str]] = None,
        ttl_millis: Optional[int] = None,
    ) -> Optional[str]:
        """Store an entry and return an opaque id for it, or None on error.

        The returned id is whatever :meth:`delete_entry` accepts; callers treat
        it as opaque and only ever round-trip it.
        """
        ...

    async def delete_entry(self, entry_id: str) -> bool:
        """Delete the entry named by an id from :meth:`set_entry`/:meth:`search`.

        Returns True only when the entry is confirmed gone. ``invalidate`` keeps
        the provenance link for anything that returns False so a later pass can
        retry, so a falsely-True return permanently strands the entry.
        """
        ...

    async def aclose(self) -> None:
        """Release only resources this instance exclusively owns.

        A per-turn transport closes its client here. A process-lifetime transport
        is shared across turns and MUST make this a no-op -- see
        ``RedisVLBackend.aclose``.
        """
        ...
