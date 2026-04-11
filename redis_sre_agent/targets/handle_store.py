"""Redis-backed private target handle storage."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, Iterable, Optional

from redis_sre_agent.core.redis import get_redis_client

from .contracts import TargetHandleRecord

logger = logging.getLogger(__name__)

_TARGET_HANDLE_STORE_PREFIX = "sre_target_handles"
_DEFAULT_TTL_SECONDS = 24 * 60 * 60
_DEFAULT_STORE: "RedisTargetHandleStore | None" = None


class RedisTargetHandleStore:
    """Persist private target handle records separately from thread context."""

    def __init__(self, *, key_prefix: str = _TARGET_HANDLE_STORE_PREFIX):
        self.key_prefix = key_prefix

    def _key(self, target_handle: str) -> str:
        return f"{self.key_prefix}:{target_handle}"

    @staticmethod
    def _ttl_seconds(record: TargetHandleRecord) -> int:
        expires_at = record.expires_at
        if not expires_at:
            return _DEFAULT_TTL_SECONDS
        try:
            value = expires_at.replace("Z", "+00:00") if expires_at.endswith("Z") else expires_at
            ttl = int(
                max(
                    1,
                    (datetime.fromisoformat(value) - datetime.now(timezone.utc)).total_seconds(),
                )
            )
            return ttl
        except Exception:
            return _DEFAULT_TTL_SECONDS

    async def save_record(self, record: TargetHandleRecord) -> None:
        client = get_redis_client()
        try:
            await client.set(
                self._key(record.target_handle),
                record.model_dump_json(),
                ex=self._ttl_seconds(record),
            )
        except Exception:
            logger.debug("Target handle store unavailable while saving %s", record.target_handle)

    async def save_records(self, records: Iterable[TargetHandleRecord]) -> None:
        for record in records:
            await self.save_record(record)

    async def get_record(self, target_handle: str) -> Optional[TargetHandleRecord]:
        client = get_redis_client()
        try:
            raw = await client.get(self._key(target_handle))
        except Exception:
            logger.debug("Target handle store unavailable while loading %s", target_handle)
            return None
        if not raw:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        try:
            return TargetHandleRecord.model_validate_json(raw)
        except Exception:
            logger.warning("Invalid target handle record for %s", target_handle)
            return None

    async def get_records(self, target_handles: Iterable[str]) -> Dict[str, TargetHandleRecord]:
        records: Dict[str, TargetHandleRecord] = {}
        for target_handle in target_handles:
            record = await self.get_record(target_handle)
            if record is not None:
                records[target_handle] = record
        return records


def get_target_handle_store() -> RedisTargetHandleStore:
    """Return the default target handle store."""
    global _DEFAULT_STORE
    if _DEFAULT_STORE is None:
        _DEFAULT_STORE = RedisTargetHandleStore()
    return _DEFAULT_STORE


def reset_target_handle_store() -> None:
    """Clear the cached target handle store singleton."""
    global _DEFAULT_STORE
    _DEFAULT_STORE = None
