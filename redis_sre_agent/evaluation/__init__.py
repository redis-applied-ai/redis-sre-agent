"""Redis SRE Agent Evaluation Suite."""

from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
    "EvalFullTurnResult",
    "EvalRunResult",
    "EvalRuntime",
    "EvalRunner",
    "build_full_turn_context",
    "load_eval_scenario",
    "run_full_turn_scenario",
]


def __getattr__(name: str) -> Any:
    """Load evaluation entrypoints lazily to keep submodules independently importable."""

    if name == "EvalRunner":
        return getattr(import_module("redis_sre_agent.evaluation.runner"), name)
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
