import pytest
from langchain_core.messages import AIMessage

from redis_sre_agent.agent.models import Recommendation, RecommendationStep
from redis_sre_agent.agent.subgraphs.recommendation_worker import build_recommendation_worker


class FakeLLM:
    async def ainvoke(self, messages):
        # Return an AI message with no tool_calls so worker goes straight to synth
        return AIMessage(content="ok", tool_calls=[])

    def with_structured_output(self, schema):
        class _Struct:
            async def ainvoke(self, messages):
                # Emit a minimal Recommendation model
                return Recommendation(
                    topic_id="T?",
                    title="Test Rec",
                    steps=[
                        RecommendationStep(description="Do X"),
                        RecommendationStep(description="Do Y"),
                    ],
                )

        return _Struct()


@pytest.mark.asyncio
async def test_integration_two_topics_two_workers_then_compose():
    llm = FakeLLM()
    worker = build_recommendation_worker(llm, knowledge_tool_adapters=[], max_tool_steps=1)

    topics = [
        {
            "id": "T1",
            "title": "Conn",
            "category": "Networking",
            "scope": "cluster",
            "narrative": "",
            "evidence_keys": ["k1"],
        },
        {
            "id": "T2",
            "title": "Perf",
            "category": "Performance",
            "scope": "db",
            "narrative": "",
            "evidence_keys": ["k2"],
        },
    ]
    envs_by_key = {
        "k1": {
            "tool_key": "knowledge.kb.search",
            "name": "search",
            "args": {"q": "a"},
            "status": "success",
            "data": {"hits": 1},
        },
        "k2": {
            "tool_key": "knowledge.kb.search",
            "name": "search",
            "args": {"q": "b"},
            "status": "success",
            "data": {"hits": 2},
        },
    }

    results = []
    for t in topics:
        ev = [envs_by_key[k] for k in t["evidence_keys"] if k in envs_by_key]
        state = {"messages": [], "topic": t, "evidence": ev, "instance": {}}
        out = await worker.ainvoke(state)
        results.append(out.get("result"))

    assert len(results) == 2
    assert all(r.get("steps") for r in results)
    # Compose (very light): ensure distinct topic_ids are present
    ids = {r.get("topic_id") for r in results}
    assert ids == {"T1", "T2"}
