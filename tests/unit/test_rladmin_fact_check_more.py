"""Additional unit tests for rladmin CLI detection in fact-checker.

Covers:
- Multiple rladmin commands across lines are detected and de-duplicated
- No rladmin commands -> section is omitted in fact-check input
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from redis_sre_agent.agent.langgraph_agent import SRELangGraphAgent


@pytest.mark.asyncio
@patch("redis_sre_agent.agent.langgraph_agent.ChatOpenAI")
async def test_cli_detection_multiple_commands_unique(mock_chat_openai):
    # Mock LLM to return minimal valid JSON in fence
    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(
        return_value=MagicMock(
            content="""```json\n{\n  \"has_errors\": false,\n  \"validation_notes\": \"ok\",\n  \"url_validation_performed\": true\n}\n```"""
        )
    )
    mock_chat_openai.return_value = mock_llm

    agent = SRELangGraphAgent()

    response = (
        "First try: rladmin list databases\n"
        "Then again: rladmin list databases\n"
        "Finally check: rladmin get database stats"
    )

    _ = await agent._fact_check_response(response)

    # Inspect what was sent to the fact-checker
    args = mock_llm.ainvoke.call_args
    messages = args.args[0] if args.args else args.kwargs.get("messages")
    user_msg = messages[1]["content"] if isinstance(messages[1], dict) else messages[1].content

    # One section
    assert user_msg.count("Detected CLI Commands (to validate)") == 1

    # Extract the CLI section only
    start = user_msg.index("Detected CLI Commands (to validate)")
    section = user_msg[start:]

    # Unique commands listed once within the section
    assert section.count("rladmin list databases") == 1
    assert "rladmin get database stats" in section


@pytest.mark.asyncio
@patch("redis_sre_agent.agent.langgraph_agent.ChatOpenAI")
async def test_cli_detection_absent_section(mock_chat_openai):
    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(
        return_value=MagicMock(
            content="""```json\n{\n  \"has_errors\": false,\n  \"validation_notes\": \"ok\",\n  \"url_validation_performed\": true\n}\n```"""
        )
    )
    mock_chat_openai.return_value = mock_llm

    agent = SRELangGraphAgent()

    response = "No CLI suggestions here."
    _ = await agent._fact_check_response(response)

    args = mock_llm.ainvoke.call_args
    messages = args.args[0] if args.args else args.kwargs.get("messages")
    user_msg = messages[1]["content"] if isinstance(messages[1], dict) else messages[1].content

    assert "Detected CLI Commands (to validate)" not in user_msg
