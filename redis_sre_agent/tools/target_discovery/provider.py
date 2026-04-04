"""Natural-language target discovery provider."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from redis_sre_agent.core.targets import (
    attach_target_matches,
    build_ephemeral_target_bindings,
    resolve_target_query,
)
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
        toolset_generation = manager.get_toolset_generation() if manager else 0

        if attach_tools and manager and result.selected_matches:
            replace_existing = not allow_multiple
            if thread_id:
                bindings, persisted_generation = await attach_target_matches(
                    thread_id=thread_id,
                    matches=result.selected_matches,
                    task_id=task_id,
                    replace_existing=replace_existing,
                )
                await manager.attach_bound_targets(bindings, generation=persisted_generation)
            else:
                bindings = build_ephemeral_target_bindings(
                    result.selected_matches,
                    thread_id=thread_id,
                    task_id=task_id,
                )
                await manager.attach_bound_targets(bindings)
            attached_handles = [binding.target_handle for binding in bindings]
            toolset_generation = manager.get_toolset_generation()

        payload = result.model_dump()
        payload["attached_target_handles"] = attached_handles
        payload["toolset_generation"] = toolset_generation
        return payload
