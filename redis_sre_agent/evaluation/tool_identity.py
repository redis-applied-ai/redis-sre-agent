"""Logical tool identity helpers for eval scenarios and reporting."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable, Mapping, Sequence

from pydantic import BaseModel, model_validator

from redis_sre_agent.tools.models import Tool
from redis_sre_agent.tools.protocols import ToolProvider

_PROVIDER_FAMILY_ALIASES = {
    "knowledge": "knowledge",
    "loki": "loki",
    "prometheus": "prometheus",
    "re_admin": "redis_enterprise_admin",
    "redis_cloud": "redis_cloud",
    "redis_command": "redis_command",
    "redis_enterprise_admin": "redis_enterprise_admin",
    "target_discovery": "target_discovery",
    "utilities": "utilities",
}


def _normalize_token(value: Any) -> str:
    normalized = str(value or "").strip().lower().replace("-", "_")
    return normalized


def _normalize_optional_token(value: Any) -> str | None:
    normalized = _normalize_token(value)
    return normalized or None


def normalize_tool_name_token(value: Any) -> str:
    normalized = " ".join(str(value or "").strip().lower().split())
    return normalized.replace("-", "_").replace(" ", "_")


def normalize_provider_family(provider_family: str) -> str:
    """Return the canonical scenario-facing provider family."""
    normalized = _normalize_token(provider_family)
    if normalized.startswith("mcp_"):
        return "mcp"
    return _PROVIDER_FAMILY_ALIASES.get(normalized, normalized)


def concrete_provider_family_prefixes(provider_family: str) -> set[str]:
    """Return all concrete provider-name prefixes that map to this family."""

    normalized = _normalize_token(provider_family)
    canonical = normalize_provider_family(normalized)
    prefixes = {normalized, canonical}
    prefixes.update(
        alias for alias, target in _PROVIDER_FAMILY_ALIASES.items() if target == canonical
    )
    return prefixes


def extract_mcp_server_name(provider_name: str) -> str | None:
    """Return the MCP server name encoded in a provider name, if any."""
    normalized = _normalize_token(provider_name)
    if not normalized.startswith("mcp_"):
        return None
    server_name = normalized[4:]
    return server_name or None


def _extract_target_handle(provider: ToolProvider) -> str | None:
    instance = getattr(provider, "redis_instance", None)
    if instance is None:
        return None
    return _normalize_optional_token(getattr(instance, "id", None))


class LogicalToolIdentity(BaseModel):
    """Stable tool identity used by eval scenarios and scoring rules."""

    provider_family: str
    operation: str
    target_handle: str | None = None
    server_name: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, value: Any) -> Any:
        payload = dict(value or {})
        provider_family = _normalize_token(payload.get("provider_family"))
        if not provider_family:
            raise ValueError("provider_family is required")

        server_name = _normalize_optional_token(payload.get("server_name"))
        embedded_server_name = extract_mcp_server_name(provider_family)
        if embedded_server_name:
            if server_name and server_name != embedded_server_name:
                raise ValueError("server_name must match the MCP server encoded in provider_family")
            server_name = embedded_server_name

        payload["provider_family"] = normalize_provider_family(provider_family)

        operation = _normalize_token(payload.get("operation"))
        if not operation:
            raise ValueError("operation is required")
        payload["operation"] = operation
        payload["target_handle"] = _normalize_optional_token(payload.get("target_handle"))
        payload["server_name"] = server_name
        return payload

    @model_validator(mode="after")
    def _validate_cross_fields(self) -> "LogicalToolIdentity":
        if self.provider_family == "mcp" and not self.server_name:
            raise ValueError("MCP logical tool identities must include server_name")
        if self.provider_family != "mcp" and self.server_name:
            raise ValueError("server_name is only valid for MCP logical tool identities")
        return self


class ConcreteToolIdentity(BaseModel):
    """Concrete runtime tool plus its normalized logical identity."""

    concrete_name: str
    provider_name: str
    provider_family: str
    operation: str
    target_handle: str | None = None
    server_name: str | None = None
    capability: str | None = None
    requires_instance: bool = False

    @classmethod
    def from_tool(cls, tool: Tool, provider: ToolProvider) -> "ConcreteToolIdentity":
        provider_name = _normalize_token(provider.provider_name)
        operation = _normalize_optional_token(
            provider.resolve_operation(tool.definition.name, {})
        ) or _normalize_token(tool.definition.name)
        server_name = extract_mcp_server_name(provider_name)
        return cls(
            concrete_name=tool.definition.name,
            provider_name=provider_name,
            provider_family=normalize_provider_family(provider_name),
            operation=operation,
            target_handle=_extract_target_handle(provider),
            server_name=server_name,
            capability=getattr(tool.metadata.capability, "value", None),
            requires_instance=bool(getattr(tool.metadata, "requires_instance", False)),
        )

    @property
    def logical_identity(self) -> LogicalToolIdentity:
        return LogicalToolIdentity(
            provider_family=self.provider_family,
            operation=self.operation,
            target_handle=self.target_handle,
            server_name=self.server_name,
        )

    def matches(self, identity: LogicalToolIdentity) -> bool:
        if self.provider_family != identity.provider_family:
            return False
        if self.operation != identity.operation:
            return False
        if identity.server_name is not None and self.server_name != identity.server_name:
            return False
        if identity.target_handle is not None and self.target_handle != identity.target_handle:
            return False
        return True


class ToolIdentityCatalog:
    """Index concrete runtime tools by stable logical identities."""

    def __init__(self, entries: Sequence[ConcreteToolIdentity]):
        self._entries = list(entries)
        self._by_concrete_name = {entry.concrete_name: entry for entry in self._entries}
        self._by_family_operation: dict[tuple[str, str], list[ConcreteToolIdentity]] = defaultdict(
            list
        )
        for entry in self._entries:
            self._by_family_operation[(entry.provider_family, entry.operation)].append(entry)

    @classmethod
    def from_provider_tools(
        cls,
        bindings: Iterable[tuple[ToolProvider, Sequence[Tool]]],
    ) -> "ToolIdentityCatalog":
        entries: list[ConcreteToolIdentity] = []
        for provider, tools in bindings:
            for tool in tools:
                entries.append(ConcreteToolIdentity.from_tool(tool, provider))
        return cls(entries)

    @classmethod
    def from_providers(cls, providers: Sequence[ToolProvider]) -> "ToolIdentityCatalog":
        return cls.from_provider_tools((provider, provider.tools()) for provider in providers)

    @classmethod
    def from_runtime_tables(
        cls,
        tool_by_name: Mapping[str, Tool],
        routing_table: Mapping[str, ToolProvider],
    ) -> "ToolIdentityCatalog":
        bindings: list[tuple[ToolProvider, list[Tool]]] = []
        grouped_tools: dict[int, tuple[ToolProvider, list[Tool]]] = {}
        for concrete_name, tool in tool_by_name.items():
            provider = routing_table.get(concrete_name)
            if provider is None:
                continue
            provider_key = id(provider)
            if provider_key not in grouped_tools:
                grouped_tools[provider_key] = (provider, [])
            grouped_tools[provider_key][1].append(tool)
        bindings.extend(grouped_tools.values())
        return cls.from_provider_tools(bindings)

    def entries(self) -> list[ConcreteToolIdentity]:
        return list(self._entries)

    def get(self, concrete_name: str) -> ConcreteToolIdentity:
        try:
            return self._by_concrete_name[concrete_name]
        except KeyError as exc:
            raise KeyError(f"Unknown concrete tool name: {concrete_name}") from exc

    def logical_identity_for_tool(self, concrete_name: str) -> LogicalToolIdentity:
        return self.get(concrete_name).logical_identity

    def resolve_all(
        self, identity: LogicalToolIdentity | Mapping[str, Any]
    ) -> list[ConcreteToolIdentity]:
        logical = (
            identity
            if isinstance(identity, LogicalToolIdentity)
            else LogicalToolIdentity.model_validate(identity)
        )
        candidates = self._by_family_operation.get((logical.provider_family, logical.operation), [])
        return [entry for entry in candidates if entry.matches(logical)]

    def resolve(self, identity: LogicalToolIdentity | Mapping[str, Any]) -> ConcreteToolIdentity:
        logical = (
            identity
            if isinstance(identity, LogicalToolIdentity)
            else LogicalToolIdentity.model_validate(identity)
        )
        matches = self.resolve_all(logical)
        if not matches:
            raise KeyError(f"No concrete tool matches logical identity {logical.model_dump()}")
        if len(matches) > 1:
            concrete_names = ", ".join(sorted(entry.concrete_name for entry in matches))
            raise ValueError(
                "Logical identity is ambiguous; narrow it with target_handle or server_name: "
                f"{logical.model_dump()} -> {concrete_names}"
            )
        return matches[0]

    def resolve_name(self, identity: LogicalToolIdentity | Mapping[str, Any]) -> str:
        return self.resolve(identity).concrete_name

    def report_rows(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for entry in self._entries:
            rows.append(
                {
                    "concrete_name": entry.concrete_name,
                    "provider_name": entry.provider_name,
                    "provider_family": entry.provider_family,
                    "operation": entry.operation,
                    "target_handle": entry.target_handle,
                    "server_name": entry.server_name,
                    "capability": entry.capability,
                    "requires_instance": entry.requires_instance,
                }
            )
        return rows
