import pytest
from langchain_core.messages import AIMessage

from redis_sre_agent.agent.subgraphs.problem_worker import build_problem_worker


class FakeLLM:
    def __init__(self, message: AIMessage):
        self._message = message

    async def ainvoke(self, messages):
        return self._message


@pytest.mark.asyncio
async def test_problem_worker_synth_without_tools():
    # LLM returns plain JSON content; no tool_calls -> synth immediately
    msg = AIMessage(content='{"summary":"ok","actions":[]}')
    llm = FakeLLM(msg)
    worker = build_problem_worker(llm, knowledge_tools=[], max_tool_steps=2)

    state = {"messages": [], "budget": 2}
    out = await worker.ainvoke(state)

    assert out.get("result", {}).get("summary") == "ok"


@pytest.mark.asyncio
async def test_problem_worker_budget_zero_bypasses_tools():
    # LLM suggests tools but budget is zero -> synth anyway
    msg = AIMessage(content='{"summary":"would_use_tools"}')
    # Simulate tool_calls present (attribute is checked via getattr)
    msg.tool_calls = [
        {"id": "t1", "type": "function", "function": {"name": "search", "arguments": "{}"}}
    ]
    llm = FakeLLM(msg)
    worker = build_problem_worker(llm, knowledge_tools=[], max_tool_steps=1)

    state = {"messages": [], "budget": 0}
    out = await worker.ainvoke(state)

    assert out.get("result", {}).get("summary") == "would_use_tools"


@pytest.mark.asyncio
async def test_problem_worker_planning_failed_on_bad_json():
    # Bad JSON should trigger planning_failed fallback
    msg = AIMessage(content="not-json")
    llm = FakeLLM(msg)
    worker = build_problem_worker(llm, knowledge_tools=[], max_tool_steps=1)

    out = await worker.ainvoke({"messages": [], "budget": 1})

    assert out.get("result", {}).get("summary") == "planning_failed"
    assert "not-json" in out.get("result", {}).get("raw", "")
