"""Tests for citation message formatting (TDD approach).

Tests written first for the feature that appends citation messages to threads.
"""

from redis_sre_agent.core.citation_message import (
    build_citation_message_payloads,
    format_citation_message,
    should_include_citations,
)


class TestShouldIncludeCitations:
    """Test the should_include_citations helper function."""

    def test_returns_false_for_empty_list(self):
        """Empty search results should not include citations."""
        assert should_include_citations([]) is False

    def test_returns_false_for_none(self):
        """None search results should not include citations."""
        assert should_include_citations(None) is False

    def test_returns_true_for_non_empty_list(self):
        """Non-empty search results should include citations."""
        results = [{"title": "Test", "source": "test.com", "document_hash": "abc"}]
        assert should_include_citations(results) is True

    def test_returns_true_for_single_result(self):
        """Single search result should include citations."""
        results = [{"title": "Doc", "source": "example.com", "document_hash": "xyz"}]
        assert should_include_citations(results) is True


class TestFormatCitationMessage:
    """Test the format_citation_message helper function."""

    def test_formats_single_citation(self):
        """Test formatting a single citation."""
        results = [
            {
                "title": "Redis Memory Management",
                "source": "redis.io/docs/memory",
                "document_hash": "abc123def",
                "score": 0.95,
            }
        ]
        message = format_citation_message(results)

        assert "**Sources for previous response**" in message
        assert "Redis Memory Management" in message
        assert "redis.io/docs/memory" in message
        assert "abc123def" in message
        assert "0.95" in message

    def test_formats_multiple_citations(self):
        """Test formatting multiple citations."""
        results = [
            {
                "title": "Redis Memory Management",
                "source": "redis.io/docs/memory",
                "document_hash": "abc123",
                "score": 0.95,
            },
            {
                "title": "Eviction Policies",
                "source": "redis.io/docs/eviction",
                "document_hash": "def456",
                "score": 0.88,
            },
        ]
        message = format_citation_message(results)

        assert "Redis Memory Management" in message
        assert "Eviction Policies" in message
        assert "abc123" in message
        assert "def456" in message

    def test_handles_missing_score(self):
        """Test formatting when score is missing."""
        results = [
            {
                "title": "No Score Doc",
                "source": "example.com",
                "document_hash": "noscore123",
            }
        ]
        message = format_citation_message(results)

        assert "No Score Doc" in message
        assert "noscore123" in message
        # Should not crash, should handle missing score gracefully

    def test_handles_missing_title(self):
        """Test formatting when title is missing."""
        results = [
            {
                "source": "example.com/untitled",
                "document_hash": "notitle456",
                "score": 0.85,
            }
        ]
        message = format_citation_message(results)

        assert "notitle456" in message
        assert "example.com/untitled" in message

    def test_returns_empty_string_for_empty_results(self):
        """Test that empty results return empty string."""
        assert format_citation_message([]) == ""
        assert format_citation_message(None) == ""

    def test_handles_long_hashes(self):
        """Test that very long hashes are handled correctly."""
        results = [
            {
                "title": "Long Hash Doc",
                "source": "test.com",
                "document_hash": "a" * 64,  # Very long hash
                "score": 0.9,
            }
        ]
        message = format_citation_message(results)

        # Hash should be present in the message
        assert "a" * 64 in message

    def test_builds_separate_payloads_for_discovered_and_startup_context(self):
        results = [
            {
                "title": "Redis Memory Management",
                "source": "redis.io/docs/memory",
                "document_hash": "abc123def",
                "score": 0.95,
                "retrieval_kind": "knowledge_search",
            },
            {
                "title": "Pinned Runbook",
                "source": "file:///tmp/pinned.md",
                "document_hash": "pinned123",
                "retrieval_kind": "pinned_context",
            },
        ]

        payloads = build_citation_message_payloads(results)

        assert len(payloads) == 2
        assert payloads[0]["metadata"]["citation_group"] == "discovered_context"
        assert payloads[0]["content"].startswith("**Discovered context**")
        assert payloads[1]["metadata"]["citation_group"] == "startup_context_loaded"
        assert payloads[1]["content"].startswith("**Startup context loaded**")
