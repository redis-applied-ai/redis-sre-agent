"""Contracts and models for pluggable Redis target discovery and binding."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Protocol

from pydantic import BaseModel, Field, field_validator


class PublicTargetMatch(BaseModel):
    """Secret-safe target match shown to the model."""

    target_kind: str
    display_name: str
    environment: Optional[str] = None
    target_type: Optional[str] = None
    capabilities: List[str] = Field(default_factory=list)
    confidence: float
    match_reasons: List[str] = Field(default_factory=list)
    public_metadata: Dict[str, Any] = Field(default_factory=dict)
    resource_id: Optional[str] = Field(default=None, exclude=True)
    score: float = Field(default=0.0, exclude=True)


class PublicTargetBinding(BaseModel):
    """Public binding summary stored in thread context and shown to the model."""

    target_handle: str
    target_kind: str
    display_name: str
    capabilities: List[str] = Field(default_factory=list)
    public_metadata: Dict[str, Any] = Field(default_factory=dict)
    thread_id: Optional[str] = None
    task_id: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    expires_at: Optional[str] = Field(
        default_factory=lambda: (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
    )
    # Compatibility-only fallback while legacy seed-hint paths still exist.
    resource_id: Optional[str] = None

    def public_dump(self) -> Dict[str, Any]:
        """Return the thread-context binding payload."""
        return self.model_dump(mode="json")


class TargetHandleRecord(BaseModel):
    """Server-only record keyed by target_handle."""

    target_handle: str
    discovery_backend: str
    binding_strategy: str
    binding_subject: str
    private_binding_ref: Dict[str, Any] = Field(default_factory=dict)
    public_summary: PublicTargetBinding
    thread_id: Optional[str] = None
    task_id: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    expires_at: Optional[str] = Field(
        default_factory=lambda: (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
    )


class DiscoveryRequest(BaseModel):
    """Natural-language discovery request."""

    query: str
    allow_multiple: bool = False
    max_results: int = 5
    preferred_capabilities: List[str] = Field(default_factory=list)
    user_id: Optional[str] = None
    thread_id: Optional[str] = None
    task_id: Optional[str] = None


class DiscoveryCandidate(BaseModel):
    """Internal selected match with private binding metadata."""

    public_match: PublicTargetMatch
    binding_strategy: str
    binding_subject: str
    private_binding_ref: Dict[str, Any] = Field(default_factory=dict)
    discovery_backend: str
    score: float
    confidence: float

    @classmethod
    def from_public_match(
        cls,
        public_match: PublicTargetMatch,
        *,
        binding_strategy: str = "redis_default",
        binding_subject: Optional[str] = None,
        private_binding_ref: Optional[Dict[str, Any]] = None,
        discovery_backend: str = "redis_catalog",
    ) -> "DiscoveryCandidate":
        """Build an internal candidate from a public match payload."""
        return cls(
            public_match=public_match,
            binding_strategy=binding_strategy,
            binding_subject=binding_subject or public_match.resource_id or "",
            private_binding_ref=private_binding_ref or {"target_kind": public_match.target_kind},
            discovery_backend=discovery_backend,
            score=public_match.score,
            confidence=public_match.confidence,
        )

    @property
    def target_kind(self) -> str:
        return self.public_match.target_kind

    @property
    def display_name(self) -> str:
        return self.public_match.display_name

    @property
    def capabilities(self) -> List[str]:
        return list(self.public_match.capabilities or [])

    @property
    def resource_id(self) -> Optional[str]:
        return self.public_match.resource_id or self.binding_subject

    @property
    def match_reasons(self) -> List[str]:
        return list(self.public_match.match_reasons or [])


class DiscoveryResponse(BaseModel):
    """Public discovery response with private selected candidates excluded."""

    status: str
    clarification_required: bool = False
    matches: List[PublicTargetMatch] = Field(default_factory=list)
    attached_target_handles: List[str] = Field(default_factory=list)
    toolset_generation: int = 0
    selected_matches: List[DiscoveryCandidate] = Field(default_factory=list, exclude=True)

    @field_validator("selected_matches", mode="before")
    @classmethod
    def _coerce_selected_matches(cls, value: Any) -> Any:
        if not isinstance(value, list):
            return value
        coerced: List[Any] = []
        for item in value:
            if isinstance(item, DiscoveryCandidate):
                coerced.append(item)
                continue
            if isinstance(item, PublicTargetMatch):
                coerced.append(DiscoveryCandidate.from_public_match(item))
                continue
            coerced.append(item)
        return coerced


class BindingRequest(BaseModel):
    """Request to turn a private handle record into runtime provider loads."""

    handle_record: TargetHandleRecord
    thread_id: Optional[str] = None
    task_id: Optional[str] = None


class ProviderLoadRequest(BaseModel):
    """Description of a provider load ToolManager can perform generically."""

    provider_path: str
    provider_key: str
    target_handle: str
    provider_context: Dict[str, Any] = Field(default_factory=dict)


class BindingResult(BaseModel):
    """Result of binding a private handle record into provider loads."""

    public_summary: PublicTargetBinding
    provider_loads: List[ProviderLoadRequest] = Field(default_factory=list)
    client_refs: Dict[str, Any] = Field(default_factory=dict)


class TargetDiscoveryBackend(Protocol):
    """Resolve natural-language Redis targets into safe matches and private candidates."""

    backend_name: str

    async def resolve(self, request: DiscoveryRequest) -> DiscoveryResponse: ...


class TargetBindingStrategy(Protocol):
    """Bind a private Redis handle record into provider loads."""

    strategy_name: str

    async def bind(self, request: BindingRequest) -> BindingResult: ...


class AuthenticatedClientFactory(Protocol):
    """Build a live client or provider input from a private handle record."""

    client_family: str

    async def build(self, handle_record: TargetHandleRecord) -> Any: ...
