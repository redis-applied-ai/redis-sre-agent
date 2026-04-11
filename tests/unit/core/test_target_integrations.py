"""Unit tests for target integration registry, services, bindings, and handle storage."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from time import sleep
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from redis_sre_agent.core.config import (
    TargetIntegrationComponentConfig,
    TargetIntegrationsConfig,
    settings,
)
from redis_sre_agent.core.targets import build_public_match_from_doc, build_seed_hint_candidates
from redis_sre_agent.targets.contracts import (
    BindingRequest,
    DiscoveryCandidate,
    DiscoveryRequest,
    DiscoveryResponse,
    PublicTargetBinding,
    PublicTargetMatch,
    TargetHandleRecord,
)
from redis_sre_agent.targets.handle_store import (
    RedisTargetHandleStore,
    get_target_handle_store,
    reset_target_handle_store,
)
from redis_sre_agent.targets.redis_binding import RedisDataClientFactory, RedisTargetBindingStrategy
from redis_sre_agent.targets.registry import (
    TargetIntegrationRegistry,
    get_target_integration_registry,
    reset_target_integration_registry,
)
from redis_sre_agent.targets.services import TargetBindingService, TargetDiscoveryService


class MockDiscoveryBackend:
    backend_name = "mock_backend"

    async def resolve(self, request: DiscoveryRequest) -> DiscoveryResponse:
        public_match = PublicTargetMatch(
            target_kind="instance",
            display_name="mock-cache",
            environment="test",
            target_type="oss_single",
            capabilities=["redis"],
            confidence=0.9,
            match_reasons=["mocked"],
            public_metadata={"environment": "test"},
            resource_id="mock-private-id",
        )
        return DiscoveryResponse(
            status="resolved",
            clarification_required=False,
            matches=[public_match],
            selected_matches=[
                DiscoveryCandidate(
                    public_match=public_match,
                    binding_strategy="mock_strategy",
                    binding_subject="mock-private-id",
                    private_binding_ref={"source": "mock"},
                    discovery_backend="mock_backend",
                    score=9.0,
                    confidence=0.9,
                )
            ],
        )


class BrokenDiscoveryBackend:
    backend_name = "broken_backend"

    async def resolve(self, request: DiscoveryRequest) -> DiscoveryResponse:
        public_match = PublicTargetMatch(
            target_kind="instance",
            display_name="broken-cache",
            environment="test",
            target_type="oss_single",
            capabilities=["redis"],
            confidence=0.9,
            match_reasons=["mocked"],
            resource_id="broken-private-id",
        )
        return DiscoveryResponse(
            status="resolved",
            matches=[public_match],
            selected_matches=[
                DiscoveryCandidate(
                    public_match=public_match,
                    binding_strategy="missing_strategy",
                    binding_subject="broken-private-id",
                    discovery_backend="broken_backend",
                    score=9.0,
                    confidence=0.9,
                )
            ],
        )


class MockBindingStrategy:
    strategy_name = "mock_strategy"

    async def bind(self, request):  # pragma: no cover - registry lookup only
        raise AssertionError("bind() should not be called in this test")


class FakePipeline:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, int]] = []
        self.executed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def set(self, key: str, value: str, ex: int):
        self.calls.append((key, value, ex))
        return self

    async def execute(self) -> None:
        self.executed = True


def test_public_target_match_serialization_strips_duplicate_metadata_fields():
    doc = SimpleNamespace(
        target_kind="instance",
        display_name="checkout-cache-prod",
        environment="production",
        target_type="oss_single",
        capabilities=["redis", "diagnostics"],
        usage="cache",
        status="healthy",
        resource_id="redis-prod-checkout-cache",
    )

    public_match = build_public_match_from_doc(doc)
    payload = public_match.public_dump()

    assert payload["environment"] == "production"
    assert payload["target_type"] == "oss_single"
    assert payload["public_metadata"] == {"usage": "cache", "status": "healthy"}

    binding = TargetBindingService.build_public_binding(
        DiscoveryCandidate.from_public_match(
            public_match,
            binding_strategy="redis_default",
            binding_subject="redis-prod-checkout-cache",
            discovery_backend="redis_catalog",
        ),
        thread_id="thread-1",
        task_id="task-1",
    )

    assert binding.public_metadata == {
        "environment": "production",
        "target_type": "oss_single",
        "usage": "cache",
        "status": "healthy",
    }


@pytest.mark.asyncio
async def test_target_discovery_service_validates_registered_binding_strategy():
    registry = TargetIntegrationRegistry(
        default_discovery_backend="mock_backend",
        default_binding_strategy="mock_strategy",
    )
    registry.register_discovery_backend(MockDiscoveryBackend())
    registry.register_binding_strategy(MockBindingStrategy())

    response = await TargetDiscoveryService(registry=registry).resolve(
        DiscoveryRequest(query="mock cache")
    )

    assert response.status == "resolved"
    assert response.selected_matches[0].binding_strategy == "mock_strategy"


@pytest.mark.asyncio
async def test_target_discovery_service_rejects_unknown_binding_strategy():
    registry = TargetIntegrationRegistry(
        default_discovery_backend="broken_backend",
        default_binding_strategy="mock_strategy",
    )
    registry.register_discovery_backend(BrokenDiscoveryBackend())

    with pytest.raises(ValueError, match="Unknown target binding strategy"):
        await TargetDiscoveryService(registry=registry).resolve(DiscoveryRequest(query="broken"))


@pytest.mark.asyncio
async def test_target_binding_service_persists_private_handle_records():
    handle_store = AsyncMock()
    service = TargetBindingService(handle_store=handle_store)
    public_match = PublicTargetMatch(
        target_kind="instance",
        display_name="mock-cache",
        environment="test",
        target_type="oss_single",
        capabilities=["redis"],
        confidence=0.9,
        match_reasons=["mocked"],
        public_metadata={"environment": "test"},
        resource_id="mock-private-id",
    )

    bindings = await service.build_and_persist_records(
        [
            DiscoveryCandidate(
                public_match=public_match,
                binding_strategy="mock_strategy",
                binding_subject="mock-private-id",
                private_binding_ref={"source": "mock"},
                discovery_backend="mock_backend",
                score=9.0,
                confidence=0.9,
            )
        ],
        thread_id="thread-1",
        task_id="task-1",
    )

    assert len(bindings) == 1
    handle_store.save_records.assert_awaited_once()


@pytest.mark.asyncio
async def test_build_seed_hint_candidates_maps_legacy_instance_ids_to_private_candidates():
    instance = AsyncMock()
    instance.id = "redis-prod-checkout-cache"
    instance.name = "checkout-cache-prod"
    instance.environment = "production"
    instance.status = "healthy"
    instance.instance_type = "oss_single"
    instance.usage = "cache"
    instance.description = "Checkout cache"
    instance.notes = None
    instance.repo_url = None
    instance.monitoring_identifier = None
    instance.logging_identifier = None
    instance.redis_cloud_subscription_id = None
    instance.redis_cloud_database_id = None
    instance.redis_cloud_database_name = None
    instance.cluster_id = None
    instance.updated_at = "2026-04-10T00:00:00+00:00"
    instance.created_at = "2026-04-10T00:00:00+00:00"
    instance.user_id = None
    instance.extension_data = {"target_discovery": {"aliases": ["checkout cache"]}}

    with patch(
        "redis_sre_agent.core.targets.get_instance_by_id",
        new_callable=AsyncMock,
        return_value=instance,
    ):
        candidates = await build_seed_hint_candidates(instance_id="redis-prod-checkout-cache")

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.binding_subject == "redis-prod-checkout-cache"
    assert candidate.private_binding_ref["seed_hint"] is True
    assert candidate.public_match.display_name == "checkout-cache-prod"
    assert candidate.public_match.environment == "production"
    assert candidate.public_match.target_type == "oss_single"
    assert candidate.public_match.public_metadata == {
        "usage": "cache",
        "status": "healthy",
    }


@pytest.mark.asyncio
async def test_build_seed_hint_candidates_uses_configured_registry_defaults():
    fake_registry = SimpleNamespace(
        default_binding_strategy="fake_strategy",
        default_discovery_backend="fake_backend",
    )

    with patch(
        "redis_sre_agent.core.targets.get_target_integration_registry",
        return_value=fake_registry,
    ):
        candidates = await build_seed_hint_candidates(instance_id="redis-prod-checkout-cache")

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.binding_strategy == "fake_strategy"
    assert candidate.discovery_backend == "fake_backend"
    assert candidate.binding_subject == "redis-prod-checkout-cache"


def test_discovery_candidate_from_public_match_uses_registry_defaults():
    public_match = PublicTargetMatch(
        target_kind="instance",
        display_name="mock-cache",
        capabilities=["redis"],
        confidence=0.9,
        resource_id="mock-private-id",
    )
    fake_registry = SimpleNamespace(
        default_binding_strategy="fake_strategy",
        default_discovery_backend="fake_backend",
    )

    with patch(
        "redis_sre_agent.targets.registry.get_target_integration_registry",
        return_value=fake_registry,
    ):
        candidate = DiscoveryCandidate.from_public_match(public_match)

    assert candidate.binding_strategy == "fake_strategy"
    assert candidate.discovery_backend == "fake_backend"
    assert candidate.binding_subject == "mock-private-id"


def test_discovery_candidate_from_public_match_skips_registry_when_defaults_are_explicit():
    public_match = PublicTargetMatch(
        target_kind="instance",
        display_name="mock-cache",
        capabilities=["redis"],
        confidence=0.9,
        resource_id="mock-private-id",
    )

    with patch(
        "redis_sre_agent.targets.contracts.DiscoveryCandidate._resolve_default_integration_names",
        side_effect=AssertionError("registry defaults should not be resolved"),
    ):
        candidate = DiscoveryCandidate.from_public_match(
            public_match,
            binding_strategy="explicit_strategy",
            binding_subject="explicit-subject",
            private_binding_ref={"source": "explicit"},
            discovery_backend="explicit_backend",
        )

    assert candidate.binding_strategy == "explicit_strategy"
    assert candidate.discovery_backend == "explicit_backend"
    assert candidate.binding_subject == "explicit-subject"
    assert candidate.private_binding_ref == {"source": "explicit"}


@pytest.mark.asyncio
async def test_target_binding_service_normalizes_public_matches_with_registry_defaults():
    handle_store = AsyncMock()
    fake_registry = SimpleNamespace(
        default_binding_strategy="fake_strategy",
        default_discovery_backend="fake_backend",
    )
    service = TargetBindingService(registry=fake_registry, handle_store=handle_store)
    public_match = PublicTargetMatch(
        target_kind="instance",
        display_name="mock-cache",
        capabilities=["redis"],
        confidence=0.9,
        public_metadata={"environment": "test"},
        resource_id="mock-private-id",
    )

    with patch(
        "redis_sre_agent.targets.registry.get_target_integration_registry",
        return_value=fake_registry,
    ):
        bindings = await service.build_and_persist_records(
            [public_match],
            thread_id="thread-1",
            task_id="task-1",
        )

    saved_record = handle_store.save_records.await_args.args[0][0]
    assert len(bindings) == 1
    assert saved_record.binding_strategy == "fake_strategy"
    assert saved_record.discovery_backend == "fake_backend"
    assert saved_record.binding_subject == "mock-private-id"


@pytest.mark.asyncio
async def test_redis_data_client_factory_builds_handle_scoped_instance():
    from redis_sre_agent.core.instances import RedisInstance

    instance = RedisInstance(
        id="redis-prod-checkout-cache",
        name="checkout-cache-prod",
        connection_url="redis://localhost:6379",
        environment="production",
        usage="cache",
        description="Checkout cache",
        instance_type="oss_single",
    )
    handle_record = TargetHandleRecord(
        target_handle="tgt_01",
        discovery_backend="redis_catalog",
        binding_strategy="redis_default",
        binding_subject=instance.id,
        public_summary=PublicTargetBinding(
            target_handle="tgt_01",
            target_kind="instance",
            display_name=instance.name,
            capabilities=["redis"],
        ),
    )

    with patch(
        "redis_sre_agent.targets.redis_binding.get_instance_by_id",
        new_callable=AsyncMock,
        return_value=instance,
    ):
        built = await RedisDataClientFactory().build(handle_record)

    assert built is not None
    assert built.id == "tgt_01"
    assert built.connection_url == instance.connection_url


@pytest.mark.asyncio
async def test_redis_target_binding_strategy_builds_provider_loads_for_instance():
    handle_record = TargetHandleRecord(
        target_handle="tgt_01",
        discovery_backend="redis_catalog",
        binding_strategy="redis_default",
        binding_subject="redis-prod-checkout-cache",
        public_summary=PublicTargetBinding(
            target_handle="tgt_01",
            target_kind="instance",
            display_name="checkout-cache-prod",
            capabilities=["redis", "diagnostics"],
        ),
    )
    data_instance = SimpleNamespace(id="tgt_01")

    class StubRegistry:
        def get_client_factory(self, family: str):
            mapping = {
                "redis.data": SimpleNamespace(build=AsyncMock(return_value=data_instance)),
                "redis.enterprise_admin": SimpleNamespace(build=AsyncMock(return_value=None)),
                "redis.cloud": SimpleNamespace(build=AsyncMock(return_value=None)),
            }
            return mapping[family]

    with (
        patch(
            "redis_sre_agent.targets.registry.get_target_integration_registry",
            return_value=StubRegistry(),
        ),
        patch(
            "redis_sre_agent.targets.redis_binding.settings",
            new=SimpleNamespace(
                tool_providers=[
                    "redis_sre_agent.tools.diagnostics.redis_command.provider.RedisCommandToolProvider",
                    "redis_sre_agent.tools.metrics.prometheus.provider.PrometheusToolProvider",
                ]
            ),
        ),
    ):
        result = await RedisTargetBindingStrategy().bind(
            BindingRequest(handle_record=handle_record)
        )

    assert result.public_summary.target_handle == "tgt_01"
    assert result.client_refs["redis.data"] is data_instance
    assert len(result.provider_loads) == 2
    assert {load.provider_path for load in result.provider_loads} == {
        "redis_sre_agent.tools.diagnostics.redis_command.provider.RedisCommandToolProvider",
        "redis_sre_agent.tools.metrics.prometheus.provider.PrometheusToolProvider",
    }


@pytest.mark.asyncio
async def test_redis_target_handle_store_sets_ttl_and_round_trips_records():
    fake_client = AsyncMock()
    store = RedisTargetHandleStore()
    record = TargetHandleRecord(
        target_handle="tgt_01",
        discovery_backend="redis_catalog",
        binding_strategy="redis_default",
        binding_subject="redis-prod-checkout-cache",
        public_summary=PublicTargetBinding(
            target_handle="tgt_01",
            target_kind="instance",
            display_name="checkout-cache-prod",
            capabilities=["redis"],
        ),
        expires_at=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
    )

    stored_payload: dict[str, str] = {}

    async def _set(key: str, value: str, ex: int):
        stored_payload["key"] = key
        stored_payload["value"] = value
        stored_payload["ttl"] = ex

    fake_client.set.side_effect = _set
    fake_client.get.return_value = None

    with patch("redis_sre_agent.targets.handle_store.get_redis_client", return_value=fake_client):
        await store.save_record(record)
        fake_client.get.return_value = stored_payload["value"]
        loaded = await store.get_record("tgt_01")

    assert stored_payload["key"].endswith(":tgt_01")
    assert stored_payload["ttl"] > 0
    assert loaded is not None
    assert loaded.binding_subject == "redis-prod-checkout-cache"
    assert loaded.public_summary.display_name == "checkout-cache-prod"


@pytest.mark.asyncio
async def test_redis_target_handle_store_logs_save_failures_at_warning_level():
    fake_client = AsyncMock()
    fake_client.set.side_effect = RuntimeError("redis unavailable")
    store = RedisTargetHandleStore()
    record = TargetHandleRecord(
        target_handle="tgt_01",
        discovery_backend="redis_catalog",
        binding_strategy="redis_default",
        binding_subject="redis-prod-checkout-cache",
        public_summary=PublicTargetBinding(
            target_handle="tgt_01",
            target_kind="instance",
            display_name="checkout-cache-prod",
            capabilities=["redis"],
        ),
    )

    with (
        patch("redis_sre_agent.targets.handle_store.get_redis_client", return_value=fake_client),
        patch("redis_sre_agent.targets.handle_store.logger.warning") as mock_warning,
    ):
        await store.save_record(record)

    mock_warning.assert_called_once()
    assert "saving %s" in mock_warning.call_args.args[0]
    assert mock_warning.call_args.args[1] == "tgt_01"
    assert mock_warning.call_args.kwargs["exc_info"] is True


@pytest.mark.asyncio
async def test_redis_target_handle_store_batches_save_records_with_pipeline():
    fake_pipeline = FakePipeline()
    fake_client = AsyncMock()
    fake_client.pipeline = MagicMock(return_value=fake_pipeline)
    store = RedisTargetHandleStore()
    records = [
        TargetHandleRecord(
            target_handle="tgt_01",
            discovery_backend="redis_catalog",
            binding_strategy="redis_default",
            binding_subject="redis-prod-checkout-cache",
            public_summary=PublicTargetBinding(
                target_handle="tgt_01",
                target_kind="instance",
                display_name="checkout-cache-prod",
                capabilities=["redis"],
            ),
        ),
        TargetHandleRecord(
            target_handle="tgt_02",
            discovery_backend="redis_catalog",
            binding_strategy="redis_default",
            binding_subject="redis-prod-session-cache",
            public_summary=PublicTargetBinding(
                target_handle="tgt_02",
                target_kind="instance",
                display_name="session-cache-prod",
                capabilities=["redis"],
            ),
        ),
    ]

    with patch("redis_sre_agent.targets.handle_store.get_redis_client", return_value=fake_client):
        await store.save_records(records)

    fake_client.pipeline.assert_called_once_with(transaction=True)
    assert fake_pipeline.executed is True
    assert [call[0] for call in fake_pipeline.calls] == [
        "sre_target_handles:tgt_01",
        "sre_target_handles:tgt_02",
    ]


@pytest.mark.asyncio
async def test_redis_target_handle_store_batches_get_records_with_mget():
    fake_client = AsyncMock()
    store = RedisTargetHandleStore()
    record_one = TargetHandleRecord(
        target_handle="tgt_01",
        discovery_backend="redis_catalog",
        binding_strategy="redis_default",
        binding_subject="redis-prod-checkout-cache",
        public_summary=PublicTargetBinding(
            target_handle="tgt_01",
            target_kind="instance",
            display_name="checkout-cache-prod",
            capabilities=["redis"],
        ),
    )
    record_two = TargetHandleRecord(
        target_handle="tgt_02",
        discovery_backend="redis_catalog",
        binding_strategy="redis_default",
        binding_subject="redis-prod-session-cache",
        public_summary=PublicTargetBinding(
            target_handle="tgt_02",
            target_kind="instance",
            display_name="session-cache-prod",
            capabilities=["redis"],
        ),
    )
    fake_client.mget.return_value = [
        record_one.model_dump_json(),
        None,
        record_two.model_dump_json(),
    ]

    with patch("redis_sre_agent.targets.handle_store.get_redis_client", return_value=fake_client):
        records = await store.get_records(["tgt_01", "missing", "tgt_02"])

    fake_client.mget.assert_awaited_once_with(
        "sre_target_handles:tgt_01",
        "sre_target_handles:missing",
        "sre_target_handles:tgt_02",
    )
    assert set(records) == {"tgt_01", "tgt_02"}
    assert records["tgt_01"].binding_subject == "redis-prod-checkout-cache"
    assert records["tgt_02"].binding_subject == "redis-prod-session-cache"


@pytest.mark.asyncio
async def test_registry_from_settings_loads_fake_target_components(monkeypatch):
    fake_integrations = TargetIntegrationsConfig(
        default_discovery_backend="fake_demo",
        default_binding_strategy="fake_authenticated",
        discovery_backends={
            "fake_demo": TargetIntegrationComponentConfig(
                class_path="redis_sre_agent.targets.fake_integration.FakeTargetDiscoveryBackend",
                config={
                    "targets": [
                        {
                            "display_name": "demo fake cache",
                            "binding_subject": "fake-demo-cache",
                            "aliases": ["demo cache"],
                            "environment": "test",
                            "username": "demo-user",
                            "token": "demo-token",
                        }
                    ]
                },
            )
        },
        binding_strategies={
            "fake_authenticated": TargetIntegrationComponentConfig(
                class_path="redis_sre_agent.targets.fake_integration.FakeTargetBindingStrategy"
            )
        },
        client_factories={
            "fake.auth": TargetIntegrationComponentConfig(
                class_path="redis_sre_agent.targets.fake_integration.FakeAuthenticatedClientFactory"
            )
        },
    )
    monkeypatch.setattr(settings, "target_integrations", fake_integrations)
    reset_target_integration_registry()

    registry = TargetIntegrationRegistry.from_settings()
    response = await registry.get_discovery_backend().resolve(DiscoveryRequest(query="demo cache"))

    assert response.status == "resolved"
    assert response.selected_matches[0].binding_strategy == "fake_authenticated"

    binding_service = TargetBindingService(registry=registry, handle_store=AsyncMock())
    bindings = await binding_service.build_and_persist_records(
        response.selected_matches,
        thread_id="thread-1",
        task_id="task-1",
    )
    handle_record = binding_service.build_handle_record(response.selected_matches[0], bindings[0])

    binding_result = await registry.get_binding_strategy("fake_authenticated").bind(
        BindingRequest(handle_record=handle_record)
    )

    assert binding_result.provider_loads[0].provider_path.endswith("FakeAuthenticatedToolProvider")
    fake_client = binding_result.client_refs["fake.auth"]
    assert fake_client.id == bindings[0].target_handle
    assert fake_client.extension_data["fake_target.username"] == "demo-user"


@pytest.mark.asyncio
async def test_redis_catalog_backend_uses_registry_default_binding_strategy():
    from redis_sre_agent.core.targets import TargetCatalogDoc
    from redis_sre_agent.targets.redis_catalog import RedisCatalogDiscoveryBackend

    registry = TargetIntegrationRegistry(
        default_discovery_backend="redis_catalog",
        default_binding_strategy="custom_default",
    )
    backend = RedisCatalogDiscoveryBackend()
    doc = TargetCatalogDoc(
        target_id="target-1",
        target_kind="instance",
        resource_id="instance-1",
        display_name="primary cache",
        name="primary-cache",
        capabilities=["redis"],
    )

    with (
        patch(
            "redis_sre_agent.targets.redis_catalog.get_target_integration_registry",
            return_value=registry,
        ),
        patch(
            "redis_sre_agent.core.targets.get_target_catalog",
            new=AsyncMock(return_value=[doc]),
        ),
    ):
        result = await backend.resolve(DiscoveryRequest(query="primary cache"))

    assert result.selected_matches
    assert result.selected_matches[0].binding_strategy == "custom_default"


@pytest.mark.asyncio
async def test_fake_backend_returns_candidates_when_clarification_is_required():
    from redis_sre_agent.targets.fake_integration import FakeTargetDiscoveryBackend

    backend = FakeTargetDiscoveryBackend(
        targets=[
            {
                "display_name": "demo fake cache one",
                "binding_subject": "fake-demo-cache-1",
                "aliases": ["demo cache"],
            },
            {
                "display_name": "demo fake cache two",
                "binding_subject": "fake-demo-cache-2",
                "aliases": ["demo cache"],
            },
        ]
    )

    result = await backend.resolve(DiscoveryRequest(query="demo cache", allow_multiple=False))

    assert result.status == "clarification_required"
    assert result.clarification_required is True
    assert len(result.selected_matches) == 2


def test_reset_target_integration_registry_clears_cached_singleton():
    reset_target_integration_registry()
    first = get_target_integration_registry()
    second = get_target_integration_registry()

    assert first is second

    reset_target_integration_registry()
    third = get_target_integration_registry()

    assert third is not first
    reset_target_integration_registry()


def test_target_integration_registry_singleton_initializes_once_under_concurrency():
    reset_target_integration_registry()
    created: list[TargetIntegrationRegistry] = []

    def _build_registry() -> TargetIntegrationRegistry:
        sleep(0.01)
        registry = TargetIntegrationRegistry(
            default_discovery_backend="redis_catalog",
            default_binding_strategy="redis_default",
        )
        created.append(registry)
        return registry

    with patch(
        "redis_sre_agent.targets.registry.TargetIntegrationRegistry.from_settings",
        side_effect=_build_registry,
    ):
        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(lambda _: get_target_integration_registry(), range(4)))

    assert len(created) == 1
    assert len({id(result) for result in results}) == 1
    reset_target_integration_registry()


def test_reset_target_handle_store_clears_cached_singleton():
    reset_target_handle_store()
    first = get_target_handle_store()
    second = get_target_handle_store()

    assert first is second

    reset_target_handle_store()
    third = get_target_handle_store()

    assert third is not first
    reset_target_handle_store()


def test_target_handle_store_singleton_initializes_once_under_concurrency():
    reset_target_handle_store()
    created: list[RedisTargetHandleStore] = []

    def _build_store() -> RedisTargetHandleStore:
        sleep(0.01)
        store = RedisTargetHandleStore()
        created.append(store)
        return store

    with patch(
        "redis_sre_agent.targets.handle_store.RedisTargetHandleStore",
        side_effect=_build_store,
    ):
        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(lambda _: get_target_handle_store(), range(4)))

    assert len(created) == 1
    assert len({id(result) for result in results}) == 1
    reset_target_handle_store()
