"""Provenance reverse index for the semantic cache (stored in *our* Redis).

Three structures, three jobs (design §C):

* ``cache_prov:{path_hash}``  → SET of LangCache ``entry_id`` s (invalidation).
* ``cache_meta:{entry_id}``   → JSON side metadata (debug/audit; off the serve path).
* ``cache_inval:{path_hash}`` → short-TTL tombstone (write-vs-invalidate race).

``path_hash`` is ``sha256(source_document_path)[:16]`` — the *same* hash
ingestion uses (``deduplication.py:66``), so the invalidation signal and the
cache speak one identifier with no translation.

Every method fails open: any Redis error is logged and swallowed so the cache
never raises into the agent path.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Dict, Iterable, List, Optional

from redis.asyncio import Redis

from redis_sre_agent.core.keys import RedisKeys

logger = logging.getLogger(__name__)


def path_hash_for_source(source_document_path: str) -> str:
    """Compute the path hash exactly as ingestion does (``deduplication.py:66``)."""
    return hashlib.sha256(source_document_path.encode("utf-8")).hexdigest()[:16]


class ProvenanceStore:
    """Reverse-index + side-metadata + tombstone operations in our Redis."""

    def __init__(self, redis_client: Redis, *, tombstone_ttl_seconds: int = 120):
        self._redis = redis_client
        self._tombstone_ttl = max(int(tombstone_ttl_seconds), 1)

    async def record_entry(
        self,
        entry_id: str,
        path_hashes: Iterable[str],
        *,
        meta: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Index a stored entry: SADD per cited path_hash + persist side metadata.

        Returns True on success, False on any error (fail open).
        """
        try:
            for path_hash in {h for h in path_hashes if h}:
                await self._redis.sadd(RedisKeys.semantic_cache_provenance(path_hash), entry_id)
            if meta is not None:
                await self._redis.set(
                    RedisKeys.semantic_cache_meta(entry_id),
                    json.dumps(meta, default=str),
                )
            return True
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("semantic-cache provenance record failed: %s", exc)
            return False

    async def remove_entry(self, entry_id: str, path_hashes: Iterable[str]) -> None:
        """Undo a recorded entry (used by the post-SADD write-race recheck)."""
        try:
            for path_hash in {h for h in path_hashes if h}:
                await self._redis.srem(RedisKeys.semantic_cache_provenance(path_hash), entry_id)
            await self._redis.delete(RedisKeys.semantic_cache_meta(entry_id))
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("semantic-cache provenance remove failed: %s", exc)

    async def entries_for_path(self, path_hash: str) -> List[str]:
        """Return the entry_ids cited by a source path (SMEMBERS), or [] on error."""
        try:
            members = await self._redis.smembers(RedisKeys.semantic_cache_provenance(path_hash))
            return [m.decode() if isinstance(m, bytes) else str(m) for m in (members or [])]
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("semantic-cache provenance read failed: %s", exc)
            return []

    async def clear_path(self, path_hash: str, entry_ids: Iterable[str]) -> None:
        """Remove reverse-index links + side metadata for the given entries only.

        Uses SREM per entry (not a full-set delete) so entries whose LangCache
        delete failed keep their link and can be retried on a later invalidation.
        Redis drops the set automatically once its last member is removed.
        """
        try:
            prov_key = RedisKeys.semantic_cache_provenance(path_hash)
            for entry_id in entry_ids:
                await self._redis.srem(prov_key, entry_id)
                await self._redis.delete(RedisKeys.semantic_cache_meta(entry_id))
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("semantic-cache provenance clear failed: %s", exc)

    async def write_tombstone(self, path_hash: str) -> None:
        """Write a short-TTL tombstone marking that this path just changed."""
        try:
            await self._redis.set(
                RedisKeys.semantic_cache_invalidation(path_hash),
                "1",
                ex=self._tombstone_ttl,
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("semantic-cache tombstone write failed: %s", exc)

    async def has_fresh_tombstone(self, path_hashes: Iterable[str]) -> bool:
        """True if any cited path has a fresh tombstone (content just changed)."""
        try:
            for path_hash in {h for h in path_hashes if h}:
                if await self._redis.exists(RedisKeys.semantic_cache_invalidation(path_hash)):
                    return True
            return False
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("semantic-cache tombstone check failed: %s", exc)
            # Fail safe: if we cannot confirm freshness, assume changed (skip write).
            return True
