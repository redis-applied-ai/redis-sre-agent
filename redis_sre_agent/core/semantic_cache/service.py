"""SemanticCache orchestrator: read (lookup) and write (store) + invalidation.

This ties together the LangCache client (match + serve), the provenance store
(invalidate), and the extraction/rewrite/cacheability helpers. It is the only
object the agent and ingestion paths interact with.

Design references: read path §D, write path §H, invalidation §G, identifiers §I.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Sequence, Tuple

from langchain_core.messages import BaseMessage
from redis.asyncio import Redis

if TYPE_CHECKING:
    from redis_sre_agent.agent.models import AgentResponse

from redis_sre_agent.core.config import Settings
from redis_sre_agent.core.config import settings as global_settings
from redis_sre_agent.core.semantic_cache.cacheability import decide_cacheability
from redis_sre_agent.core.semantic_cache.client import LangCacheClient
from redis_sre_agent.core.semantic_cache.extraction import DEFAULT_VERSION, extract_cache_scope
from redis_sre_agent.core.semantic_cache.provenance import ProvenanceStore, path_hash_for_source
from redis_sre_agent.core.semantic_cache.rewrite import rewrite_query

logger = logging.getLogger(__name__)

# LangCache prompt field max length (api.yaml SearchEntriesRequest/SetEntryRequest).
_MAX_PROMPT_LEN = 1024
_CACHE_ORIGIN_DYNAMIC = "dynamic"


class SemanticCache:
    """Semantic answer cache sitting above the knowledge-agent graph."""

    def __init__(
        self,
        *,
        client: LangCacheClient,
        provenance: ProvenanceStore,
        similarity_threshold: float,
        ttl_latest_ms: int,
        ttl_pinned_ms: int,
    ):
        self._client = client
        self._provenance = provenance
        self._threshold = similarity_threshold
        self._ttl_latest_ms = ttl_latest_ms
        self._ttl_pinned_ms = ttl_pinned_ms

    # -- construction ---------------------------------------------------------

    @classmethod
    def from_settings(
        cls,
        redis_client: Redis,
        *,
        settings: Optional[Settings] = None,
        require_enabled: bool = True,
    ) -> Optional["SemanticCache"]:
        """Build a SemanticCache from settings, or None if it cannot/should not run.

        Returns None when LangCache credentials are missing. When
        ``require_enabled`` is True (serve/store paths) it also returns None
        while ``semantic_cache_enabled`` is False. Invalidation passes
        ``require_enabled=False`` so push invalidation keeps running even with
        the kill switch off (design §L). Callers treat None as "cache absent".
        """
        cfg = settings or global_settings
        if require_enabled and not cfg.semantic_cache_enabled:
            return None
        if not cfg.langcache_cache_id or not cfg.langcache_api_key:
            if cfg.semantic_cache_enabled:
                logger.warning(
                    "semantic_cache_enabled but LangCache credentials missing; disabling."
                )
            return None
        client = LangCacheClient(
            server_url=cfg.langcache_server_url,
            cache_id=cfg.langcache_cache_id.get_secret_value(),
            api_key=cfg.langcache_api_key.get_secret_value(),
        )
        provenance = ProvenanceStore(
            redis_client,
            tombstone_ttl_seconds=cfg.semantic_cache_inval_tombstone_ttl_seconds,
        )
        return cls(
            client=client,
            provenance=provenance,
            similarity_threshold=cfg.semantic_cache_similarity_threshold,
            ttl_latest_ms=cfg.semantic_cache_ttl_latest_ms,
            ttl_pinned_ms=cfg.semantic_cache_ttl_pinned_ms,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    # -- helpers --------------------------------------------------------------

    @staticmethod
    def _canonical_key(rewritten_query: str) -> str:
        return rewritten_query[:_MAX_PROMPT_LEN]

    @staticmethod
    def _path_hashes(search_results: Sequence[Dict[str, Any]]) -> List[str]:
        # Key strictly on source_document_path — the exact field ingestion hashes
        # for its tombstones (deduplication.py). A `source` fallback would mint a
        # hash ingestion never emits, so those reverse-index entries could never be
        # push-invalidated; such results simply get no reverse-index entry (the
        # fixed TTL is their only backstop).
        hashes: List[str] = []
        for result in search_results or []:
            source = str(result.get("source_document_path") or "").strip()
            if source:
                hashes.append(path_hash_for_source(source))
        return hashes

    def _ttl_for_version(self, version: str) -> int:
        return self._ttl_latest_ms if version == DEFAULT_VERSION else self._ttl_pinned_ms

    # -- read path (§D) -------------------------------------------------------

    async def canonical_key(
        self,
        query: str,
        conversation_history: Optional[List[BaseMessage]] = None,
    ) -> str:
        """Compute the canonical cache key for a query (rewrite + truncate).

        Exposed so a caller can compute the key once and reuse it for both
        ``lookup`` and ``store`` in the same turn (design §F: "computed once,
        reused as the store key"), avoiding a second nano call and guaranteeing
        the store and lookup keys match for a rewritten mid-conversation query.
        """
        return self._canonical_key(await rewrite_query(query, conversation_history))

    async def lookup(
        self,
        query: str,
        conversation_history: Optional[List[BaseMessage]] = None,
        *,
        rewritten_query: Optional[str] = None,
    ) -> Optional["AgentResponse"]:
        """Return a cached ``AgentResponse`` on a sufficiently-similar hit, else None.

        ``rewritten_query`` lets the caller supply a pre-computed canonical key
        (see :meth:`canonical_key`); when omitted it is computed here.
        Fails open: any error is logged and treated as a miss.
        """
        try:
            key = (
                rewritten_query
                if rewritten_query is not None
                else await self.canonical_key(query, conversation_history)
            )
            # Resolve version/entity from the canonical key (the rewritten,
            # standalone question) — not the raw query — so a context-resolved
            # version (e.g. a mid-conversation "what about for 7.2?") tags and
            # filters the entry correctly (§D/§F).
            scope = extract_cache_scope(key)
            attributes: Dict[str, str] = {"version": scope.version}
            if scope.entity_id:
                attributes["entity_id"] = scope.entity_id

            entries = await self._client.search(
                key,
                similarity_threshold=self._threshold,
                attributes=attributes,
            )
            if not entries:
                logger.debug("semantic-cache miss")
                return None

            candidate = entries[0]
            if candidate.similarity < self._threshold:
                return None

            # Post-filter safety net (§D note 4): the served entry's entity_id must
            # EQUAL the requested one — symmetrically. A general query (no entity_id)
            # must not receive a ticket-scoped entry, and vice versa. Holds
            # regardless of whether LangCache pre- or post-filters on attributes.
            if (candidate.attributes.get("entity_id") or None) != scope.entity_id:
                logger.debug("semantic-cache post-filter reject: entity_id mismatch")
                return None

            response = self._reconstruct_response(candidate.response)
            logger.info(
                "semantic-cache hit via %s (similarity=%.3f)",
                candidate.search_strategy or "?",
                candidate.similarity,
            )
            return response
        except Exception as exc:
            logger.warning("semantic-cache lookup failed (fail-open miss): %s", exc)
            return None

    @staticmethod
    def _reconstruct_response(stored_response: str) -> "AgentResponse":
        from redis_sre_agent.agent.models import AgentResponse

        try:
            payload = json.loads(stored_response)
            text = str(payload.get("response", ""))
            search_results = list(payload.get("search_results") or [])
        except (ValueError, TypeError):
            text, search_results = stored_response, []
        return AgentResponse(response=text, search_results=search_results, tool_envelopes=[])

    # -- write path (§H) ------------------------------------------------------

    async def store(
        self,
        query: str,
        response: str,
        search_results: Sequence[Dict[str, Any]],
        conversation_history: Optional[List[BaseMessage]] = None,
        *,
        rewritten_query: Optional[str] = None,
    ) -> Optional[str]:
        """Store a grounded answer. Fire-and-forget safe; returns entry_id or None.

        ``rewritten_query`` lets the caller reuse the key already computed for the
        lookup (design §F). Skips ungrounded answers and skips/undoes around fresh
        invalidation tombstones to close the write-vs-invalidate race (§H).
        """
        try:
            decision = decide_cacheability(list(search_results), response=response)
            if not decision.cacheable:
                logger.debug("semantic-cache store skipped: %s", decision.reason)
                return None

            path_hashes = self._path_hashes(search_results)
            if await self._provenance.has_fresh_tombstone(path_hashes):
                logger.debug("semantic-cache store skipped: fresh invalidation tombstone")
                return None

            key = (
                rewritten_query
                if rewritten_query is not None
                else await self.canonical_key(query, conversation_history)
            )
            # Scope from the canonical key so the stored version/entity match the
            # form the lookup filters on (§D/§F).
            scope = extract_cache_scope(key)
            attributes: Dict[str, str] = {
                "version": scope.version,
                "cache_origin": _CACHE_ORIGIN_DYNAMIC,
            }
            if scope.entity_id:
                attributes["entity_id"] = scope.entity_id

            payload = json.dumps(
                {"response": response, "search_results": list(search_results)}, default=str
            )
            entry_id = await self._client.set_entry(
                key,
                payload,
                attributes=attributes,
                ttl_millis=self._ttl_for_version(scope.version),
            )
            if not entry_id:
                return None

            meta = {
                "original_question": query,
                "rewritten_question": key,
                "version": scope.version,
                "entity_id": scope.entity_id,
                "num_sources": len(search_results),
                # Compute each row's path_hash inline (aligned per-result). Do NOT
                # zip against path_hashes: that list omits rows without
                # source_document_path, which would shift pairings for mixed
                # citations and attach the wrong hash to a result.
                "provenance": [
                    {
                        "source_document_path": r.get("source_document_path"),
                        "path_hash": (
                            path_hash_for_source(sp)
                            if (sp := str(r.get("source_document_path") or "").strip())
                            else None
                        ),
                        "index_type": r.get("index_type"),
                        "title": r.get("title"),
                        "doc_version": r.get("version"),
                        "document_hash": r.get("document_hash"),
                    }
                    for r in search_results
                ],
            }
            recorded = await self._provenance.record_entry(entry_id, path_hashes, meta=meta)
            if path_hashes and not recorded:
                # The reverse-index links failed to write, so this entry could not
                # be push-invalidated (only TTL would reach it). Roll the LangCache
                # write back rather than leave an un-invalidatable orphan (§G/§H).
                logger.warning("semantic-cache store undone: provenance recording failed")
                await self._client.delete_entry(entry_id)
                await self._provenance.remove_entry(entry_id, path_hashes)
                return None

            # Recheck for a tombstone that appeared during the write window (§H).
            if await self._provenance.has_fresh_tombstone(path_hashes):
                logger.debug("semantic-cache store undone: tombstone appeared during write")
                await self._client.delete_entry(entry_id)
                await self._provenance.remove_entry(entry_id, path_hashes)
                return None

            logger.info("semantic-cache stored entry (sources=%d)", len(search_results))
            return entry_id
        except Exception as exc:
            logger.warning("semantic-cache store failed (no-op): %s", exc)
            return None

    # -- invalidation (§G) ----------------------------------------------------

    async def invalidate(self, source_document_paths: Sequence[str]) -> int:
        """Push-invalidate all cache entries citing the given changed source docs.

        Runs even when serving is disabled (kill-switch semantics) and fails
        open. Returns the number of LangCache entries deleted.
        """
        deleted = 0
        try:
            for source in source_document_paths or []:
                source = str(source or "").strip()
                if not source:
                    continue
                path_hash = path_hash_for_source(source)
                # Write the tombstone FIRST so a concurrent store that completes
                # mid-invalidation observes it (on its pre-store check or post-SADD
                # recheck) and undoes itself — closing the window before we clear
                # the reverse index (§H).
                await self._provenance.write_tombstone(path_hash)
                entry_ids = await self._provenance.entries_for_path(path_hash)
                # Only clear reverse-index links for entries we actually deleted.
                # A failed delete means the LangCache row may still exist, so we
                # keep its link so a later invalidation can retry — dropping it
                # would strand the row (reachable only by TTL) (§G).
                succeeded = []
                for entry_id in entry_ids:
                    if await self._client.delete_entry(entry_id):
                        deleted += 1
                        succeeded.append(entry_id)
                await self._provenance.clear_path(path_hash, succeeded)
        except Exception as exc:
            logger.warning("semantic-cache invalidate failed: %s", exc)
        return deleted


# Actions that mean a source document was replaced or removed (not a pure add).
_INVALIDATING_ACTIONS = {"update", "updated", "delete", "deleted", "remove", "removed"}


def _changed_source_paths(source_document_changes: Any) -> List[str]:
    """Extract replaced/removed source paths from an ingestion change summary.

    Accepts the summary dict (with a ``files`` list of ``{path, action}``) or a
    plain list of such file dicts. Pure adds and unchanged docs are ignored.
    """
    if isinstance(source_document_changes, dict):
        files = source_document_changes.get("files") or []
    elif isinstance(source_document_changes, list):
        files = source_document_changes
    else:
        return []
    paths: List[str] = []
    for entry in files:
        if not isinstance(entry, dict):
            continue
        action = str(entry.get("action") or "").strip().lower()
        path = str(entry.get("path") or entry.get("file") or "").strip()
        if path and action in _INVALIDATING_ACTIONS:
            paths.append(path)
    return paths


async def invalidate_changed_sources(
    source_document_changes: Any,
    *,
    redis_client: Optional[Redis] = None,
    settings: Optional[Settings] = None,
) -> int:
    """Push-invalidate cache entries for docs replaced/removed during ingestion.

    Runs regardless of ``semantic_cache_enabled`` (kill-switch semantics, §L);
    no-op when LangCache credentials are absent. Fails open. Returns the number
    of LangCache entries deleted.
    """
    paths = _changed_source_paths(source_document_changes)
    if not paths:
        return 0
    try:
        from redis_sre_agent.core.redis import get_redis_client

        client = redis_client if redis_client is not None else get_redis_client()
        cache = SemanticCache.from_settings(client, settings=settings, require_enabled=False)
        if cache is None:
            return 0
        try:
            return await cache.invalidate(paths)
        finally:
            await cache.aclose()
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("semantic-cache ingestion invalidation failed: %s", exc)
        return 0


# -- request-path helpers (build-from-settings + fail-open + fire-and-forget) --
#
# Used by the knowledge-only turn in the worker (docket_tasks). Kept here so the
# serve/store wiring lives in one place regardless of which caller uses it.

# Retain references to in-flight fire-and-forget writes so they are not
# garbage-collected before they run (see asyncio.create_task docs).
_STORE_TASKS: "set[asyncio.Task[Any]]" = set()


async def lookup_cached_answer(
    query: str,
    conversation_history: Optional[List[BaseMessage]] = None,
) -> Tuple[Optional["AgentResponse"], Optional[str]]:
    """Look up a cached answer. Returns ``(response_or_None, canonical_key_or_None)``.

    Builds a short-lived cache from settings; returns ``(None, None)`` when the
    cache is disabled or misconfigured. The returned key can be reused for a
    later store so the rewrite is computed once (§F). Fails open on any error.
    """
    try:
        from redis_sre_agent.core.redis import get_redis_client

        cache = SemanticCache.from_settings(get_redis_client())
        if cache is None:
            return None, None
        try:
            key = await cache.canonical_key(query, conversation_history)
            return await cache.lookup(query, conversation_history, rewritten_query=key), key
        finally:
            await cache.aclose()
    except Exception as exc:
        logger.warning("semantic-cache lookup failed (fail-open miss): %s", exc)
        return None, None


async def _run_store(
    query: str,
    response: str,
    search_results: Sequence[Dict[str, Any]],
    conversation_history: Optional[List[BaseMessage]],
    rewritten_query: Optional[str],
) -> None:
    from redis_sre_agent.core.redis import get_redis_client

    cache = SemanticCache.from_settings(get_redis_client())
    if cache is None:
        return
    try:
        await cache.store(
            query, response, search_results, conversation_history, rewritten_query=rewritten_query
        )
    except Exception as exc:  # pragma: no cover - store() already fails open
        logger.warning("semantic-cache background store failed: %s", exc)
    finally:
        await cache.aclose()


def schedule_store(
    query: str,
    response: str,
    search_results: Sequence[Dict[str, Any]],
    conversation_history: Optional[List[BaseMessage]] = None,
    rewritten_query: Optional[str] = None,
) -> None:
    """Fire-and-forget store; never adds user-facing latency, never raises.

    Cacheability (grounded vs ungrounded) and the write-vs-invalidate race are
    handled inside ``store``; a no-op when the cache is disabled/misconfigured.
    """
    task = asyncio.create_task(
        _run_store(query, response, search_results, conversation_history, rewritten_query)
    )
    _STORE_TASKS.add(task)
    task.add_done_callback(_STORE_TASKS.discard)
