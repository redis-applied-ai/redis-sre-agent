"""Request-path helpers used by the knowledge-only worker turn (docket_tasks).

These are the real integration seam (the knowledge agent class is eval-only), so
they must fail open when disabled and reuse one canonical key for lookup+store.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import redis_sre_agent.core.semantic_cache.service as service_mod
from redis_sre_agent.core.semantic_cache.service import (
    _STORE_TASKS,
    lookup_cached_answer,
    schedule_store,
)


@pytest.mark.asyncio
async def test_lookup_returns_none_when_cache_disabled():
    # from_settings returns None when disabled/misconfigured => (None, None).
    with (
        patch.object(service_mod.SemanticCache, "from_settings", return_value=None),
        patch("redis_sre_agent.core.redis.get_redis_client", return_value=MagicMock()),
    ):
        result, key = await lookup_cached_answer("how do I tune maxmemory?")
    assert result is None and key is None


@pytest.mark.asyncio
async def test_lookup_computes_key_once_and_reuses_it_for_lookup():
    fake_cache = MagicMock()
    fake_cache.canonical_key = AsyncMock(return_value="canonical-q")
    fake_cache.lookup = AsyncMock(return_value="CACHED_RESPONSE")
    fake_cache.aclose = AsyncMock()

    with (
        patch.object(service_mod.SemanticCache, "from_settings", return_value=fake_cache),
        patch("redis_sre_agent.core.redis.get_redis_client", return_value=MagicMock()),
    ):
        result, key = await lookup_cached_answer("q", conversation_history=None)

    assert result == "CACHED_RESPONSE"
    assert key == "canonical-q"
    # The canonical key computed once is the one passed to lookup (design §F).
    fake_cache.lookup.assert_awaited_once()
    assert fake_cache.lookup.await_args.kwargs["rewritten_query"] == "canonical-q"
    fake_cache.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_lookup_fails_open_on_error():
    with (
        patch.object(service_mod.SemanticCache, "from_settings", side_effect=RuntimeError("boom")),
        patch("redis_sre_agent.core.redis.get_redis_client", return_value=MagicMock()),
    ):
        result, key = await lookup_cached_answer("q")
    assert result is None and key is None


@pytest.mark.asyncio
async def test_schedule_store_runs_store_in_background():
    fake_cache = MagicMock()
    fake_cache.store = AsyncMock(return_value="entry-1")
    fake_cache.aclose = AsyncMock()

    with (
        patch.object(service_mod.SemanticCache, "from_settings", return_value=fake_cache),
        patch("redis_sre_agent.core.redis.get_redis_client", return_value=MagicMock()),
    ):
        schedule_store("q", "answer", [{"source_document_path": "a.md"}], None, "canonical-q")
        # Let the fire-and-forget task run to completion.
        await asyncio.gather(*list(_STORE_TASKS))

    fake_cache.store.assert_awaited_once()
    assert fake_cache.store.await_args.kwargs["rewritten_query"] == "canonical-q"
    fake_cache.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_schedule_store_noop_when_disabled():
    with (
        patch.object(service_mod.SemanticCache, "from_settings", return_value=None),
        patch("redis_sre_agent.core.redis.get_redis_client", return_value=MagicMock()),
    ):
        schedule_store("q", "answer", [{"source_document_path": "a.md"}])
        await asyncio.gather(*list(_STORE_TASKS))
    # No cache built => nothing to assert beyond "did not raise".


@pytest.mark.asyncio
async def test_lookup_preserves_key_when_lookup_errors():
    """If the lookup path errors after the key is computed, the key is still
    returned so the store can reuse it (no second nano rewrite)."""
    fake_cache = MagicMock()
    fake_cache.canonical_key = AsyncMock(return_value="canonical-q")
    fake_cache.lookup = AsyncMock(side_effect=RuntimeError("lookup boom"))
    fake_cache.aclose = AsyncMock()
    with (
        patch.object(service_mod.SemanticCache, "from_settings", return_value=fake_cache),
        patch("redis_sre_agent.core.redis.get_redis_client", return_value=MagicMock()),
    ):
        result, key = await lookup_cached_answer("q")
    assert result is None
    assert key == "canonical-q"
    fake_cache.aclose.assert_awaited_once()
