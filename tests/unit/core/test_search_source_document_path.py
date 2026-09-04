"""US-001: source_document_path is surfaced in knowledge search results.

The semantic cache's provenance/invalidation keys on source_document_path, so it
must reach the serialized search-result dict (design §0).
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from redis_sre_agent.core.knowledge_helpers import (
    _SEARCH_RETURN_FIELDS,
    search_knowledge_base_helper,
)


def test_source_document_path_in_return_fields():
    """RediSearch RETURN must request the hash field so it reaches results."""
    assert "source_document_path" in _SEARCH_RETURN_FIELDS


@pytest.mark.asyncio
async def test_search_result_includes_source_document_path():
    mock_index = AsyncMock()
    mock_index.query = AsyncMock(
        return_value=[
            {
                "id": "doc-1",
                "document_hash": "hash-1",
                "chunk_index": 0,
                "title": "Redis Memory",
                "content": "Redis memory management guide",
                "source": "docs",
                "category": "monitoring",
                "doc_type": "runbook",
                "version": "latest",
                "source_document_path": "runbooks/memory.md",
                "score": 0.95,
            }
        ]
    )
    mock_vectorizer = MagicMock()
    mock_vectorizer.aembed_many = AsyncMock(return_value=[[0.1, 0.2, 0.3]])

    with (
        patch(
            "redis_sre_agent.core.knowledge_helpers.get_knowledge_index",
            new_callable=AsyncMock,
            return_value=mock_index,
        ),
        patch(
            "redis_sre_agent.core.knowledge_helpers.get_vectorizer",
            return_value=mock_vectorizer,
        ),
    ):
        result = await search_knowledge_base_helper(query="redis memory", limit=10)

    assert result["results"][0]["source_document_path"] == "runbooks/memory.md"


@pytest.mark.asyncio
async def test_search_result_source_document_path_defaults_empty():
    """A doc hash without the field serializes to an empty string, not a KeyError."""
    mock_index = AsyncMock()
    mock_index.query = AsyncMock(
        return_value=[
            {
                "id": "doc-2",
                "document_hash": "hash-2",
                "title": "No path doc",
                "content": "body",
                "source": "docs",
                "doc_type": "runbook",
                "version": "latest",
                "score": 0.9,
            }
        ]
    )
    mock_vectorizer = MagicMock()
    mock_vectorizer.aembed_many = AsyncMock(return_value=[[0.1, 0.2, 0.3]])

    with (
        patch(
            "redis_sre_agent.core.knowledge_helpers.get_knowledge_index",
            new_callable=AsyncMock,
            return_value=mock_index,
        ),
        patch(
            "redis_sre_agent.core.knowledge_helpers.get_vectorizer",
            return_value=mock_vectorizer,
        ),
    ):
        result = await search_knowledge_base_helper(query="x", limit=10)

    assert result["results"][0]["source_document_path"] == ""
