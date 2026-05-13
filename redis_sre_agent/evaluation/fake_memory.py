"""Fake AMS memory session and scenario injection for eval harness."""

from __future__ import annotations

import contextlib
from types import SimpleNamespace
from typing import Any, AsyncIterator
from unittest import mock

from redis_sre_agent.core.agent_memory import (
    AgentMemoryService,
    LongTermSearchResult,
    WorkingMemoryResult,
)
from redis_sre_agent.evaluation.scenarios import EvalMemoryFixture, EvalScenario


def _stub_working_memory(context: str | None) -> Any:
    return SimpleNamespace(
        context=context,
        messages=[],
        memories=[],
        data={},
    )


def _record_to_namespace(record: Any) -> Any:
    return SimpleNamespace(
        text=record.text,
        memory_type=record.memory_type,
        id=record.id,
        topics=list(record.topics),
        entities=list(record.entities),
    )


class FakeMemorySession:
    """Fixture-backed drop-in for MemorySession used in eval scenarios."""

    def __init__(self, fixture: EvalMemoryFixture) -> None:
        self._fixture = fixture

    async def get_user_working_memory(
        self,
        *,
        session_id: str,
        user_id: str,
        create_if_missing: bool = True,
    ) -> WorkingMemoryResult:
        memory = _stub_working_memory(self._fixture.user_context)
        return WorkingMemoryResult(memory=memory, created=False)

    async def get_asset_working_memory(
        self,
        *,
        instance_id: str | None = None,
        cluster_id: str | None = None,
        fallback_session_id: str | None = None,
        create_if_missing: bool = True,
    ) -> WorkingMemoryResult:
        memory = _stub_working_memory(self._fixture.asset_context)
        return WorkingMemoryResult(memory=memory, created=False)

    async def search_user_long_term(
        self,
        *,
        query: str,
        user_id: str,
        limit: int = 10,
        offset: int = 0,
    ) -> LongTermSearchResult:
        all_records = [_record_to_namespace(r) for r in self._fixture.user_long_term]
        page = all_records[offset : offset + limit]
        next_offset = offset + len(page) if len(page) >= limit else None
        return LongTermSearchResult(memories=page, total=len(all_records), next_offset=next_offset)

    async def search_asset_long_term(
        self,
        *,
        query: str,
        instance_id: str | None = None,
        cluster_id: str | None = None,
        limit: int = 10,
        offset: int = 0,
        filter_preferences: bool = True,
    ) -> LongTermSearchResult:
        all_records = [_record_to_namespace(r) for r in self._fixture.asset_long_term]
        if filter_preferences:
            all_records = AgentMemoryService._filter_asset_memories(all_records)
        page = all_records[offset : offset + limit]
        next_offset = offset + len(page) if len(page) >= limit else None
        return LongTermSearchResult(memories=page, total=len(all_records), next_offset=next_offset)


def _has_memory(fixture: EvalMemoryFixture) -> bool:
    return bool(
        fixture.user_context
        or fixture.user_long_term
        or fixture.asset_context
        or fixture.asset_long_term
    )


def _has_asset_memory(fixture: EvalMemoryFixture) -> bool:
    return bool(fixture.asset_context or fixture.asset_long_term)


def _fake_open_session(fixture: EvalMemoryFixture):
    @contextlib.asynccontextmanager
    async def _patched(self) -> AsyncIterator[FakeMemorySession]:
        yield FakeMemorySession(fixture)

    return _patched


def _force_enabled_init(self) -> None:
    self._enabled = True


def _fake_target_entities(self, instance_id: Any = None, cluster_id: Any = None) -> list:
    # Return a synthetic entity so prepare_turn_context sets asset_scope=True
    # even when the scenario has no real Redis instance attached.
    return ["instance:eval-fixture"]


@contextlib.asynccontextmanager
async def inject_memory_fixture(scenario: "EvalScenario") -> AsyncIterator[None]:
    """Patch AgentMemoryService to serve fixture-backed memory for a scenario.

    No-ops when the scenario's memory fixture is entirely empty.
    When the fixture has asset content, also patches _target_entities so
    prepare_turn_context enables the asset memory path without a real instance.
    """
    fixture = scenario.memory
    if not _has_memory(fixture):
        yield
        return
    with contextlib.ExitStack() as stack:
        stack.enter_context(mock.patch.object(AgentMemoryService, "__init__", _force_enabled_init))
        stack.enter_context(
            mock.patch.object(AgentMemoryService, "open_session", _fake_open_session(fixture))
        )
        if _has_asset_memory(fixture):
            stack.enter_context(
                mock.patch.object(AgentMemoryService, "_target_entities", _fake_target_entities)
            )
        yield


__all__ = [
    "FakeMemorySession",
    "inject_memory_fixture",
]
