"""Semantic answer cache for the knowledge agent.

A flag-gated (``settings.semantic_cache_enabled``, default OFF) semantic answer
cache that sits above the knowledge-agent LangGraph run. On a sufficiently
similar prior question it serves the previously synthesized answer and
short-circuits the entire graph.

Two transports, chosen by ``settings.semantic_cache_backend``, behind one
:class:`~redis_sre_agent.core.semantic_cache.backend.CacheBackend` seam:

* ``redisvl`` (default) -- ``redisvl``'s ``SemanticCache`` on this service's own
  Redis. No external provisioning; embeddings computed client-side.
* ``langcache`` -- the managed LangCache service, which owns embeddings, index,
  similarity and attribute filters; requires credentials.

Either way our Redis owns provenance (``path_hash -> {entry_id}`` reverse index,
side metadata, tombstones), and the whole strategy layer in ``service.py`` is
shared verbatim. See ``docs/how-to/semantic-cache.md``.

``SemanticCache`` is the only entry point callers need; the submodules
(backend, extraction, cacheability, provenance, client, redisvl_backend, rewrite,
service) are imported directly where used.
"""

from redis_sre_agent.core.semantic_cache.service import SemanticCache

__all__ = ["SemanticCache"]
