"""Unit tests for shared terminal response synthesis helpers."""

import logging
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import HumanMessage

from redis_sre_agent.agent.terminal_synthesis import (
    TerminalSynthesisConfig,
    synthesize_terminal_response,
)
from redis_sre_agent.core.llm_token_usage import LLMTokenLimitExceededError


def _terminal_synthesis_config() -> TerminalSynthesisConfig:
    return TerminalSynthesisConfig(
        request_kind="unit.terminal_synthesis",
        system_prompt="Synthesize a final answer.",
        messages_heading="Messages",
        evidence_heading="Evidence",
        no_messages_text="No messages.",
        no_evidence_text="No evidence.",
        failure_log_message="Terminal synthesis failed: %s",
        empty_log_message="Terminal synthesis returned an empty response.",
        context_limit=2000,
        item_limit=500,
        message_item_limit=500,
        message_tail_limit=4,
    )


@pytest.mark.asyncio
async def test_synthesize_terminal_response_propagates_token_limit_error():
    guarded_invoke = AsyncMock(
        side_effect=LLMTokenLimitExceededError(
            "LLM token usage limit exceeded for unit.terminal_synthesis: "
            "used 16 total tokens; limit is 15"
        )
    )
    failure_response_factory = MagicMock(return_value="fallback")

    with pytest.raises(LLMTokenLimitExceededError, match="used 16 total tokens"):
        await synthesize_terminal_response(
            MagicMock(),
            config=_terminal_synthesis_config(),
            messages=[HumanMessage(content="What happened?")],
            tool_envelopes=[],
            guarded_invoke=guarded_invoke,
            failure_response_factory=failure_response_factory,
            logger=logging.getLogger("test"),
        )

    failure_response_factory.assert_not_called()


@pytest.mark.asyncio
async def test_synthesize_terminal_response_uses_fallback_for_generic_failure():
    guarded_invoke = AsyncMock(side_effect=RuntimeError("provider unavailable"))
    failure_response_factory = MagicMock(return_value="fallback")

    response = await synthesize_terminal_response(
        MagicMock(),
        config=_terminal_synthesis_config(),
        messages=[HumanMessage(content="What happened?")],
        tool_envelopes=[],
        guarded_invoke=guarded_invoke,
        failure_response_factory=failure_response_factory,
        logger=logging.getLogger("test"),
    )

    assert response == "fallback"
    failure_response_factory.assert_called_once_with()
