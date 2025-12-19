"""Centralized OpenTelemetry tracing configuration and helpers.

This module provides:
- Unified tracer setup for API and worker
- Span category constants for filtering in Grafana/Tempo
- Redis instrumentation with request/response hooks
- Helper decorators for consistent span attributes
"""

from __future__ import annotations

import logging
import os
from enum import Enum
from functools import wraps
from typing import Any, Callable, Optional, TypeVar

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.aiohttp_client import AioHttpClientInstrumentor
from opentelemetry.instrumentation.asyncio import AsyncioInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.openai import OpenAIInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

logger = logging.getLogger(__name__)

# Type var for decorators
F = TypeVar("F", bound=Callable[..., Any])


class SpanCategory(str, Enum):
    """Span categories for filtering traces in Grafana/Tempo.

    Use TraceQL like: {span.sre_agent.category = "llm"}
    """

    LLM = "llm"
    TOOL = "tool"
    GRAPH_NODE = "graph_node"
    AGENT = "agent"
    KNOWLEDGE = "knowledge"
    HTTP = "http"
    REDIS = "redis"  # Infrastructure - can be filtered out


# Attribute keys
ATTR_CATEGORY = "sre_agent.category"
ATTR_COMPONENT = "sre_agent.component"
ATTR_GRAPH_NAME = "langgraph.graph"
ATTR_NODE_NAME = "langgraph.node"

# Redis commands that are "noisy" infrastructure - useful for filtering
REDIS_INFRA_COMMANDS = frozenset(
    {
        "PING",
        "SELECT",
        "INFO",
        "CONFIG",
        "CLIENT",
        "DEBUG",
        "SLOWLOG",
        "MEMORY",
        "DBSIZE",
        "LASTSAVE",
        "TIME",
        "SCAN",
        "HSCAN",
        "SSCAN",
        "ZSCAN",  # Iteration commands
        "WATCH",
        "MULTI",
        "EXEC",
        "DISCARD",  # Transaction commands
    }
)


def _redis_request_hook(span: trace.Span, instance: Any, args: tuple, kwargs: dict) -> None:
    """Hook called before each Redis command to add custom attributes."""
    if not span or not span.is_recording():
        return

    # Add category for filtering
    span.set_attribute(ATTR_CATEGORY, SpanCategory.REDIS.value)

    # Extract command name for filtering (handle bytes and string)
    if args:
        cmd = args[0]
        if isinstance(cmd, bytes):
            cmd_str = cmd.decode("utf-8", errors="replace")
        else:
            cmd_str = str(cmd)
        command = cmd_str.upper()
    else:
        command = "UNKNOWN"
    span.set_attribute("redis.command", command)

    # Mark infrastructure commands for easy filtering
    is_infra = command in REDIS_INFRA_COMMANDS
    span.set_attribute("redis.is_infrastructure", is_infra)

    # Add key pattern (first key arg, if present) without exposing values
    if len(args) > 1 and isinstance(args[1], (str, bytes)):
        key = args[1] if isinstance(args[1], str) else args[1].decode("utf-8", errors="replace")
        # Extract key prefix (before first colon) for grouping
        prefix = key.split(":")[0] if ":" in key else key
        span.set_attribute("redis.key_prefix", prefix[:50])  # Truncate for safety


def _redis_response_hook(span: trace.Span, instance: Any, response: Any) -> None:
    """Hook called after Redis command completion."""
    if not span or not span.is_recording():
        return

    # Add response type for debugging
    if response is not None:
        resp_type = type(response).__name__
        span.set_attribute("redis.response_type", resp_type)


def setup_tracing(
    service_name: str,
    service_version: str = "0.1.0",
) -> bool:
    """Initialize OpenTelemetry tracing if OTLP endpoint is configured.

    Returns True if tracing was enabled, False otherwise.
    """
    otlp_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not otlp_endpoint:
        logger.info(
            f"OpenTelemetry tracing disabled for {service_name} (no OTEL_EXPORTER_OTLP_ENDPOINT)"
        )
        return False

    resource = Resource.create(
        {
            "service.name": service_name,
            "service.version": service_version,
        }
    )
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(
        endpoint=otlp_endpoint,
        headers=os.environ.get("OTEL_EXPORTER_OTLP_HEADERS"),
    )
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    # Instrument Redis with custom hooks for filtering
    RedisInstrumentor().instrument(
        request_hook=_redis_request_hook,
        response_hook=_redis_response_hook,
    )

    # Instrument HTTP clients
    HTTPXClientInstrumentor().instrument()
    AioHttpClientInstrumentor().instrument()
    AsyncioInstrumentor().instrument()
    OpenAIInstrumentor().instrument()

    logger.info(f"OpenTelemetry tracing initialized for {service_name}")
    return True


def get_tracer(name: str) -> trace.Tracer:
    """Get a tracer instance for creating spans."""
    return trace.get_tracer(name)


def trace_graph_node(graph_name: str, node_name: str):
    """Decorator to trace LangGraph node execution with standard attributes."""

    def decorator(fn: F) -> F:
        tracer = get_tracer(fn.__module__)

        @wraps(fn)
        async def wrapper(*args, **kwargs):
            with tracer.start_as_current_span(
                f"langgraph.{graph_name}.{node_name}",
                attributes={
                    ATTR_CATEGORY: SpanCategory.GRAPH_NODE.value,
                    ATTR_GRAPH_NAME: graph_name,
                    ATTR_NODE_NAME: node_name,
                },
            ):
                return await fn(*args, **kwargs)

        return wrapper  # type: ignore

    return decorator


def trace_tool(tool_name: str, component: Optional[str] = None):
    """Decorator to trace tool execution with standard attributes."""

    def decorator(fn: F) -> F:
        tracer = get_tracer(fn.__module__)

        @wraps(fn)
        async def wrapper(*args, **kwargs):
            attrs = {
                ATTR_CATEGORY: SpanCategory.TOOL.value,
                "tool.name": tool_name,
            }
            if component:
                attrs[ATTR_COMPONENT] = component
            with tracer.start_as_current_span(f"tool.{tool_name}", attributes=attrs):
                return await fn(*args, **kwargs)

        return wrapper  # type: ignore

    return decorator


def trace_llm(component: str):
    """Decorator to trace LLM calls with standard attributes.

    Note: This creates the span; use record_llm_call_metrics() to add token usage.
    """

    def decorator(fn: F) -> F:
        tracer = get_tracer(fn.__module__)

        @wraps(fn)
        async def wrapper(*args, **kwargs):
            with tracer.start_as_current_span(
                f"llm.{component}",
                attributes={
                    ATTR_CATEGORY: SpanCategory.LLM.value,
                    ATTR_COMPONENT: component,
                },
            ):
                return await fn(*args, **kwargs)

        return wrapper  # type: ignore

    return decorator


def add_span_attributes(attrs: dict[str, Any]) -> None:
    """Add attributes to the current span if recording."""
    span = trace.get_current_span()
    if span and span.is_recording():
        for key, value in attrs.items():
            try:
                span.set_attribute(key, value)
            except Exception:
                pass  # Ignore invalid attribute values


# Common TraceQL queries for Grafana/Tempo
# These can be used as saved queries or in dashboard panels
TRACEQL_QUERIES = {
    "agent_turns": '{ span.name = "agent.turn" }',
    "llm_calls": '{ span.sre_agent.category = "llm" }',
    "tool_calls": '{ span.sre_agent.category = "tool" }',
    "graph_nodes": '{ span.sre_agent.category = "graph_node" }',
    "exclude_redis": '{ span.sre_agent.category != "redis" }',
    "slow_llm": '{ span.sre_agent.category = "llm" && duration > 5s }',
    "knowledge_ops": '{ span.sre_agent.category = "knowledge" }',
    # Filter out Redis infrastructure commands
    "app_only": '{ span.sre_agent.category != "redis" || span.redis.is_infrastructure = false }',
}
