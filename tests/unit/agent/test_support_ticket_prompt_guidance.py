"""Tests for support-ticket guidance in startup and agent prompts."""

from redis_sre_agent.agent.chat_agent import CHAT_SYSTEM_PROMPT
from redis_sre_agent.agent.knowledge_agent import KNOWLEDGE_SYSTEM_PROMPT
from redis_sre_agent.agent.knowledge_context import _tool_instruction_lines_for_categories
from redis_sre_agent.agent.prompts import REDIS_COMMAND_SEMANTICS_GUARDRAILS, SRE_SYSTEM_PROMPT
from redis_sre_agent.tools.models import ToolCapability, ToolDefinition


def test_startup_context_includes_support_ticket_tool_instructions():
    lines = _tool_instruction_lines_for_categories(
        [
            ToolDefinition(
                name="knowledge_test_skills_check",
                description="Skills lookup",
                capability=ToolCapability.KNOWLEDGE,
                parameters={"type": "object", "properties": {}, "required": []},
            ),
            ToolDefinition(
                name="knowledge_test_search_support_tickets",
                description="Support ticket search",
                capability=ToolCapability.TICKETS,
                parameters={"type": "object", "properties": {}, "required": []},
            ),
        ]
    )
    joined = "\n".join(lines)
    assert "available tool categories: knowledge, tickets." in joined.lower()
    assert "tickets tools for historical incidents" in joined.lower()
    assert "general knowledge search does not include support tickets" in joined.lower()
    assert "cluster name or cluster host" in joined
    assert "search_support_tickets" not in joined
    assert "get_support_ticket" not in joined


def test_startup_context_omits_ticket_workflow_when_tickets_category_unavailable():
    lines = _tool_instruction_lines_for_categories(
        [
            ToolDefinition(
                name="knowledge_test_skills_check",
                description="Skills lookup",
                capability=ToolCapability.KNOWLEDGE,
                parameters={"type": "object", "properties": {}, "required": []},
            ),
        ]
    )
    joined = "\n".join(lines)
    assert "support-ticket workflow" not in joined.lower()


def test_chat_prompt_mentions_support_ticket_usage():
    prompt = CHAT_SYSTEM_PROMPT.lower()
    assert "tools are available" in prompt
    assert "tickets" in prompt
    assert "support tickets" in prompt
    assert "general knowledge search excludes support tickets" in prompt


def test_chat_prompt_requires_explicit_skill_retrieval_and_scope_evidence():
    prompt = CHAT_SYSTEM_PROMPT.lower()
    assert "inventory only" in prompt
    assert "`get_skill`" in CHAT_SYSTEM_PROMPT
    assert "health check skill" in prompt
    assert "response as satisfying a skill" in prompt
    assert "captured package contents" in prompt
    assert "hostname mention by itself is not proof" in prompt


def test_knowledge_prompt_mentions_support_tickets():
    prompt = KNOWLEDGE_SYSTEM_PROMPT.lower()
    assert "support ticket" in prompt
    assert "general knowledge search excludes support tickets" in prompt


def test_sre_prompt_mentions_support_ticket_usage():
    prompt = SRE_SYSTEM_PROMPT.lower()
    assert "category tools in your batch" in prompt
    assert "support tickets" in prompt
    assert "general knowledge search excludes support tickets" in prompt


def test_sre_prompt_requires_explicit_skill_retrieval_and_scope_evidence():
    prompt = SRE_SYSTEM_PROMPT.lower()
    assert "inventory only" in prompt
    assert "`get_skill`" in SRE_SYSTEM_PROMPT
    assert "health-check skill" in prompt
    assert "response as satisfying a skill" in prompt
    assert "captured evidence, not current live state" in prompt
    assert "resolve the target before making live-state claims" in prompt


def test_chat_prompt_includes_command_semantics_guardrails():
    prompt = CHAT_SYSTEM_PROMPT.lower()
    assert "do not infer connection counts from `memory stats`".lower() in prompt
    assert "`info clients`" in prompt
    assert "`client list`" in prompt
    assert "clients.normal" in prompt


def test_sre_prompt_includes_command_semantics_guardrails():
    prompt = SRE_SYSTEM_PROMPT.lower()
    assert "do not infer connection counts from `memory stats`".lower() in prompt
    assert "`info clients`" in prompt
    assert "`client list`" in prompt
    assert "clients.normal" in prompt


def test_chat_and_sre_prompts_share_guardrails_constant():
    shared = REDIS_COMMAND_SEMANTICS_GUARDRAILS.strip()
    assert shared in CHAT_SYSTEM_PROMPT
    assert shared in SRE_SYSTEM_PROMPT
