"""Tests for the Redis-backed skill backend."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from redis_sre_agent.skills import backend as skill_backend_module
from redis_sre_agent.skills.backend import RedisSkillBackend, get_skill_backend


@pytest.mark.asyncio
async def test_list_skills_collapses_package_resource_matches_by_skill():
    backend = RedisSkillBackend(config=SimpleNamespace(skill_reference_char_budget=12000))
    mock_index = AsyncMock()
    mock_index.query = AsyncMock(
        return_value=[
            {
                "id": "chunk-1",
                "document_hash": "hash-entry",
                "chunk_index": 0,
                "name": "redis-maintenance-triage",
                "title": "Redis Maintenance Triage",
                "source": "file://skills/redis-maintenance-triage/SKILL.md",
                "version": "latest",
                "skill_protocol": "agent_skills_v1",
                "resource_kind": "entrypoint",
                "resource_path": "SKILL.md",
                "skill_description": "Investigate maintenance mode first.",
                "score": 0.42,
            },
            {
                "id": "chunk-2",
                "document_hash": "hash-ref",
                "chunk_index": 0,
                "name": "redis-maintenance-triage",
                "title": "Redis Maintenance Triage",
                "source": "file://skills/redis-maintenance-triage/references/maintenance-checklist.md",
                "version": "latest",
                "skill_protocol": "agent_skills_v1",
                "resource_kind": "reference",
                "resource_path": "references/maintenance-checklist.md",
                "skill_description": "Investigate maintenance mode first.",
                "score": 0.09,
            },
            {
                "id": "chunk-3",
                "document_hash": "hash-other",
                "chunk_index": 0,
                "name": "memory-pressure-triage",
                "title": "Memory Pressure Triage",
                "source": "file://skills/memory-pressure-triage/SKILL.md",
                "version": "latest",
                "skill_protocol": "agent_skills_v1",
                "resource_kind": "entrypoint",
                "resource_path": "SKILL.md",
                "skill_description": "Check workload and memory headroom.",
                "score": 0.21,
            },
        ]
    )
    vectorizer = AsyncMock()
    vectorizer.aembed_many = AsyncMock(return_value=[[0.1, 0.2, 0.3]])

    with (
        patch(
            "redis_sre_agent.core.knowledge_helpers.get_skills_index",
            new=AsyncMock(return_value=mock_index),
        ),
        patch("redis_sre_agent.core.knowledge_helpers.get_vectorizer", return_value=vectorizer),
    ):
        result = await backend.list_skills(
            query="maintenance checklist",
            limit=10,
            offset=0,
            version="latest",
        )

    assert result["results_count"] == 2
    assert [skill["name"] for skill in result["skills"]] == [
        "redis-maintenance-triage",
        "memory-pressure-triage",
    ]
    assert result["skills"][0]["matched_resource_path"] == "references/maintenance-checklist.md"
    assert result["skills"][0]["matched_resource_kind"] == "reference"


@pytest.mark.asyncio
async def test_list_skills_without_query_prefers_entrypoint_for_package_representative():
    backend = RedisSkillBackend(config=SimpleNamespace(skill_reference_char_budget=12000))
    mock_index = AsyncMock()
    mock_index.query = AsyncMock(
        return_value=[
            {
                "id": "chunk-ref",
                "document_hash": "hash-ref",
                "chunk_index": 0,
                "name": "redis-maintenance-triage",
                "title": "Redis Maintenance Triage",
                "source": "file://skills/redis-maintenance-triage/references/maintenance-checklist.md",
                "version": "latest",
                "skill_protocol": "agent_skills_v1",
                "resource_kind": "reference",
                "resource_path": "references/maintenance-checklist.md",
                "skill_description": "Investigate maintenance mode first.",
            },
            {
                "id": "chunk-entry",
                "document_hash": "hash-entry",
                "chunk_index": 0,
                "name": "redis-maintenance-triage",
                "title": "Redis Maintenance Triage",
                "source": "file://skills/redis-maintenance-triage/SKILL.md",
                "version": "latest",
                "skill_protocol": "agent_skills_v1",
                "resource_kind": "entrypoint",
                "resource_path": "SKILL.md",
                "skill_description": "Investigate maintenance mode first.",
            },
        ]
    )

    with patch(
        "redis_sre_agent.core.knowledge_helpers.get_skills_index",
        new=AsyncMock(return_value=mock_index),
    ):
        result = await backend.list_skills(
            query=None,
            limit=10,
            offset=0,
            version="latest",
        )

    assert result["results_count"] == 1
    assert result["skills"][0]["matched_resource_path"] == "SKILL.md"
    assert result["skills"][0]["matched_resource_kind"] == "entrypoint"


@pytest.mark.asyncio
async def test_get_skill_returns_manifest_for_agent_skills_package():
    backend = RedisSkillBackend(config=SimpleNamespace(skill_reference_char_budget=12000))
    rows = [
        {"document_hash": "entry", "name": "redis-maintenance-triage", "resource_path": "SKILL.md"},
        {
            "document_hash": "ref",
            "name": "redis-maintenance-triage",
            "resource_path": "references/maintenance-checklist.md",
        },
        {
            "document_hash": "script",
            "name": "redis-maintenance-triage",
            "resource_path": "scripts/collect_context.sh",
        },
    ]
    manifest = {
        "references": [
            {
                "path": "references/maintenance-checklist.md",
                "title": "Maintenance Checklist",
                "description": "Evidence checklist.",
            }
        ],
        "assets": [
            {"path": "assets/example-query.txt", "title": "Example Query", "description": "Sample"}
        ],
    }

    with (
        patch.object(backend, "_query_skill_rows", new=AsyncMock(return_value=rows)),
        patch(
            "redis_sre_agent.core.knowledge_helpers.get_all_document_fragments",
            new=AsyncMock(
                side_effect=[
                    {
                        "doc_type": "skill",
                        "title": "Redis Maintenance Triage",
                        "summary": "Check maintenance state before disruptive actions.",
                        "fragments": [{"chunk_index": 0, "content": "Entrypoint body"}],
                        "metadata": {
                            "name": "redis-maintenance-triage",
                            "skill_protocol": "agent_skills_v1",
                            "resource_kind": "entrypoint",
                            "resource_path": "SKILL.md",
                            "resource_title": "Redis Maintenance Triage",
                            "skill_description": "Investigate maintenance mode first.",
                            "skill_manifest": json.dumps(manifest),
                            "ui_metadata": json.dumps({"display_name": "Redis Maintenance Triage"}),
                        },
                    },
                    {
                        "doc_type": "skill",
                        "title": "Maintenance Checklist",
                        "fragments": [{"chunk_index": 0, "content": "Checklist body"}],
                        "metadata": {
                            "name": "redis-maintenance-triage",
                            "skill_protocol": "agent_skills_v1",
                            "resource_kind": "reference",
                            "resource_path": "references/maintenance-checklist.md",
                            "resource_title": "Maintenance Checklist",
                            "resource_description": "Evidence checklist.",
                        },
                    },
                    {
                        "doc_type": "skill",
                        "title": "collect_context.sh",
                        "fragments": [{"chunk_index": 0, "content": "echo collect"}],
                        "metadata": {
                            "name": "redis-maintenance-triage",
                            "skill_protocol": "agent_skills_v1",
                            "resource_kind": "script",
                            "resource_path": "scripts/collect_context.sh",
                            "resource_description": "Collect maintenance context.",
                        },
                    },
                ]
            ),
        ),
    ):
        result = await backend.get_skill(skill_name="redis-maintenance-triage", version="latest")

    assert result["protocol"] == "agent_skills_v1"
    assert result["backend_kind"] == "redis"
    assert result["references"] == [
        {
            "path": "references/maintenance-checklist.md",
            "title": "Maintenance Checklist",
            "summary": "Evidence checklist.",
        }
    ]
    assert result["assets"] == manifest["assets"]
    assert result["scripts"] == [
        {"path": "scripts/collect_context.sh", "description": "Collect maintenance context."}
    ]
    assert result["ui_metadata"] == {"display_name": "Redis Maintenance Triage"}


@pytest.mark.asyncio
async def test_get_skill_preserves_legacy_markdown_shape():
    backend = RedisSkillBackend(config=SimpleNamespace(skill_reference_char_budget=12000))

    with (
        patch.object(
            backend,
            "_query_skill_rows",
            new=AsyncMock(return_value=[{"document_hash": "legacy", "name": "legacy-skill"}]),
        ),
        patch(
            "redis_sre_agent.core.knowledge_helpers.get_all_document_fragments",
            new=AsyncMock(
                return_value={
                    "doc_type": "skill",
                    "fragments": [{"chunk_index": 0, "content": "Legacy body"}],
                    "metadata": {"name": "legacy-skill"},
                }
            ),
        ),
    ):
        result = await backend.get_skill(skill_name="legacy-skill", version="latest")

    assert result == {"skill_name": "legacy-skill", "full_content": "Legacy body"}


@pytest.mark.asyncio
async def test_get_skill_returns_not_found_when_loaded_resources_are_empty():
    backend = RedisSkillBackend(config=SimpleNamespace(skill_reference_char_budget=12000))

    with (
        patch.object(
            backend,
            "_query_skill_rows",
            new=AsyncMock(return_value=[{"document_hash": "legacy", "name": "legacy-skill"}]),
        ),
        patch.object(backend, "_load_skill_resources", new=AsyncMock(return_value=[])),
    ):
        result = await backend.get_skill(skill_name="legacy-skill", version="latest")

    assert result == {
        "skill_name": "legacy-skill",
        "error": "Skill not found",
        "available_skills": [],
    }


@pytest.mark.asyncio
async def test_get_skill_resource_applies_char_budget():
    backend = RedisSkillBackend(config=SimpleNamespace(skill_reference_char_budget=10))

    with (
        patch.object(
            backend,
            "_query_skill_rows",
            new=AsyncMock(
                return_value=[
                    {
                        "document_hash": "ref",
                        "name": "redis-maintenance-triage",
                        "resource_path": "references/maintenance-checklist.md",
                    }
                ]
            ),
        ),
        patch(
            "redis_sre_agent.core.knowledge_helpers.get_all_document_fragments",
            new=AsyncMock(
                return_value={
                    "doc_type": "skill",
                    "fragments": [{"chunk_index": 0, "content": "123456789012345"}],
                    "metadata": {
                        "name": "redis-maintenance-triage",
                        "skill_protocol": "agent_skills_v1",
                        "resource_kind": "reference",
                        "resource_path": "references/maintenance-checklist.md",
                        "mime_type": "text/markdown",
                    },
                }
            ),
        ),
    ):
        result = await backend.get_skill_resource(
            skill_name="redis-maintenance-triage",
            resource_path="references/maintenance-checklist.md",
            version="latest",
        )

    assert result["truncated"] is True
    assert result["char_budget"] == 10
    assert result["content_length"] == 15
    assert result["content"] == "1234567..."


@pytest.mark.asyncio
async def test_get_skill_resource_returns_not_found_when_loaded_resources_are_empty():
    backend = RedisSkillBackend(config=SimpleNamespace(skill_reference_char_budget=12000))

    with (
        patch.object(
            backend,
            "_query_skill_rows",
            new=AsyncMock(
                return_value=[
                    {
                        "document_hash": "ref",
                        "name": "redis-maintenance-triage",
                        "resource_path": "references/maintenance-checklist.md",
                    }
                ]
            ),
        ),
        patch.object(backend, "_load_skill_resources", new=AsyncMock(return_value=[])),
    ):
        result = await backend.get_skill_resource(
            skill_name="redis-maintenance-triage",
            resource_path="references/maintenance-checklist.md",
            version="latest",
        )

    assert result == {
        "skill_name": "redis-maintenance-triage",
        "resource_path": "references/maintenance-checklist.md",
        "error": "Skill resource not found",
    }


def test_get_skill_backend_caches_default_backend_instance():
    skill_backend_module._DEFAULT_BACKEND_CACHE = None
    config = SimpleNamespace(
        skill_backend_kind="redis",
        skill_backend_class="",
        skill_reference_char_budget=12000,
    )

    with patch.object(skill_backend_module, "settings", config):
        first = get_skill_backend()
        second = get_skill_backend()

    assert first is second
    skill_backend_module._DEFAULT_BACKEND_CACHE = None
