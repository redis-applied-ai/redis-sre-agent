"""Integration tests for symbol-heavy chat queries through actual agent entry points."""

from array import array
from typing import Any, List

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from redis_sre_agent.agent.chat_agent import ChatAgent
from redis_sre_agent.agent.knowledge_agent import KnowledgeOnlyAgent
from redis_sre_agent.agent.langgraph_agent import SRELangGraphAgent
from redis_sre_agent.core.redis import (
    SRE_KNOWLEDGE_INDEX,
    create_indices,
    get_knowledge_index,
    get_skills_index,
    get_support_tickets_index,
)
from redis_sre_agent.tools.manager import ToolManager

VECTOR_DIM = 1536


def _vec(index: int) -> List[float]:
    values = [0.0] * VECTOR_DIM
    values[index] = 1.0
    return values


def _vec_buffer(vec: List[float]) -> bytes:
    return array("f", vec).tobytes()


class MockVectorizer:
    """Return deterministic vectors without calling the real embeddings API."""

    def __init__(self, query_vec: List[float]):
        self._query_vec = query_vec

    async def aembed_many(self, texts: List[str]):
        return [self._query_vec for _ in texts]

    async def aembed(self, text: str, as_buffer: bool = False):
        import numpy as np

        arr = np.array(self._query_vec, dtype=np.float32)
        return arr.tobytes() if as_buffer else arr


class ToolCallingLLM:
    """Minimal fake LLM that always calls the knowledge search tool once."""

    def __init__(self):
        self._search_tool_name: str | None = None

    def bind_tools(self, schemas):
        for schema in schemas:
            name = getattr(schema, "name", None)
            if not name:
                continue
            if name.startswith("knowledge_") and name.endswith("_search"):
                self._search_tool_name = name
                break
        return self

    def bind(self, **kwargs):
        return self

    def with_structured_output(self, schema):
        class _StructuredOutputLLM:
            async def ainvoke(self, messages):
                try:
                    return schema(items=[])
                except Exception:
                    return type("TopicsResponse", (), {"items": []})()

        return _StructuredOutputLLM()

    async def ainvoke(self, messages):
        if any(isinstance(message, ToolMessage) for message in messages):
            return AIMessage(content="Search completed.", tool_calls=[])

        if not self._search_tool_name:
            raise AssertionError("Knowledge search tool was not bound")

        human_message = next(
            message for message in reversed(messages) if isinstance(message, HumanMessage)
        )
        query = str(human_message.content)
        marker = "User Query:"
        if marker in query:
            query = query.split(marker, 1)[1].strip().splitlines()[0].strip()
        return AIMessage(
            content="",
            tool_calls=[
                {
                    "id": "tool-call-1",
                    "name": self._search_tool_name,
                    "args": {"query": query},
                }
            ],
        )


def _doc(
    *,
    doc_id: str,
    title: str,
    content: str,
    source: str,
    name: str,
    document_hash: str,
    vector: bytes,
) -> dict[str, Any]:
    return {
        "id": doc_id,
        "title": title,
        "content": content,
        "source": source,
        "category": "incident",
        "severity": "info",
        "doc_type": "knowledge",
        "name": name,
        "summary": "",
        "priority": "normal",
        "pinned": "false",
        "version": "latest",
        "document_hash": document_hash,
        "content_hash": f"{document_hash}-content",
        "chunk_index": 0,
        "created_at": 0,
        "vector": vector,
    }


async def _load_docs(index, docs: List[dict[str, Any]]) -> None:
    keys = [f"{SRE_KNOWLEDGE_INDEX}:{doc['id']}" for doc in docs]
    await index.load(id_field="id", keys=keys, data=docs)


def _build_agent(agent_kind: str) -> Any:
    if agent_kind == "chat":
        return ChatAgent()
    if agent_kind == "knowledge":
        return KnowledgeOnlyAgent()
    if agent_kind == "sre":
        return SRELangGraphAgent()
    raise AssertionError(f"Unknown agent kind: {agent_kind}")


def _patch_agent_llms(monkeypatch, agent_kind: str) -> None:
    if agent_kind == "chat":
        monkeypatch.setattr("redis_sre_agent.agent.chat_agent.create_llm", ToolCallingLLM)
        monkeypatch.setattr("redis_sre_agent.agent.chat_agent.create_mini_llm", ToolCallingLLM)
        return
    if agent_kind == "knowledge":
        monkeypatch.setattr("redis_sre_agent.agent.knowledge_agent.create_llm", ToolCallingLLM)
        return
    if agent_kind == "sre":
        monkeypatch.setattr("redis_sre_agent.agent.langgraph_agent.create_llm", ToolCallingLLM)
        monkeypatch.setattr("redis_sre_agent.agent.langgraph_agent.create_mini_llm", ToolCallingLLM)
        return
    raise AssertionError(f"Unknown agent kind: {agent_kind}")


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize("agent_kind", ["chat", "knowledge", "sre"])
@pytest.mark.parametrize(
    ("query", "expected_hash"),
    [
        ("runbooks/cache/failover.md", "symbol-source-hash"),
        ("foo|bar/baz[prod]", "symbol-name-hash"),
    ],
)
async def test_symbol_heavy_queries_work_through_agent_entry_points(
    agent_kind: str,
    query: str,
    expected_hash: str,
    async_redis_client,
    test_settings,
    monkeypatch,
):
    """Actual agents should survive slash- and punctuation-heavy knowledge searches."""
    await create_indices(config=test_settings)
    knowledge_index = await get_knowledge_index(config=test_settings)
    skills_index = await get_skills_index(config=test_settings)
    support_tickets_index = await get_support_tickets_index(config=test_settings)

    semantic_vec = _vec(0)
    exact_vec = _vec(1)
    docs = [
        _doc(
            doc_id="symbol-source",
            title="Cache Failover Runbook",
            content="Failover steps for cache replica recovery.",
            source="runbooks/cache/failover.md",
            name="cache-failover-runbook",
            document_hash="symbol-source-hash",
            vector=_vec_buffer(exact_vec),
        ),
        _doc(
            doc_id="symbol-name",
            title="Bracketed Config Identifier",
            content="Notes about prod config identifiers with punctuation.",
            source="configs/prod-config.md",
            name="foo|bar/baz[prod]",
            document_hash="symbol-name-hash",
            vector=_vec_buffer(exact_vec),
        ),
        _doc(
            doc_id="semantic-distractor",
            title="Semantic Distractor",
            content="General failover and config guidance.",
            source="runbooks/general-guidance.md",
            name="general-guidance",
            document_hash="symbol-distractor-hash",
            vector=_vec_buffer(semantic_vec),
        ),
    ]
    await _load_docs(knowledge_index, docs)

    async def _get_knowledge_index(*, config=None):
        return knowledge_index

    async def _get_skills_index(*, config=None):
        return skills_index

    async def _get_support_tickets_index(*, config=None):
        return support_tickets_index

    monkeypatch.setattr(
        "redis_sre_agent.core.knowledge_helpers.get_knowledge_index", _get_knowledge_index
    )
    monkeypatch.setattr(
        "redis_sre_agent.core.knowledge_helpers.get_skills_index", _get_skills_index
    )
    monkeypatch.setattr(
        "redis_sre_agent.core.knowledge_helpers.get_support_tickets_index",
        _get_support_tickets_index,
    )
    monkeypatch.setattr(
        "redis_sre_agent.core.knowledge_helpers.get_vectorizer",
        lambda: MockVectorizer(semantic_vec),
    )

    async def _skip_mcp_providers(self):
        return None

    monkeypatch.setattr(ToolManager, "_load_mcp_providers", _skip_mcp_providers, raising=False)
    _patch_agent_llms(monkeypatch, agent_kind)

    agent = _build_agent(agent_kind)
    response = await agent.process_query(
        query=query,
        session_id=f"{agent_kind}-session",
        user_id="integration-user",
    )

    assert "error" not in response.response.lower()
    assert response.tool_envelopes, "Expected at least one tool envelope from the search"

    envelope = response.tool_envelopes[0]
    assert str(envelope.get("tool_key", "")).startswith("knowledge_")
    data = envelope.get("data") or {}
    assert data.get("query") == query
    assert data.get("results_count", 0) >= 1
    assert data["results"][0]["document_hash"] == expected_hash


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize("agent_kind", ["chat", "knowledge", "sre"])
@pytest.mark.parametrize("query", ["I/O", "What does I/O saturation mean on Redis?"])
async def test_io_queries_do_not_crash_agent_entry_points(
    agent_kind: str,
    query: str,
    async_redis_client,
    test_settings,
    monkeypatch,
):
    """Prompts containing `I/O` should complete through each agent graph."""
    await create_indices(config=test_settings)
    knowledge_index = await get_knowledge_index(config=test_settings)
    skills_index = await get_skills_index(config=test_settings)
    support_tickets_index = await get_support_tickets_index(config=test_settings)

    io_vec = _vec(2)
    distractor_vec = _vec(3)
    docs = [
        _doc(
            doc_id="io-target",
            title="I/O saturation guidance",
            content="High I/O saturation usually indicates disk pressure during persistence.",
            source="runbooks/io-saturation.md",
            name="io-saturation",
            document_hash="io-target-hash",
            vector=_vec_buffer(io_vec),
        ),
        _doc(
            doc_id="io-distractor",
            title="CPU saturation guidance",
            content="High CPU saturation usually indicates command load or inefficient queries.",
            source="runbooks/cpu-saturation.md",
            name="cpu-saturation",
            document_hash="io-distractor-hash",
            vector=_vec_buffer(distractor_vec),
        ),
    ]
    await _load_docs(knowledge_index, docs)

    async def _get_knowledge_index(*, config=None):
        return knowledge_index

    async def _get_skills_index(*, config=None):
        return skills_index

    async def _get_support_tickets_index(*, config=None):
        return support_tickets_index

    monkeypatch.setattr(
        "redis_sre_agent.core.knowledge_helpers.get_knowledge_index", _get_knowledge_index
    )
    monkeypatch.setattr(
        "redis_sre_agent.core.knowledge_helpers.get_skills_index", _get_skills_index
    )
    monkeypatch.setattr(
        "redis_sre_agent.core.knowledge_helpers.get_support_tickets_index",
        _get_support_tickets_index,
    )
    monkeypatch.setattr(
        "redis_sre_agent.core.knowledge_helpers.get_vectorizer",
        lambda: MockVectorizer(io_vec),
    )

    async def _skip_mcp_providers(self):
        return None

    monkeypatch.setattr(ToolManager, "_load_mcp_providers", _skip_mcp_providers, raising=False)
    _patch_agent_llms(monkeypatch, agent_kind)

    agent = _build_agent(agent_kind)
    response = await agent.process_query(
        query=query,
        session_id=f"{agent_kind}-io-session",
        user_id="integration-user",
    )

    assert "error processing query" not in response.response.lower()
    assert "encountered an error" not in response.response.lower()
    assert response.tool_envelopes, "Expected a knowledge search tool call for the I/O prompt"

    envelope = response.tool_envelopes[0]
    data = envelope.get("data") or {}
    assert data.get("query") == query
    assert data.get("results_count", 0) >= 1
    assert data["results"][0]["document_hash"] == "io-target-hash"
