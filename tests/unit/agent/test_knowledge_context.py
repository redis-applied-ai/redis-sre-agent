"""Tests for startup knowledge context assembly."""

from unittest.mock import AsyncMock, patch

import pytest

from redis_sre_agent.agent.knowledge_context import build_startup_knowledge_context
from redis_sre_agent.tools.models import Tool, ToolCapability, ToolDefinition, ToolMetadata


@pytest.mark.asyncio
async def test_startup_context_memorizes_pinned_skills_and_tickets():
    with (
        patch(
            "redis_sre_agent.agent.knowledge_context.get_pinned_documents_helper",
            new=AsyncMock(
                return_value={
                    "pinned_documents": [
                        {
                            "name": "Pinned Skill",
                            "priority": "critical",
                            "doc_type": "skill",
                            "full_content": "Skill steps: ask for usage, then run diagnostics.",
                        },
                        {
                            "name": "Pinned Ticket",
                            "priority": "high",
                            "doc_type": "support_ticket",
                            "full_content": "Ticket finding: cluster-a had memory pressure from burst traffic.",
                        },
                    ]
                }
            ),
        ),
        patch(
            "redis_sre_agent.agent.knowledge_context.skills_check_helper",
            new=AsyncMock(
                return_value={
                    "skills": [
                        {
                            "name": "General Memory Investigation",
                            "summary": "Use diagnostics then confirm workload.",
                        }
                    ]
                }
            ),
        ),
    ):
        context = await build_startup_knowledge_context(query="memory issue", version="latest")

    assert "Pinned documents:" in context
    assert "Pinned Skill" in context
    assert "Memorize this pinned skill by heart" in context
    assert "Skill steps: ask for usage" in context
    assert "Pinned Ticket" in context
    assert "Memorize this pinned support ticket by heart" in context
    assert "Ticket finding: cluster-a had memory pressure" in context
    assert "Skills you know:" in context
    assert "General Memory Investigation: Use diagnostics then confirm workload." in context


@pytest.mark.asyncio
async def test_startup_context_is_empty_without_pinned_docs_or_skills():
    with (
        patch(
            "redis_sre_agent.agent.knowledge_context.get_pinned_documents_helper",
            new=AsyncMock(return_value={"pinned_documents": []}),
        ),
        patch(
            "redis_sre_agent.agent.knowledge_context.skills_check_helper",
            new=AsyncMock(return_value={"skills": []}),
        ),
    ):
        context = await build_startup_knowledge_context(query="memory issue", version="latest")

    assert context == ""


@pytest.mark.asyncio
async def test_startup_context_includes_tool_instructions_without_pinned_or_skills():
    with (
        patch(
            "redis_sre_agent.agent.knowledge_context.get_pinned_documents_helper",
            new=AsyncMock(return_value={"pinned_documents": []}),
        ),
        patch(
            "redis_sre_agent.agent.knowledge_context.skills_check_helper",
            new=AsyncMock(return_value={"skills": []}),
        ),
    ):
        context = await build_startup_knowledge_context(
            query="memory issue",
            version="latest",
            available_tools=[
                ToolDefinition(
                    name="diag_test_health",
                    description="Health check",
                    capability=ToolCapability.DIAGNOSTICS,
                    parameters={"type": "object", "properties": {}, "required": []},
                ),
                ToolDefinition(
                    name="tickets_test_search",
                    description="Search tickets",
                    capability=ToolCapability.TICKETS,
                    parameters={"type": "object", "properties": {}, "required": []},
                ),
            ],
        )

    assert "Tool usage instructions:" in context
    assert "Available tool categories: diagnostics, tickets." in context
    assert "Support-ticket workflow:" in context


@pytest.mark.asyncio
async def test_startup_context_extracts_capability_from_tool_definition():
    with (
        patch(
            "redis_sre_agent.agent.knowledge_context.get_pinned_documents_helper",
            new=AsyncMock(return_value={"pinned_documents": []}),
        ),
        patch(
            "redis_sre_agent.agent.knowledge_context.skills_check_helper",
            new=AsyncMock(return_value={"skills": []}),
        ),
    ):
        wrapped_tool = Tool(
            metadata=ToolMetadata(
                name="wrapped_tool",
                description="Wrapped tool",
                capability=ToolCapability.DIAGNOSTICS,
                provider_name="provider",
                requires_instance=False,
            ),
            definition=ToolDefinition(
                name="tickets_wrapped_tool",
                description="Ticket search tool",
                capability=ToolCapability.TICKETS,
                parameters={"type": "object", "properties": {}, "required": []},
            ),
            invoke=AsyncMock(return_value={}),
        )
        context = await build_startup_knowledge_context(
            query="memory issue",
            version="latest",
            available_tools=[wrapped_tool],
        )

    assert "Available tool categories: tickets." in context
