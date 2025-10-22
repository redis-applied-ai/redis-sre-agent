"""
Reducer utilities for merging per-problem plans and producing ordered summaries.

Exported helper:
- reduce_plans(per_problem_results, leftover_problems) -> tuple
  Returns:
    merged_actions, per_problem_results_sorted, skipped_lines,
    initial_assessment_lines, what_im_seeing_lines
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Tuple


def _severity_key(p: Dict[str, Any]) -> int:
    s = (p.get("problem", {}).get("severity") or "medium").lower()
    return {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(s, 2)


def _dedupe_actions(per_problem_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    merged: List[Dict[str, Any]] = []
    seen = set()
    for r in per_problem_results:
        for a in r.get("actions") or []:
            try:
                ident = f"{a.get('target')}|{a.get('verb')}|{json.dumps(a.get('args', {}), sort_keys=True)}"
            except Exception:
                ident = f"{a.get('target')}|{a.get('verb')}"
            if ident not in seen:
                seen.add(ident)
                merged.append(a)
    return merged


def reduce_plans(
    per_problem_results: List[Dict[str, Any]], leftover_problems: List[Dict[str, Any]]
) -> Tuple[
    List[Dict[str, Any]],  # merged_actions
    List[Dict[str, Any]],  # per_problem_results_sorted
    List[str],  # skipped_lines
    List[str],  # initial_assessment_lines
    List[str],  # what_im_seeing_lines
]:
    # Dedupe
    merged_actions = _dedupe_actions(per_problem_results)

    # Order problems by severity
    per_problem_results_sorted = sorted(per_problem_results or [], key=_severity_key)

    # Build skipped list for leftover problems
    skipped_lines: List[str] = []
    for sp in leftover_problems or []:
        title = sp.get("title") or sp.get("category") or "Problem"
        sev = sp.get("severity") or "medium"
        skipped_lines.append(f"- {title} (severity: {sev})")

    # Initial assessment and what I'm seeing sections
    initial_assessment_lines: List[str] = []
    for r in per_problem_results_sorted:
        p = r.get("problem", {})
        initial_assessment_lines.append(
            f"- {p.get('title') or p.get('category')} (severity: {p.get('severity', 'medium')})"
        )

    what_im_seeing_lines: List[str] = []
    for r in per_problem_results_sorted:
        p = r.get("problem", {})
        what_im_seeing_lines.append(
            f"- {p.get('title') or p.get('category')}: {r.get('summary') or ''}"
        )

    return (
        merged_actions,
        per_problem_results_sorted,
        skipped_lines,
        initial_assessment_lines,
        what_im_seeing_lines,
    )
