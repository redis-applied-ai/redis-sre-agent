"""Helpers for guarding outbound LLM request text with PII remediation."""

from __future__ import annotations

import copy
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from langchain_core.messages import BaseMessage, HumanMessage

from redis_sre_agent.core.config import settings
from redis_sre_agent.core.pii_remediation import (
    PIIFinding,
    PIIRemediationDecision,
    PIIRemediationMode,
    PIIRemediationRequest,
    PIIRemediationResult,
    PIITextBlock,
    get_pii_remediator,
    is_pii_remediation_enabled,
)
from redis_sre_agent.observability.pii_remediation_metrics import (
    decision_value,
    record_pii_remediation_metrics,
)

logger = logging.getLogger(__name__)

GuardableMessage = BaseMessage | dict[str, Any]
GuardablePayload = str | BaseMessage | Sequence[GuardableMessage]
GuardedPayload = str | BaseMessage | List[GuardableMessage]


class PIIRemediationError(RuntimeError):
    """Base exception for request-guard failures."""


class PIIRemediationBlockedError(PIIRemediationError):
    """Raised when remediation policy blocks an outbound request."""


class GuardedMemoizeLLMProxy:
    """Proxy that preserves guarded outbound calls when passed through memoizers."""

    _sre_guarded_memoize_proxy = True

    def __init__(
        self,
        inner_llm: Any,
        *,
        request_kind: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._inner_llm = inner_llm
        self._request_kind = request_kind
        self._metadata = metadata or {}

    async def ainvoke(self, messages):
        return await guarded_ainvoke(
            self._inner_llm,
            messages,
            request_kind=self._request_kind,
            metadata=self._metadata,
        )

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner_llm, name)


@dataclass(frozen=True)
class _BlockLocation:
    block_id: str
    container: str
    indexes: Tuple[int, ...]
    role: str
    path: str


def _mode() -> PIIRemediationMode:
    raw = str(settings.pii_remediation_mode or "").strip().lower()
    try:
        return PIIRemediationMode(raw)
    except ValueError:
        return PIIRemediationMode.OFF


def _text_part_value(part: Any) -> Optional[str]:
    if isinstance(part, dict):
        if part.get("type") == "text" and isinstance(part.get("text"), str):
            return part["text"]
        if isinstance(part.get("content"), str):
            return part["content"]
    return None


def _is_dict_message_sequence(payload: Any) -> bool:
    return (
        bool(payload)
        and isinstance(payload, Sequence)
        and not isinstance(payload, (str, bytes))
        and all(isinstance(message, dict) for message in payload)
    )


def _iter_langchain_blocks(
    messages: Sequence[Any],
) -> tuple[List[PIITextBlock], List[_BlockLocation]]:
    blocks: List[PIITextBlock] = []
    locations: List[_BlockLocation] = []
    for idx, message in enumerate(messages):
        if isinstance(message, dict):
            role = str(message.get("role") or "user")
            content = message.get("content")
        else:
            role = getattr(message, "type", None) or message.__class__.__name__.lower()
            content = getattr(message, "content", None)
        if isinstance(content, str):
            block_id = f"lc:{idx}"
            blocks.append(
                PIITextBlock(
                    block_id=block_id,
                    path=f"messages[{idx}].content",
                    role=role,
                    text=content,
                )
            )
            locations.append(
                _BlockLocation(
                    block_id=block_id,
                    container="langchain_str",
                    indexes=(idx,),
                    role=role,
                    path=f"messages[{idx}].content",
                )
            )
        elif isinstance(content, list):
            for part_idx, part in enumerate(content):
                text = _text_part_value(part)
                if text is None:
                    continue
                block_id = f"lc:{idx}:{part_idx}"
                blocks.append(
                    PIITextBlock(
                        block_id=block_id,
                        path=f"messages[{idx}].content[{part_idx}].text",
                        role=role,
                        text=text,
                    )
                )
                locations.append(
                    _BlockLocation(
                        block_id=block_id,
                        container="langchain_part",
                        indexes=(idx, part_idx),
                        role=role,
                        path=f"messages[{idx}].content[{part_idx}].text",
                    )
                )
    return blocks, locations


def _iter_openai_blocks(
    messages: Sequence[dict[str, Any]],
) -> tuple[List[PIITextBlock], List[_BlockLocation]]:
    blocks: List[PIITextBlock] = []
    locations: List[_BlockLocation] = []
    for idx, message in enumerate(messages):
        role = str(message.get("role") or "user")
        content = message.get("content")
        if isinstance(content, str):
            block_id = f"oa:{idx}"
            blocks.append(
                PIITextBlock(
                    block_id=block_id,
                    path=f"messages[{idx}].content",
                    role=role,
                    text=content,
                )
            )
            locations.append(
                _BlockLocation(
                    block_id=block_id,
                    container="openai_str",
                    indexes=(idx,),
                    role=role,
                    path=f"messages[{idx}].content",
                )
            )
        elif isinstance(content, list):
            for part_idx, part in enumerate(content):
                text = _text_part_value(part)
                if text is None:
                    continue
                block_id = f"oa:{idx}:{part_idx}"
                blocks.append(
                    PIITextBlock(
                        block_id=block_id,
                        path=f"messages[{idx}].content[{part_idx}].text",
                        role=role,
                        text=text,
                    )
                )
                locations.append(
                    _BlockLocation(
                        block_id=block_id,
                        container="openai_part",
                        indexes=(idx, part_idx),
                        role=role,
                        path=f"messages[{idx}].content[{part_idx}].text",
                    )
                )
    return blocks, locations


def _render_langchain_messages(
    messages: Sequence[Any],
    locations: Sequence[_BlockLocation],
    blocks_by_id: Dict[str, PIITextBlock],
) -> List[Any]:
    rendered: List[Any] = []
    part_updates: Dict[tuple[int, int], str] = {}
    string_updates: Dict[int, str] = {}

    for location in locations:
        block = blocks_by_id.get(location.block_id)
        if block is None:
            continue
        if location.container == "langchain_str":
            string_updates[location.indexes[0]] = block.text
        elif location.container == "langchain_part":
            part_updates[(location.indexes[0], location.indexes[1])] = block.text

    for idx, message in enumerate(messages):
        content = getattr(message, "content", None)
        if isinstance(message, dict):
            content = message.get("content")
        if idx in string_updates:
            if isinstance(message, dict):
                new_message = copy.deepcopy(message)
                new_message["content"] = string_updates[idx]
                rendered.append(new_message)
            else:
                rendered.append(message.model_copy(update={"content": string_updates[idx]}))
            continue
        if isinstance(content, list):
            new_content = copy.deepcopy(content)
            for part_idx, part in enumerate(new_content):
                key = (idx, part_idx)
                if key not in part_updates or not isinstance(part, dict):
                    continue
                if part.get("type") == "text":
                    part["text"] = part_updates[key]
                elif "content" in part and isinstance(part["content"], str):
                    part["content"] = part_updates[key]
            if isinstance(message, dict):
                new_message = copy.deepcopy(message)
                new_message["content"] = new_content
                rendered.append(new_message)
            else:
                rendered.append(message.model_copy(update={"content": new_content}))
            continue
        rendered.append(message)
    return rendered


def _render_openai_messages(
    messages: Sequence[dict[str, Any]],
    locations: Sequence[_BlockLocation],
    blocks_by_id: Dict[str, PIITextBlock],
) -> List[dict[str, Any]]:
    rendered = copy.deepcopy(list(messages))
    for location in locations:
        block = blocks_by_id.get(location.block_id)
        if block is None:
            continue
        msg_index = location.indexes[0]
        if location.container == "openai_str":
            rendered[msg_index]["content"] = block.text
        elif location.container == "openai_part":
            part_index = location.indexes[1]
            part = rendered[msg_index]["content"][part_index]
            if part.get("type") == "text":
                part["text"] = block.text
            elif "content" in part and isinstance(part["content"], str):
                part["content"] = block.text
    return rendered


def _apply_guard_failure(mode: PIIRemediationMode, exc: Exception) -> None:
    if mode == PIIRemediationMode.DETECT:
        return
    if mode == PIIRemediationMode.REDACT and settings.pii_remediation_fail_open_for_redact:
        return
    raise PIIRemediationError(str(exc)) from exc


def _bounded_blocks(blocks: Iterable[PIITextBlock]) -> tuple[List[PIITextBlock], Dict[str, str]]:
    bounded: List[PIITextBlock] = []
    truncated_suffixes: Dict[str, str] = {}
    for block in blocks:
        text = block.text or ""
        if len(text) > settings.pii_remediation_max_chars:
            truncated_suffixes[block.block_id] = text[settings.pii_remediation_max_chars :]
            bounded.append(
                block.model_copy(update={"text": text[: settings.pii_remediation_max_chars]})
            )
        else:
            bounded.append(block)
    return bounded, truncated_suffixes


def _truncation_findings(
    blocks: Sequence[PIITextBlock],
    truncated_suffixes: Dict[str, str],
) -> List[PIIFinding]:
    return [
        PIIFinding(
            category="truncated_input",
            block_id=block.block_id,
            metadata={"truncated_chars": len(truncated_suffixes[block.block_id])},
        )
        for block in blocks
        if block.block_id in truncated_suffixes
    ]


async def _run_remediation(
    blocks: Sequence[PIITextBlock],
    *,
    mode: PIIRemediationMode,
    request_kind: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> PIIRemediationResult:
    bounded_blocks, truncated_suffixes = _bounded_blocks(blocks)
    started = time.perf_counter()
    if truncated_suffixes:
        findings = _truncation_findings(blocks, truncated_suffixes)
        reason = (
            "PII remediation skipped because one or more text blocks exceeded "
            f"pii_remediation_max_chars={settings.pii_remediation_max_chars}"
        )
        allow_truncated = mode == PIIRemediationMode.DETECT or (
            mode == PIIRemediationMode.REDACT and settings.pii_remediation_fail_open_for_redact
        )
        decision = (
            PIIRemediationDecision.ALLOW if allow_truncated else PIIRemediationDecision.BLOCKED
        )
        record_pii_remediation_metrics(
            request_kind=request_kind,
            mode=mode.value,
            decision=decision_value(decision),
            findings=findings,
            start_time=started,
            detector_name="guard",
            changed_text=False,
            status="truncated",
        )
        logger.warning(
            "%s for %s mode=%s truncated_blocks=%d",
            reason,
            request_kind,
            mode.value,
            len(truncated_suffixes),
        )
        if allow_truncated:
            return PIIRemediationResult(
                decision=PIIRemediationDecision.ALLOW,
                blocks=list(blocks),
                findings=findings,
                detector_name="guard",
                reason=reason,
            )
        if mode == PIIRemediationMode.BLOCK:
            raise PIIRemediationBlockedError(reason)
        raise PIIRemediationError(reason)

    try:
        result = await get_pii_remediator().remediate(
            PIIRemediationRequest(
                mode=mode,
                request_kind=request_kind,
                blocks=bounded_blocks,
                categories=list(settings.pii_remediation_categories),
                metadata=metadata or {},
            )
        )
    except Exception as exc:
        record_pii_remediation_metrics(
            request_kind=request_kind,
            mode=mode.value,
            decision="error",
            findings=[],
            start_time=started,
            status="error",
        )
        logger.warning(
            "PII remediation failed for %s mode=%s: %s",
            request_kind,
            mode.value,
            exc,
        )
        _apply_guard_failure(mode, exc)
        return PIIRemediationResult(
            decision=PIIRemediationDecision.ALLOW,
            blocks=list(blocks),
            detector_name="guard",
            reason=str(exc),
        )

    changed_text = result.decision == PIIRemediationDecision.REDACTED
    record_pii_remediation_metrics(
        request_kind=request_kind,
        mode=mode.value,
        decision=decision_value(result.decision),
        findings=result.findings,
        start_time=started,
        detector_name=result.detector_name,
        detector_model=result.detector_model,
        changed_text=changed_text,
    )
    logger.info(
        "PII remediation request_kind=%s mode=%s decision=%s findings=%d categories=%s detector=%s model=%s changed_text=%s",
        request_kind,
        mode.value,
        decision_value(result.decision),
        len(result.findings),
        sorted({finding.category for finding in result.findings}),
        result.detector_name,
        result.detector_model,
        changed_text,
    )
    return result


async def guard_langchain_input(
    payload: GuardablePayload,
    *,
    request_kind: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> GuardedPayload:
    """Return a guarded LangChain payload with PII remediation applied."""

    mode = _mode()
    if not is_pii_remediation_enabled(mode.value):
        return list(payload) if isinstance(payload, list) else payload

    if _is_dict_message_sequence(payload):
        return await guard_openai_chat_messages(
            payload,
            request_kind=request_kind,
            metadata=metadata,
        )

    if isinstance(payload, str):
        original_messages: List[BaseMessage] = [HumanMessage(content=payload)]
        restore = "string"
    elif isinstance(payload, BaseMessage):
        original_messages = [payload]
        restore = "message"
    else:
        original_messages = list(payload)
        restore = "messages"

    blocks, locations = _iter_langchain_blocks(original_messages)
    if not blocks:
        return list(payload) if isinstance(payload, list) else payload

    result = await _run_remediation(
        blocks,
        mode=mode,
        request_kind=request_kind,
        metadata=metadata,
    )

    if result.decision == PIIRemediationDecision.BLOCKED:
        raise PIIRemediationBlockedError(result.reason or "PII remediation blocked request")

    if result.decision == PIIRemediationDecision.ALLOW:
        return list(payload) if isinstance(payload, list) else payload

    rendered = _render_langchain_messages(
        original_messages,
        locations,
        {block.block_id: block for block in result.blocks},
    )
    if restore == "string":
        return str(rendered[0].content or "")
    if restore == "message":
        return rendered[0]
    return rendered


async def guard_openai_chat_messages(
    messages: Sequence[dict[str, Any]],
    *,
    request_kind: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> List[dict[str, Any]]:
    """Return guarded OpenAI chat-completions messages."""

    mode = _mode()
    original = list(messages)
    if not is_pii_remediation_enabled(mode.value):
        return copy.deepcopy(original)

    blocks, locations = _iter_openai_blocks(original)
    if not blocks:
        return copy.deepcopy(original)

    result = await _run_remediation(
        blocks,
        mode=mode,
        request_kind=request_kind,
        metadata=metadata,
    )

    if result.decision == PIIRemediationDecision.BLOCKED:
        raise PIIRemediationBlockedError(result.reason or "PII remediation blocked request")

    if result.decision == PIIRemediationDecision.ALLOW:
        return copy.deepcopy(original)

    return _render_openai_messages(
        original, locations, {block.block_id: block for block in result.blocks}
    )


async def guarded_ainvoke(
    llm: Any,
    payload: GuardablePayload,
    *,
    request_kind: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> Any:
    """Guard outbound text before calling a LangChain LLM."""

    guarded_payload = await guard_langchain_input(
        payload,
        request_kind=request_kind,
        metadata=metadata,
    )
    return await llm.ainvoke(guarded_payload)


async def guarded_chat_completions_create(
    client: Any,
    *,
    model: str,
    messages: Sequence[dict[str, Any]],
    request_kind: str,
    metadata: Optional[Dict[str, Any]] = None,
    **kwargs: Any,
) -> Any:
    """Guard outbound text before calling the OpenAI chat-completions API."""

    guarded_messages = await guard_openai_chat_messages(
        messages,
        request_kind=request_kind,
        metadata=metadata,
    )
    return await client.chat.completions.create(model=model, messages=guarded_messages, **kwargs)
