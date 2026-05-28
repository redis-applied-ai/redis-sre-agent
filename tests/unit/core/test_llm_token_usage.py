from types import SimpleNamespace

import pytest

import redis_sre_agent.core.llm_token_usage as token_usage_module
from redis_sre_agent.core.llm_token_usage import (
    LLMTokenLimitExceededError,
    extract_llm_token_usage,
    llm_token_usage_scope,
    record_llm_token_usage,
)


def test_extract_llm_token_usage_from_langchain_usage_metadata():
    response = SimpleNamespace(
        usage_metadata={
            "input_tokens": 4,
            "output_tokens": 6,
            "total_tokens": 10,
        }
    )

    usage = extract_llm_token_usage(response)

    assert usage.prompt_tokens == 4
    assert usage.completion_tokens == 6
    assert usage.total_tokens == 10


def test_extract_llm_token_usage_from_openai_usage_object():
    response = SimpleNamespace(
        usage=SimpleNamespace(
            prompt_tokens=3,
            completion_tokens=8,
            total_tokens=11,
        )
    )

    usage = extract_llm_token_usage(response)

    assert usage.prompt_tokens == 3
    assert usage.completion_tokens == 8
    assert usage.total_tokens == 11


def test_extract_llm_token_usage_uses_components_when_total_is_zero():
    response = SimpleNamespace(
        usage_metadata={
            "input_tokens": 4,
            "output_tokens": 6,
            "total_tokens": 0,
        }
    )

    usage = extract_llm_token_usage(response)

    assert usage.prompt_tokens == 4
    assert usage.completion_tokens == 6
    assert usage.total_tokens == 10


def test_extract_llm_token_usage_preserves_zero_total_without_components():
    response = SimpleNamespace(
        usage_metadata={
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
        }
    )

    usage = extract_llm_token_usage(response)

    assert usage.prompt_tokens == 0
    assert usage.completion_tokens == 0
    assert usage.total_tokens == 0


def test_record_llm_token_usage_accumulates_within_scope():
    with llm_token_usage_scope(limit=15) as state:
        record_llm_token_usage(SimpleNamespace(usage_metadata={"total_tokens": 7}))
        record_llm_token_usage(SimpleNamespace(usage_metadata={"total_tokens": 8}))

    assert state.total_tokens == 15


def test_record_llm_token_usage_raises_when_scope_exceeds_limit():
    with llm_token_usage_scope(limit=10) as state:
        record_llm_token_usage(
            SimpleNamespace(usage_metadata={"total_tokens": 6}),
            request_kind="unit.first",
        )
        with pytest.raises(LLMTokenLimitExceededError, match="unit.second.*used 11"):
            record_llm_token_usage(
                SimpleNamespace(usage_metadata={"total_tokens": 5}),
                request_kind="unit.second",
            )

    assert state.total_tokens == 11


def test_record_llm_token_usage_enforces_limit_when_zero_total_has_components():
    with llm_token_usage_scope(limit=5) as state:
        with pytest.raises(LLMTokenLimitExceededError, match="unit.zero.*used 6"):
            record_llm_token_usage(
                SimpleNamespace(
                    usage_metadata={
                        "input_tokens": 4,
                        "output_tokens": 2,
                        "total_tokens": 0,
                    }
                ),
                request_kind="unit.zero",
            )

    assert state.prompt_tokens == 4
    assert state.completion_tokens == 2
    assert state.total_tokens == 6


def test_token_usage_scope_resets_between_turns():
    with llm_token_usage_scope(limit=10):
        record_llm_token_usage(SimpleNamespace(usage_metadata={"total_tokens": 9}))

    with llm_token_usage_scope(limit=10) as state:
        record_llm_token_usage(SimpleNamespace(usage_metadata={"total_tokens": 9}))

    assert state.total_tokens == 9


def test_unscoped_recording_uses_configured_limit_for_single_response(monkeypatch):
    monkeypatch.setattr(
        token_usage_module,
        "settings",
        SimpleNamespace(llm_single_turn_token_limit=5),
    )

    with pytest.raises(LLMTokenLimitExceededError, match="used 6"):
        record_llm_token_usage(SimpleNamespace(usage_metadata={"total_tokens": 6}))
