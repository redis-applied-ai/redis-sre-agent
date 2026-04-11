"""Target discovery and binding services."""

from __future__ import annotations

from typing import Iterable, Optional, Sequence

from ulid import ULID

from .contracts import (
    DiscoveryCandidate,
    DiscoveryRequest,
    DiscoveryResponse,
    PublicTargetBinding,
    PublicTargetMatch,
    TargetHandleRecord,
)
from .handle_store import RedisTargetHandleStore, get_target_handle_store
from .registry import TargetIntegrationRegistry, get_target_integration_registry


class TargetDiscoveryService:
    """Resolve target queries through the registered discovery backend."""

    def __init__(self, *, registry: Optional[TargetIntegrationRegistry] = None) -> None:
        self.registry = registry or get_target_integration_registry()

    async def resolve(self, request: DiscoveryRequest) -> DiscoveryResponse:
        backend = self.registry.get_discovery_backend()
        response = await backend.resolve(request)
        for candidate in response.selected_matches:
            self.registry.validate_candidate(candidate)
        return response


class TargetBindingService:
    """Persist private handle records and build public binding summaries."""

    def __init__(
        self,
        *,
        registry: Optional[TargetIntegrationRegistry] = None,
        handle_store: Optional[RedisTargetHandleStore] = None,
    ) -> None:
        self.registry = registry or get_target_integration_registry()
        self.handle_store = handle_store or get_target_handle_store()

    @staticmethod
    def _normalize_candidate(
        candidate: DiscoveryCandidate | PublicTargetMatch,
    ) -> DiscoveryCandidate:
        if isinstance(candidate, DiscoveryCandidate):
            return candidate
        return DiscoveryCandidate.from_public_match(candidate)

    @classmethod
    def build_public_binding(
        cls,
        candidate: DiscoveryCandidate | PublicTargetMatch,
        *,
        thread_id: Optional[str],
        task_id: Optional[str],
        existing_handle: Optional[str] = None,
    ) -> PublicTargetBinding:
        normalized_candidate = cls._normalize_candidate(candidate)
        public_match = normalized_candidate.public_match
        public_metadata = dict(public_match.public_metadata or {})
        for key, value in (
            ("environment", public_match.environment),
            ("target_type", public_match.target_type),
        ):
            if value not in (None, ""):
                public_metadata.setdefault(key, value)
        return PublicTargetBinding(
            target_handle=existing_handle or f"tgt_{ULID()}",
            target_kind=public_match.target_kind,
            display_name=public_match.display_name,
            capabilities=list(public_match.capabilities or []),
            public_metadata=public_metadata,
            thread_id=thread_id,
            task_id=task_id,
            resource_id=public_match.resource_id,
        )

    @staticmethod
    def build_handle_record(
        candidate: DiscoveryCandidate | PublicTargetMatch,
        public_binding: PublicTargetBinding,
    ) -> TargetHandleRecord:
        normalized_candidate = TargetBindingService._normalize_candidate(candidate)
        return TargetHandleRecord(
            target_handle=public_binding.target_handle,
            discovery_backend=normalized_candidate.discovery_backend,
            binding_strategy=normalized_candidate.binding_strategy,
            binding_subject=normalized_candidate.binding_subject,
            private_binding_ref=dict(normalized_candidate.private_binding_ref or {}),
            public_summary=public_binding,
            thread_id=public_binding.thread_id,
            task_id=public_binding.task_id,
            expires_at=public_binding.expires_at,
        )

    async def persist_handle_records(self, records: Iterable[TargetHandleRecord]) -> None:
        await self.handle_store.save_records(records)

    async def get_handle_record(self, target_handle: str) -> Optional[TargetHandleRecord]:
        return await self.handle_store.get_record(target_handle)

    async def get_handle_records(
        self, target_handles: Iterable[str]
    ) -> dict[str, TargetHandleRecord]:
        return await self.handle_store.get_records(target_handles)

    async def build_and_persist_records(
        self,
        matches: Sequence[DiscoveryCandidate | PublicTargetMatch],
        *,
        thread_id: Optional[str],
        task_id: Optional[str],
        existing_by_subject: Optional[dict[tuple[str, str], PublicTargetBinding]] = None,
    ) -> list[PublicTargetBinding]:
        bindings: list[PublicTargetBinding] = []
        records: list[TargetHandleRecord] = []
        existing_lookup = existing_by_subject or {}
        for candidate in matches:
            normalized_candidate = self._normalize_candidate(candidate)
            subject_key = (
                normalized_candidate.public_match.target_kind,
                normalized_candidate.binding_subject,
            )
            existing = existing_lookup.get(subject_key)
            binding = self.build_public_binding(
                normalized_candidate,
                thread_id=thread_id,
                task_id=task_id,
                existing_handle=existing.target_handle if existing else None,
            )
            if existing and not binding.public_metadata:
                binding.public_metadata = dict(existing.public_metadata or {})
            bindings.append(binding)
            records.append(self.build_handle_record(normalized_candidate, binding))
        await self.persist_handle_records(records)
        return bindings
