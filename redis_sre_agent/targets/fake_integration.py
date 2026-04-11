"""Fake pluggable target integration used to prove runtime configurability."""

from __future__ import annotations

from typing import Any, Sequence

from pydantic import BaseModel, Field, SecretStr

from redis_sre_agent.core.instances import RedisInstance

from .contracts import (
    BindingRequest,
    BindingResult,
    DiscoveryCandidate,
    DiscoveryRequest,
    DiscoveryResponse,
    ProviderLoadRequest,
    PublicTargetMatch,
)


class FakeDiscoveryTarget(BaseModel):
    """Config for one fake target discovery record."""

    display_name: str
    binding_subject: str
    aliases: list[str] = Field(default_factory=list)
    target_kind: str = "instance"
    environment: str = "test"
    target_type: str = "fake"
    capabilities: list[str] = Field(default_factory=lambda: ["fake", "auth"])
    public_metadata: dict[str, Any] = Field(default_factory=dict)
    username: str = "demo-user"
    token: SecretStr = Field(default_factory=lambda: SecretStr("demo-token"))
    audience: str = "fake-control-plane"


class FakeTargetDiscoveryBackend:
    """Resolve targets from a configured in-memory catalog."""

    backend_name = "fake_demo"

    def __init__(
        self,
        *,
        targets: Sequence[dict[str, Any]] | None = None,
        binding_strategy: str = "fake_authenticated",
    ) -> None:
        configured_targets = targets or [
            {
                "display_name": "demo fake cache",
                "binding_subject": "fake-demo-cache",
                "aliases": ["demo cache", "fake cache"],
                "environment": "test",
                "public_metadata": {"owner": "demo"},
                "username": "demo-user",
                "token": "demo-token",
            }
        ]
        self.binding_strategy = binding_strategy
        self.targets = [FakeDiscoveryTarget.model_validate(target) for target in configured_targets]

    @staticmethod
    def _normalize(text: str) -> str:
        return " ".join((text or "").lower().split())

    def _match_score(self, query: str, target: FakeDiscoveryTarget) -> float | None:
        normalized_query = self._normalize(query)
        if not normalized_query:
            return None

        candidates = [target.display_name, target.binding_subject, *target.aliases]
        normalized_candidates = [
            self._normalize(candidate) for candidate in candidates if candidate
        ]
        if any(normalized_query == candidate for candidate in normalized_candidates):
            return 1.0
        if any(normalized_query in candidate for candidate in normalized_candidates):
            return 0.95
        query_tokens = normalized_query.split()
        if query_tokens and any(
            all(token in candidate for token in query_tokens) for candidate in normalized_candidates
        ):
            return 0.8
        return None

    def _build_candidate(self, target: FakeDiscoveryTarget, score: float) -> DiscoveryCandidate:
        public_metadata = {"audience": target.audience, **(target.public_metadata or {})}
        public_match = PublicTargetMatch(
            target_kind=target.target_kind,
            display_name=target.display_name,
            environment=target.environment,
            target_type=target.target_type,
            capabilities=list(target.capabilities or []),
            confidence=score,
            match_reasons=[f"matched fake target catalog score={score:.2f}"],
            public_metadata=public_metadata,
            resource_id=target.binding_subject,
            score=score,
        )
        return DiscoveryCandidate(
            public_match=public_match,
            binding_strategy=self.binding_strategy,
            binding_subject=target.binding_subject,
            private_binding_ref={
                "username": target.username,
                "token": target.token.get_secret_value(),
                "audience": target.audience,
            },
            discovery_backend=self.backend_name,
            score=score,
            confidence=score,
        )

    async def resolve(self, request: DiscoveryRequest) -> DiscoveryResponse:
        scored_candidates: list[tuple[float, DiscoveryCandidate]] = []
        for target in self.targets:
            score = self._match_score(request.query, target)
            if score is None:
                continue
            scored_candidates.append((score, self._build_candidate(target, score)))

        scored_candidates.sort(key=lambda item: item[0], reverse=True)
        candidates = [candidate for _, candidate in scored_candidates[: request.max_results]]
        matches = [candidate.public_match for candidate in candidates]
        if not candidates:
            return DiscoveryResponse(status="not_found", clarification_required=False, matches=[])
        if len(candidates) > 1 and not request.allow_multiple:
            return DiscoveryResponse(
                status="clarification_required",
                clarification_required=True,
                matches=matches,
                selected_matches=[],
            )
        selected = candidates if request.allow_multiple else candidates[:1]
        return DiscoveryResponse(
            status="resolved",
            clarification_required=False,
            matches=matches,
            selected_matches=selected,
        )


class FakeAuthenticatedClientFactory:
    """Build a fake authenticated target instance from a handle record."""

    client_family = "fake.auth"

    async def build(self, handle_record) -> Any:
        auth_ref = dict(handle_record.private_binding_ref or {})
        token = str(auth_ref.get("token") or "demo-token")
        username = str(auth_ref.get("username") or "demo-user")
        audience = str(auth_ref.get("audience") or "fake-control-plane")
        environment = str(handle_record.public_summary.public_metadata.get("environment") or "test")
        return RedisInstance(
            id=handle_record.target_handle,
            name=handle_record.public_summary.display_name,
            connection_url="redis://fake.invalid:6379/0",
            environment=environment,
            usage="custom",
            description=f"Fake authenticated target for {handle_record.public_summary.display_name}",
            instance_type="unknown",
            extension_data={
                "fake_target.username": username,
                "fake_target.audience": audience,
            },
            extension_secrets={"fake_target.token": SecretStr(token)},
        )


class FakeTargetBindingStrategy:
    """Bind fake targets through the fake auth client factory."""

    strategy_name = "fake_authenticated"

    def __init__(
        self,
        *,
        client_family: str = "fake.auth",
        provider_path: str = "redis_sre_agent.tools.fake.provider.FakeAuthenticatedToolProvider",
    ) -> None:
        self.client_family = client_family
        self.provider_path = provider_path

    async def bind(self, request: BindingRequest) -> BindingResult:
        from .registry import get_target_integration_registry

        registry = get_target_integration_registry()
        fake_instance = await registry.get_client_factory(self.client_family).build(
            request.handle_record
        )
        if fake_instance is None:
            return BindingResult(public_summary=request.handle_record.public_summary)

        handle = request.handle_record.target_handle
        return BindingResult(
            public_summary=request.handle_record.public_summary,
            provider_loads=[
                ProviderLoadRequest(
                    provider_path=self.provider_path,
                    provider_key=f"target:{handle}:fake_target",
                    target_handle=handle,
                    provider_context={"redis_instance_override": fake_instance},
                )
            ],
            client_refs={self.client_family: fake_instance},
        )
