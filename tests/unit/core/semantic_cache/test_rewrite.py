"""US-006: mid-conversation query rewriting (nano), first-turn passthrough."""

from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from redis_sre_agent.core.semantic_cache import rewrite as rewrite_mod
from redis_sre_agent.core.semantic_cache.rewrite import rewrite_query


class _FakeLLM:
    def __init__(self, content):
        self._content = content
        self.invoked = False

    async def ainvoke(self, messages):
        self.invoked = True
        return AIMessage(content=self._content)


class _RaisingLLM:
    async def ainvoke(self, messages):
        raise RuntimeError("llm down")


@pytest.mark.asyncio
async def test_first_turn_returns_raw_without_calling_llm():
    fake = _FakeLLM("SHOULD NOT BE USED")
    with patch.object(rewrite_mod, "create_nano_llm", return_value=fake):
        out = await rewrite_query("what is maxmemory?", conversation_history=None)
    assert out == "what is maxmemory?"
    assert fake.invoked is False


@pytest.mark.asyncio
async def test_mid_conversation_uses_nano_rewrite():
    fake = _FakeLLM("How do I set maxmemory in Redis 7.2?")
    history = [
        HumanMessage(content="How do I configure Redis 7.2?"),
        AIMessage(content="You can use CONFIG SET."),
    ]
    with patch.object(rewrite_mod, "create_nano_llm", return_value=fake):
        out = await rewrite_query("what about maxmemory?", conversation_history=history)
    assert out == "How do I set maxmemory in Redis 7.2?"
    assert fake.invoked is True


@pytest.mark.asyncio
async def test_rewrite_fails_open_to_raw_query():
    history = [HumanMessage(content="prior")]
    with patch.object(rewrite_mod, "create_nano_llm", return_value=_RaisingLLM()):
        out = await rewrite_query("follow up question", conversation_history=history)
    assert out == "follow up question"
