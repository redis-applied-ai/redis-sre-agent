"""Unified Redis target catalog, resolver, and thread binding helpers."""

from __future__ import annotations

import copy
import inspect
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Optional, Sequence
from urllib.parse import urlparse

from pydantic import BaseModel, Field
from redisvl.query import CountQuery, FilterQuery
from ulid import ULID

from redis_sre_agent.core.clusters import RedisCluster, get_cluster_by_id, get_clusters
from redis_sre_agent.core.instances import RedisInstance, get_instance_by_id, get_instances
from redis_sre_agent.core.redis import SRE_TARGETS_INDEX, get_redis_client, get_targets_index
from redis_sre_agent.core.threads import ThreadManager

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_ENV_ALIASES = {
    "prod": "production",
    "production": "production",
    "stage": "staging",
    "staging": "staging",
    "dev": "development",
    "development": "development",
    "test": "test",
    "qa": "test",
}
_USAGE_TERMS = {"cache", "queue", "session", "analytics", "custom"}
_INSTANCE_HINTS = {"instance", "database", "db"}
_CLUSTER_HINTS = {"cluster", "subscription"}
_TYPE_HINTS = {
    "enterprise": "redis_enterprise",
    "cloud": "redis_cloud",
    "oss": "oss_single",
    "clustered": "oss_cluster",
}
_HEALTHY_STATUSES = {"healthy", "ok", "active", "available", "connected"}


class TargetCatalogDoc(BaseModel):
    """Safe denormalized metadata used for natural-language discovery."""

    target_id: str
    target_kind: str
    resource_id: str
    display_name: str
    name: str
    environment: Optional[str] = None
    status: Optional[str] = None
    target_type: Optional[str] = None
    usage: Optional[str] = None
    description: Optional[str] = None
    notes: Optional[str] = None
    repo_url: Optional[str] = None
    repo_slug: Optional[str] = None
    monitoring_identifier: Optional[str] = None
    logging_identifier: Optional[str] = None
    cluster_id: Optional[str] = None
    redis_cloud_subscription_id: Optional[str] = None
    redis_cloud_database_id: Optional[str] = None
    redis_cloud_database_name: Optional[str] = None
    search_text: str = ""
    search_aliases: List[str] = Field(default_factory=list)
    capabilities: List[str] = Field(default_factory=list)
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    user_id: Optional[str] = None


class TargetBinding(BaseModel):
    """Opaque handle persisted in thread context for attached targets."""

    target_handle: str
    target_kind: str
    resource_id: str
    display_name: str
    capabilities: List[str] = Field(default_factory=list)
    thread_id: Optional[str] = None
    task_id: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    expires_at: Optional[str] = Field(
        default_factory=lambda: (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
    )


def build_single_attached_binding_prompt(binding: TargetBinding) -> str:
    """Build minimal scope context when richer attached-target prompt loading fails."""
    capability_text = ", ".join(binding.capabilities or []) or "unspecified"
    return (
        "ATTACHED TARGET SCOPE: This conversation has 1 attached Redis target.\n"
        "Attached target:\n"
        f"- {binding.display_name} [handle={binding.target_handle}, "
        f"kind={binding.target_kind}, resource_id={binding.resource_id}, "
        f"capabilities={capability_text}]"
    )


def build_attached_target_prompt_fallback(
    attached_target_count: int,
    bindings: Sequence[TargetBinding],
    attached_handles: Optional[Sequence[str]] = None,
) -> Optional[str]:
    """Build deterministic attached-target scope context when async prompt loading fails."""
    ordered_handles = [
        handle for handle in (str(handle).strip() for handle in (attached_handles or [])) if handle
    ]
    binding_by_handle = {binding.target_handle: binding for binding in bindings}
    for binding in bindings:
        if binding.target_handle not in ordered_handles:
            ordered_handles.append(binding.target_handle)

    target_count = max(attached_target_count, len(ordered_handles))
    if target_count <= 0:
        return None

    prompt_lines = [
        (f"ATTACHED TARGET SCOPE: This conversation has {target_count} attached Redis target(s)."),
        "Attached targets:" if target_count > 1 else "Attached target:",
    ]

    if ordered_handles:
        for handle in ordered_handles:
            binding = binding_by_handle.get(handle)
            if binding is None:
                prompt_lines.append(f"- handle={handle} [metadata unavailable]")
                continue

            capability_text = ", ".join(binding.capabilities or []) or "unspecified"
            prompt_lines.append(
                "- "
                f"{binding.display_name} [handle={binding.target_handle}, "
                f"kind={binding.target_kind}, resource_id={binding.resource_id}, "
                f"capabilities={capability_text}]"
            )
    else:
        prompt_lines.append("- [metadata unavailable]")

    if target_count > 1:
        prompt_lines.extend(
            [
                "MULTI-TARGET REQUIREMENT: Treat these attached targets as a target set.",
                (
                    "Do not silently collapse scope to a single instance or cluster unless the "
                    "user explicitly narrows it."
                ),
                (
                    "When the user asks for investigation or comparison, gather evidence per "
                    "target, keep the findings separated by handle/display name, and then "
                    "return a structured comparison."
                ),
            ]
        )
    else:
        prompt_lines.append(
            "Use the target-scoped tools for the attached handle above when investigating it."
        )

    return "\n".join(prompt_lines)


class ResolvedTargetMatch(BaseModel):
    """A ranked candidate returned by the deterministic resolver."""

    target_kind: str
    resource_id: str
    display_name: str
    environment: Optional[str] = None
    target_type: Optional[str] = None
    capabilities: List[str] = Field(default_factory=list)
    confidence: float
    match_reasons: List[str] = Field(default_factory=list)
    score: float = Field(default=0.0, exclude=True)


class TargetResolutionResult(BaseModel):
    """Public result shape for target resolution."""

    status: str
    clarification_required: bool = False
    matches: List[ResolvedTargetMatch] = Field(default_factory=list)
    attached_target_handles: List[str] = Field(default_factory=list)
    toolset_generation: int = 0
    selected_matches: List[ResolvedTargetMatch] = Field(default_factory=list, exclude=True)


class ThreadTargetState(BaseModel):
    """Attached target handles plus binding metadata for a thread."""

    attached_target_handles: List[str] = Field(default_factory=list)
    active_target_handle: Optional[str] = None
    target_toolset_generation: int = 0
    target_bindings: List[TargetBinding] = Field(default_factory=list)


class MaterializedTargetScope(BaseModel):
    """Shared output for resolved target selection and attachment."""

    selected_bindings: List[TargetBinding] = Field(default_factory=list)
    attached_bindings: List[TargetBinding] = Field(default_factory=list)
    target_toolset_generation: int = 0
    context_updates: Dict[str, Any] = Field(default_factory=dict)


class BoundTargetScope(BaseModel):
    """Shared result shape for attached target binding flows."""

    bindings: List[TargetBinding] = Field(default_factory=list)
    toolset_generation: int = 0
    context_updates: Dict[str, Any] = Field(default_factory=dict)


def get_attached_target_handles_from_context(context: Optional[Dict[str, Any]]) -> List[str]:
    """Return normalized attached target handles from a routing context."""
    if not isinstance(context, dict):
        return []

    raw_handles = context.get("attached_target_handles") or []
    if not isinstance(raw_handles, list):
        return []

    handles: List[str] = []
    for raw_handle in raw_handles:
        handle = str(raw_handle or "").strip()
        if handle:
            handles.append(handle)
    return handles


def get_target_bindings_from_context(context: Optional[Dict[str, Any]]) -> List[TargetBinding]:
    """Parse serialized target bindings from a routing context."""
    if not isinstance(context, dict):
        return []

    raw_bindings = context.get("target_bindings") or []
    if not isinstance(raw_bindings, list):
        return []

    bindings: List[TargetBinding] = []
    for raw_binding in raw_bindings:
        try:
            bindings.append(TargetBinding.model_validate(raw_binding))
        except Exception:
            continue
    return bindings


def build_bound_target_scope_context(
    bindings: Sequence[TargetBinding],
    *,
    generation: int,
    active_handle: Optional[str] = None,
) -> Dict[str, Any]:
    """Build normalized routing/thread context fields for attached bindings."""
    attached_bindings = list(bindings)
    attached_handles = [binding.target_handle for binding in attached_bindings]
    resolved_active_handle = active_handle or (
        attached_bindings[0].target_handle if attached_bindings else ""
    )

    context_updates: Dict[str, Any] = {
        "attached_target_handles": attached_handles,
        "active_target_handle": resolved_active_handle or "",
        "target_toolset_generation": generation,
        "target_bindings": [binding.model_dump(mode="json") for binding in attached_bindings],
        "instance_id": "",
        "cluster_id": "",
    }

    return context_updates


async def build_attached_target_scope_prompt(context: Optional[Dict[str, Any]]) -> Optional[str]:
    """Build prompt context for attached targets, including comparison guidance."""
    handles = get_attached_target_handles_from_context(context)
    bindings = get_target_bindings_from_context(context)
    if not handles and not bindings:
        return None

    active_handle = ""
    if isinstance(context, dict):
        active_handle = str(context.get("active_target_handle") or "").strip()

    binding_by_handle = {binding.target_handle: binding for binding in bindings}
    ordered_handles = list(handles)
    for binding in bindings:
        if binding.target_handle not in ordered_handles:
            ordered_handles.append(binding.target_handle)

    target_lines: List[str] = []
    for handle in ordered_handles:
        binding = binding_by_handle.get(handle)
        if binding is None:
            target_lines.append(f"- handle={handle} [metadata unavailable]")
            continue

        capability_text = ", ".join(binding.capabilities or []) or "unspecified"
        if binding.target_kind == "instance":
            instance = await get_instance_by_id(binding.resource_id)
            if instance is not None:
                target_lines.append(
                    "- "
                    f"{binding.display_name} [handle={handle}, kind=instance, instance_id={instance.id}, "
                    f"environment={instance.environment}, usage={instance.usage}, "
                    f"type={instance.instance_type}, capabilities={capability_text}]"
                )
            else:
                target_lines.append(
                    "- "
                    f"{binding.display_name} [handle={handle}, kind=instance, instance_id={binding.resource_id}, "
                    f"capabilities={capability_text}, state=missing]"
                )
        elif binding.target_kind == "cluster":
            cluster = await get_cluster_by_id(binding.resource_id)
            if cluster is not None:
                target_lines.append(
                    "- "
                    f"{binding.display_name} [handle={handle}, kind=cluster, cluster_id={cluster.id}, "
                    f"environment={cluster.environment}, type={cluster.cluster_type}, "
                    f"capabilities={capability_text}]"
                )
            else:
                target_lines.append(
                    "- "
                    f"{binding.display_name} [handle={handle}, kind=cluster, cluster_id={binding.resource_id}, "
                    f"capabilities={capability_text}, state=missing]"
                )
        else:
            target_lines.append(
                "- "
                f"{binding.display_name} [handle={handle}, kind={binding.target_kind}, "
                f"resource_id={binding.resource_id}, capabilities={capability_text}]"
            )

    prompt_lines = [
        (
            "ATTACHED TARGET SCOPE: This conversation has "
            f"{len(ordered_handles)} attached Redis target(s)."
        ),
    ]
    if active_handle and active_handle in ordered_handles:
        prompt_lines.append(f"Active target handle: {active_handle}")
    prompt_lines.append("Attached targets:")
    prompt_lines.extend(target_lines)

    if len(ordered_handles) > 1:
        prompt_lines.extend(
            [
                "MULTI-TARGET REQUIREMENT: Treat these attached targets as a target set.",
                (
                    "Do not silently collapse scope to a single instance or cluster unless the "
                    "user explicitly narrows it."
                ),
                (
                    "When the user asks for investigation or comparison, gather evidence per "
                    "target, keep the findings separated by handle/display name, and then "
                    "return a structured comparison with metrics, config differences, findings, "
                    "and recommendations."
                ),
                (
                    "Use the target-scoped tool variants for each attached handle as needed. "
                    "If some targets lack equivalent tooling, state that explicitly."
                ),
            ]
        )
    else:
        prompt_lines.append(
            "Use the target-scoped tools for the attached handle above when investigating it."
        )

    return "\n".join(prompt_lines)


def build_attached_target_prompt_loader(
    context: Optional[Dict[str, Any]],
    attached_target_count: int,
    prompt_builder: Callable[[Optional[Dict[str, Any]]], Awaitable[Optional[str]]],
) -> Callable[[], Awaitable[Optional[str]]]:
    """Return a memoized attached-target prompt loader for a single turn."""

    context_snapshot = copy.deepcopy(context) if isinstance(context, dict) else context
    prompt_unset = object()
    attached_target_prompt: Any = prompt_unset

    async def _get_attached_target_prompt() -> Optional[str]:
        nonlocal attached_target_prompt
        if attached_target_prompt is prompt_unset and attached_target_count:
            attached_target_prompt = await prompt_builder(context_snapshot)
        if attached_target_prompt is prompt_unset:
            return None
        return attached_target_prompt

    return _get_attached_target_prompt


def _to_epoch(ts: Optional[str]) -> float:
    if not ts:
        return 0.0
    try:
        if ts.endswith("Z"):
            ts = ts.replace("Z", "+00:00")
        return datetime.fromisoformat(ts).timestamp()
    except Exception:
        try:
            return float(ts)
        except Exception:
            return 0.0


def _normalize(value: Any) -> str:
    return str(value or "").strip().lower()


def _normalize_environment(value: Any) -> str:
    normalized = _normalize(value)
    return _ENV_ALIASES.get(normalized, normalized)


def _tokenize(value: Any) -> List[str]:
    text = _normalize(value)
    return _TOKEN_RE.findall(text.replace("-", " ").replace("_", " "))


def _dedupe(values: Iterable[str]) -> List[str]:
    seen: set[str] = set()
    out: List[str] = []
    for value in values:
        normalized = _normalize(value)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        out.append(normalized)
    return out


def _safe_repo_tokens(repo_url: Optional[str]) -> tuple[Optional[str], List[str]]:
    if not repo_url:
        return None, []
    try:
        parsed = urlparse(repo_url)
        path_parts = [part for part in (parsed.path or "").split("/") if part]
        slug = (
            "/".join(path_parts[-2:])
            if len(path_parts) >= 2
            else (path_parts[0] if path_parts else "")
        )
        tokens = [parsed.netloc or "", slug]
        tokens.extend(path_parts[-2:])
        return slug or None, _dedupe(tokens)
    except Exception:
        return None, []


def _extract_safe_aliases(extension_data: Optional[Dict[str, Any]]) -> List[str]:
    if not isinstance(extension_data, dict):
        return []

    aliases: List[str] = []
    for key in ("aliases", "search_aliases", "target_aliases"):
        value = extension_data.get(key)
        if isinstance(value, str):
            aliases.extend([part.strip() for part in value.split(",")])
        elif isinstance(value, list):
            aliases.extend(str(item).strip() for item in value)

    target_discovery = extension_data.get("target_discovery")
    if isinstance(target_discovery, dict):
        nested_aliases = target_discovery.get("aliases")
        if isinstance(nested_aliases, list):
            aliases.extend(str(item).strip() for item in nested_aliases)
        elif isinstance(nested_aliases, str):
            aliases.extend([part.strip() for part in nested_aliases.split(",")])

    return _dedupe(aliases)


def _instance_capabilities(instance: RedisInstance) -> List[str]:
    capabilities = ["redis", "diagnostics", "metrics", "logs"]
    instance_type = _normalize(
        instance.instance_type.value
        if hasattr(instance.instance_type, "value")
        else instance.instance_type
    )
    if instance_type == "redis_enterprise":
        capabilities.append("admin")
    if instance_type == "redis_cloud":
        capabilities.append("cloud")
    return _dedupe(capabilities)


def _cluster_capabilities(cluster: RedisCluster) -> List[str]:
    cluster_type = _normalize(
        cluster.cluster_type.value
        if hasattr(cluster.cluster_type, "value")
        else cluster.cluster_type
    )
    capabilities = ["redis", "diagnostics", "metrics", "logs"]
    if cluster_type == "redis_enterprise":
        capabilities.append("admin")
    if cluster_type == "redis_cloud":
        capabilities.append("cloud")
    return _dedupe(capabilities)


def build_target_doc_from_instance(instance: RedisInstance) -> TargetCatalogDoc:
    """Build a safe unified target document from a Redis instance."""
    repo_slug, repo_tokens = _safe_repo_tokens(instance.repo_url)
    aliases = _extract_safe_aliases(instance.extension_data)
    cloud_subscription_id = (
        str(instance.redis_cloud_subscription_id)
        if instance.redis_cloud_subscription_id is not None
        else None
    )
    cloud_database_id = (
        str(instance.redis_cloud_database_id)
        if instance.redis_cloud_database_id is not None
        else None
    )
    safe_bits = _dedupe(
        [
            instance.name,
            instance.environment,
            instance.usage,
            instance.description,
            instance.notes,
            instance.monitoring_identifier,
            instance.logging_identifier,
            instance.redis_cloud_database_name,
            repo_slug,
            *repo_tokens,
            *aliases,
        ]
    )
    instance_type = (
        instance.instance_type.value
        if hasattr(instance.instance_type, "value")
        else str(instance.instance_type)
    )
    return TargetCatalogDoc(
        target_id=f"instance:{instance.id}",
        target_kind="instance",
        resource_id=instance.id,
        display_name=instance.name,
        name=instance.name,
        environment=_normalize_environment(instance.environment),
        status=_normalize(instance.status),
        target_type=_normalize(instance_type),
        usage=_normalize(instance.usage),
        description=instance.description,
        notes=instance.notes,
        repo_url=instance.repo_url,
        repo_slug=repo_slug,
        monitoring_identifier=instance.monitoring_identifier,
        logging_identifier=instance.logging_identifier,
        cluster_id=instance.cluster_id,
        redis_cloud_subscription_id=cloud_subscription_id,
        redis_cloud_database_id=cloud_database_id,
        redis_cloud_database_name=instance.redis_cloud_database_name,
        search_text=" ".join(safe_bits),
        search_aliases=aliases,
        capabilities=_instance_capabilities(instance),
        updated_at=instance.updated_at,
        created_at=instance.created_at,
        user_id=instance.user_id,
    )


def build_target_doc_from_cluster(cluster: RedisCluster) -> TargetCatalogDoc:
    """Build a safe unified target document from a Redis cluster."""
    aliases = _extract_safe_aliases(cluster.extension_data)
    cluster_type = (
        cluster.cluster_type.value
        if hasattr(cluster.cluster_type, "value")
        else str(cluster.cluster_type)
    )
    safe_bits = _dedupe(
        [
            cluster.name,
            cluster.environment,
            cluster.description,
            cluster.notes,
            *aliases,
        ]
    )
    return TargetCatalogDoc(
        target_id=f"cluster:{cluster.id}",
        target_kind="cluster",
        resource_id=cluster.id,
        display_name=cluster.name,
        name=cluster.name,
        environment=_normalize_environment(cluster.environment),
        status=_normalize(cluster.status),
        target_type=_normalize(cluster_type),
        description=cluster.description,
        notes=cluster.notes,
        search_text=" ".join(safe_bits),
        search_aliases=aliases,
        capabilities=_cluster_capabilities(cluster),
        updated_at=cluster.updated_at,
        created_at=cluster.created_at,
        user_id=cluster.user_id,
    )


def build_target_catalog_docs(
    instances: Sequence[RedisInstance],
    clusters: Sequence[RedisCluster],
) -> List[TargetCatalogDoc]:
    """Build the complete unified target catalog from stored resources."""
    docs: List[TargetCatalogDoc] = [
        build_target_doc_from_instance(instance) for instance in instances
    ]
    docs.extend(build_target_doc_from_cluster(cluster) for cluster in clusters)
    return docs


async def _ensure_targets_index_exists() -> None:
    try:
        index = await get_targets_index()
        if not await index.exists():
            await index.create()
    except Exception:
        return


async def sync_target_catalog(
    *,
    instances: Optional[Sequence[RedisInstance]] = None,
    clusters: Optional[Sequence[RedisCluster]] = None,
) -> bool:
    """Rebuild the target catalog from authoritative instance and cluster records."""
    try:
        await _ensure_targets_index_exists()
        client = get_redis_client()

        actual_instances = list(instances) if instances is not None else await get_instances()
        actual_clusters = list(clusters) if clusters is not None else await get_clusters()
        docs = build_target_catalog_docs(actual_instances, actual_clusters)
        keep_ids = {doc.target_id for doc in docs}

        for doc in docs:
            key = f"{SRE_TARGETS_INDEX}:{doc.target_id}"
            await client.hset(
                key,
                mapping={
                    "target_id": doc.target_id,
                    "target_kind": doc.target_kind,
                    "resource_id": doc.resource_id,
                    "display_name": doc.display_name,
                    "name": doc.name,
                    "environment": doc.environment or "",
                    "status": doc.status or "",
                    "target_type": doc.target_type or "",
                    "usage": doc.usage or "",
                    "cluster_id": doc.cluster_id or "",
                    "repo_slug": doc.repo_slug or "",
                    "monitoring_identifier": doc.monitoring_identifier or "",
                    "logging_identifier": doc.logging_identifier or "",
                    "redis_cloud_subscription_id": doc.redis_cloud_subscription_id or "",
                    "redis_cloud_database_id": doc.redis_cloud_database_id or "",
                    "redis_cloud_database_name": doc.redis_cloud_database_name or "",
                    "search_aliases": ",".join(doc.search_aliases),
                    "capabilities": ",".join(doc.capabilities),
                    "updated_at": _to_epoch(doc.updated_at),
                    "created_at": _to_epoch(doc.created_at),
                    "search_text": doc.search_text,
                    "user_id": doc.user_id or "",
                    "data": doc.model_dump_json(),
                },
            )

        stale_ids: List[str] = []
        try:
            index = await get_targets_index()
            try:
                total = await index.query(CountQuery(filter_expression="*"))
            except Exception:
                total = 1000

            if total:
                q = FilterQuery(
                    filter_expression="*",
                    return_fields=["data"],
                    num_results=int(total) if isinstance(total, int) else 1000,
                )
                results = await index.query(q)
                for doc in results or []:
                    raw = doc.get("data")
                    if not raw:
                        continue
                    if isinstance(raw, bytes):
                        raw = raw.decode("utf-8")
                    try:
                        target_doc = TargetCatalogDoc.model_validate_json(raw)
                    except Exception:
                        continue
                    if target_doc.target_id not in keep_ids:
                        stale_ids.append(target_doc.target_id)
        except Exception:
            prefix = f"{SRE_TARGETS_INDEX}:"
            cursor = 0
            while True:
                cursor, batch = await client.scan(cursor=cursor, match=f"{prefix}*")
                if batch:
                    for key in batch:
                        decoded = (
                            key.decode("utf-8") if isinstance(key, (bytes, bytearray)) else str(key)
                        )
                        if not decoded.startswith(prefix):
                            continue
                        target_id = decoded.removeprefix(prefix)
                        if not target_id:
                            continue
                        if target_id not in keep_ids:
                            stale_ids.append(target_id)
                if cursor == 0:
                    break

        for stale_id in stale_ids:
            await client.delete(f"{SRE_TARGETS_INDEX}:{stale_id}")

        return True
    except Exception:
        logger.exception("Failed to sync unified target catalog")
        return False


async def get_target_catalog(
    *,
    user_id: Optional[str] = None,
) -> List[TargetCatalogDoc]:
    """Return all safe target docs from the unified discovery index."""
    try:
        await _ensure_targets_index_exists()
        index = await get_targets_index()
        client = get_redis_client()
        try:
            total = await index.query(CountQuery(filter_expression="*"))
        except Exception:
            total = 1000

        docs: List[TargetCatalogDoc] = []
        if total:
            q = FilterQuery(
                filter_expression="*",
                return_fields=["data"],
                num_results=int(total) if isinstance(total, int) else 1000,
            ).sort_by("updated_at", asc=False)
            results = await index.query(q)
            for doc in results or []:
                raw = doc.get("data")
                if not raw:
                    continue
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8")
                try:
                    docs.append(TargetCatalogDoc.model_validate_json(raw))
                except Exception:
                    continue

        if not docs:
            cursor = 0
            prefix = f"{SRE_TARGETS_INDEX}:"
            while True:
                cursor, batch = await client.scan(cursor=cursor, match=f"{prefix}*")
                for key in batch or []:
                    raw = await client.hget(key, "data")
                    if not raw:
                        continue
                    if isinstance(raw, bytes):
                        raw = raw.decode("utf-8")
                    try:
                        docs.append(TargetCatalogDoc.model_validate_json(raw))
                    except Exception:
                        continue
                if cursor == 0:
                    break

        filtered: List[TargetCatalogDoc] = []
        for parsed in docs:
            if user_id and parsed.user_id not in {None, "", user_id}:
                continue
            filtered.append(parsed)
        filtered.sort(key=lambda doc: _to_epoch(doc.updated_at), reverse=True)
        return filtered
    except Exception:
        logger.exception("Failed to load target catalog")
        return []


def _parse_query_hints(query: str) -> Dict[str, Any]:
    normalized = _normalize(query)
    tokens = set(_tokenize(normalized))
    environments = {_ENV_ALIASES[token] for token in tokens if token in _ENV_ALIASES}
    usages = {token for token in tokens if token in _USAGE_TERMS}
    preferred_kinds = set()
    if tokens & _INSTANCE_HINTS:
        preferred_kinds.add("instance")
    if tokens & _CLUSTER_HINTS:
        preferred_kinds.add("cluster")
    target_types = {_TYPE_HINTS[token] for token in tokens if token in _TYPE_HINTS}
    return {
        "normalized": normalized,
        "tokens": tokens,
        "environments": environments,
        "usages": usages,
        "preferred_kinds": preferred_kinds,
        "target_types": target_types,
    }


def _score_target_doc(
    query: str,
    doc: TargetCatalogDoc,
    *,
    preferred_capabilities: Optional[Sequence[str]] = None,
    hints: Optional[Dict[str, Any]] = None,
) -> tuple[float, List[str]]:
    hints = hints or _parse_query_hints(query)
    normalized = hints["normalized"]
    query_tokens = hints["tokens"]
    reasons: List[str] = []
    score = 0.0

    name_tokens = set(_tokenize(doc.display_name)) | set(_tokenize(doc.name))
    alias_tokens = set()
    for alias in doc.search_aliases:
        alias_tokens.update(_tokenize(alias))

    if normalized and normalized in {_normalize(doc.display_name), _normalize(doc.name)}:
        score += 8.0
        reasons.append("matched exact target name")

    exact_alias_matches = [alias for alias in doc.search_aliases if _normalize(alias) == normalized]
    if exact_alias_matches:
        score += 7.0
        reasons.append(f"matched alias={exact_alias_matches[0]}")

    partial_alias_matches: List[str] = []
    for alias in doc.search_aliases:
        alias_token_set = set(_tokenize(alias))
        if not alias_token_set:
            continue
        if alias_token_set <= query_tokens and _normalize(alias) != normalized:
            partial_alias_matches.append(alias)
    if partial_alias_matches and not exact_alias_matches:
        score += 3.0
        reasons.append(f"matched alias={partial_alias_matches[0]}")

    hint_tokens = (
        set(hints["environments"])
        | set(hints["usages"])
        | set(hints["preferred_kinds"])
        | {token for target_type in hints["target_types"] for token in _tokenize(target_type)}
    )
    token_overlap = sorted(
        (query_tokens - hint_tokens)
        & (name_tokens | alias_tokens | set(_tokenize(doc.search_text)))
    )
    if token_overlap:
        overlap_score = min(4.0, len(token_overlap) * 0.9)
        score += overlap_score
        reasons.append(f"matched tokens={','.join(token_overlap[:4])}")

    normalized_environment = _normalize_environment(doc.environment)
    if normalized_environment and normalized_environment in hints["environments"]:
        score += 3.0
        reasons.append(f"matched environment={normalized_environment}")

    normalized_usage = _normalize(doc.usage)
    if normalized_usage and normalized_usage in hints["usages"]:
        score += 2.5
        reasons.append(f"matched usage={normalized_usage}")

    if hints["preferred_kinds"]:
        if doc.target_kind in hints["preferred_kinds"]:
            score += 2.0
            reasons.append(f"matched kind={doc.target_kind}")
        else:
            score -= 0.5

    if hints["target_types"] and _normalize(doc.target_type) in hints["target_types"]:
        score += 2.0
        reasons.append(f"matched type={doc.target_type}")

    if preferred_capabilities:
        preferred = {_normalize(capability) for capability in preferred_capabilities if capability}
        supported = {_normalize(capability) for capability in doc.capabilities}
        matched = sorted(preferred & supported)
        if matched:
            score += min(2.0, len(matched) * 0.75)
            reasons.append(f"matched capabilities={','.join(matched[:3])}")

    if _normalize(doc.status) in _HEALTHY_STATUSES:
        score += 0.2

    return score, reasons


def _confidence_from_score(score: float) -> float:
    if score <= 0:
        return 0.0
    if score >= 10:
        return 0.99
    return round(min(0.99, 0.45 + (score / 20.0)), 2)


async def resolve_target_query(
    *,
    query: str,
    user_id: Optional[str] = None,
    allow_multiple: bool = False,
    max_results: int = 5,
    preferred_capabilities: Optional[Sequence[str]] = None,
) -> TargetResolutionResult:
    """Resolve natural-language query text against the safe target catalog."""
    docs = await get_target_catalog(user_id=user_id)
    if not docs:
        return TargetResolutionResult(status="no_match")

    hints = _parse_query_hints(query)
    ranked: List[ResolvedTargetMatch] = []
    for doc in docs:
        score, reasons = _score_target_doc(
            query,
            doc,
            preferred_capabilities=preferred_capabilities,
            hints=hints,
        )
        if score < 2.5:
            continue
        ranked.append(
            ResolvedTargetMatch(
                target_kind=doc.target_kind,
                resource_id=doc.resource_id,
                display_name=doc.display_name,
                environment=doc.environment,
                target_type=doc.target_type,
                capabilities=doc.capabilities,
                confidence=_confidence_from_score(score),
                match_reasons=reasons,
                score=score,
            )
        )

    ranked.sort(key=lambda match: (match.score, match.confidence), reverse=True)
    limited = ranked[: max(1, min(max_results, 10))]

    if not limited:
        return TargetResolutionResult(status="no_match")

    top = limited[0]
    selected: List[ResolvedTargetMatch] = []
    clarification_required = False

    if allow_multiple:
        selected = [match for match in limited if match.score >= max(3.0, top.score - 1.5)]
        selected = selected[: min(3, max_results)]
    else:
        if len(limited) > 1 and limited[1].score >= top.score - 0.75:
            clarification_required = True
            selected = limited[: min(3, max_results)]
        else:
            selected = [top]

    status = (
        "clarification_required"
        if clarification_required
        else ("resolved" if selected else "no_match")
    )
    return TargetResolutionResult(
        status=status,
        clarification_required=clarification_required,
        matches=limited,
        selected_matches=selected,
    )


def build_ephemeral_target_bindings(
    matches: Sequence[ResolvedTargetMatch],
    *,
    thread_id: Optional[str] = None,
    task_id: Optional[str] = None,
) -> List[TargetBinding]:
    """Build opaque target handles without persisting them."""
    return [
        TargetBinding(
            target_handle=f"tgt_{ULID()}",
            target_kind=match.target_kind,
            resource_id=match.resource_id,
            display_name=match.display_name,
            capabilities=match.capabilities,
            thread_id=thread_id,
            task_id=task_id,
        )
        for match in matches
    ]


async def get_thread_target_state(thread_id: str) -> ThreadTargetState:
    """Read target bindings from thread context."""
    manager = ThreadManager(redis_client=get_redis_client())
    thread = await manager.get_thread(thread_id)
    if not thread:
        return ThreadTargetState()

    bindings: List[TargetBinding] = []
    raw_bindings = thread.context.get("target_bindings") or []
    if isinstance(raw_bindings, list):
        for raw_binding in raw_bindings:
            try:
                bindings.append(TargetBinding.model_validate(raw_binding))
            except Exception:
                continue

    raw_handles = thread.context.get("attached_target_handles") or []
    attached_handles = (
        [str(handle) for handle in raw_handles] if isinstance(raw_handles, list) else []
    )
    active_handle = thread.context.get("active_target_handle")
    try:
        generation = int(thread.context.get("target_toolset_generation") or 0)
    except Exception:
        generation = 0

    return ThreadTargetState(
        attached_target_handles=attached_handles,
        active_target_handle=str(active_handle) if active_handle else None,
        target_toolset_generation=generation,
        target_bindings=bindings,
    )


async def attach_target_matches(
    *,
    thread_id: str,
    matches: Sequence[ResolvedTargetMatch],
    task_id: Optional[str] = None,
    replace_existing: bool = False,
) -> tuple[List[TargetBinding], int]:
    """Persist safe target handles on a thread and return attached bindings."""
    thread_manager = ThreadManager(redis_client=get_redis_client())
    current_state = await get_thread_target_state(thread_id)

    existing_by_resource = {
        (binding.target_kind, binding.resource_id): binding
        for binding in current_state.target_bindings
    }
    attached_bindings = [] if replace_existing else list(current_state.target_bindings)
    attached_by_handle = {binding.target_handle: binding for binding in attached_bindings}
    selected_bindings: List[TargetBinding] = []

    for match in matches:
        binding = existing_by_resource.get((match.target_kind, match.resource_id))
        if binding is None:
            binding = TargetBinding(
                target_handle=f"tgt_{ULID()}",
                target_kind=match.target_kind,
                resource_id=match.resource_id,
                display_name=match.display_name,
                capabilities=match.capabilities,
                thread_id=thread_id,
                task_id=task_id,
            )
        if binding.target_handle not in attached_by_handle:
            attached_bindings.append(binding)
            attached_by_handle[binding.target_handle] = binding
        selected_bindings.append(binding)

    bindings_to_store = selected_bindings if replace_existing else attached_bindings
    active_handle = (
        selected_bindings[0].target_handle
        if selected_bindings
        else current_state.active_target_handle
    )
    generation = max(1, current_state.target_toolset_generation) + (1 if selected_bindings else 0)
    context_updates = build_bound_target_scope_context(
        bindings_to_store,
        generation=generation,
        active_handle=active_handle,
    )

    await thread_manager.update_thread_context(thread_id, context_updates, merge=True)
    return selected_bindings, generation


async def materialize_bound_target_scope(
    *,
    matches: Sequence[ResolvedTargetMatch],
    thread_id: Optional[str] = None,
    task_id: Optional[str] = None,
    replace_existing: bool = False,
) -> MaterializedTargetScope:
    """Resolve target matches into one authoritative bound-scope payload."""
    if thread_id:
        selected_bindings, generation = await attach_target_matches(
            thread_id=thread_id,
            matches=matches,
            task_id=task_id,
            replace_existing=replace_existing,
        )
        state = await get_thread_target_state(thread_id)
        attached_bindings = list(state.target_bindings)
        active_handle = state.active_target_handle
    else:
        selected_bindings = build_ephemeral_target_bindings(
            matches,
            thread_id=thread_id,
            task_id=task_id,
        )
        attached_bindings = list(selected_bindings)
        generation = 0
        active_handle = selected_bindings[0].target_handle if selected_bindings else None

    return MaterializedTargetScope(
        selected_bindings=list(selected_bindings),
        attached_bindings=attached_bindings,
        target_toolset_generation=generation,
        context_updates=build_bound_target_scope_context(
            attached_bindings,
            generation=generation,
            active_handle=active_handle,
        ),
    )


async def bind_target_matches(
    *,
    matches: Sequence[ResolvedTargetMatch],
    thread_id: Optional[str] = None,
    task_id: Optional[str] = None,
    replace_existing: bool = False,
    manager: Optional[Any] = None,
) -> BoundTargetScope:
    """Bind resolved matches through the shared attached-target flow."""
    materialized = await materialize_bound_target_scope(
        matches=matches,
        thread_id=thread_id,
        task_id=task_id,
        replace_existing=replace_existing,
    )
    attached_bindings = list(materialized.attached_bindings)
    generation = materialized.target_toolset_generation

    if manager and attached_bindings:
        if thread_id:
            await manager.attach_bound_targets(attached_bindings, generation=generation)
        else:
            await manager.attach_bound_targets(attached_bindings)
        updated_generation = manager.get_toolset_generation()
        if inspect.isawaitable(updated_generation):
            updated_generation = await updated_generation
        generation = int(updated_generation)

    return BoundTargetScope(
        bindings=attached_bindings,
        toolset_generation=generation,
        context_updates=build_bound_target_scope_context(
            attached_bindings,
            generation=generation,
            active_handle=materialized.context_updates.get("active_target_handle"),
        ),
    )
