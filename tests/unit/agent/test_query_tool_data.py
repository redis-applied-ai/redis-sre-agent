"""Tests for query_tool_data JMESPath query helper.

This module tests the query_tool_data function that enables JQ-like queries
on tool envelope data using JMESPath expressions.
"""

import pytest

from redis_sre_agent.agent.chat_agent import ChatAgent
from redis_sre_agent.agent.helpers import query_tool_data


class TestQueryToolData:
    """Test query_tool_data helper function."""

    def test_query_simple_field(self):
        """Test extracting a simple field from tool data."""
        envelopes = [
            {
                "tool_key": "redis_info",
                "name": "Get Redis INFO",
                "status": "success",
                "data": {
                    "memory": {
                        "used_memory_human": "1.2G",
                        "maxmemory_human": "2G",
                    }
                },
            }
        ]

        result = query_tool_data(envelopes, "redis_info", "memory.used_memory_human")
        assert result == "1.2G"

    def test_query_nested_field(self):
        """Test extracting nested field from tool data."""
        envelopes = [
            {
                "tool_key": "redis_info",
                "status": "success",
                "data": {
                    "server": {"redis_version": "7.2.0", "os": "Linux"},
                    "memory": {"used_memory": 123456},
                },
            }
        ]

        result = query_tool_data(envelopes, "redis_info", "server.redis_version")
        assert result == "7.2.0"

    def test_query_array_slice(self):
        """Test extracting array slice from tool data."""
        envelopes = [
            {
                "tool_key": "slowlog",
                "status": "success",
                "data": {
                    "entries": [
                        {"id": 1, "duration_us": 1000},
                        {"id": 2, "duration_us": 2000},
                        {"id": 3, "duration_us": 3000},
                        {"id": 4, "duration_us": 4000},
                    ]
                },
            }
        ]

        result = query_tool_data(envelopes, "slowlog", "entries[:2]")
        assert len(result) == 2
        assert result[0]["id"] == 1
        assert result[1]["id"] == 2

    def test_query_array_filter(self):
        """Test filtering array items using JMESPath filter expression."""
        envelopes = [
            {
                "tool_key": "slowlog",
                "status": "success",
                "data": {
                    "entries": [
                        {"id": 1, "duration_us": 500},
                        {"id": 2, "duration_us": 1500},
                        {"id": 3, "duration_us": 2500},
                    ]
                },
            }
        ]

        result = query_tool_data(envelopes, "slowlog", "entries[?duration_us > `1000`]")
        assert len(result) == 2
        assert result[0]["id"] == 2
        assert result[1]["id"] == 3

    def test_query_projection(self):
        """Test projecting specific fields from array items."""
        envelopes = [
            {
                "tool_key": "slowlog",
                "status": "success",
                "data": {
                    "entries": [
                        {"id": 1, "command": "GET", "duration_us": 1000},
                        {"id": 2, "command": "SET", "duration_us": 2000},
                    ]
                },
            }
        ]

        result = query_tool_data(
            envelopes, "slowlog", "entries[*].{cmd: command, dur: duration_us}"
        )
        assert len(result) == 2
        assert result[0] == {"cmd": "GET", "dur": 1000}
        assert result[1] == {"cmd": "SET", "dur": 2000}

    def test_query_tool_not_found(self):
        """Test querying non-existent tool_key returns None."""
        envelopes = [
            {
                "tool_key": "redis_info",
                "status": "success",
                "data": {"memory": {"used_memory": 123}},
            }
        ]

        result = query_tool_data(envelopes, "nonexistent_tool", "memory")
        assert result is None

    def test_query_empty_envelopes(self):
        """Test querying empty envelope list returns None."""
        result = query_tool_data([], "redis_info", "memory")
        assert result is None

    def test_query_invalid_expression(self):
        """Test invalid JMESPath expression raises appropriate error."""
        envelopes = [
            {
                "tool_key": "redis_info",
                "status": "success",
                "data": {"memory": {"used_memory": 123}},
            }
        ]

        with pytest.raises(ValueError, match="Invalid JMESPath"):
            query_tool_data(envelopes, "redis_info", "[[[invalid")

    def test_query_uses_most_recent_envelope(self):
        """Test that when multiple envelopes have same tool_key, most recent is used."""
        envelopes = [
            {
                "tool_key": "redis_info",
                "status": "success",
                "data": {"memory": {"used_memory_human": "1G"}},
            },
            {
                "tool_key": "redis_info",
                "status": "success",
                "data": {"memory": {"used_memory_human": "2G"}},
            },
        ]

        result = query_tool_data(envelopes, "redis_info", "memory.used_memory_human")
        assert result == "2G"  # Should use the most recent (last) envelope


class TestExpandEvidenceWithQuery:
    """Test expand_evidence tool with optional JMESPath query parameter."""

    def test_expand_evidence_returns_full_data_without_query(self):
        """Test expand_evidence returns full data when no query is specified."""
        envelopes = [
            {
                "tool_key": "redis_info",
                "name": "Get Redis INFO",
                "status": "success",
                "data": {
                    "memory": {"used_memory_human": "1.2G", "maxmemory_human": "2G"},
                    "server": {"redis_version": "7.2.0"},
                },
            }
        ]

        agent = ChatAgent.__new__(ChatAgent)
        tool_spec = agent._build_expand_evidence_tool(envelopes)
        expand_fn = tool_spec["func"]

        result = expand_fn("redis_info")
        assert result["status"] == "success"
        assert result["full_data"]["memory"]["used_memory_human"] == "1.2G"
        assert result["full_data"]["server"]["redis_version"] == "7.2.0"

    def test_expand_evidence_with_simple_query(self):
        """Test expand_evidence with JMESPath query extracts specific data."""
        envelopes = [
            {
                "tool_key": "redis_info",
                "name": "Get Redis INFO",
                "status": "success",
                "data": {
                    "memory": {"used_memory_human": "1.2G", "maxmemory_human": "2G"},
                    "server": {"redis_version": "7.2.0"},
                },
            }
        ]

        agent = ChatAgent.__new__(ChatAgent)
        tool_spec = agent._build_expand_evidence_tool(envelopes)
        expand_fn = tool_spec["func"]

        result = expand_fn("redis_info", query="memory.used_memory_human")
        assert result["status"] == "success"
        assert result["queried_data"] == "1.2G"
        assert "full_data" not in result  # Should not include full_data when query is used

    def test_expand_evidence_with_array_slice_query(self):
        """Test expand_evidence with array slice query."""
        envelopes = [
            {
                "tool_key": "slowlog",
                "name": "Get SLOWLOG",
                "status": "success",
                "data": {
                    "entries": [
                        {"id": 1, "duration_us": 1000},
                        {"id": 2, "duration_us": 2000},
                        {"id": 3, "duration_us": 3000},
                    ]
                },
            }
        ]

        agent = ChatAgent.__new__(ChatAgent)
        tool_spec = agent._build_expand_evidence_tool(envelopes)
        expand_fn = tool_spec["func"]

        result = expand_fn("slowlog", query="entries[:2]")
        assert result["status"] == "success"
        assert len(result["queried_data"]) == 2
        assert result["queried_data"][0]["id"] == 1

    def test_expand_evidence_with_filter_query(self):
        """Test expand_evidence with JMESPath filter expression."""
        envelopes = [
            {
                "tool_key": "slowlog",
                "name": "Get SLOWLOG",
                "status": "success",
                "data": {
                    "entries": [
                        {"id": 1, "duration_us": 500},
                        {"id": 2, "duration_us": 1500},
                        {"id": 3, "duration_us": 2500},
                    ]
                },
            }
        ]

        agent = ChatAgent.__new__(ChatAgent)
        tool_spec = agent._build_expand_evidence_tool(envelopes)
        expand_fn = tool_spec["func"]

        result = expand_fn("slowlog", query="entries[?duration_us > `1000`]")
        assert result["status"] == "success"
        assert len(result["queried_data"]) == 2
        assert result["queried_data"][0]["id"] == 2

    def test_expand_evidence_invalid_query(self):
        """Test expand_evidence with invalid JMESPath returns error."""
        envelopes = [
            {
                "tool_key": "redis_info",
                "name": "Get Redis INFO",
                "status": "success",
                "data": {"memory": {"used_memory": 123}},
            }
        ]

        agent = ChatAgent.__new__(ChatAgent)
        tool_spec = agent._build_expand_evidence_tool(envelopes)
        expand_fn = tool_spec["func"]

        result = expand_fn("redis_info", query="[[[invalid")
        assert result["status"] == "error"
        assert "Invalid JMESPath" in result["error"]

    def test_expand_evidence_query_parameter_in_schema(self):
        """Test that expand_evidence tool schema includes optional query parameter."""
        envelopes = [
            {
                "tool_key": "redis_info",
                "status": "success",
                "data": {"memory": {"used_memory": 123}},
            }
        ]

        agent = ChatAgent.__new__(ChatAgent)
        tool_spec = agent._build_expand_evidence_tool(envelopes)

        # Check schema has query parameter
        assert "query" in tool_spec["parameters"]["properties"]
        query_schema = tool_spec["parameters"]["properties"]["query"]
        assert query_schema["type"] == "string"
        # query should be optional (not in required)
        assert "query" not in tool_spec["parameters"].get("required", [])
