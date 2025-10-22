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
