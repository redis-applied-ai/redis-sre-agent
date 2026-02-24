"""Tests for extract_citations helper and AgentResponse citation derivation.

This module tests the extract_citations function that derives citation data
from knowledge tool envelopes, replacing the separate CitationTrace tracking.
"""

import pytest

from redis_sre_agent.agent.helpers import extract_citations
from redis_sre_agent.agent.models import AgentResponse


class TestExtractCitations:
    """Test extract_citations helper function."""

    def test_extract_citations_from_knowledge_search(self):
        """Test extracting citations from knowledge_search tool envelope."""
        envelopes = [
            {
                "tool_key": "knowledge_search",
                "name": "Search knowledge base",
                "args": {"query": "redis memory"},
                "status": "success",
                "data": {
                    "results": [
                        {
                            "id": "doc1",
                            "title": "Redis Memory Management",
                            "source": "redis.io",
                            "score": 0.92,
                            "document_hash": "abc123",
                            "chunk_index": 0,
                            "content": "Redis memory content...",
                        },
                        {
                            "id": "doc2",
                            "title": "Memory Optimization Guide",
                            "source": "redis.io/kb",
                            "score": 0.85,
                            "document_hash": "def456",
                            "chunk_index": 1,
                            "content": "Optimization tips...",
                        },
                    ]
                },
            }
        ]

        citations = extract_citations(envelopes)

        assert len(citations) == 2
        assert citations[0]["title"] == "Redis Memory Management"
        assert citations[0]["source"] == "redis.io"
        assert citations[0]["score"] == 0.92
        assert citations[0]["document_hash"] == "abc123"
        assert citations[1]["title"] == "Memory Optimization Guide"

    def test_extract_citations_multiple_knowledge_tools(self):
        """Test extracting citations from multiple knowledge tool calls."""
        envelopes = [
            {
                "tool_key": "knowledge_search",
                "name": "Search",
                "status": "success",
                "data": {
                    "results": [
                        {"title": "Doc A", "source": "source1", "score": 0.9}
                    ]
                },
            },
            {
                "tool_key": "redis_info",
                "name": "Get Redis INFO",
                "status": "success",
                "data": {"used_memory": "1GB"},
            },
            {
                "tool_key": "knowledge_search",
                "name": "Search",
                "status": "success",
                "data": {
                    "results": [
                        {"title": "Doc B", "source": "source2", "score": 0.8}
                    ]
                },
            },
        ]

        citations = extract_citations(envelopes)

        assert len(citations) == 2
        assert citations[0]["title"] == "Doc A"
        assert citations[1]["title"] == "Doc B"

    def test_extract_citations_ignores_non_knowledge_tools(self):
        """Test that non-knowledge tools are ignored."""
        envelopes = [
            {
                "tool_key": "redis_info",
                "name": "Get Redis INFO",
                "status": "success",
                "data": {"used_memory": "1GB"},
            },
            {
                "tool_key": "slowlog",
                "name": "Get SLOWLOG",
                "status": "success",
                "data": {"entries": []},
            },
        ]

        citations = extract_citations(envelopes)

        assert len(citations) == 0

    def test_extract_citations_empty_envelopes(self):
        """Test with empty envelopes list."""
        citations = extract_citations([])
        assert len(citations) == 0

    def test_extract_citations_empty_results(self):
        """Test knowledge tool with no results."""
        envelopes = [
            {
                "tool_key": "knowledge_search",
                "name": "Search",
                "status": "success",
                "data": {"results": []},
            }
        ]

        citations = extract_citations(envelopes)

        assert len(citations) == 0

    def test_extract_citations_missing_data_field(self):
        """Test knowledge tool with missing data field."""
        envelopes = [
            {
                "tool_key": "knowledge_search",
                "name": "Search",
                "status": "error",
            }
        ]

        citations = extract_citations(envelopes)

        assert len(citations) == 0

    def test_extract_citations_preserves_all_fields(self):
        """Test that all relevant citation fields are preserved."""
        envelopes = [
            {
                "tool_key": "knowledge_search",
                "name": "Search",
                "status": "success",
                "data": {
                    "results": [
                        {
                            "id": "unique-id",
                            "title": "Test Document",
                            "source": "test-source",
                            "score": 0.95,
                            "document_hash": "hash123",
                            "chunk_index": 5,
                            "content": "Full content here",
                            "category": "troubleshooting",
                        }
                    ]
                },
            }
        ]

        citations = extract_citations(envelopes)

        assert len(citations) == 1
        citation = citations[0]
        assert citation["id"] == "unique-id"
        assert citation["title"] == "Test Document"
        assert citation["source"] == "test-source"
        assert citation["score"] == 0.95
        assert citation["document_hash"] == "hash123"
        assert citation["chunk_index"] == 5
        assert citation["content"] == "Full content here"
        assert citation["category"] == "troubleshooting"

    def test_extract_citations_handles_dict_envelopes(self):
        """Test that function works with dict-type envelopes (not Pydantic models)."""
        # Envelopes can be raw dicts or model_dump() output
        envelopes = [
            dict(
                tool_key="knowledge_search",
                name="Search",
                status="success",
                data={
                    "results": [
                        {"title": "Dict-based Doc", "source": "test"}
                    ]
                },
            )
        ]

        citations = extract_citations(envelopes)

        assert len(citations) == 1
        assert citations[0]["title"] == "Dict-based Doc"


class TestAgentResponseSearchResults:
    """Test AgentResponse search_results derivation from tool_envelopes."""

    def test_search_results_derived_from_tool_envelopes(self):
        """Test that search_results returns citations derived from tool_envelopes."""
        response = AgentResponse(
            response="Test response",
            tool_envelopes=[
                {
                    "tool_key": "knowledge_search",
                    "name": "Search",
                    "status": "success",
                    "data": {
                        "results": [
                            {"title": "Doc 1", "source": "source1", "score": 0.9}
                        ]
                    },
                },
                {
                    "tool_key": "redis_info",
                    "name": "Get INFO",
                    "status": "success",
                    "data": {"memory": "1GB"},
                },
            ],
        )

        assert len(response.search_results) == 1
        assert response.search_results[0]["title"] == "Doc 1"

    def test_search_results_empty_when_no_knowledge_tools(self):
        """Test that search_results is empty when no knowledge tools used."""
        response = AgentResponse(
            response="Test response",
            tool_envelopes=[
                {
                    "tool_key": "redis_info",
                    "name": "Get INFO",
                    "status": "success",
                    "data": {"memory": "1GB"},
                }
            ],
        )

        assert len(response.search_results) == 0

    def test_search_results_empty_when_no_envelopes(self):
        """Test that search_results is empty when no envelopes."""
        response = AgentResponse(response="Test response")

        assert len(response.search_results) == 0

    def test_search_results_backwards_compatible_with_explicit_value(self):
        """Test that explicit search_results still works for backwards compatibility."""
        # When search_results is explicitly passed, it should be used
        # This is for backwards compatibility during migration
        explicit_results = [{"title": "Explicit Doc", "source": "test"}]
        response = AgentResponse(
            response="Test response",
            search_results=explicit_results,
        )

        assert len(response.search_results) == 1
        assert response.search_results[0]["title"] == "Explicit Doc"
