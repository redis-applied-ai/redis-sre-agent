"""Pluggable Redis target discovery and binding runtime."""

from .contracts import (
    AuthenticatedClientFactory,
    BindingRequest,
    BindingResult,
    DiscoveryCandidate,
    DiscoveryRequest,
    DiscoveryResponse,
    ProviderLoadRequest,
    PublicTargetBinding,
    PublicTargetMatch,
    TargetBindingStrategy,
    TargetDiscoveryBackend,
    TargetHandleRecord,
)
from .fake_integration import (
    FakeAuthenticatedClientFactory,
    FakeTargetBindingStrategy,
    FakeTargetDiscoveryBackend,
)
from .handle_store import RedisTargetHandleStore, get_target_handle_store
from .registry import TargetIntegrationRegistry, get_target_integration_registry
from .services import TargetBindingService, TargetDiscoveryService

__all__ = [
    "AuthenticatedClientFactory",
    "BindingRequest",
    "BindingResult",
    "DiscoveryCandidate",
    "DiscoveryRequest",
    "DiscoveryResponse",
    "FakeAuthenticatedClientFactory",
    "FakeTargetBindingStrategy",
    "FakeTargetDiscoveryBackend",
    "ProviderLoadRequest",
    "PublicTargetBinding",
    "PublicTargetMatch",
    "RedisTargetHandleStore",
    "TargetBindingService",
    "TargetBindingStrategy",
    "TargetDiscoveryBackend",
    "TargetDiscoveryService",
    "TargetHandleRecord",
    "TargetIntegrationRegistry",
    "get_target_handle_store",
    "get_target_integration_registry",
]
