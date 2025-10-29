"""
Helper utilities for the SRE LangGraph agent.
Separated from langgraph_agent.py to reduce duplication and improve testability.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional


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
                for tc in getattr(m, "tool_calls", []) or []:
                    if isinstance(tc, dict):
                        tid = tc.get("id") or tc.get("tool_call_id")
                        if tid:
                            seen_tool_ids.add(tid)
            except Exception:
                pass
            clean.append(m)
        elif isinstance(m, _TM) or getattr(m, "type", "") == "tool":
            tid = getattr(m, "tool_call_id", None)
            if tid and tid in seen_tool_ids:
                clean.append(m)
            else:
                continue
        else:
            clean.append(m)
    while clean and (isinstance(clean[0], _TM) or getattr(clean[0], "type", "") == "tool"):
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
        role = getattr(m, "type", m.__class__.__name__.lower())
        row: Dict[str, Any] = {"role": role}
        try:
            is_ai = (_AI is not None and isinstance(m, _AI)) or getattr(m, "type", "") in (
                "ai",
                "assistant",
            )
            if is_ai:
                ids: List[str] = []
                for tc in getattr(m, "tool_calls", []) or []:
                    if isinstance(tc, dict):
                        tid = tc.get("id") or tc.get("tool_call_id")
                        if tid:
                            ids.append(tid)
                if ids:
                    row["tool_calls"] = ids
            is_tool = (_TM is not None and isinstance(m, _TM)) or getattr(m, "type", "") == "tool"
            if is_tool:
                row["tool_call_id"] = getattr(m, "tool_call_id", None)
                name = getattr(m, "name", None)
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
        _logger.info(f"{head} total={len(msgs)} tail={compact}")
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

    content = getattr(tool_message, "content", None)
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

    description = (
        getattr(tooldefs_by_name.get(tool_name), "description", None) if tool_name else None
    )
    env = ResultEnvelope(
        tool_key=tool_name or "tool",
        name=_extract_operation_from_tool_name(tool_name or "tool"),
        description=description,
        args=dict(tool_args or {}),
        status="success",
        data=data_obj if isinstance(data_obj, dict) else {"raw": (content or "")[:4000]},
    )
    return env.model_dump()


async def build_adapters_for_tooldefs(
    tool_manager: Any, tooldefs: List[Any]
) -> tuple[list[dict], list[Any]]:
    """Create OpenAI tool schemas and LangChain StructuredTool adapters for ToolDefinitions.

    Returns (tool_schemas, adapters)
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
        return [], []

    def _args_model_from_parameters(tool_name: str, params: dict) -> type[_BaseModel]:
        props = (params or {}).get("properties", {}) or {}
        required = set((params or {}).get("required", []) or [])
        fields: dict[str, tuple[_Any, _Any]] = {}
        for k, spec in props.items():
            default = ... if k in required else None
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

    tool_schemas: list[dict] = [t.to_openai_schema() for t in (tooldefs or [])]
    adapters: list[_StructuredTool] = []
    for tdef in tooldefs or []:

        async def _exec_fn(_name=tdef.name, **kwargs):
            return await tool_manager.resolve_tool_call(_name, kwargs or {})

        ArgsModel = _args_model_from_parameters(tdef.name, getattr(tdef, "parameters", {}) or {})  # noqa: N806
        adapters.append(
            _StructuredTool.from_function(
                coroutine=_exec_fn,
                name=tdef.name,
                description=getattr(tdef, "description", "") or "",
                args_schema=ArgsModel,
            )
        )
    return tool_schemas, adapters
