"""Redis SRE Agent Evaluation Suite."""

from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
    "EvalFullTurnResult",
    "EvalLiveSuite",
    "EvalRunResult",
    "EvalRuntime",
    "EvalRunner",
    "LiveEvalComparisonSummary",
    "LiveEvalSuiteConfig",
    "LiveEvalSuiteDefinition",
    "LiveEvalSuiteSummary",
    "build_full_turn_context",
    "compare_live_eval_reports",
    "load_baseline_policy",
    "load_eval_scenario",
    "live_eval_git_sha",
    "normalize_agent_response_payload",
    "resolve_live_eval_trigger",
    "run_live_eval_suite",
    "run_full_turn_scenario",
    "validate_live_eval_trigger",
]


def __getattr__(name: str) -> Any:
    """Load evaluation entrypoints lazily to keep submodules independently importable."""

    if name == "EvalRunner":
        return getattr(import_module("redis_sre_agent.evaluation.runner"), name)
    if name in {
        "EvalLiveSuite",
        "LiveEvalComparisonSummary",
        "LiveEvalSuiteConfig",
        "LiveEvalSuiteDefinition",
        "LiveEvalSuiteSummary",
        "compare_live_eval_reports",
        "load_baseline_policy",
        "live_eval_git_sha",
        "normalize_agent_response_payload",
        "resolve_live_eval_trigger",
        "run_live_eval_suite",
        "validate_live_eval_trigger",
    }:
        return getattr(import_module("redis_sre_agent.evaluation.live_suite"), name)
    if name in {
        "EvalFullTurnResult",
        "EvalRunResult",
        "EvalRuntime",
        "build_full_turn_context",
        "load_eval_scenario",
        "run_full_turn_scenario",
    }:
        return getattr(import_module("redis_sre_agent.evaluation.runtime"), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
