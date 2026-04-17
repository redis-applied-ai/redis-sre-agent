"""Compatibility exports for eval injection overrides."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from redis_sre_agent.evaluation.injection import (
    EvalKnowledgeBackend,
    EvalMCPRuntime,
    EvalMCPServerConfigs,
    EvalRuntimeOverrides,
    EvalToolDispatchResult,
    EvalToolRuntime,
    eval_injection_scope,
    get_eval_runtime_overrides,
)


def get_current_eval_runtime_overrides() -> EvalRuntimeOverrides | None:
    """Return the current eval overrides bundle."""

    return get_eval_runtime_overrides()


@contextmanager
def use_eval_runtime_overrides(
    overrides: EvalRuntimeOverrides,
) -> Iterator[EvalRuntimeOverrides]:
    """Apply a prebuilt eval overrides object for the current context."""

    with eval_injection_scope(
        knowledge_backend=overrides.knowledge_backend,
        mcp_servers=overrides.mcp_servers,
        mcp_runtime=overrides.mcp_runtime,
        tool_runtime=overrides.tool_runtime,
    ):
        yield overrides


__all__ = [
    "EvalKnowledgeBackend",
    "EvalMCPServerConfigs",
    "EvalMCPRuntime",
    "EvalRuntimeOverrides",
    "EvalToolDispatchResult",
    "EvalToolRuntime",
    "get_current_eval_runtime_overrides",
    "use_eval_runtime_overrides",
]
