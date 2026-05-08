import pytest
from pydantic import ValidationError

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
