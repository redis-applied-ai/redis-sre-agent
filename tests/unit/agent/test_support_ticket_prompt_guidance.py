"""Tests for support-ticket guidance in startup and agent prompts."""

from redis_sre_agent.agent.chat_agent import CHAT_SYSTEM_PROMPT
from redis_sre_agent.agent.knowledge_agent import KNOWLEDGE_SYSTEM_PROMPT
from redis_sre_agent.agent.knowledge_context import _tool_instruction_lines_with_names
from redis_sre_agent.agent.prompts import SRE_SYSTEM_PROMPT


def test_startup_context_includes_support_ticket_tool_instructions():
    lines = _tool_instruction_lines_with_names()
    joined = "\n".join(lines)
    assert "search_support_tickets" in joined
    assert "get_support_ticket" in joined
    assert "cluster name or cluster host" in joined


def test_chat_prompt_mentions_support_ticket_usage():
    prompt = CHAT_SYSTEM_PROMPT.lower()
    assert "support_tickets" in prompt
    assert "get_support_ticket" in prompt


def test_knowledge_prompt_mentions_support_tickets():
    prompt = KNOWLEDGE_SYSTEM_PROMPT.lower()
    assert "support ticket" in prompt


def test_sre_prompt_mentions_support_ticket_usage():
    prompt = SRE_SYSTEM_PROMPT.lower()
    assert "search_support_tickets" in prompt
    assert "get_support_ticket" in prompt
