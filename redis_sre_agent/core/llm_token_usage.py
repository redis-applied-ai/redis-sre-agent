"""Track LLM token usage across a single agent turn."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Any, Iterator, Optional

from redis_sre_agent.core.config import settings


@dataclass
class LLMTokenUsage:
    """Token usage reported by one LLM response."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass
class LLMTokenUsageState:
    """Accumulated token usage for one logical agent turn."""

    limit: Optional[int]
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    def add(self, usage: LLMTokenUsage) -> None:
        self.prompt_tokens += usage.prompt_tokens
        self.completion_tokens += usage.completion_tokens
        self.total_tokens += usage.total_tokens


class LLMTokenLimitExceededError(RuntimeError):
    """Raised when a configured single-turn LLM token limit is exceeded."""


_token_usage_state: ContextVar[Optional[LLMTokenUsageState]] = ContextVar(
    "llm_token_usage_state",
    default=None,
)


def _coerce_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


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


def _normalize_limit(value: Any) -> Optional[int]:
    limit = _coerce_int(value)
    if limit is None or limit <= 0:
        return None
    return limit


def _configured_limit() -> Optional[int]:
    return _normalize_limit(getattr(settings, "llm_single_turn_token_limit", None))


def start_llm_token_usage_scope(limit: Any = None) -> Token[Optional[LLMTokenUsageState]]:
    """Start a logical LLM token accounting scope for one agent turn."""

    effective_limit = _normalize_limit(limit) if limit is not None else _configured_limit()
    return _token_usage_state.set(LLMTokenUsageState(limit=effective_limit))


def reset_llm_token_usage_scope(token: Token[Optional[LLMTokenUsageState]]) -> None:
    """Reset a token accounting scope created by start_llm_token_usage_scope()."""

    _token_usage_state.reset(token)


@contextmanager
def llm_token_usage_scope(limit: Any = None) -> Iterator[LLMTokenUsageState]:
    """Context manager for single-turn token accounting."""

    token = start_llm_token_usage_scope(limit)
    state = _token_usage_state.get()
    if state is None:
        raise RuntimeError("Failed to initialize LLM token usage scope")
    try:
        yield state
    finally:
        reset_llm_token_usage_scope(token)


def _raise_if_limit_exceeded(
    *,
    total_tokens: int,
    limit: int,
    request_kind: Optional[str],
) -> None:
    if total_tokens <= limit:
        return
    suffix = f" for {request_kind}" if request_kind else ""
    raise LLMTokenLimitExceededError(
        "LLM token usage limit exceeded"
        f"{suffix}: used {total_tokens} total tokens; limit is {limit}"
    )


def record_llm_token_usage(
    response: Any,
    *,
    request_kind: Optional[str] = None,
) -> LLMTokenUsage:
    """Record one LLM response against the current single-turn token scope."""

    usage = extract_llm_token_usage(response)
    if usage.total_tokens <= 0:
        return usage

    state = _token_usage_state.get()
    if state is None:
        limit = _configured_limit()
        if limit is not None:
            _raise_if_limit_exceeded(
                total_tokens=usage.total_tokens,
                limit=limit,
                request_kind=request_kind,
            )
        return usage

    state.add(usage)
    if state.limit is not None:
        _raise_if_limit_exceeded(
            total_tokens=state.total_tokens,
            limit=state.limit,
            request_kind=request_kind,
        )
    return usage
