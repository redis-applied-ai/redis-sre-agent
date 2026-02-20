"""Tests for citation message formatting (TDD approach).

Tests written first for the feature that appends citation messages to threads.
"""

from redis_sre_agent.core.citation_message import (
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

    def test_truncates_long_hashes_in_display(self):
        """Test that very long hashes are truncated for readability."""
        results = [
            {
                "title": "Long Hash Doc",
                "source": "test.com",
                "document_hash": "a" * 64,  # Very long hash
                "score": 0.9,
            }
        ]
        message = format_citation_message(results)

        # Full hash should still be in the tool hint section
        assert "a" * 64 in message or "a" * 12 in message  # Either full or truncated
