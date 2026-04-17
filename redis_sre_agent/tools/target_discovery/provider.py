"""Natural-language target discovery provider."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from redis_sre_agent.core.targets import bind_target_matches, list_known_targets, resolve_target_query
from redis_sre_agent.targets.contracts import DiscoveryResponse
from redis_sre_agent.tools.models import ToolCapability, ToolDefinition
from redis_sre_agent.tools.protocols import ToolProvider


class TargetDiscoveryToolProvider(ToolProvider):
    """Resolve safe Redis targets from natural-language metadata queries."""

    @property
    def provider_name(self) -> str:
        return "target_discovery"

    @property
    def requires_redis_instance(self) -> bool:
        return False

    def create_tool_schemas(self) -> List[ToolDefinition]:
        return [
            ToolDefinition(
                name=self._make_tool_name("list_known_redis_targets"),
                description=(
                    "List the safe Redis targets currently known in your target catalog. "
                    "Use this when the user asks what Redis targets, instances, databases, "
                    "or clusters you know about without naming a specific one yet. "
                    "This does not attach live tools."
                ),
                capability=ToolCapability.UTILITIES,
                parameters={
                    "type": "object",
                    "properties": {
                        "target_kind": {
                            "type": "string",
                            "enum": ["instance", "cluster"],
                            "description": "Optional filter for instance or cluster targets.",
                        },
                        "environment": {
                            "type": "string",
                            "description": "Optional environment filter such as production or staging.",
                        },
                        "capability": {
                            "type": "string",
                            "description": "Optional required capability such as diagnostics, admin, cloud, metrics, or logs.",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of known targets to return.",
                            "default": 20,
                            "minimum": 1,
                            "maximum": 100,
                        },
                        "offset": {
                            "type": "integer",
                            "description": "Number of known targets to skip before returning results.",
                            "default": 0,
                            "minimum": 0,
                        },
                        "include_aliases": {
                            "type": "boolean",
                            "description": "Whether to include safe search aliases in public metadata.",
                            "default": False,
                        },
                    },
                },
            ),
            ToolDefinition(
                name=self._make_tool_name("resolve_redis_targets"),
                description=(
                    "Resolve natural-language target descriptions like 'prod checkout cache' "
                    "or 'the us-east enterprise cluster' into safe Redis target matches. "
                    "This tool only returns secret-safe metadata and opaque target handles. "
                    "Use it before live diagnostics when the user has not provided an "
                    "explicit instance_id or cluster_id."
                ),
                capability=ToolCapability.UTILITIES,
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Natural-language description of the Redis target to resolve.",
                        },
                        "allow_multiple": {
                            "type": "boolean",
                            "description": "Whether multiple matching targets may be selected and attached.",
                            "default": False,
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of candidate matches to return.",
                            "default": 5,
                            "minimum": 1,
                            "maximum": 10,
                        },
                        "attach_tools": {
                            "type": "boolean",
                            "description": "Whether to attach the resolved targets to the current tool manager.",
                            "default": True,
                        },
                        "preferred_capabilities": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional capability hints such as diagnostics, admin, cloud, metrics, or logs.",
                        },
                    },
                    "required": ["query"],
                },
            )
        ]

    async def list_known_redis_targets(
        self,
        target_kind: Optional[str] = None,
        environment: Optional[str] = None,
        capability: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
        include_aliases: bool = False,
    ) -> Dict[str, Any]:
        manager = getattr(self, "_manager", None)
        user_id = getattr(manager, "user_id", None)
        toolset_generation = manager.get_toolset_generation() if manager else 0

        payload = await list_known_targets(
            user_id=user_id,
            target_kind=target_kind,
            environment=environment,
            capability=capability,
            limit=limit,
            offset=offset,
            include_aliases=include_aliases,
        )
        payload["toolset_generation"] = toolset_generation
        return payload

    async def resolve_redis_targets(
        self,
        query: str,
        allow_multiple: bool = False,
        max_results: int = 5,
        attach_tools: bool = True,
        preferred_capabilities: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        manager = getattr(self, "_manager", None)
        thread_id = getattr(manager, "thread_id", None)
        task_id = getattr(manager, "task_id", None)
        user_id = getattr(manager, "user_id", None)

        result = await resolve_target_query(
            query=query,
            user_id=user_id,
            allow_multiple=allow_multiple,
            max_results=max_results,
            preferred_capabilities=preferred_capabilities,
        )

        attached_handles: List[str] = []
        scope = None
        toolset_generation = manager.get_toolset_generation() if manager else 0

        if attach_tools and manager and result.selected_matches:
            scope = await bind_target_matches(
                matches=result.selected_matches,
                thread_id=thread_id,
                task_id=task_id,
                replace_existing=not allow_multiple,
                manager=manager,
            )
            attached_handles = scope.context_updates.get("attached_target_handles", [])
            toolset_generation = scope.toolset_generation

        payload = (
            result.public_dump() if isinstance(result, DiscoveryResponse) else result.model_dump()
        )
        payload["attached_target_handles"] = attached_handles
        payload["toolset_generation"] = toolset_generation
        if scope is not None:
            payload.update(
                {
                    key: value
                    for key, value in scope.context_updates.items()
                    if key not in {"instance_id", "cluster_id"}
                }
            )
        return payload
