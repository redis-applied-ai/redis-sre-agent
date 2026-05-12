"""Tests for startup knowledge context assembly."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from redis_sre_agent.agent import knowledge_context as knowledge_context_module
from redis_sre_agent.agent.knowledge_context import (
    _build_internal_pinned_context_envelope,
    _build_internal_startup_skills_envelope,
    build_startup_knowledge_context,
    merge_internal_tool_envelopes,
)
from redis_sre_agent.evaluation.injection import eval_runtime_overrides
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
        context = await build_startup_knowledge_context(version="latest")

    assert "Pinned documents:" in context
    assert "Pinned Skill" in context
    assert "Memorize this pinned skill by heart" in context
    assert "Skill steps: ask for usage" in context
    assert "Pinned Ticket" in context
    assert "Memorize this pinned support ticket by heart" in context
    assert "Ticket finding: cluster-a had memory pressure" in context
    assert "Skills you know:" in context
    assert "Skill inventory rules:" in context
    assert "inventory only" in context
    assert "`get_skill`" in context
    assert "General Memory Investigation: Use diagnostics then confirm workload." in context


@pytest.mark.asyncio
async def test_startup_context_mentions_truncated_skill_inventory():
    with (
        patch(
            "redis_sre_agent.agent.knowledge_context.get_pinned_documents_helper",
            new=AsyncMock(return_value={"pinned_documents": []}),
        ),
        patch(
            "redis_sre_agent.agent.knowledge_context.skills_check_helper",
            new=AsyncMock(
                return_value={
                    "skills": [
                        {
                            "name": "Redis Cluster Health Check",
                            "summary": "Run a fast health check for the cluster.",
                        },
                        {
                            "name": "Redis Memory Triage",
                            "summary": "Inspect memory pressure and fragmentation.",
                        },
                    ],
                    "total_fetched": 53,
                }
            ),
        ),
    ):
        context = await build_startup_knowledge_context(version="latest", skills_limit=2)

    assert "startup inventory is truncated" in context
    assert "2 skills shown, 51 more available" in context
    assert "search for related skills" in context


@pytest.mark.asyncio
async def test_startup_context_renders_skill_title_with_lookup_slug():
    with (
        patch(
            "redis_sre_agent.agent.knowledge_context.get_pinned_documents_helper",
            new=AsyncMock(return_value={"pinned_documents": []}),
        ),
        patch(
            "redis_sre_agent.agent.knowledge_context.skills_check_helper",
            new=AsyncMock(
                return_value={
                    "skills": [
                        {
                            "name": "redis-cluster-health-check",
                            "title": "Redis Cluster Health Check",
                            "summary": "Run a fast cluster health check.",
                        }
                    ]
                }
            ),
        ),
    ):
        context = await build_startup_knowledge_context(version="latest")

    assert "Redis Cluster Health Check (`redis-cluster-health-check`): Run a fast cluster health check." in context


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
        context = await build_startup_knowledge_context(version="latest")

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
            version="latest",
            available_tools=[wrapped_tool],
        )

    assert "Available tool categories: tickets." in context


@pytest.mark.asyncio
async def test_startup_context_extracts_capability_from_tool_metadata_only():
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
        metadata_only_tool = SimpleNamespace(
            metadata=SimpleNamespace(capability=ToolCapability.LOGS),
            definition=SimpleNamespace(capability=None),
            capability=None,
        )
        ignored_tool = SimpleNamespace(metadata=SimpleNamespace(), definition=None, capability=None)
        context = await build_startup_knowledge_context(
            version="latest",
            available_tools=[metadata_only_tool, ignored_tool],
        )

    assert "Available tool categories: logs." in context


def test_merge_internal_tool_envelopes_deduplicates_dict_entries():
    existing = [{"tool_key": "knowledge.pinned_context"}]
    new = [
        {"tool_key": "knowledge.pinned_context"},
        {"tool_key": "knowledge.startup_skills_check"},
    ]

    merged = merge_internal_tool_envelopes(existing, new)

    assert merged == [
        {"tool_key": "knowledge.pinned_context"},
        {"tool_key": "knowledge.startup_skills_check"},
    ]


def test_internal_envelope_builders_return_none_for_empty_inputs():
    assert (
        _build_internal_pinned_context_envelope(
            [],
            version="latest",
            pinned_limit=20,
            pinned_content_char_budget=12000,
        )
        is None
    )
    assert (
        _build_internal_startup_skills_envelope(
            [],
            query="memory issue",
            version="latest",
            skills_limit=20,
        )
        is None
    )


@pytest.mark.asyncio
async def test_startup_context_carries_internal_pinned_context_envelope():
    with (
        patch(
            "redis_sre_agent.agent.knowledge_context.get_pinned_documents_helper",
            new=AsyncMock(
                return_value={
                    "pinned_documents": [
                        {
                            "document_hash": "hash-123",
                            "name": "Pinned Runbook",
                            "summary": "Pinned memory triage guidance.",
                            "priority": "high",
                            "source": "file:///tmp/pinned.md",
                            "doc_type": "runbook",
                            "truncated": False,
                            "full_content": "Pinned guidance content",
                        }
                    ]
                }
            ),
        ),
        patch(
            "redis_sre_agent.agent.knowledge_context.skills_check_helper",
            new=AsyncMock(return_value={"skills": []}),
        ),
    ):
        context = await build_startup_knowledge_context(version="latest")

    envelopes = getattr(context, "internal_tool_envelopes", [])
    assert len(envelopes) == 1
    envelope = envelopes[0]
    assert envelope["tool_key"] == "knowledge.pinned_context"
    assert envelope["name"] == "pinned_context"
    assert envelope["data"]["retrieval_kind"] == "pinned_context"
    assert envelope["data"]["results"][0]["title"] == "Pinned Runbook"
    assert envelope["data"]["results"][0]["retrieval_kind"] == "pinned_context"


@pytest.mark.asyncio
async def test_startup_context_carries_internal_skill_discovery_envelope():
    with (
        patch(
            "redis_sre_agent.agent.knowledge_context.get_pinned_documents_helper",
            new=AsyncMock(return_value={"pinned_documents": []}),
        ),
        patch(
            "redis_sre_agent.agent.knowledge_context.skills_check_helper",
            new=AsyncMock(
                return_value={
                    "skills": [
                        {
                            "name": "Iterative Memory Check",
                            "document_hash": "iterative-memory-check",
                            "summary": "Check INFO memory before remediation.",
                            "source": "fixture://skills/iterative-memory-check.md",
                        },
                        {
                            "name": "Failover Investigation Skill",
                            "document_hash": "failover-investigation-skill",
                            "summary": "Verify replica health before role changes.",
                            "source": "fixture://skills/failover-investigation-skill.md",
                        },
                    ]
                }
            ),
        ),
    ):
        context = await build_startup_knowledge_context(version="latest")

    envelopes = getattr(context, "internal_tool_envelopes", [])
    assert len(envelopes) == 1
    envelope = envelopes[0]
    assert envelope["tool_key"] == "knowledge.startup_skills_check"
    assert envelope["name"] == "skills_check"
    assert envelope["args"] == {
        "query": "",
        "limit": 25,
        "offset": 0,
        "version": "latest",
    }
    assert envelope["data"]["retrieval_kind"] == "startup_skills"
    assert envelope["data"]["results"][0]["title"] == "Iterative Memory Check"
    assert envelope["data"]["results"][0]["document_hash"] == "iterative-memory-check"
    assert envelope["data"]["results"][0]["retrieval_label"] == "Startup skills"


@pytest.mark.asyncio
async def test_startup_context_continues_when_pinned_document_load_fails():
    with (
        patch(
            "redis_sre_agent.agent.knowledge_context.get_pinned_documents_helper",
            new=AsyncMock(side_effect=RuntimeError("pinned backend unavailable")),
        ),
        patch(
            "redis_sre_agent.agent.knowledge_context.skills_check_helper",
            new=AsyncMock(
                return_value={
                    "skills": [
                        {"name": "Iterative Memory Check", "summary": "Use INFO memory first."}
                    ]
                }
            ),
        ),
    ):
        context = await build_startup_knowledge_context(version="latest")

    assert "Pinned documents:" not in context
    assert "Iterative Memory Check: Use INFO memory first." in context


@pytest.mark.asyncio
async def test_startup_context_continues_when_skills_check_fails():
    with (
        patch(
            "redis_sre_agent.agent.knowledge_context.get_pinned_documents_helper",
            new=AsyncMock(
                return_value={
                    "pinned_documents": [
                        {
                            "name": "Pinned Runbook",
                            "priority": "high",
                            "doc_type": "runbook",
                            "full_content": "Use evidence-first triage.",
                        }
                    ]
                }
            ),
        ),
        patch(
            "redis_sre_agent.agent.knowledge_context.skills_check_helper",
            new=AsyncMock(side_effect=RuntimeError("skills index unavailable")),
        ),
    ):
        context = await build_startup_knowledge_context(version="latest")

    assert "Pinned Runbook" in context
    assert "Skills you know:" not in context


@pytest.mark.asyncio
async def test_startup_context_uses_eval_scoped_knowledge_backend():
    class FakeKnowledgeBackend:
        async def get_pinned_documents(self, **kwargs):
            assert kwargs["version"] == "latest"
            return {
                "pinned_documents": [
                    {
                        "name": "Scoped Pinned Doc",
                        "priority": "high",
                        "doc_type": "runbook",
                        "full_content": "Pinned eval content",
                    }
                ]
            }

        async def skills_check(self, **kwargs):
            assert kwargs["query"] is None
            assert kwargs["limit"] == 25
            return {
                "skills": [
                    {
                        "name": "Scoped Skill",
                        "summary": "Use the scenario fixture backend.",
                    }
                ]
            }

    with (
        eval_runtime_overrides(knowledge_backend=FakeKnowledgeBackend()),
        patch(
            "redis_sre_agent.agent.knowledge_context.get_pinned_documents_helper",
            new=AsyncMock(side_effect=AssertionError("global pinned helper should not run")),
        ),
        patch(
            "redis_sre_agent.agent.knowledge_context.skills_check_helper",
            new=AsyncMock(side_effect=AssertionError("global skills helper should not run")),
        ),
    ):
        context = await build_startup_knowledge_context(version="latest")

    assert "Scoped Pinned Doc" in context
    assert "Pinned eval content" in context
    assert "Scoped Skill: Use the scenario fixture backend." in context


@pytest.mark.asyncio
async def test_startup_context_keeps_skill_listing_compact():
    with (
        patch(
            "redis_sre_agent.agent.knowledge_context.get_pinned_documents_helper",
            new=AsyncMock(return_value={"pinned_documents": []}),
        ),
        patch(
            "redis_sre_agent.agent.knowledge_context.skills_check_helper",
            new=AsyncMock(
                return_value={
                    "skills": [
                        {
                            "name": "Redis Maintenance Triage",
                            "description": "Investigate maintenance mode before failover.",
                            "summary": "",
                            "has_references": True,
                            "has_scripts": True,
                            "matched_resource_path": "references/maintenance-checklist.md",
                        }
                    ]
                }
            ),
        ),
    ):
        context = await build_startup_knowledge_context(version="latest")

    assert "Redis Maintenance Triage: Investigate maintenance mode before failover." in context
    assert "references/maintenance-checklist.md" not in context
    assert "Scripts:" not in context


@pytest.mark.asyncio
async def test_startup_context_uses_unfiltered_skills_toc_limit_from_settings():
    skills_check = AsyncMock(
        return_value={
            "skills": [
                {
                    "name": "Redis Maintenance Triage",
                    "description": "Investigate maintenance mode before failover.",
                }
            ]
        }
    )
    with (
        patch(
            "redis_sre_agent.agent.knowledge_context.get_pinned_documents_helper",
            new=AsyncMock(return_value={"pinned_documents": []}),
        ),
        patch(
            "redis_sre_agent.agent.knowledge_context.skills_check_helper",
            new=skills_check,
        ),
        patch.object(knowledge_context_module.settings, "startup_skills_toc_limit", 7),
    ):
        context = await build_startup_knowledge_context(version="latest")

    assert "Redis Maintenance Triage: Investigate maintenance mode before failover." in context
    skills_check.assert_awaited_once_with(query=None, limit=7, offset=0, version="latest")
