"""Registry for target discovery, binding, and client factories."""

from __future__ import annotations

import importlib
from typing import Any, Dict, Optional

from redis_sre_agent.core.config import settings

from .contracts import (
    AuthenticatedClientFactory,
    DiscoveryCandidate,
    TargetBindingStrategy,
    TargetDiscoveryBackend,
)

_DEFAULT_REGISTRY: "TargetIntegrationRegistry | None" = None


def _load_object(class_path: str) -> Any:
    module_path, attr_name = class_path.rsplit(".", 1)
    module = importlib.import_module(module_path)
    return getattr(module, attr_name)


class TargetIntegrationRegistry:
    """Runtime registry for target integrations."""

    def __init__(
        self,
        *,
        default_discovery_backend: str,
        default_binding_strategy: str,
    ) -> None:
        self.default_discovery_backend = default_discovery_backend
        self.default_binding_strategy = default_binding_strategy
        self._discovery_backends: Dict[str, TargetDiscoveryBackend] = {}
        self._binding_strategies: Dict[str, TargetBindingStrategy] = {}
        self._client_factories: Dict[str, AuthenticatedClientFactory] = {}

    def register_discovery_backend(
        self, backend: TargetDiscoveryBackend, *, name: Optional[str] = None
    ) -> None:
        self._discovery_backends[name or backend.backend_name] = backend

    def register_binding_strategy(
        self, strategy: TargetBindingStrategy, *, name: Optional[str] = None
    ) -> None:
        self._binding_strategies[name or strategy.strategy_name] = strategy

    def register_client_factory(
        self, factory: AuthenticatedClientFactory, *, family: Optional[str] = None
    ) -> None:
        self._client_factories[family or factory.client_family] = factory

    def get_discovery_backend(self, name: Optional[str] = None) -> TargetDiscoveryBackend:
        backend_name = name or self.default_discovery_backend
        try:
            return self._discovery_backends[backend_name]
        except KeyError as exc:
            raise ValueError(f"Unknown target discovery backend: {backend_name}") from exc

    def get_binding_strategy(self, name: str) -> TargetBindingStrategy:
        try:
            return self._binding_strategies[name]
        except KeyError as exc:
            raise ValueError(f"Unknown target binding strategy: {name}") from exc

    def get_client_factory(self, family: str) -> AuthenticatedClientFactory:
        try:
            return self._client_factories[family]
        except KeyError as exc:
            raise ValueError(f"Unknown target client factory: {family}") from exc

    def validate_candidate(self, candidate: DiscoveryCandidate) -> None:
        self.get_binding_strategy(candidate.binding_strategy)

    @classmethod
    def from_settings(cls) -> "TargetIntegrationRegistry":
        integrations = settings.target_integrations
        registry = cls(
            default_discovery_backend=integrations.default_discovery_backend,
            default_binding_strategy=integrations.default_binding_strategy,
        )

        for name, config in integrations.discovery_backends.items():
            backend_cls = _load_object(config.class_path)
            kwargs = dict(config.config or {})
            registry.register_discovery_backend(backend_cls(**kwargs), name=name)

        for name, config in integrations.binding_strategies.items():
            strategy_cls = _load_object(config.class_path)
            kwargs = dict(config.config or {})
            registry.register_binding_strategy(strategy_cls(**kwargs), name=name)

        for family, config in integrations.client_factories.items():
            factory_cls = _load_object(config.class_path)
            kwargs = dict(config.config or {})
            registry.register_client_factory(factory_cls(**kwargs), family=family)

        return registry


def get_target_integration_registry() -> TargetIntegrationRegistry:
    """Return the default target integration registry."""
    global _DEFAULT_REGISTRY
    if _DEFAULT_REGISTRY is None:
        _DEFAULT_REGISTRY = TargetIntegrationRegistry.from_settings()
    return _DEFAULT_REGISTRY


def reset_target_integration_registry() -> None:
    """Clear the cached target integration registry singleton."""
    global _DEFAULT_REGISTRY
    _DEFAULT_REGISTRY = None
