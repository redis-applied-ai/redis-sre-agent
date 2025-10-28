import pytest

from redis_sre_agent.agent.knowledge_agent import KnowledgeOnlyAgent
from redis_sre_agent.tools.manager import ToolManager


class FakeResponse:
    def __init__(self):
        self.content = "Tool call"
        self.tool_calls = [{"id": "call-1", "name": "knowledge_search", "args": {"query": "foo"}}]


class FakeLLM:
    def bind_tools(self, _schemas):
        return self

    async def ainvoke(self, _messages):
        # First agent node returns a response with a tool call
        return FakeResponse()


@pytest.mark.asyncio
async def test_knowledge_agent_emits_knowledge_sources(monkeypatch):
    agent = KnowledgeOnlyAgent()
    # Replace real LLM with our fake
    agent.llm = FakeLLM()

    # Capture progress callback calls (support optional metadata)
    calls = []

    async def cb(message, update_type, metadata=None):  # noqa: ARG001
        calls.append((update_type, metadata))

    # Patch ToolManager.execute_tool_calls to return a knowledge search result
    async def fake_execute_tool_calls(self, tool_calls):  # noqa: ARG001
        return [
            {
                "status": "success",
                "results_count": 2,
                "results": [
                    {
                        "id": "frag-1",
                        "document_hash": "doc-1",
                        "chunk_index": 0,
                        "title": "T1",
                        "source": "S1",
                    },
                    {
                        "id": "frag-2",
                        "document_hash": "doc-2",
                        "chunk_index": 1,
                        "title": "T2",
                        "source": "S2",
                    },
                ],
            }
        ]

    monkeypatch.setattr(ToolManager, "execute_tool_calls", fake_execute_tool_calls, raising=False)

    # Run a single query; the fake LLM triggers a tool call, and our patched tool manager returns results
    await agent.process_query(
        "test query", session_id="sess-1", user_id="user-1", progress_callback=cb
    )

    # Validate that a knowledge_sources update was emitted with fragments
    assert any(u == "knowledge_sources" for (u, _md) in calls)
    # Find the metadata for the knowledge_sources call
    md = next((md for (u, md) in calls if u == "knowledge_sources"), None)
    assert md is not None
    frags = md.get("fragments") or []
    assert len(frags) == 2
    assert frags[0]["id"] == "frag-1"
    assert frags[1]["id"] == "frag-2"
