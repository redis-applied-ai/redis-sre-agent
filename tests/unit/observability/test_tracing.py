"""Tests for the centralized tracing module.

Tests cover:
- SpanCategory enum values
- Redis request/response hooks
- Tracing decorators (trace_graph_node, trace_tool, trace_llm)
- add_span_attributes helper
- setup_tracing behavior (with and without OTLP endpoint)
"""

from unittest.mock import MagicMock, patch

import pytest

from redis_sre_agent.observability.tracing import (
    ATTR_CATEGORY,
    ATTR_COMPONENT,
    ATTR_GRAPH_NAME,
    ATTR_NODE_NAME,
    REDIS_INFRA_COMMANDS,
    TRACEQL_QUERIES,
    SpanCategory,
    _redis_request_hook,
    _redis_response_hook,
    add_span_attributes,
    get_tracer,
    setup_tracing,
    trace_graph_node,
    trace_llm,
    trace_tool,
)


class TestSpanCategory:
    """Test SpanCategory enum."""

    def test_span_categories_are_strings(self):
        """All span categories should be string values."""
        assert SpanCategory.LLM.value == "llm"
        assert SpanCategory.TOOL.value == "tool"
        assert SpanCategory.GRAPH_NODE.value == "graph_node"
        assert SpanCategory.AGENT.value == "agent"
        assert SpanCategory.KNOWLEDGE.value == "knowledge"
        assert SpanCategory.HTTP.value == "http"
        assert SpanCategory.REDIS.value == "redis"

    def test_span_category_is_string_subclass(self):
        """SpanCategory should be usable as a string."""
        assert isinstance(SpanCategory.LLM, str)
        assert SpanCategory.LLM == "llm"


class TestAttributeConstants:
    """Test attribute key constants."""

    def test_attribute_keys_defined(self):
        """Verify attribute key constants are defined."""
        assert ATTR_CATEGORY == "sre_agent.category"
        assert ATTR_COMPONENT == "sre_agent.component"
        assert ATTR_GRAPH_NAME == "langgraph.graph"
        assert ATTR_NODE_NAME == "langgraph.node"


class TestRedisInfraCommands:
    """Test Redis infrastructure command detection."""

    def test_ping_is_infra(self):
        """PING should be an infrastructure command."""
        assert "PING" in REDIS_INFRA_COMMANDS

    def test_info_is_infra(self):
        """INFO should be an infrastructure command."""
        assert "INFO" in REDIS_INFRA_COMMANDS

    def test_scan_commands_are_infra(self):
        """SCAN variants should be infrastructure commands."""
        assert "SCAN" in REDIS_INFRA_COMMANDS
        assert "HSCAN" in REDIS_INFRA_COMMANDS
        assert "SSCAN" in REDIS_INFRA_COMMANDS
        assert "ZSCAN" in REDIS_INFRA_COMMANDS

    def test_get_set_not_infra(self):
        """GET and SET should not be infrastructure commands."""
        assert "GET" not in REDIS_INFRA_COMMANDS
        assert "SET" not in REDIS_INFRA_COMMANDS
        assert "HSET" not in REDIS_INFRA_COMMANDS


class TestRedisRequestHook:
    """Test the Redis request hook."""

    def test_hook_sets_category_attribute(self):
        """Hook should set sre_agent.category to redis."""
        mock_span = MagicMock()
        mock_span.is_recording.return_value = True

        _redis_request_hook(mock_span, None, ("GET", "mykey"), {})

        mock_span.set_attribute.assert_any_call(ATTR_CATEGORY, "redis")

    def test_hook_sets_command_attribute(self):
        """Hook should set redis.command attribute."""
        mock_span = MagicMock()
        mock_span.is_recording.return_value = True

        _redis_request_hook(mock_span, None, ("HSET", "myhash", "field", "value"), {})

        mock_span.set_attribute.assert_any_call("redis.command", "HSET")

    def test_hook_marks_infra_commands(self):
        """Hook should mark infrastructure commands."""
        mock_span = MagicMock()
        mock_span.is_recording.return_value = True

        _redis_request_hook(mock_span, None, ("PING",), {})

        mock_span.set_attribute.assert_any_call("redis.is_infrastructure", True)

    def test_hook_marks_non_infra_commands(self):
        """Hook should mark non-infrastructure commands."""
        mock_span = MagicMock()
        mock_span.is_recording.return_value = True

        _redis_request_hook(mock_span, None, ("GET", "mykey"), {})

        mock_span.set_attribute.assert_any_call("redis.is_infrastructure", False)

    def test_hook_extracts_key_prefix(self):
        """Hook should extract key prefix before colon."""
        mock_span = MagicMock()
        mock_span.is_recording.return_value = True

        _redis_request_hook(mock_span, None, ("GET", "user:123:profile"), {})

        mock_span.set_attribute.assert_any_call("redis.key_prefix", "user")

    def test_hook_handles_key_without_colon(self):
        """Hook should handle keys without colons."""
        mock_span = MagicMock()
        mock_span.is_recording.return_value = True

        _redis_request_hook(mock_span, None, ("GET", "simplekey"), {})

        mock_span.set_attribute.assert_any_call("redis.key_prefix", "simplekey")

    def test_hook_handles_bytes_key(self):
        """Hook should handle bytes keys."""
        mock_span = MagicMock()
        mock_span.is_recording.return_value = True

        _redis_request_hook(mock_span, None, ("GET", b"mykey:123"), {})

        mock_span.set_attribute.assert_any_call("redis.key_prefix", "mykey")

    def test_hook_skips_non_recording_span(self):
        """Hook should skip if span is not recording."""
        mock_span = MagicMock()
        mock_span.is_recording.return_value = False

        _redis_request_hook(mock_span, None, ("GET", "mykey"), {})

        mock_span.set_attribute.assert_not_called()

    def test_hook_handles_none_span(self):
        """Hook should handle None span gracefully."""
        # Should not raise
        _redis_request_hook(None, None, ("GET", "mykey"), {})

    def test_hook_handles_empty_args(self):
        """Hook should handle empty args gracefully."""
        mock_span = MagicMock()
        mock_span.is_recording.return_value = True

        _redis_request_hook(mock_span, None, (), {})

        mock_span.set_attribute.assert_any_call("redis.command", "UNKNOWN")

    def test_hook_handles_bytes_command(self):
        """Hook should handle bytes command names."""
        mock_span = MagicMock()
        mock_span.is_recording.return_value = True

        _redis_request_hook(mock_span, None, (b"GET", b"mykey"), {})

        mock_span.set_attribute.assert_any_call("redis.command", "GET")


class TestRedisResponseHook:
    """Test the Redis response hook."""

    def test_hook_sets_response_type(self):
        """Hook should set redis.response_type attribute."""
        mock_span = MagicMock()
        mock_span.is_recording.return_value = True

        _redis_response_hook(mock_span, None, "OK")

        mock_span.set_attribute.assert_called_with("redis.response_type", "str")

    def test_hook_handles_list_response(self):
        """Hook should handle list responses."""
        mock_span = MagicMock()
        mock_span.is_recording.return_value = True

        _redis_response_hook(mock_span, None, [b"item1", b"item2"])

        mock_span.set_attribute.assert_called_with("redis.response_type", "list")

    def test_hook_skips_none_response(self):
        """Hook should skip None responses."""
        mock_span = MagicMock()
        mock_span.is_recording.return_value = True

        _redis_response_hook(mock_span, None, None)

        mock_span.set_attribute.assert_not_called()

    def test_hook_skips_non_recording_span(self):
        """Hook should skip if span is not recording."""
        mock_span = MagicMock()
        mock_span.is_recording.return_value = False

        _redis_response_hook(mock_span, None, "OK")

        mock_span.set_attribute.assert_not_called()


class TestSetupTracing:
    """Test setup_tracing function."""

    def test_returns_false_without_endpoint(self):
        """Should return False when OTLP endpoint not set."""
        with patch.dict("os.environ", {}, clear=True):
            # Remove OTEL_EXPORTER_OTLP_ENDPOINT if present
            import os
            os.environ.pop("OTEL_EXPORTER_OTLP_ENDPOINT", None)
            result = setup_tracing("test-service")
            assert result is False

    @patch("redis_sre_agent.observability.tracing.RedisInstrumentor")
    @patch("redis_sre_agent.observability.tracing.HTTPXClientInstrumentor")
    @patch("redis_sre_agent.observability.tracing.AioHttpClientInstrumentor")
    @patch("redis_sre_agent.observability.tracing.AsyncioInstrumentor")
    @patch("redis_sre_agent.observability.tracing.OpenAIInstrumentor")
    @patch("redis_sre_agent.observability.tracing.trace")
    @patch("redis_sre_agent.observability.tracing.BatchSpanProcessor")
    @patch("redis_sre_agent.observability.tracing.OTLPSpanExporter")
    @patch("redis_sre_agent.observability.tracing.TracerProvider")
    def test_returns_true_with_endpoint(
        self,
        mock_provider,
        mock_exporter,
        mock_processor,
        mock_trace,
        mock_openai,
        mock_asyncio,
        mock_aiohttp,
        mock_httpx,
        mock_redis,
    ):
        """Should return True when OTLP endpoint is set."""
        with patch.dict("os.environ", {"OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4318"}):
            result = setup_tracing("test-service", "1.0.0")
            assert result is True
            mock_redis.return_value.instrument.assert_called_once()


class TestGetTracer:
    """Test get_tracer function."""

    @patch("redis_sre_agent.observability.tracing.trace")
    def test_returns_tracer(self, mock_trace):
        """Should return a tracer for the given name."""
        mock_tracer = MagicMock()
        mock_trace.get_tracer.return_value = mock_tracer

        result = get_tracer("test.module")

        mock_trace.get_tracer.assert_called_with("test.module")
        assert result == mock_tracer


class TestTraceGraphNodeDecorator:
    """Test trace_graph_node decorator."""

    @pytest.mark.asyncio
    async def test_decorator_wraps_function(self):
        """Decorator should preserve function behavior."""
        @trace_graph_node("test_graph", "test_node")
        async def my_node(state):
            return {"processed": True}

        result = await my_node({})
        assert result == {"processed": True}

    def test_decorator_preserves_function_name(self):
        """Decorator should preserve function name."""
        @trace_graph_node("test_graph", "test_node")
        async def my_special_node(state):
            return state

        assert my_special_node.__name__ == "my_special_node"


class TestTraceToolDecorator:
    """Test trace_tool decorator."""

    @pytest.mark.asyncio
    async def test_decorator_wraps_function(self):
        """Decorator should preserve function behavior."""
        @trace_tool("test_tool")
        async def my_tool(query):
            return f"result for {query}"

        result = await my_tool("test")
        assert result == "result for test"

    @pytest.mark.asyncio
    async def test_decorator_with_component(self):
        """Decorator should work with component parameter."""
        @trace_tool("search", component="knowledge")
        async def search_knowledge(query):
            return ["doc1", "doc2"]

        result = await search_knowledge("redis")
        assert result == ["doc1", "doc2"]


class TestTraceLlmDecorator:
    """Test trace_llm decorator."""

    @pytest.mark.asyncio
    async def test_decorator_wraps_function(self):
        """Decorator should preserve function behavior."""
        @trace_llm("router")
        async def call_llm(prompt):
            return "response"

        result = await call_llm("test prompt")
        assert result == "response"


class TestAddSpanAttributes:
    """Test add_span_attributes helper."""

    @patch("redis_sre_agent.observability.tracing.trace")
    def test_adds_attributes_to_current_span(self, mock_trace):
        """Should add attributes to current span."""
        mock_span = MagicMock()
        mock_span.is_recording.return_value = True
        mock_trace.get_current_span.return_value = mock_span

        add_span_attributes({"key1": "value1", "key2": 42})

        mock_span.set_attribute.assert_any_call("key1", "value1")
        mock_span.set_attribute.assert_any_call("key2", 42)

    @patch("redis_sre_agent.observability.tracing.trace")
    def test_skips_non_recording_span(self, mock_trace):
        """Should skip if span is not recording."""
        mock_span = MagicMock()
        mock_span.is_recording.return_value = False
        mock_trace.get_current_span.return_value = mock_span

        add_span_attributes({"key1": "value1"})

        mock_span.set_attribute.assert_not_called()

    @patch("redis_sre_agent.observability.tracing.trace")
    def test_handles_no_current_span(self, mock_trace):
        """Should handle None current span gracefully."""
        mock_trace.get_current_span.return_value = None

        # Should not raise
        add_span_attributes({"key1": "value1"})


class TestTraceQLQueries:
    """Test TraceQL query constants."""

    def test_queries_defined(self):
        """TraceQL queries should be defined."""
        assert "agent_turns" in TRACEQL_QUERIES
        assert "llm_calls" in TRACEQL_QUERIES
        assert "tool_calls" in TRACEQL_QUERIES
        assert "exclude_redis" in TRACEQL_QUERIES
        assert "app_only" in TRACEQL_QUERIES

    def test_queries_are_valid_traceql_format(self):
        """Queries should have TraceQL braces format."""
        for name, query in TRACEQL_QUERIES.items():
            assert query.startswith("{"), f"{name} should start with {{"
            assert query.endswith("}"), f"{name} should end with }}"
