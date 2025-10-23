"""Plan reduction utilities used by tests.

This module provides a small, test-focused implementation for aggregating
per-problem plans into a merged action list and some helper summary sections.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Sequence, Tuple

_SEVERITY_ORDER = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
    "info": 4,
}


def _severity_rank(severity: str | None) -> int:
    if not severity:
        return 999
    return _SEVERITY_ORDER.get(str(severity).lower(), 999)


def _normalize_action(action: Dict[str, Any]) -> Tuple[Any, Any, Tuple[Tuple[str, Any], ...]]:
    """Return a hashable representation of an action for deduping.

    We consider target, verb, and args (as a sorted tuple of items). Other
    fields are ignored for deduplication.
    """
    target = action.get("target")
    verb = action.get("verb")
    args = action.get("args") or {}
    if isinstance(args, dict):
        args_items = tuple(sorted(args.items()))
    else:
        # Fallback for non-dict args – treat as-is but ensure hashable
        if isinstance(args, Iterable) and not isinstance(args, (str, bytes, bytearray)):
            args_items = tuple(args)  # best effort
        else:
            args_items = (("value", args),)
    return target, verb, args_items


def _dedupe_actions(per_problem_results: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    merged: List[Dict[str, Any]] = []
    for res in per_problem_results:
        for action in res.get("actions", []) or []:
            key = _normalize_action(action)
            if key in seen:
                continue
            seen.add(key)
            merged.append(action)
    return merged


def _sort_problems(per_problem_results: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(
        per_problem_results,
        key=lambda r: _severity_rank(((r.get("problem") or {}).get("severity"))),
    )


def reduce_plans(
    per_problem_results: Sequence[Dict[str, Any]],
    leftover_problems: Sequence[Dict[str, Any]] | None = None,
):
    """Reduce per-problem plans to a single actionable plan and helper sections.

    Returns:
        merged_actions: List of deduplicated actions across problems
        per_problem_results_sorted: Input problems sorted by severity
        skipped_lines: Lines describing leftover/unaddressed problems
        initial_assessment_lines: Lines for an initial assessment section
        what_im_seeing_lines: Lines summarizing observations per problem
    """
    leftover_problems = leftover_problems or []

    merged_actions = _dedupe_actions(per_problem_results)
    per_problem_results_sorted = _sort_problems(per_problem_results)

    # Skipped/leftover lines
    skipped_lines = []
    for p in leftover_problems:
        title = p.get("title") or (p.get("id") or "Unknown")
        sev = p.get("severity") or "unknown"
        skipped_lines.append(f"- {title} (severity: {sev})")

    # Initial assessment – mention title and severity
    initial_assessment_lines = []
    for r in per_problem_results_sorted:
        prob = r.get("problem") or {}
        title = prob.get("title") or (prob.get("id") or "Unknown")
        sev = prob.get("severity") or "unknown"
        initial_assessment_lines.append(f"- {title} (severity: {sev})")

    # What I'm seeing – include summary snippets
    what_im_seeing_lines = []
    for r in per_problem_results_sorted:
        prob = r.get("problem") or {}
        title = prob.get("title") or (prob.get("id") or "Unknown")
        summary = (r.get("summary") or "").strip()
        if summary:
            what_im_seeing_lines.append(f"- {title}: {summary}")
        else:
            what_im_seeing_lines.append(f"- {title}: (no summary)")

    return (
        merged_actions,
        per_problem_results_sorted,
        skipped_lines,
        initial_assessment_lines,
        what_im_seeing_lines,
    )
