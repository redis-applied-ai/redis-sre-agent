import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from redis_sre_agent.agent.langgraph_agent import SRELangGraphAgent


@pytest.mark.asyncio
async def test_compose_final_markdown_builds_messages_and_payload(caplog):
    # Bypass __init__ to avoid real LLM init; set minimal settings needed
    with patch.object(SRELangGraphAgent, "__init__", lambda self: None):
        agent = SRELangGraphAgent()
        agent.settings = SimpleNamespace(
            openai_model_mini="test-mini", openai_api_key="test-key", llm_timeout=5
        )
        agent._run_cache_active = False

        captured = {}

        class FakeLLM:
            def __init__(self, *args, **kwargs):
                self.kwargs = kwargs
                self.last_msgs = None

            async def ainvoke(self, msgs):
                self.last_msgs = msgs
                captured["msgs"] = msgs
                return SimpleNamespace(content="## Initial Assessment\nOK")

        fake_llm = FakeLLM()

        # Patch ChatOpenAI used inside _compose_final_markdown
        with patch("redis_sre_agent.agent.langgraph_agent.ChatOpenAI", return_value=fake_llm):
            initial = ["Duplicated", "Duplicated", "Unique finding"]
            recommendations = [
                {
                    "title": "Latency",
                    "steps": [
                        {
                            "description": "Reduce N by half",
                            "commands": ["echo fix-latency"],
                            "api_examples": ["GET /v1/latency"],
                        }
                    ],
                },
                {
                    "title": "Latency",  # duplicate title to test consolidation instruction
                    "steps": [{"description": "Reduce N by half"}],
                },
                {"title": "Memory", "steps": []},
            ]
            instance_ctx = {"instance_id": "i-123"}

            result = await agent._compose_final_markdown(
                initial_assessment_lines=initial,
                per_topic_recommendations=recommendations,
                instance_ctx=instance_ctx,
            )

        # Returns LLM content verbatim when it's a string
        assert result.startswith("## Initial Assessment\nOK")

        # Verify messages sent to the LLM contain the expected instructions and payload
        msgs = captured["msgs"]
        assert len(msgs) == 2, "Should send exactly one SystemMessage and one HumanMessage"

        # System message guardrails present
        system_content = msgs[0].content
        assert "CRITICAL RULES" in system_content
        assert "Do NOT invent facts" in system_content
        assert "You MAY remove duplicates" in system_content

        # Human message contains headings-only outline and consolidation rules
        human_content = msgs[1].content
        assert "ONE set of top-level headings" in human_content
        assert "## Initial Assessment" in human_content
        assert "## What I'm Seeing" in human_content
        assert "## My Recommendation" in human_content
        assert "## Supporting Info" in human_content
        assert "Consolidation rules" in human_content
        assert "Use '### <topic or plan title>' sub-headings" in human_content

        # Payload JSON is embedded verbatim in the HumanMessage
        expected_payload = {
            "initial_assessment_lines": initial,
            "per_topic_recommendations": recommendations,
            "instance": instance_ctx,
        }
        expected_json = json.dumps(expected_payload, default=str)
        assert expected_json in human_content


@pytest.mark.asyncio
async def test_compose_final_markdown_normalizes_list_content():
    # Bypass __init__ and supply minimal settings
    with patch.object(SRELangGraphAgent, "__init__", lambda self: None):
        agent = SRELangGraphAgent()
        agent.settings = SimpleNamespace(
            openai_model_mini="test-mini", openai_api_key="test-key", llm_timeout=5
        )
        agent._run_cache_active = False

        class FakeLLM:
            async def ainvoke(self, msgs):
                parts = [
                    {"text": "Part1"},
                    "Part2",
                    {"content": "Part3"},
                    123,  # ignored non-str/non-dict
                ]
                return SimpleNamespace(content=parts)

        with patch("redis_sre_agent.agent.langgraph_agent.ChatOpenAI", return_value=FakeLLM()):
            result = await agent._compose_final_markdown(
                initial_assessment_lines=["x"],
                per_topic_recommendations=[],
                instance_ctx=None,
            )

    assert result == "Part1\nPart2\nPart3"


@pytest.mark.asyncio
async def test_compose_final_markdown_handles_empty_content(caplog):
    with patch.object(SRELangGraphAgent, "__init__", lambda self: None):
        agent = SRELangGraphAgent()
        agent.settings = SimpleNamespace(
            openai_model_mini="test-mini", openai_api_key="test-key", llm_timeout=5
        )
        agent._run_cache_active = False

        class FakeLLM:
            async def ainvoke(self, msgs):
                return SimpleNamespace(content="")

        with patch("redis_sre_agent.agent.langgraph_agent.ChatOpenAI", return_value=FakeLLM()):
            with caplog.at_level("WARNING"):
                result = await agent._compose_final_markdown(
                    initial_assessment_lines=[],
                    per_topic_recommendations=[],
                    instance_ctx=None,
                )

    assert result == ""
    # Optional: we expect a warning log about no content
    assert any("composer returned no content" in rec.message.lower() for rec in caplog.records)
