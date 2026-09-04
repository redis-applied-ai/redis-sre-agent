"""US-005: cacheability gate truth table (only grounded answers are stored)."""

from redis_sre_agent.core.semantic_cache.cacheability import decide_cacheability


def test_ungrounded_empty_results_not_cacheable():
    decision = decide_cacheability([], response="some answer")
    assert decision.cacheable is False
    assert decision.reason == "ungrounded"


def test_ungrounded_none_results_not_cacheable():
    decision = decide_cacheability(None, response="some answer")
    assert decision.cacheable is False
    assert decision.reason == "ungrounded"


def test_grounded_answer_cacheable():
    decision = decide_cacheability([{"source_document_path": "a.md"}], response="answer")
    assert decision.cacheable is True
    assert decision.reason == "grounded"


def test_empty_response_not_cacheable_even_if_grounded():
    decision = decide_cacheability([{"source_document_path": "a.md"}], response="   ")
    assert decision.cacheable is False
    assert decision.reason == "empty_response"


def test_response_optional_defaults_to_grounding_only():
    # When response is not supplied, only grounding is considered.
    assert decide_cacheability([{"x": 1}]).cacheable is True
    assert decide_cacheability([]).cacheable is False
