import pytest
from langchain_core.messages import HumanMessage

from redis_sre_agent.agent.models import Topic, TopicsList


class FakeLLM:
    def with_structured_output(self, schema):
        class _Struct:
            async def ainvoke(self, messages):
                return TopicsList(
                    items=[
                        Topic(
                            id="T1",
                            title="Connectivity",
                            category="Networking",
                            scope="cluster",
                            narrative="",
                            evidence_keys=["k1"],
                        ),
                        Topic(
                            id="T2",
                            title="Performance",
                            category="Performance",
                            scope="db",
                            narrative="",
                            evidence_keys=["k2"],
                        ),
                    ]
                )

        return _Struct()


@pytest.mark.asyncio
async def test_topics_structured_output_roundtrip():
    llm = FakeLLM()
    struct = llm.with_structured_output(TopicsList)
    out = await struct.ainvoke([HumanMessage(content="extract topics")])

    assert isinstance(out, TopicsList)
    assert len(out.items) == 2
    ids = [t.id for t in out.items]
    assert ids == ["T1", "T2"]
