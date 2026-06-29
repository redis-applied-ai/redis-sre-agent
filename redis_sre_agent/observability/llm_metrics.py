"""LLM observability helpers: Prometheus counters and OTel span attributes.

Use record_llm_call_metrics() after an LLM call to capture token usage and latency.
This module is safe to import even if OpenTelemetry is not configured; span
attributes will be no-ops in that case.
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

from opentelemetry import trace
from prometheus_client import Counter, Histogram

from redis_sre_agent.core.llm_token_usage import extract_llm_token_usage

# Prometheus metrics
LLM_TOKENS_PROMPT = Counter(
    "sre_agent_llm_tokens_prompt_total",
    "Total prompt tokens consumed by LLM calls",
    labelnames=("model", "component"),
)
LLM_TOKENS_COMPLETION = Counter(
    "sre_agent_llm_tokens_completion_total",
    "Total completion tokens consumed by LLM calls",
    labelnames=("model", "component"),
)
LLM_TOKENS_TOTAL = Counter(
    "sre_agent_llm_tokens_total",
    "Total tokens consumed by LLM calls",
    labelnames=("model", "component"),
)
LLM_REQUESTS = Counter(
    "sre_agent_llm_requests_total",
    "Total LLM requests",
    labelnames=("model", "component", "status"),
)
LLM_LATENCY = Histogram(
    "sre_agent_llm_duration_seconds",
    "Latency of LLM calls in seconds",
    labelnames=("model", "component"),
)


def _get_model_name(llm: Any) -> str:
    """Extract model name from LLM object, trying common attribute patterns."""
    for attr in ("model", "model_name", "model_id", "deployment_name", "_model"):
        try:
            model = getattr(llm, attr)
        except AttributeError:
            continue
        if model:
            return str(model)
    return "unknown"


def _extract_usage_from_response(resp: Any) -> Dict[str, Optional[int]]:
    """Try best-effort extraction of token usage from a LangChain AIMessage or similar.

    Returns dict with keys: prompt_tokens, completion_tokens, total_tokens (may be None).
    """
    usage = extract_llm_token_usage(resp)
    return {
        "prompt_tokens": usage.prompt_tokens,
        "completion_tokens": usage.completion_tokens,
        "total_tokens": usage.total_tokens,
    }


def record_llm_call_metrics(
    *,
    component: str,
    llm: Any,
    response: Any,
    start_time: float,
    status: str = "ok",
    extra_attrs: Optional[Dict[str, Any]] = None,
) -> None:
    """Record Prometheus metrics and set OTel span attributes for an LLM call.

    Args:
        component: Logical component tag (e.g., "agent", "router", "knowledge")
        llm: The LLM client/wrapper used (to extract model name)
        response: The LLM response object (to extract token usage)
        start_time: perf_counter() captured immediately before the call
        status: "ok" or "error"
        extra_attrs: Optional dict of extra attributes to attach to current span
    """
    model = _get_model_name(llm)
    elapsed = max(0.0, time.perf_counter() - start_time)

    usage = _extract_usage_from_response(response)
    prompt = int(usage.get("prompt_tokens", 0) or 0)
    completion = int(usage.get("completion_tokens", 0) or 0)
    total = int(usage.get("total_tokens", prompt + completion) or 0)

    # Prometheus
    LLM_REQUESTS.labels(model=model, component=component, status=status).inc()
    LLM_LATENCY.labels(model=model, component=component).observe(elapsed)
    if total:
        LLM_TOKENS_TOTAL.labels(model=model, component=component).inc(total)
    if prompt:
        LLM_TOKENS_PROMPT.labels(model=model, component=component).inc(prompt)
    if completion:
        LLM_TOKENS_COMPLETION.labels(model=model, component=component).inc(completion)

    # OTel attributes on current span
    span = trace.get_current_span()
    if span and span.is_recording():
        span.set_attribute("llm.model", model)
        span.set_attribute("llm.duration_ms", int(elapsed * 1000))
        span.set_attribute("llm.tokens.prompt", prompt)
        span.set_attribute("llm.tokens.completion", completion)
        span.set_attribute("llm.tokens.total", total)
        span.set_attribute("llm.status", status)
        if extra_attrs:
            for k, v in extra_attrs.items():
                try:
                    span.set_attribute(f"llm.{k}", v)
                except Exception:
                    pass
