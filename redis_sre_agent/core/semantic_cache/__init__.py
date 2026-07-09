"""Semantic answer cache (LangCache) for the knowledge agent.

A flag-gated (``settings.semantic_cache_enabled``, default OFF) semantic answer
cache that sits above the knowledge-agent LangGraph run. On a sufficiently
similar prior question it serves the previously synthesized answer and
short-circuits the entire graph.

Backend split (see ``docs/design/semantic-cache-knowledge-agent.md``): LangCache
(managed) owns embeddings/index/similarity/TTL/attribute filters; our Redis owns
provenance (``path_hash -> {entry_id}`` reverse index, side metadata, tombstones).

``SemanticCache`` is the only entry point callers need; the submodules
(extraction, cacheability, provenance, client, rewrite, service) are imported
directly where used.
"""

from redis_sre_agent.core.semantic_cache.service import SemanticCache

__all__ = ["SemanticCache"]
