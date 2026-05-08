import pytest
from pydantic import ValidationError

from redis_sre_agent.core.agent_memory import (
    AgentMemoryService,
    LongTermSearchResult,
    WorkingMemoryResult,
)
from redis_sre_agent.evaluation.scenarios import EvalMemoryFixture, EvalMemoryRecord


def test_eval_memory_fixture_parses_user_and_asset_fields():
    fixture = EvalMemoryFixture.model_validate({
        "user_context": "User prefers remediation-first answers",
        "user_long_term": [
            {"text": "User prefers remediation-first troubleshooting", "memory_type": "semantic"}
        ],
        "asset_context": "Cluster had failover during backup window",
        "asset_long_term": [
            {"text": "Redis cluster had an OOM incident last week", "memory_type": "episodic"}
        ],
    })
    assert fixture.user_context == "User prefers remediation-first answers"
    assert len(fixture.user_long_term) == 1
    assert fixture.user_long_term[0].text == "User prefers remediation-first troubleshooting"
    assert fixture.user_long_term[0].memory_type == "semantic"
    assert fixture.asset_context == "Cluster had failover during backup window"
    assert len(fixture.asset_long_term) == 1
    assert fixture.asset_long_term[0].memory_type == "episodic"


def test_eval_memory_fixture_defaults_to_empty():
    fixture = EvalMemoryFixture()
    assert fixture.user_context is None
    assert fixture.user_long_term == []
    assert fixture.asset_context is None
    assert fixture.asset_long_term == []


def test_eval_memory_record_rejects_extra_fields():
    with pytest.raises(ValidationError):
        EvalMemoryRecord.model_validate({"text": "hi", "unknown_field": "bad"})


def test_eval_memory_fixture_rejects_extra_fields():
    with pytest.raises(ValidationError):
        EvalMemoryFixture.model_validate({"user_context": "x", "unknown_field": "bad"})


@pytest.fixture
def user_fixture():
    return EvalMemoryFixture(
        user_context="User prefers remediation-first answers",
        user_long_term=[
            EvalMemoryRecord(text="User prefers remediation-first troubleshooting", memory_type="semantic"),
        ],
    )


@pytest.fixture
def asset_fixture():
    return EvalMemoryFixture(
        asset_context="Cluster had failover last week",
        asset_long_term=[
            EvalMemoryRecord(text="Redis cluster had OOM incident during backup", memory_type="episodic"),
            EvalMemoryRecord(text="Operator prefers concise replies", memory_type="semantic"),
        ],
    )


@pytest.mark.asyncio
async def test_fake_memory_session_returns_user_working_memory(user_fixture):
    from redis_sre_agent.evaluation.fake_memory import FakeMemorySession
    session = FakeMemorySession(user_fixture)
    result = await session.get_user_working_memory(session_id="s1", user_id="u1")
    assert isinstance(result, WorkingMemoryResult)
    assert result.memory is not None
    assert result.memory.context == "User prefers remediation-first answers"
    assert result.created is False


@pytest.mark.asyncio
async def test_fake_memory_session_returns_user_long_term(user_fixture):
    from redis_sre_agent.evaluation.fake_memory import FakeMemorySession
    session = FakeMemorySession(user_fixture)
    result = await session.search_user_long_term(query="latency", user_id="u1", limit=10, offset=0)
    assert isinstance(result, LongTermSearchResult)
    assert len(result.memories) == 1
    assert result.memories[0].text == "User prefers remediation-first troubleshooting"


@pytest.mark.asyncio
async def test_fake_memory_session_search_user_long_term_respects_limit(user_fixture):
    from redis_sre_agent.evaluation.fake_memory import FakeMemorySession
    fixture = EvalMemoryFixture(
        user_long_term=[
            EvalMemoryRecord(text="Memory A", memory_type="semantic"),
            EvalMemoryRecord(text="Memory B", memory_type="semantic"),
            EvalMemoryRecord(text="Memory C", memory_type="semantic"),
        ]
    )
    session = FakeMemorySession(fixture)
    result = await session.search_user_long_term(query="q", user_id="u1", limit=2, offset=0)
    assert len(result.memories) == 2
    result_p2 = await session.search_user_long_term(query="q", user_id="u1", limit=2, offset=2)
    assert len(result_p2.memories) == 1


@pytest.mark.asyncio
async def test_fake_memory_session_filters_preferences_from_asset_scope(asset_fixture):
    from redis_sre_agent.evaluation.fake_memory import FakeMemorySession
    session = FakeMemorySession(asset_fixture)
    result = await session.search_asset_long_term(
        query="oom", instance_id="i1", cluster_id=None,
        limit=10, offset=0, filter_preferences=True,
    )
    texts = [m.text for m in result.memories]
    assert "Redis cluster had OOM incident during backup" in texts
    assert "Operator prefers concise replies" not in texts


@pytest.mark.asyncio
async def test_fake_memory_session_skips_filter_when_flag_false(asset_fixture):
    from redis_sre_agent.evaluation.fake_memory import FakeMemorySession
    session = FakeMemorySession(asset_fixture)
    result = await session.search_asset_long_term(
        query="oom", instance_id="i1", cluster_id=None,
        limit=10, offset=0, filter_preferences=False,
    )
    assert len(result.memories) == 2


@pytest.mark.asyncio
async def test_inject_memory_fixture_patches_agent_memory_service(user_fixture):
    from redis_sre_agent.evaluation.fake_memory import FakeMemorySession, inject_memory_fixture
    from redis_sre_agent.evaluation.scenarios import EvalScenario

    scenario = EvalScenario.model_validate({
        "id": "test/memory-injection",
        "name": "Memory injection test",
        "provenance": {
            "source_kind": "synthetic",
            "source_pack": "test",
            "source_pack_version": "2026-05-08",
            "golden": {"expectation_basis": "human_authored"},
        },
        "execution": {"lane": "agent_only", "agent": "knowledge_only", "query": "test"},
        "memory": {
            "user_context": "User prefers remediation-first answers",
            "user_long_term": [
                {"text": "User prefers remediation-first troubleshooting", "memory_type": "semantic"}
            ],
        },
    })

    captured = {}

    async with inject_memory_fixture(scenario):
        service = AgentMemoryService()
        assert service._enabled is True  # __init__ patched to force-enable
        async with service.open_session() as session:
            captured["session"] = session

    assert isinstance(captured["session"], FakeMemorySession)


@pytest.mark.asyncio
async def test_inject_memory_fixture_is_noop_for_empty_fixture():
    from redis_sre_agent.evaluation.fake_memory import inject_memory_fixture
    from redis_sre_agent.evaluation.scenarios import EvalScenario

    scenario = EvalScenario.model_validate({
        "id": "test/no-memory",
        "name": "No memory",
        "provenance": {
            "source_kind": "synthetic",
            "source_pack": "test",
            "source_pack_version": "2026-05-08",
            "golden": {"expectation_basis": "human_authored"},
        },
        "execution": {"lane": "agent_only", "agent": "knowledge_only", "query": "test"},
    })

    service_before_enabled = AgentMemoryService()._enabled

    async with inject_memory_fixture(scenario):
        service = AgentMemoryService()
        assert service._enabled == service_before_enabled
