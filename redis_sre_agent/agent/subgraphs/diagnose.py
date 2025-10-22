"""
Diagnosis helper subgraph utilities.

Provides:
- make_diagnose_prompt(signals_summary): build the diagnosis prompt text
- parse_problems(text): robust JSON parsing and normalization to a list of ProblemSpec

This keeps the core agent lean and centralizes schema handling for problem specs.
"""

from __future__ import annotations

from typing import Any, Dict, List, TypedDict

from ..helpers import parse_json_maybe_fenced
from ..prompts import SRE_SYSTEM_PROMPT


class ProblemSpec(TypedDict, total=False):
    id: str
    category: str
    title: str
    severity: str
    scope: str
    evidence_keys: List[str]


ALLOWED_CATEGORIES = {
    "NodeInMaintenanceMode",
    "ReplicationMismatch",
    "MemoryPressure",
    "Performance",
    "Configuration",
    "Other",
}

ALLOWED_SEVERITY = {"critical", "high", "medium", "low"}


def make_diagnose_prompt(signals_summary: str) -> str:
    return f"""
{SRE_SYSTEM_PROMPT}

You are now in a diagnosis phase. Using ONLY the operational signals below, identify distinct problem areas.

Provide a strict JSON array where each item has:
- id: short stable id (e.g., "P1", "P2")
- category: one of ["NodeInMaintenanceMode","ReplicationMismatch","MemoryPressure","Performance","Configuration","Other"]
- title: concise human-readable label
- severity: one of ["critical","high","medium","low"]
- scope: e.g., "cluster","node:2","db:foo"
- evidence_keys: list of tool keys from signals that support this problem

Operational signals:
{signals_summary}
"""


def _normalize_problem(p: Dict[str, Any]) -> ProblemSpec | None:
    try:
        if not isinstance(p, dict):
            return None
        pid = str(p.get("id") or "").strip()
        cat = str(p.get("category") or "Other").strip()
        title = str(p.get("title") or cat or "Issue").strip()
        sev = str(p.get("severity") or "medium").strip().lower()
        scope = str(p.get("scope") or "cluster").strip()
        keys = p.get("evidence_keys")
        if not isinstance(keys, list):
            keys = []
        keys = [str(k) for k in keys if isinstance(k, (str, int))]

        if cat not in ALLOWED_CATEGORIES:
            cat = "Other"
        if sev not in ALLOWED_SEVERITY:
            sev = "medium"
        if not pid:
            return None

        return ProblemSpec(
            id=pid,
            category=cat,
            title=title,
            severity=sev,
            scope=scope,
            evidence_keys=keys,
        )
    except Exception:
        return None


def parse_problems(text: str) -> List[ProblemSpec]:
    """Parse a JSON array of ProblemSpec from raw LLM text, tolerating fenced JSON.

    Returns an empty list on failure.
    """
    try:
        data = parse_json_maybe_fenced(text)
        if not isinstance(data, list):
            return []
        out: List[ProblemSpec] = []
        for item in data:
            norm = _normalize_problem(item)
            if norm is not None:
                out.append(norm)
        return out
    except Exception:
        return []
