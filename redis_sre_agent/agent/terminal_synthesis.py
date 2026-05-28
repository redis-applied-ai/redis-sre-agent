"""Shared helpers for producing terminal answers from captured agent state."""

import json
import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage

from .helpers import coerce_response_text

GuardedInvoke = Callable[..., Awaitable[Any]]
FailureResponseFactory = Callable[[], str]
ExceptionFormatter = Callable[[Exception], str]


@dataclass(frozen=True)
class TerminalSynthesisConfig:
    """Formatting and request settings for terminal response synthesis."""

    request_kind: str
    system_prompt: str
    messages_heading: str
    evidence_heading: str
    no_messages_text: str
    no_evidence_text: str
    failure_log_message: str
    empty_log_message: str
    context_limit: int
    item_limit: int
    message_item_limit: int
    message_tail_limit: int
    evidence_tail_limit: int = 8
    include_system_messages: bool = True
    detailed_message_headers: bool = False
    empty_message_text: str | None = None
    message_omitted_unit: str = "conversation message(s)"
    evidence_omitted_unit: str = "tool result envelope(s)"


def describe_captured_state(
    *,
    messages: Sequence[BaseMessage],
    tool_envelopes: Sequence[dict[str, Any]],
) -> str:
    gathered: list[str] = []
    if messages:
        gathered.append(f"{len(messages)} conversation message(s)")
    if tool_envelopes:
        gathered.append(f"{len(tool_envelopes)} tool result envelope(s)")
    return ", ".join(gathered) if gathered else "no usable intermediate state"


def truncate_terminal_synthesis_text(value: Any, max_chars: int) -> str:
    text = coerce_response_text(value)
    if not text:
        text = str(value)
    if len(text) <= max_chars:
        return text
    omitted = len(text) - max_chars
    return f"{text[:max_chars].rstrip()}\n... [truncated {omitted} chars]"


def _message_tool_call_names(message: BaseMessage) -> list[str]:
    tool_calls = getattr(message, "tool_calls", None) or []
    tool_names: list[str] = []
    for tool_call in tool_calls:
        if isinstance(tool_call, dict):
            name = tool_call.get("name")
        else:
            name = getattr(tool_call, "name", None)
        if name:
            tool_names.append(str(name))
    return tool_names


def _format_terminal_message(message: BaseMessage, config: TerminalSynthesisConfig) -> str:
    role = getattr(message, "type", None) or message.__class__.__name__
    content = coerce_response_text(getattr(message, "content", None))
    if not content and isinstance(message, AIMessage) and getattr(message, "tool_calls", None):
        content = json.dumps(message.tool_calls, default=str, sort_keys=True)
    if not content and config.empty_message_text is not None:
        content = config.empty_message_text

    if not config.detailed_message_headers:
        return f"{role}: {truncate_terminal_synthesis_text(content, config.message_item_limit)}"

    header = str(role)
    tool_names = _message_tool_call_names(message)
    if tool_names:
        header = f"{header} requested tools: {', '.join(tool_names)}"

    tool_name = getattr(message, "name", None)
    if isinstance(message, ToolMessage) and tool_name:
        header = f"{header} ({tool_name})"

    return f"{header}:\n{truncate_terminal_synthesis_text(content, config.message_item_limit)}"


def format_terminal_synthesis_messages(
    messages: Sequence[BaseMessage],
    config: TerminalSynthesisConfig,
) -> str:
    visible_messages = list(messages)
    if not config.include_system_messages:
        visible_messages = [
            message for message in visible_messages if not isinstance(message, SystemMessage)
        ]
    if not visible_messages:
        return config.no_messages_text

    selected_messages = visible_messages[-config.message_tail_limit :]
    omitted_count = len(visible_messages) - len(selected_messages)
    lines: list[str] = []
    if omitted_count > 0:
        lines.append(f"... [{omitted_count} earlier {config.message_omitted_unit} omitted]")

    lines.extend(_format_terminal_message(message, config) for message in selected_messages)
    return truncate_terminal_synthesis_text("\n\n".join(lines), config.context_limit)


def format_terminal_synthesis_tool_evidence(
    tool_envelopes: Sequence[dict[str, Any]],
    config: TerminalSynthesisConfig,
) -> str:
    if not tool_envelopes:
        return config.no_evidence_text

    selected_envelopes = list(tool_envelopes)[-config.evidence_tail_limit :]
    omitted_count = len(tool_envelopes) - len(selected_envelopes)
    lines: list[str] = []
    if omitted_count > 0:
        lines.append(f"... [{omitted_count} earlier {config.evidence_omitted_unit} omitted]")

    for envelope in selected_envelopes:
        tool_key = envelope.get("tool_key") or envelope.get("name") or "unknown_tool"
        summary = envelope.get("summary")
        if summary:
            payload = str(summary)
        else:
            payload = json.dumps(envelope.get("data", {}), default=str, sort_keys=True)
        lines.append(f"{tool_key}:\n{truncate_terminal_synthesis_text(payload, config.item_limit)}")

    return truncate_terminal_synthesis_text("\n\n".join(lines), config.context_limit)


async def synthesize_terminal_response(
    llm: Any,
    *,
    config: TerminalSynthesisConfig,
    messages: Sequence[BaseMessage],
    tool_envelopes: Sequence[dict[str, Any]],
    guarded_invoke: GuardedInvoke,
    failure_response_factory: FailureResponseFactory,
    logger: logging.Logger,
    human_prelude: str | None = None,
    format_exception: ExceptionFormatter = str,
) -> str:
    human_sections = []
    if human_prelude:
        human_sections.append(human_prelude)
    human_sections.extend(
        [
            f"{config.messages_heading}:\n{format_terminal_synthesis_messages(messages, config)}",
            (
                f"{config.evidence_heading}:\n"
                f"{format_terminal_synthesis_tool_evidence(tool_envelopes, config)}"
            ),
        ]
    )
    synthesis_messages: list[BaseMessage] = [
        SystemMessage(content=config.system_prompt),
        HumanMessage(content="\n\n".join(human_sections)),
    ]

    try:
        synthesized = await guarded_invoke(
            llm,
            synthesis_messages,
            request_kind=config.request_kind,
        )
    except Exception as exc:
        logger.warning(
            config.failure_log_message,
            format_exception(exc),
            exc_info=True,
        )
        return failure_response_factory()

    response_text = coerce_response_text(getattr(synthesized, "content", ""))
    if response_text:
        return response_text

    logger.warning(config.empty_log_message)
    return failure_response_factory()
