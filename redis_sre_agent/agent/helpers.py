"""
Helper utilities for the SRE LangGraph agent.
Separated from langgraph_agent.py to reduce duplication and improve testability.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import jmespath
from jmespath.exceptions import JMESPathError
from langchain_core.messages import AIMessage

KNOWLEDGE_SEARCH_RETRIEVAL_KIND = "knowledge_search"
KNOWLEDGE_SEARCH_RETRIEVAL_LABEL = "Knowledge search"
STARTUP_CONTEXT_CITATION_GROUP = "startup_context_loaded"
STARTUP_CONTEXT_CITATION_GROUP_LABEL = "Startup context loaded"
DISCOVERED_CONTEXT_CITATION_GROUP = "discovered_context"
DISCOVERED_CONTEXT_CITATION_GROUP_LABEL = "Discovered context"


def coerce_response_text(content: Any) -> str:
    """Normalize structured model output into a non-empty text response."""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str) and text.strip():
                    parts.append(text.strip())
            elif isinstance(item, str) and item.strip():
                parts.append(item.strip())
        return "\n".join(parts).strip()
    if content is None:
        return ""
    return str(content).strip()


def extract_last_ai_response(messages: List[Any]) -> str:
    """Return the last non-empty AI message content from a transcript."""
    for message in reversed(messages):
        if isinstance(message, AIMessage):
            candidate = coerce_response_text(getattr(message, "content", None))
            if candidate:
                return candidate
    return ""


def parse_json_maybe_fenced(text: str) -> Any:
    """Parse JSON that may be wrapped in markdown code fences (``` or ```json).

    Raises json.JSONDecodeError if parsing fails.
    """
    s = (text or "").strip()
    if s.startswith("```"):
        s = s.strip("` \n")
        if s.lower().startswith("json\n"):
            s = s[5:]
    return json.loads(s)


def summarize_signals(sig: Dict[str, Any], max_items: int = 8) -> str:
    """Create a compact summary string of signals for prompting.
    Mirrors the previous inline implementation to preserve behavior.
    """
    lines: List[str] = []
    for i, (k, v) in enumerate(sig.items()):
        if i >= max_items:
            lines.append("- … (truncated)")
            break
        if isinstance(v, dict):
            # Keep small JSON fragments; avoid giant dumps
            try:
                snippet = json.dumps(v, default=str)
                if len(snippet) > 1200:
                    snippet = snippet[:1200] + ""
            except Exception:
                snippet = str(v)[:1200]
            lines.append(f"- {k}: {snippet}")
        else:
            lines.append(f"- {k}: {str(v)[:500]}")
    return "\n".join(lines) if lines else "- No tool signals captured"


def parse_tool_json_payload(payload: str) -> Optional[Any]:
    """Best-effort extraction of a JSON object embedded after a 'Result:' label.

    Returns parsed JSON or None.
    """
    try:
        # Try to find a JSON object after a 'Result:' label
        i = payload.find("Result:")
        if i >= 0:
            j = payload.find("{", i)
            if j >= 0:
                candidate = payload[j:]
                return json.loads(candidate)
    except Exception:
        return None
    return None


def sanitize_messages_for_llm(msgs: List[Any]) -> List[Any]:
    """Sanitize a chat transcript for LLM input.

    - Keep AI messages and record tool_call ids they requested
    - Keep only ToolMessages whose tool_call_id matches a prior AI tool_call id
    - Drop any leading ToolMessages (LLM providers reject tool-first histories)
    """
    if not msgs:
        return msgs
    try:
        # Import lazily to avoid hard dependency cycles for callers that don't use this
        from langchain_core.messages import AIMessage as _AI  # noqa: N814
        from langchain_core.messages import ToolMessage as _TM  # noqa: N814
    except Exception:
        # If langchain_core is unavailable in test contexts, pass-through
        return msgs

    seen_tool_ids = set()
    clean: List[Any] = []
    for m in msgs:
        if isinstance(m, _AI):
            try:
                for tc in m.tool_calls or []:
                    if isinstance(tc, dict):
                        tid = tc.get("id") or tc.get("tool_call_id")
                        if tid:
                            seen_tool_ids.add(tid)
            except Exception:
                pass
            clean.append(m)
        elif isinstance(m, _TM) or m.type == "tool":
            tid = m.tool_call_id
            if tid and tid in seen_tool_ids:
                clean.append(m)
            else:
                continue
        else:
            clean.append(m)
    while clean and (isinstance(clean[0], _TM) or clean[0].type == "tool"):
        clean = clean[1:]
    return clean


def _compact_messages_tail(msgs: List[Any], limit: int = 6) -> List[Dict[str, Any]]:
    """Return a compact representation of the last N messages for logging.

    Includes role, tool_call ids for AI messages, and tool_call_id/name for ToolMessages.
    Best-effort and resilient to missing dependencies.
    """
    try:
        from langchain_core.messages import AIMessage as _AI  # noqa: N814
        from langchain_core.messages import ToolMessage as _TM  # noqa: N814
    except Exception:
        _AI = None  # type: ignore  # noqa: N806
        _TM = None  # type: ignore  # noqa: N806

    tail = msgs[-limit:] if msgs else []
    compact: List[Dict[str, Any]] = []
    for m in tail:
        role = m.type if m.type else m.__class__.__name__.lower()
        row: Dict[str, Any] = {"role": role}
        try:
            is_ai = (_AI is not None and isinstance(m, _AI)) or m.type in (
                "ai",
                "assistant",
            )
            if is_ai:
                ids: List[str] = []
                for tc in m.tool_calls or []:
                    if isinstance(tc, dict):
                        tid = tc.get("id") or tc.get("tool_call_id")
                        if tid:
                            ids.append(tid)
                if ids:
                    row["tool_calls"] = ids
            is_tool = (_TM is not None and isinstance(m, _TM)) or m.type == "tool"
            if is_tool:
                row["tool_call_id"] = m.tool_call_id
                name = m.name
                if name:
                    row["name"] = name
        except Exception:
            pass
        compact.append(row)
    return compact


def log_preflight_messages(
    msgs: List[Any],
    *,
    label: str = "Preflight",
    note: Optional[str] = None,
    logger: Optional[Any] = None,
    limit: int = 6,
) -> None:
    """Log a compact tail of messages for LLM/ToolNode preflights.

    - label: human-friendly label to prefix (e.g., "RecWorker preflight LLM")
    - note: optional suffix in parentheses (e.g., attempt or phase name)
    - logger: defaults to this module's logger if not provided
    - limit: number of tail messages to include
    """
    try:
        import logging as _logging

        _logger = logger or _logging.getLogger(__name__)
        compact = _compact_messages_tail(msgs, limit=limit)
        head = f"{label}"
        if note:
            head = f"{head} ({note})"
        _logger.debug(f"{head} total={len(msgs)} tail={compact}")
    except Exception:
        # Never fail due to logging
        pass


def build_result_envelope(
    tool_name: str, tool_args: Dict[str, Any], tool_message: Any, tooldefs_by_name: Dict[str, Any]
) -> Dict[str, Any]:
    """Construct a ResultEnvelope dict from a tool call and corresponding ToolMessage.

    - Parses JSON from the ToolMessage content when possible, otherwise stores raw text (truncated)
    - Derives a short operation name from tool_name
    - Preserves the tool description from the tool definition if available
    """
    # Lazy imports to avoid cycles
    import json as _json

    from .models import ResultEnvelope

    content = tool_message.content
    data_obj = None
    if isinstance(content, str) and content:
        try:
            first_brace = content.find("{")
            if first_brace != -1:
                data_obj = _json.loads(content[first_brace:])
        except Exception:
            data_obj = None

    def _extract_operation_from_tool_name(full: str) -> str:
        # e.g., "knowledge.kb.search" -> "search"
        if not full:
            return "tool"
        parts = full.split(".")
        return parts[-1] if parts else full

    tdef = tooldefs_by_name.get(tool_name) if tool_name else None
    description = tdef.description if tdef else None
    raw_status = (
        str(data_obj.get("status")).lower()
        if isinstance(data_obj, dict) and data_obj.get("status") is not None
        else ""
    )
    envelope_status = "error" if raw_status in {"error", "failed", "failure"} else "success"
    env = ResultEnvelope(
        tool_key=tool_name or "tool",
        name=_extract_operation_from_tool_name(tool_name or "tool"),
        description=description,
        args=dict(tool_args or {}),
        status=envelope_status,
        data=data_obj if isinstance(data_obj, dict) else {"raw": (content or "")[:4000]},
    )
    return env.model_dump()


async def build_adapters_for_tooldefs(tool_manager: Any, tooldefs: List[Any]) -> list[Any]:
    """Create LangChain StructuredTool adapters for ToolDefinitions.

    Each adapter wraps :meth:`ToolManager.resolve_tool_call` so that tools can
    be executed either via LangGraph's :class:`ToolNode` or directly via the
    manager. The same adapters can also be passed to ``ChatOpenAI.bind_tools``
    so we do not need to maintain separate OpenAI-specific tool schemas.
    """

    try:
        from typing import Any as _Any

        from langchain_core.tools import StructuredTool as _StructuredTool
        from pydantic import BaseModel as _BaseModel
        from pydantic import ConfigDict as _ConfigDict
        from pydantic import Field as _Field
        from pydantic import create_model as _create_model
    except Exception:
        # Best-effort fallback (should not happen in runtime)
        return []

    def _field_default(spec: dict, is_required: bool):
        if is_required:
            return ...
        if "default" in (spec or {}):
            return spec.get("default")
        return None

    def _args_model_from_parameters(tool_name: str, params: dict) -> type[_BaseModel]:
        props = (params or {}).get("properties", {}) or {}
        required = set((params or {}).get("required", []) or [])
        fields: dict[str, tuple[_Any, _Any]] = {}
        for k, spec in props.items():
            default = _field_default(spec or {}, k in required)
            fields[k] = (
                _Any,
                _Field(default, description=(spec or {}).get("description")),
            )
        args_model = _create_model(f"{tool_name}_Args", __base__=_BaseModel, **fields)
        # allow extra to be resilient to provider-side schema drift
        try:
            args_model.model_config = _ConfigDict(extra="allow")  # type: ignore[attr-defined]
        except Exception:
            pass
        return args_model

    adapters: list[_StructuredTool] = []
    for tdef in tooldefs or []:

        async def _exec_fn(_name=tdef.name, **kwargs):
            from .tool_execution import execute_tool_call_with_gate

            return await execute_tool_call_with_gate(
                tool_manager=tool_manager,
                tool_name=_name,
                tool_args=kwargs or {},
            )

        args_model = _args_model_from_parameters(tdef.name, tdef.parameters or {})
        adapters.append(
            _StructuredTool.from_function(
                coroutine=_exec_fn,
                name=tdef.name,
                description=tdef.description or "",
                args_schema=args_model,
            )
        )
    return adapters


def extract_citations(envelopes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Extract citations from knowledge tool envelopes.

    Derives citation data from knowledge search tool results, replacing the
    separate CitationTrace tracking system. Citations are now stored as part
    of the tool envelope data, not as a separate model.

    Args:
        envelopes: List of ResultEnvelope dicts from tool executions.
            Each envelope should have tool_key, name, status, data fields.

    Returns:
        List of citation dicts extracted from knowledge tool results.
        Each citation preserves all fields from the original search result.
    """
    citations: List[Dict[str, Any]] = []

    for envelope in envelopes:
        tool_key = envelope.get("tool_key", "")
        name = str(envelope.get("name", ""))

        # Match knowledge search tools by tool_key containing "knowledge"
        if "knowledge" not in tool_key.lower():
            continue

        # Extract results from the data field
        data = envelope.get("data", {})
        if not isinstance(data, dict):
            continue

        results = data.get("results", [])
        if not isinstance(results, list):
            continue

        default_retrieval_kind = str(data.get("retrieval_kind", "")).strip()
        default_retrieval_label = str(data.get("retrieval_label", "")).strip()
        if not default_retrieval_kind:
            if "pinned_context" in tool_key.lower() or "pinned_context" in name.lower():
                default_retrieval_kind = "pinned_context"
                default_retrieval_label = default_retrieval_label or "Pinned context"
            elif "search" in tool_key.lower() or "search" in name.lower():
                default_retrieval_kind = KNOWLEDGE_SEARCH_RETRIEVAL_KIND
                default_retrieval_label = (
                    default_retrieval_label or KNOWLEDGE_SEARCH_RETRIEVAL_LABEL
                )

        # Add each result as a citation (preserving all fields)
        for result in results:
            if isinstance(result, dict):
                citation = dict(result)
                if default_retrieval_kind:
                    citation.setdefault("retrieval_kind", default_retrieval_kind)
                if default_retrieval_label:
                    citation.setdefault("retrieval_label", default_retrieval_label)
                citations.append(citation)

    return citations


def build_citation_groups(citations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Group citations into startup context and discovered context buckets."""
    grouped = {
        DISCOVERED_CONTEXT_CITATION_GROUP: {
            "group_key": DISCOVERED_CONTEXT_CITATION_GROUP,
            "label": DISCOVERED_CONTEXT_CITATION_GROUP_LABEL,
            "citations": [],
        },
        STARTUP_CONTEXT_CITATION_GROUP: {
            "group_key": STARTUP_CONTEXT_CITATION_GROUP,
            "label": STARTUP_CONTEXT_CITATION_GROUP_LABEL,
            "citations": [],
        },
    }

    for citation in citations or []:
        retrieval_kind = str(citation.get("retrieval_kind", "")).strip().lower()
        group_key = (
            STARTUP_CONTEXT_CITATION_GROUP
            if retrieval_kind == "pinned_context"
            else DISCOVERED_CONTEXT_CITATION_GROUP
        )
        grouped[group_key]["citations"].append(citation)

    ordered_groups: List[Dict[str, Any]] = []
    for group_key in (
        DISCOVERED_CONTEXT_CITATION_GROUP,
        STARTUP_CONTEXT_CITATION_GROUP,
    ):
        group = grouped[group_key]
        citations_for_group = list(group["citations"])
        if not citations_for_group:
            continue
        ordered_groups.append(
            {
                **group,
                "count": len(citations_for_group),
            }
        )

    return ordered_groups


def extract_citation_groups(envelopes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Extract and group citations from tool envelopes."""
    return build_citation_groups(extract_citations(envelopes))


def query_tool_data(envelopes: List[Dict[str, Any]], tool_key: str, query: str) -> Any:
    """Query data from a tool envelope using JMESPath expression.

    Finds the most recent envelope matching the tool_key and applies
    the JMESPath query to its data field.

    Args:
        envelopes: List of tool execution envelopes
        tool_key: The tool_key to find
        query: JMESPath expression to extract data

    Returns:
        Extracted data matching the query, or None if tool not found

    Raises:
        ValueError: If the JMESPath expression is invalid

    Example queries:
        - "memory.used_memory_human" - get a single field
        - "entries[:5]" - get first 5 items
        - "entries[?duration_us > `1000`]" - filter items
        - "entries[*].{cmd: command, dur: duration_us}" - project fields
    """

    # Find the most recent envelope with matching tool_key
    matching_envelope = None
    for envelope in envelopes:
        if envelope.get("tool_key") == tool_key:
            matching_envelope = envelope

    if matching_envelope is None:
        return None

    data = matching_envelope.get("data", {})

    try:
        return jmespath.search(query, data)
    except JMESPathError as e:
        raise ValueError(f"Invalid JMESPath expression '{query}': {e}") from e
