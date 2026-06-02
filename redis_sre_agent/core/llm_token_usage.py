"""Token helpers for LLM responses and outbound request context budgets."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Optional, Sequence

from redis_sre_agent.core.config import settings


@dataclass
class LLMTokenUsage:
    """Token usage reported by one LLM response."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class LLMTokenLimitExceededError(RuntimeError):
    """Base error raised when an LLM token budget is exceeded."""


class LLMContextTokenBudgetExceededError(LLMTokenLimitExceededError):
    """Raised when an outbound LLM request exceeds the configured context budget."""


def _coerce_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalize_positive_int(value: Any) -> Optional[int]:
    limit = _coerce_int(value)
    if limit is None or limit <= 0:
        return None
    return limit


def configured_context_token_budget() -> Optional[int]:
    """Return the configured per-request context token budget, if enabled."""

    return _normalize_positive_int(getattr(settings, "llm_context_token_budget", None))


def _usage_value(usage: Any, *names: str) -> Optional[int]:
    for name in names:
        if isinstance(usage, dict):
            value = usage.get(name)
        else:
            value = getattr(usage, name, None)
        coerced = _coerce_int(value)
        if coerced is not None:
            return coerced
    return None


def _usage_mapping_from_response(resp: Any) -> Any:
    if isinstance(resp, dict):
        usage = resp.get("usage") or resp.get("token_usage")
        if usage is not None:
            return usage

    usage = getattr(resp, "usage_metadata", None)
    if usage is not None:
        return usage

    response_metadata = getattr(resp, "response_metadata", None)
    if isinstance(response_metadata, dict):
        usage = response_metadata.get("usage") or response_metadata.get("token_usage")
        if usage is not None:
            return usage

    return getattr(resp, "usage", None)


def extract_llm_token_usage(resp: Any) -> LLMTokenUsage:
    """Extract token usage from LangChain or OpenAI-compatible responses."""

    usage = _usage_mapping_from_response(resp)
    prompt = _usage_value(usage, "input_tokens", "prompt_tokens")
    completion = _usage_value(usage, "output_tokens", "completion_tokens")
    total = _usage_value(usage, "total_tokens")
    component_total = (prompt or 0) + (completion or 0)

    if total is None and prompt is not None and completion is not None:
        total = component_total
    elif total is not None and total <= 0 and component_total > 0:
        total = component_total

    return LLMTokenUsage(
        prompt_tokens=prompt if prompt is not None else 0,
        completion_tokens=completion if completion is not None else 0,
        total_tokens=total if total is not None else component_total,
    )


def record_llm_token_usage(
    response: Any,
    *,
    request_kind: Optional[str] = None,
) -> LLMTokenUsage:
    """Extract reported response token usage for metrics and tracing."""

    return extract_llm_token_usage(response)


@lru_cache(maxsize=32)
def _encoding_for_model(model: Optional[str]) -> Any:
    try:
        import tiktoken
    except Exception:
        return None

    if model:
        try:
            return tiktoken.encoding_for_model(model)
        except Exception:
            pass

    try:
        return tiktoken.get_encoding("cl100k_base")
    except Exception:
        return None


def _json_default(value: Any) -> str:
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return model_dump(mode="json")
    return repr(value)


def _json_for_count(value: Any) -> str:
    try:
        return json.dumps(value, default=_json_default, sort_keys=True, separators=(",", ":"))
    except TypeError:
        return repr(value)


def _coerce_countable_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return "\n".join(_coerce_countable_text(item) for item in value)
    if isinstance(value, dict):
        if value.get("type") == "text" and isinstance(value.get("text"), str):
            return value["text"]
        if isinstance(value.get("content"), str):
            return value["content"]
        return _json_for_count(value)
    return str(value)


def _count_text_tokens(text: str, *, model: Optional[str]) -> int:
    if not text:
        return 0

    encoding = _encoding_for_model(model)
    if encoding is not None:
        return len(encoding.encode(text))

    return max(1, (len(text) + 3) // 4)


def _is_message_like(value: Any) -> bool:
    return isinstance(value, dict) or hasattr(value, "content")


def _payload_messages(payload: Any) -> Optional[list[Any]]:
    if isinstance(payload, (str, bytes, bytearray)):
        return None
    if _is_message_like(payload):
        return [payload]
    if isinstance(payload, Sequence):
        return list(payload)
    return None


def _message_countable_parts(message: Any) -> tuple[str, str, str, str]:
    if isinstance(message, dict):
        role = str(message.get("role") or "user")
        name = str(message.get("name") or "")
        content = _coerce_countable_text(message.get("content"))
        extras = {
            key: value
            for key, value in message.items()
            if key not in {"role", "name", "content"} and value is not None
        }
        return role, name, content, _json_for_count(extras) if extras else ""

    role = str(getattr(message, "type", None) or message.__class__.__name__.lower())
    name = str(getattr(message, "name", None) or "")
    content = _coerce_countable_text(getattr(message, "content", None))
    extras: dict[str, Any] = {}
    for attr in ("tool_calls", "invalid_tool_calls", "tool_call_id", "additional_kwargs"):
        value = getattr(message, attr, None)
        if value:
            extras[attr] = value
    return role, name, content, _json_for_count(extras) if extras else ""


def estimate_llm_context_tokens(
    payload: Any,
    *,
    model: Optional[str] = None,
    extra_payload: Any = None,
) -> int:
    """Estimate input/context tokens for an outbound LLM request."""

    messages = _payload_messages(payload)
    if messages is None:
        total = _count_text_tokens(_coerce_countable_text(payload), model=model)
    else:
        total = 3
        for message in messages:
            role, name, content, extras = _message_countable_parts(message)
            total += 4
            total += _count_text_tokens(role, model=model)
            total += _count_text_tokens(name, model=model)
            total += _count_text_tokens(content, model=model)
            total += _count_text_tokens(extras, model=model)

    if extra_payload:
        total += _count_text_tokens(_json_for_count(extra_payload), model=model)

    return total


def infer_llm_model_name(llm: Any) -> Optional[str]:
    """Best-effort extraction of a model name from a LangChain LLM or binding."""

    current = llm
    seen: set[int] = set()
    for _ in range(6):
        if current is None or id(current) in seen:
            break
        seen.add(id(current))
        for attr in ("model_name", "model", "model_id", "deployment_name"):
            value = getattr(current, attr, None)
            if isinstance(value, str) and value.strip():
                return value.strip()
        current = getattr(current, "bound", None)
    return None


def _bound_request_payloads(llm: Any) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    current = llm
    seen: set[int] = set()
    token_fields = {
        "tools",
        "tool_choice",
        "functions",
        "function_call",
        "response_format",
        "parallel_tool_calls",
    }

    for _ in range(6):
        if current is None or id(current) in seen:
            break
        seen.add(id(current))
        kwargs = getattr(current, "kwargs", None)
        if isinstance(kwargs, dict):
            payload = {key: kwargs[key] for key in token_fields if key in kwargs}
            if payload:
                payloads.append(payload)
        current = getattr(current, "bound", None)
    return payloads


def enforce_llm_context_token_budget(
    payload: Any,
    *,
    request_kind: Optional[str],
    model: Optional[str] = None,
    llm: Any = None,
    extra_payload: Any = None,
    token_budget: Any = None,
) -> Optional[int]:
    """Raise when an outbound request exceeds the configured context token budget."""

    budget = (
        _normalize_positive_int(token_budget)
        if token_budget is not None
        else configured_context_token_budget()
    )
    if budget is None:
        return None

    model_name = model or infer_llm_model_name(llm)
    extras: list[Any] = []
    if llm is not None:
        extras.extend(_bound_request_payloads(llm))
    if extra_payload:
        extras.append(extra_payload)

    estimated_tokens = estimate_llm_context_tokens(
        payload,
        model=model_name,
        extra_payload=extras or None,
    )
    if estimated_tokens <= budget:
        return estimated_tokens

    suffix = f" for {request_kind}" if request_kind else ""
    raise LLMContextTokenBudgetExceededError(
        "LLM context token budget exceeded"
        f"{suffix}: estimated {estimated_tokens} input tokens; budget is {budget}. "
        "Reduce conversation history, retrieved context, or tool payload size before retrying."
    )
