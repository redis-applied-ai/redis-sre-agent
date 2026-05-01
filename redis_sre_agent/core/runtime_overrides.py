"""Context-scoped runtime overrides shared by production and eval code."""

from __future__ import annotations

import inspect
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Iterator, Mapping, Optional, Protocol, runtime_checkable

from redis_sre_agent.core.config import MCPServerConfig


@runtime_checkable
class EvalKnowledgeBackend(Protocol):
    """Protocol for eval-only knowledge backend overrides."""

    async def search_knowledge_base(
        self,
        *,
        query: str,
        category: Optional[str] = None,
        doc_type: Optional[str] = None,
        limit: int = 10,
        offset: int = 0,
        distance_threshold: Optional[float] = 0.8,
        hybrid_search: bool = False,
        version: Optional[str] = "latest",
        index_type: str = "knowledge",
        include_special_document_types: bool = False,
    ) -> dict[str, Any]: ...

    async def skills_check(
        self,
        *,
        query: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
        version: Optional[str] = "latest",
        distance_threshold: Optional[float] = 0.8,
    ) -> dict[str, Any]: ...

    async def get_skill(
        self,
        *,
        skill_name: str,
        version: Optional[str] = "latest",
    ) -> dict[str, Any]: ...

    async def get_skill_resource(
        self,
        *,
        skill_name: str,
        resource_path: str,
        version: Optional[str] = "latest",
    ) -> dict[str, Any]: ...

    async def search_support_tickets(
        self,
        *,
        query: str,
        limit: int = 10,
        offset: int = 0,
        distance_threshold: Optional[float] = 0.8,
        hybrid_search: bool = False,
        version: Optional[str] = "latest",
    ) -> dict[str, Any]: ...

    async def get_support_ticket(
        self,
        *,
        ticket_id: str,
    ) -> dict[str, Any]: ...

    async def get_pinned_documents(
        self,
        *,
        version: Optional[str] = "latest",
        limit: int = 50,
        content_char_budget: int = 12000,
    ) -> dict[str, Any]: ...

    async def get_all_document_fragments(
        self,
        *,
        document_hash: str,
        include_metadata: bool = True,
        index_type: str = "knowledge",
        version: Optional[str] = "latest",
    ) -> dict[str, Any]: ...

    async def get_related_document_fragments(
        self,
        *,
        document_hash: str,
        current_chunk_index: int | None = None,
        context_window: int = 2,
        version: Optional[str] = "latest",
        index_type: str = "knowledge",
    ) -> dict[str, Any]: ...


@dataclass(frozen=True)
class EvalToolDispatchResult:
    """Wrapped result for an eval-only tool dispatch override."""

    result: Any


@runtime_checkable
class EvalToolRuntime(Protocol):
    """Protocol for eval-only tool execution overrides."""

    async def dispatch_tool_call(
        self,
        *,
        tool_name: str,
        args: dict[str, Any],
        tool_by_name: Mapping[str, Any],
        routing_table: Mapping[str, Any],
    ) -> EvalToolDispatchResult | None: ...


@runtime_checkable
class EvalMCPRuntime(Protocol):
    """Protocol for eval-only fake MCP server catalogs."""

    def get_server_configs(self) -> EvalMCPServerConfigs: ...

    def get_server_session(self, server_name: str) -> Any | None: ...


EvalMCPServerConfigs = Mapping[str, MCPServerConfig | dict[str, Any]]


@dataclass(frozen=True)
class EvalInjectionOverrides:
    """Context-local override values used during eval execution."""

    knowledge_backend: EvalKnowledgeBackend | None = None
    mcp_servers: EvalMCPServerConfigs | None = None
    mcp_runtime: EvalMCPRuntime | None = None
    tool_runtime: EvalToolRuntime | None = None


EvalRuntimeOverrides = EvalInjectionOverrides


_eval_runtime_overrides: ContextVar[EvalInjectionOverrides | None] = ContextVar(
    "eval_runtime_overrides",
    default=None,
)


def get_active_eval_injection_overrides() -> EvalInjectionOverrides | None:
    """Return the active eval override bundle for the current context."""

    return _eval_runtime_overrides.get()


def get_eval_runtime_overrides() -> EvalRuntimeOverrides:
    """Return the active eval override bundle, defaulting to an empty payload."""

    return get_active_eval_injection_overrides() or EvalInjectionOverrides()


def get_active_knowledge_backend() -> EvalKnowledgeBackend | None:
    """Return the active knowledge backend override, if one is installed."""

    overrides = get_active_eval_injection_overrides()
    if overrides is None:
        return None
    return overrides.knowledge_backend


def get_eval_knowledge_backend() -> EvalKnowledgeBackend | None:
    """Compatibility wrapper for older helper call sites."""

    return get_active_knowledge_backend()


def has_active_mcp_server_override() -> bool:
    """Return True when the current eval run overrides the MCP catalog."""

    overrides = get_active_eval_injection_overrides()
    return overrides is not None and overrides.mcp_servers is not None


def get_active_mcp_servers(
    default: EvalMCPServerConfigs | None = None,
) -> EvalMCPServerConfigs:
    """Resolve the active MCP catalog for the current run."""

    overrides = get_active_eval_injection_overrides()
    if overrides is not None and overrides.mcp_servers is not None:
        return overrides.mcp_servers
    return default or {}


def get_active_tool_runtime() -> EvalToolRuntime | None:
    """Return the active tool runtime override, if one is installed."""

    overrides = get_active_eval_injection_overrides()
    if overrides is None:
        return None
    return overrides.tool_runtime


def get_active_mcp_runtime() -> EvalMCPRuntime | None:
    """Return the active fake MCP runtime override, if one is installed."""

    overrides = get_active_eval_injection_overrides()
    if overrides is None:
        return None
    return overrides.mcp_runtime


def _filter_supported_kwargs(method: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
    """Drop kwargs that the override method does not accept."""

    try:
        signature = inspect.signature(method)
    except (TypeError, ValueError):
        return kwargs

    if any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    ):
        return kwargs

    supported = {
        name
        for name, parameter in signature.parameters.items()
        if parameter.kind
        in (
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        )
    }
    return {key: value for key, value in kwargs.items() if key in supported}


async def dispatch_knowledge_backend_override(
    method_name: str,
    **kwargs: Any,
) -> dict[str, Any] | None:
    """Dispatch one helper call to the active eval knowledge backend, if present."""

    backend = get_active_knowledge_backend()
    if backend is None:
        return None

    method = getattr(backend, method_name, None)
    if method is None:
        return None

    result = method(**_filter_supported_kwargs(method, kwargs))
    if inspect.isawaitable(result):
        return await result
    return result


async def dispatch_tool_runtime_override(
    *,
    tool_name: str,
    args: dict[str, Any],
    tool_by_name: Mapping[str, Any],
    routing_table: Mapping[str, Any],
) -> EvalToolDispatchResult | None:
    """Dispatch one tool call to the active eval tool runtime, if present."""

    runtime = get_active_tool_runtime()
    if runtime is None:
        return None

    result = runtime.dispatch_tool_call(
        tool_name=tool_name,
        args=args,
        tool_by_name=tool_by_name,
        routing_table=routing_table,
    )
    if inspect.isawaitable(result):
        return await result
    return result


@contextmanager
def eval_injection_scope(
    *,
    knowledge_backend: EvalKnowledgeBackend | None = None,
    mcp_servers: EvalMCPServerConfigs | None = None,
    mcp_runtime: EvalMCPRuntime | None = None,
    tool_runtime: EvalToolRuntime | None = None,
) -> Iterator[EvalInjectionOverrides]:
    """Temporarily install eval-only backend overrides for the current context."""

    current = get_active_eval_injection_overrides()
    merged = EvalInjectionOverrides(
        knowledge_backend=(
            knowledge_backend
            if knowledge_backend is not None
            else (current.knowledge_backend if current is not None else None)
        ),
        mcp_servers=(
            mcp_servers if mcp_servers is not None else (current.mcp_servers if current else None)
        ),
        mcp_runtime=(
            mcp_runtime if mcp_runtime is not None else (current.mcp_runtime if current else None)
        ),
        tool_runtime=(
            tool_runtime
            if tool_runtime is not None
            else (current.tool_runtime if current is not None else None)
        ),
    )
    token = _eval_runtime_overrides.set(merged)
    try:
        yield merged
    finally:
        _eval_runtime_overrides.reset(token)


@contextmanager
def eval_runtime_overrides(
    *,
    knowledge_backend: EvalKnowledgeBackend | None = None,
    mcp_servers: EvalMCPServerConfigs | None = None,
    mcp_runtime: EvalMCPRuntime | None = None,
    tool_runtime: EvalToolRuntime | None = None,
) -> Iterator[EvalRuntimeOverrides]:
    """Compatibility alias for callers using the newer override name."""

    with eval_injection_scope(
        knowledge_backend=knowledge_backend,
        mcp_servers=mcp_servers,
        mcp_runtime=mcp_runtime,
        tool_runtime=tool_runtime,
    ) as overrides:
        yield overrides


__all__ = [
    "EvalInjectionOverrides",
    "EvalKnowledgeBackend",
    "EvalMCPRuntime",
    "EvalToolDispatchResult",
    "EvalToolRuntime",
    "EvalMCPServerConfigs",
    "EvalRuntimeOverrides",
    "dispatch_knowledge_backend_override",
    "dispatch_tool_runtime_override",
    "eval_injection_scope",
    "eval_runtime_overrides",
    "get_active_eval_injection_overrides",
    "get_active_knowledge_backend",
    "get_active_mcp_runtime",
    "get_active_mcp_servers",
    "get_active_tool_runtime",
    "get_eval_knowledge_backend",
    "get_eval_runtime_overrides",
    "has_active_mcp_server_override",
]
