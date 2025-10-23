from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from redis_sre_agent.agent.langgraph_agent import FACT_CHECKER_PROMPT, SRELangGraphAgent


@pytest.mark.asyncio
@patch("redis_sre_agent.agent.langgraph_agent.ChatOpenAI")
async def test_fact_checker_skips_url_validation(mock_chat_openai):
    # Mock LLM to return minimal valid JSON
    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(
        return_value=MagicMock(
            content="""```json\n{\n  \"has_errors\": false,\n  \"validation_notes\": \"ok\"\n}\n```"""
        )
    )
    mock_chat_openai.return_value = mock_llm

    agent = SRELangGraphAgent()

    response = "See http://example.com/a and https://redis.io/docs/latest/ for details."

    _ = await agent._fact_check_response(response)

    # Inspect the messages sent to the fact-checker
    args = mock_llm.ainvoke.call_args
    messages = args.args[0] if args.args else args.kwargs.get("messages")

    sys_msg = messages[0]["content"] if isinstance(messages[0], dict) else messages[0].content
    user_msg = messages[1]["content"] if isinstance(messages[1], dict) else messages[1].content

    assert sys_msg == FACT_CHECKER_PROMPT
    assert "## URL Validation Results:" not in user_msg


@pytest.mark.asyncio
@patch("redis_sre_agent.agent.langgraph_agent.ChatOpenAI")
async def test_fact_checker_skips_out_of_scope(mock_chat_openai):
    # Mock LLM
    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock()
    mock_chat_openai.return_value = mock_llm

    agent = SRELangGraphAgent()
    _ = await agent._fact_check_response("No URLs here.")  # also no Redis terms -> out of scope

    # Ensure fact-check LLM was not called when out of Redis scope
    mock_llm.ainvoke.assert_not_called()
