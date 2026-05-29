from types import SimpleNamespace

import pytest

import redis_sre_agent.core.llm_token_usage as token_usage_module
from redis_sre_agent.core.llm_token_usage import (
    LLMContextTokenBudgetExceededError,
    LLMTokenLimitExceededError,
    enforce_llm_context_token_budget,
    estimate_llm_context_tokens,
    extract_llm_token_usage,
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


def test_record_llm_token_usage_extracts_without_enforcing_context_budget(monkeypatch):
    monkeypatch.setattr(
        token_usage_module,
        "settings",
        SimpleNamespace(llm_context_token_budget=5),
    )

    usage = record_llm_token_usage(SimpleNamespace(usage_metadata={"total_tokens": 6}))

    assert usage.total_tokens == 6


def test_estimate_llm_context_tokens_counts_message_content():
    estimated = estimate_llm_context_tokens(
        [{"role": "user", "content": "Summarize Redis persistence."}],
        model="gpt-4o-mini",
    )

    assert estimated > 4


def test_enforce_llm_context_token_budget_allows_estimate_at_budget():
    payload = [{"role": "user", "content": "short"}]
    estimated = estimate_llm_context_tokens(payload, model="gpt-4o-mini")

    result = enforce_llm_context_token_budget(
        payload,
        request_kind="unit.allowed",
        model="gpt-4o-mini",
        token_budget=estimated,
    )

    assert result == estimated


def test_enforce_llm_context_token_budget_raises_when_request_exceeds_budget():
    with pytest.raises(
        LLMContextTokenBudgetExceededError,
        match="unit.large.*estimated .* input tokens; budget is 10",
    ) as exc_info:
        enforce_llm_context_token_budget(
            [{"role": "user", "content": "token " * 100}],
            request_kind="unit.large",
            model="gpt-4o-mini",
            token_budget=10,
        )

    assert isinstance(exc_info.value, LLMTokenLimitExceededError)


def test_enforce_llm_context_token_budget_counts_bound_tool_payloads():
    llm = SimpleNamespace(
        model_name="gpt-4o-mini",
        kwargs={
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "large_tool",
                        "description": "token " * 100,
                        "parameters": {"type": "object", "properties": {}},
                    },
                }
            ]
        },
    )

    with pytest.raises(
        LLMContextTokenBudgetExceededError,
        match="unit.tools.*estimated .* input tokens; budget is 30",
    ):
        enforce_llm_context_token_budget(
            [{"role": "user", "content": "short"}],
            request_kind="unit.tools",
            llm=llm,
            token_budget=30,
        )
