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
    try:
        model = llm.model  # type: ignore[attr-defined]
        if model:
            return model
    except AttributeError:
        pass  # LLM may not have .model attribute
    try:
        model = llm._model  # type: ignore[attr-defined]
        if model:
            return model
    except AttributeError:
        pass  # LLM may not have ._model attribute
    return "unknown"


def _extract_usage_from_response(resp: Any) -> Dict[str, Optional[int]]:
    """Try best-effort extraction of token usage from a LangChain AIMessage or similar.

    Returns dict with keys: prompt_tokens, completion_tokens, total_tokens (may be None).
    """
    prompt = completion = total = None

    # LangChain AIMessage often exposes usage via .usage_metadata
    try:
        usage_md = resp.usage_metadata  # type: ignore[attr-defined]
        if isinstance(usage_md, dict):
            prompt = usage_md.get("input_tokens") or usage_md.get("prompt_tokens")
            completion = usage_md.get("output_tokens") or usage_md.get("completion_tokens")
            total = usage_md.get("total_tokens")
    except AttributeError:
        pass  # Response may not have .usage_metadata attribute

    # Some wrappers place the raw OpenAI usage in response_metadata
    if prompt is None or completion is None:
        try:
            resp_md = resp.response_metadata  # type: ignore[attr-defined]
            if isinstance(resp_md, dict):
                # OpenAI python client
                usage = resp_md.get("usage") or resp_md.get("token_usage")
                if isinstance(usage, dict):
                    prompt = prompt or usage.get("prompt_tokens") or usage.get("input_tokens")
                    completion = (
                        completion or usage.get("completion_tokens") or usage.get("output_tokens")
                    )
                    total = total or usage.get("total_tokens")
        except AttributeError:
            pass  # Response may not have .response_metadata attribute

    # Many providers only give total
    if total is None and prompt is not None and completion is not None:
        total = int(prompt) + int(completion)

    return {
        "prompt_tokens": prompt if prompt is not None else 0,
        "completion_tokens": completion if completion is not None else 0,
        "total_tokens": total if total is not None else ((prompt or 0) + (completion or 0)),
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
