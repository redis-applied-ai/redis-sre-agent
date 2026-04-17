"""Default Redis target binding strategy and client factories."""

from __future__ import annotations

import os
from typing import Any, List, Optional

from redis_sre_agent.core import clusters as core_clusters
from redis_sre_agent.core.config import settings
from redis_sre_agent.core.instances import RedisInstance, get_instance_by_id

from .contracts import BindingRequest, BindingResult, ProviderLoadRequest, TargetHandleRecord


def _eval_target_seed(handle_record: TargetHandleRecord) -> dict[str, Any] | None:
    seed = (handle_record.private_binding_ref or {}).get("eval_target_seed")
    return seed if isinstance(seed, dict) else None


def _build_seeded_instance(handle_record: TargetHandleRecord) -> RedisInstance | None:
    seed = _eval_target_seed(handle_record)
    if not seed or seed.get("seed_kind") != "instance":
        return None
    payload = dict(seed)
    payload["id"] = handle_record.target_handle
    payload.setdefault("created_by", "agent")
    payload.setdefault("user_id", "eval")
    return RedisInstance.model_validate(payload)


def _build_seeded_cluster_admin_instance(handle_record: TargetHandleRecord) -> RedisInstance | None:
    seed = _eval_target_seed(handle_record)
    if not seed:
        return None

    if seed.get("seed_kind") == "instance":
        instance_type = str(seed.get("instance_type") or "").strip().lower()
        if instance_type != "redis_enterprise":
            return None
        payload = dict(seed)
        payload["id"] = handle_record.target_handle
        payload.setdefault("created_by", "agent")
        payload.setdefault("user_id", "eval")
        return RedisInstance.model_validate(payload)

    if seed.get("seed_kind") != "cluster":
        return None

    cluster_type = str(seed.get("cluster_type") or "").strip().lower()
    if cluster_type != "redis_enterprise":
        return None

    return RedisInstance.model_validate(
        {
            "id": handle_record.target_handle,
            "name": f"{seed.get('name') or handle_record.public_summary.display_name} (cluster admin)",
            "connection_url": "redis://cluster-only.invalid:6379",
            "environment": seed.get("environment") or "test",
            "usage": "custom",
            "description": seed.get("description")
            or f"Eval cluster admin target for {handle_record.public_summary.display_name}",
            "instance_type": "redis_enterprise",
            "cluster_id": seed.get("id") or handle_record.binding_subject,
            "admin_url": seed.get("admin_url") or "https://eval-target.invalid:9443",
            "admin_username": seed.get("admin_username") or "eval",
            "admin_password": seed.get("admin_password") or "eval-password",
            "monitoring_identifier": seed.get("name") or handle_record.public_summary.display_name,
            "logging_identifier": seed.get("name") or handle_record.public_summary.display_name,
            "notes": f"Eval cluster admin target for {handle_record.public_summary.display_name}",
            "created_by": "agent",
            "user_id": "eval",
        }
    )


class RedisDataClientFactory:
    """Return a RedisInstance for instance-scoped provider loads."""

    client_family = "redis.data"

    async def build(self, handle_record: TargetHandleRecord) -> Any:
        if handle_record.public_summary.target_kind != "instance":
            return None
        instance = await get_instance_by_id(handle_record.binding_subject)
        if instance is None:
            return _build_seeded_instance(handle_record)
        return instance.model_copy(update={"id": handle_record.target_handle})


class RedisEnterpriseAdminClientFactory:
    """Return an effective Redis Enterprise admin instance."""

    client_family = "redis.enterprise_admin"

    @staticmethod
    def _build_cluster_admin_instance(
        cluster: "core_clusters.RedisCluster",
        *,
        target_handle: str,
    ) -> Optional[RedisInstance]:
        cluster_type = (
            cluster.cluster_type.value
            if hasattr(cluster.cluster_type, "value")
            else str(cluster.cluster_type or "").strip().lower()
        )
        has_admin_url = bool((cluster.admin_url or "").strip())
        has_admin_username = bool((cluster.admin_username or "").strip())
        has_admin_password = bool(cluster.admin_password)
        if cluster_type != "redis_enterprise" or not (
            has_admin_url and has_admin_username and has_admin_password
        ):
            return None
        connection_host = (cluster.admin_url or "").strip()
        return RedisInstance(
            id=target_handle,
            name=f"{cluster.name} (cluster admin)",
            connection_url="redis://cluster-only.invalid:6379",
            environment=cluster.environment,
            usage="custom",
            description=f"Synthetic cluster admin target for {cluster.name}",
            instance_type="redis_enterprise",
            cluster_id=cluster.id,
            admin_url=cluster.admin_url,
            admin_username=cluster.admin_username,
            admin_password=cluster.admin_password,
            monitoring_identifier=cluster.name,
            logging_identifier=cluster.name,
            notes=f"Cluster-scoped admin tooling target for {connection_host}",
            created_by="agent",
            user_id=cluster.user_id,
        )

    async def build(self, handle_record: TargetHandleRecord) -> Any:
        public_summary = handle_record.public_summary
        if public_summary.target_kind == "cluster":
            cluster = await core_clusters.get_cluster_by_id(handle_record.binding_subject)
            if cluster is None:
                return _build_seeded_cluster_admin_instance(handle_record)
            return self._build_cluster_admin_instance(
                cluster, target_handle=handle_record.target_handle
            )

        instance = await get_instance_by_id(handle_record.binding_subject)
        if instance is None:
            return _build_seeded_cluster_admin_instance(handle_record)

        instance_type = (
            instance.instance_type.value
            if hasattr(instance.instance_type, "value")
            else instance.instance_type
        )
        if str(instance_type or "").strip().lower() != "redis_enterprise":
            return None

        cluster_id = (instance.cluster_id or "").strip()
        if cluster_id:
            cluster = await core_clusters.get_cluster_by_id(cluster_id)
            if cluster is not None:
                cluster_admin = self._build_cluster_admin_instance(
                    cluster, target_handle=handle_record.target_handle
                )
                if cluster_admin is not None:
                    return cluster_admin

        has_admin_url = bool((instance.admin_url or "").strip())
        if not has_admin_url:
            return None
        return instance.model_copy(update={"id": handle_record.target_handle})


class RedisCloudClientFactory:
    """Return a cloud-capable RedisInstance when cloud credentials are configured."""

    client_family = "redis.cloud"

    async def build(self, handle_record: TargetHandleRecord) -> Any:
        if handle_record.public_summary.target_kind != "instance":
            return None
        if not (
            os.getenv("TOOLS_REDIS_CLOUD_API_KEY") and os.getenv("TOOLS_REDIS_CLOUD_API_SECRET_KEY")
        ):
            return None
        instance = await get_instance_by_id(handle_record.binding_subject)
        if instance is None:
            instance = _build_seeded_instance(handle_record)
            if instance is None:
                return None
        instance_type = (
            instance.instance_type.value
            if hasattr(instance.instance_type, "value")
            else instance.instance_type
        )
        if str(instance_type or "").strip().lower() != "redis_cloud":
            return None
        return instance.model_copy(update={"id": handle_record.target_handle})


class RedisTargetBindingStrategy:
    """Default Redis binding strategy."""

    strategy_name = "redis_default"

    async def bind(self, request: BindingRequest) -> BindingResult:
        from .registry import get_target_integration_registry

        registry = get_target_integration_registry()
        handle_record = request.handle_record
        public_summary = handle_record.public_summary

        provider_loads: List[ProviderLoadRequest] = []
        client_refs: dict[str, Any] = {}

        if public_summary.target_kind == "instance":
            data_instance = await registry.get_client_factory("redis.data").build(handle_record)
            if data_instance is not None:
                client_refs["redis.data"] = data_instance
                for provider_path in settings.tool_providers:
                    provider_loads.append(
                        ProviderLoadRequest(
                            provider_path=provider_path,
                            provider_key=f"target:{public_summary.target_handle}:{provider_path}",
                            target_handle=public_summary.target_handle,
                            provider_context={"redis_instance_override": data_instance},
                        )
                    )

            admin_instance = await registry.get_client_factory("redis.enterprise_admin").build(
                handle_record
            )
            if admin_instance is not None:
                client_refs["redis.enterprise_admin"] = admin_instance
                provider_loads.append(
                    ProviderLoadRequest(
                        provider_path="redis_sre_agent.tools.admin.redis_enterprise.provider.RedisEnterpriseAdminToolProvider",
                        provider_key=f"target:{public_summary.target_handle}:enterprise_admin",
                        target_handle=public_summary.target_handle,
                        provider_context={"redis_instance_override": admin_instance},
                    )
                )

            cloud_instance = await registry.get_client_factory("redis.cloud").build(handle_record)
            if cloud_instance is not None:
                client_refs["redis.cloud"] = cloud_instance
                provider_loads.append(
                    ProviderLoadRequest(
                        provider_path="redis_sre_agent.tools.cloud.redis_cloud.provider.RedisCloudToolProvider",
                        provider_key=f"target:{public_summary.target_handle}:redis_cloud",
                        target_handle=public_summary.target_handle,
                        provider_context={"redis_instance_override": cloud_instance},
                    )
                )

        elif public_summary.target_kind == "cluster":
            admin_instance = await registry.get_client_factory("redis.enterprise_admin").build(
                handle_record
            )
            if admin_instance is not None:
                client_refs["redis.enterprise_admin"] = admin_instance
                provider_loads.append(
                    ProviderLoadRequest(
                        provider_path="redis_sre_agent.tools.admin.redis_enterprise.provider.RedisEnterpriseAdminToolProvider",
                        provider_key=f"target:{public_summary.target_handle}:enterprise_admin",
                        target_handle=public_summary.target_handle,
                        provider_context={"redis_instance_override": admin_instance},
                    )
                )

        return BindingResult(
            public_summary=public_summary,
            provider_loads=provider_loads,
            client_refs=client_refs,
        )
