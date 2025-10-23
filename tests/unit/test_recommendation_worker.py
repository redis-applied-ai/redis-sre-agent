from typing import Any, List

import pytest
from langchain_core.messages import AIMessage, ToolMessage

from redis_sre_agent.agent.models import Recommendation
from redis_sre_agent.agent.subgraphs.recommendation_worker import build_recommendation_worker


class FakeLLM:
    def __init__(self):
        self.last_messages: List[Any] = []
        self.invoked: bool = False

    async def ainvoke(self, messages):
        # Record messages passed to LLM, return a simple AIMessage with no tool calls
        self.invoked = True
        self.last_messages = list(messages)
        return AIMessage(content="ok")

    def with_structured_output(self, schema):
        # Return a struct wrapper that yields a Recommendation instance/dict
        class _Struct:
            async def ainvoke(self, messages):
                # Minimal, valid Recommendation
                return Recommendation(topic_id="T1", title="Test", steps=[])

        return _Struct()


@pytest.mark.asyncio
async def test_rec_worker_basic_synth_returns_recommendation():
    llm = FakeLLM()
    worker = build_recommendation_worker(llm, knowledge_tool_adapters=[], max_tool_steps=1)

    state = {
        "messages": [],
        "budget": 1,
        "topic": {
            "id": "T1",
            "title": "Connectivity",
            "category": "Networking",
            "scope": "cluster",
            "evidence_keys": [],
        },
        "evidence": [],
        "instance": {"instance_type": "redis_enterprise", "name": "test"},
    }

    out = await worker.ainvoke(state)
    assert "result" in out
    rec = out["result"]
    assert rec["topic_id"] == "T1"
    assert isinstance(rec.get("steps", []), list)


@pytest.mark.asyncio
async def test_rec_worker_sanitizes_tool_first_messages():
    llm = FakeLLM()
    worker = build_recommendation_worker(llm, knowledge_tool_adapters=[], max_tool_steps=1)

    # Start with a ToolMessage first (should be dropped for LLM)
    tool_first = ToolMessage(content="{}", tool_call_id="abc")
    state = {
        "messages": [tool_first],
        "budget": 1,
        "topic": {
            "id": "T1",
            "title": "Connectivity",
            "category": "Networking",
            "scope": "cluster",
            "evidence_keys": [],
        },
        "evidence": [],
        "instance": {"instance_type": "redis_enterprise", "name": "test"},
    }

    await worker.ainvoke(state)
    assert llm.invoked, "LLM should have been invoked"
    # Ensure first message sent to LLM is not a ToolMessage (if any messages were sent)
    if llm.last_messages:
        assert not isinstance(llm.last_messages[0], ToolMessage)
