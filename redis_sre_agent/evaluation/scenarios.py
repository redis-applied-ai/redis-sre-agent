"""Scenario contracts for the mocked eval runtime."""

from __future__ import annotations

import json
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator, model_validator

from redis_sre_agent.evaluation.fixture_layout import resolve_scenario_reference

FixtureValue = str | int | float | bool | dict[str, Any] | list[Any] | None


class ExecutionLane(str, Enum):
    """Supported execution lanes for eval scenarios."""

    FULL_TURN = "full_turn"
    AGENT_ONLY = "agent_only"


class KnowledgeMode(str, Enum):
    """Knowledge-access modes supported by eval scenarios."""

    DISABLED = "disabled"
    STARTUP_ONLY = "startup_only"
    RETRIEVAL_ONLY = "retrieval_only"
    FULL = "full"


class SourceKind(str, Enum):
    """Top-level provenance category for a scenario or corpus."""

    REDIS_DOCS = "redis_docs"
    SUPPORT_TICKET_EXPORT = "support_ticket_export"
    SYNTHETIC = "synthetic"
    MIXED = "mixed"


class ReviewStatus(str, Enum):
    """Golden review state for a scenario."""

    DRAFT = "draft"
    REVIEWED = "reviewed"
    APPROVED = "approved"


class LLMMode(str, Enum):
    """LLM execution mode for the eval runtime."""

    LIVE = "live"
    REPLAY = "replay"
    STUB = "stub"


class SyntheticScenarioProvenance(BaseModel):
    """Lineage metadata for synthetic or transformed scenarios."""

    model_config = ConfigDict(extra="forbid")

    is_synthetic: bool = False
    method: str | None = None
    model: str | None = None


class GoldenScenarioProvenance(BaseModel):
    """Golden-answer provenance and review metadata."""

    model_config = ConfigDict(extra="forbid")

    expectation_basis: str
    exemplar_sources: list[str] = Field(default_factory=list)
    review_status: ReviewStatus = ReviewStatus.DRAFT
    reviewed_by: str | None = None


class ScenarioProvenance(BaseModel):
    """Source-pack, lineage, and golden metadata for a scenario."""

    model_config = ConfigDict(extra="forbid")

    source_kind: SourceKind
    source_pack: str
    source_pack_version: str
    derived_from: list[str] = Field(default_factory=list)
    synthetic: SyntheticScenarioProvenance = Field(default_factory=SyntheticScenarioProvenance)
    golden: GoldenScenarioProvenance

    @field_validator("source_pack_version", mode="before")
    @classmethod
    def _coerce_source_pack_version(cls, value: Any) -> Any:
        if isinstance(value, datetime):
            return value.date().isoformat()
        if isinstance(value, date):
            return value.isoformat()
        return value


class EvalExecutionConfig(BaseModel):
    """Execution-lane contract for one eval run."""

    model_config = ConfigDict(extra="forbid")

    lane: ExecutionLane
    query: str
    agent: str | None = None
    route_via_router: bool | None = None
    max_tool_steps: int = Field(default=8, ge=1)
    llm_mode: LLMMode = LLMMode.REPLAY

    @model_validator(mode="after")
    def _validate_lane_contract(self) -> "EvalExecutionConfig":
        if self.lane == ExecutionLane.FULL_TURN:
            if self.route_via_router is None:
                self.route_via_router = True
            if self.route_via_router is False and not self.agent:
                raise ValueError(
                    "full_turn scenarios that bypass the router must set execution.agent"
                )
            return self

        if self.route_via_router:
            raise ValueError("agent_only scenarios cannot route through the top-level router")
        if not self.agent:
            raise ValueError("agent_only scenarios must set execution.agent")
        if self.route_via_router is None:
            self.route_via_router = False
        return self


class EvalTurnScopeConfig(BaseModel):
    """TurnScope-facing options that the eval harness must compile."""

    model_config = ConfigDict(extra="forbid")

    resolution_policy: str = "require_target"
    automation_mode: str = "interactive"


class EvalTargetCatalogEntry(BaseModel):
    """Declarative target catalog entry for one opaque handle."""

    model_config = ConfigDict(extra="forbid")

    handle: str
    kind: str
    display_name: str
    resource_id: str | None = None
    cluster_type: str | None = None
    capabilities: list[str] = Field(default_factory=list)
    public_metadata: dict[str, Any] = Field(default_factory=dict)


class EvalScopeConfig(BaseModel):
    """Target scope and binding declarations for a scenario."""

    model_config = ConfigDict(extra="forbid")

    turn_scope: EvalTurnScopeConfig = Field(default_factory=EvalTurnScopeConfig)
    target_catalog: list[EvalTargetCatalogEntry] = Field(default_factory=list)
    bound_targets: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_target_bindings(self) -> "EvalScopeConfig":
        seen_handles: set[str] = set()
        for entry in self.target_catalog:
            if entry.handle in seen_handles:
                raise ValueError(f"duplicate target handle in scope.target_catalog: {entry.handle}")
            seen_handles.add(entry.handle)

        missing = [handle for handle in self.bound_targets if handle not in seen_handles]
        if missing:
            raise ValueError(
                "scope.bound_targets must reference handles declared in scope.target_catalog: "
                + ", ".join(missing)
            )
        return self


class EvalKnowledgeConfig(BaseModel):
    """Knowledge-layer configuration for one scenario."""

    model_config = ConfigDict(extra="forbid")

    mode: KnowledgeMode = KnowledgeMode.FULL
    version: str = "latest"
    pinned_documents: list[str] = Field(default_factory=list)
    corpus: list[str] = Field(default_factory=list)


class EvalLogicalToolRef(BaseModel):
    """Scenario-facing reference to a logical tool identity."""

    model_config = ConfigDict(extra="forbid")

    provider_family: str
    operation: str
    target_handle: str | None = None
    server_name: str | None = None

    @model_validator(mode="after")
    def _validate_shape(self) -> "EvalLogicalToolRef":
        if self.target_handle and self.server_name:
            raise ValueError("logical tool refs cannot set both target_handle and server_name")
        return self


class EvalToolWhen(BaseModel):
    """Conditional responder selector for one mocked tool result."""

    model_config = ConfigDict(extra="forbid")

    args_contains: dict[str, Any] = Field(default_factory=dict)
    call_count: int | None = Field(default=None, ge=1)
    state_contains: dict[str, Any] = Field(default_factory=dict)


class EvalToolFailureKind(str, Enum):
    """Supported injected failure modes for mocked tool execution."""

    TIMEOUT = "timeout"
    AUTH_ERROR = "auth_error"
    RATE_LIMIT = "rate_limit"
    PARTIAL_DATA = "partial_data"
    EMPTY_RESULT = "empty_result"


class EvalToolFailure(BaseModel):
    """Failure declaration for one mocked tool responder."""

    model_config = ConfigDict(extra="forbid")

    kind: EvalToolFailureKind
    message: str | None = None
    result: FixtureValue = None


class EvalToolResponder(BaseModel):
    """One conditional or ordered responder for a mocked tool."""

    model_config = ConfigDict(extra="forbid")

    when: EvalToolWhen | None = None
    result: FixtureValue = None
    failure: EvalToolFailure | None = None
    state_updates: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _require_result_or_failure(self) -> "EvalToolResponder":
        if self.result is None and self.failure is None:
            raise ValueError("tool responders must declare result and/or failure")
        return self


class EvalToolBehavior(BaseModel):
    """One provider operation declaration inside the scenario."""

    model_config = ConfigDict(extra="forbid")

    description: str | None = None
    input_schema: dict[str, Any] = Field(default_factory=dict)
    result: FixtureValue = None
    failure: EvalToolFailure | None = None
    state_updates: dict[str, Any] = Field(default_factory=dict)
    responders: list[EvalToolResponder] = Field(default_factory=list)

    @model_validator(mode="after")
    def _require_result_or_responder(self) -> "EvalToolBehavior":
        if self.result is None and self.failure is None and not self.responders:
            raise ValueError("tool behaviors must declare result, failure, and/or responders")
        return self


class EvalMCPServerConfig(BaseModel):
    """Declarative fake MCP server contract for one scenario."""

    model_config = ConfigDict(extra="forbid")

    capability: str | None = None
    tools: dict[str, EvalToolBehavior] = Field(default_factory=dict)


class EvalToolsConfig(BaseModel):
    """Top-level tool declarations for provider and fake-MCP fixtures."""

    model_config = ConfigDict(extra="forbid")

    providers: dict[str, dict[str, EvalToolBehavior]] = Field(default_factory=dict)
    mcp_servers: dict[str, EvalMCPServerConfig] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _lift_provider_sections(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value

        raw = dict(value)
        mcp_servers = raw.pop("mcp_servers", {}) or {}
        return {
            "providers": raw,
            "mcp_servers": mcp_servers,
        }


class EvalExpectations(BaseModel):
    """Structured hard-assertion expectations for one scenario."""

    model_config = ConfigDict(extra="forbid")

    required_tool_calls: list[EvalLogicalToolRef] = Field(default_factory=list)
    forbidden_tool_calls: list[EvalLogicalToolRef] = Field(default_factory=list)
    required_findings: list[str] = Field(default_factory=list)
    forbidden_claims: list[str] = Field(default_factory=list)
    required_sources: list[str] = Field(default_factory=list)
    expected_routing_decision: str | None = None


class EvalScenario(BaseModel):
    """Portable eval scenario contract."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    description: str | None = None
    provenance: ScenarioProvenance
    execution: EvalExecutionConfig
    scope: EvalScopeConfig = Field(default_factory=EvalScopeConfig)
    knowledge: EvalKnowledgeConfig = Field(default_factory=EvalKnowledgeConfig)
    tools: EvalToolsConfig = Field(default_factory=EvalToolsConfig)
    expectations: EvalExpectations = Field(default_factory=EvalExpectations)

    _source_path: Path | None = PrivateAttr(default=None)

    @classmethod
    def from_file(cls, path: str | Path) -> "EvalScenario":
        """Load a scenario contract from YAML or JSON."""
        source_path = Path(path).expanduser().resolve()
        raw_text = source_path.read_text(encoding="utf-8")

        if source_path.suffix in {".yaml", ".yml"}:
            payload = yaml.safe_load(raw_text) or {}
        elif source_path.suffix == ".json":
            payload = json.loads(raw_text)
        else:
            raise ValueError(f"Unsupported scenario file type: {source_path.suffix}")

        scenario = cls.model_validate(payload)
        scenario._source_path = source_path
        return scenario

    @property
    def source_path(self) -> Path | None:
        """Return the file the scenario was loaded from, if any."""
        return self._source_path

    def resolve_fixture_path(self, reference: str | Path) -> Path:
        """Resolve a relative fixture path against the scenario file."""
        ref_path = Path(reference)
        if ref_path.is_absolute() or self._source_path is None:
            return ref_path
        return resolve_scenario_reference(self._source_path, ref_path)


__all__ = [
    "EvalExecutionConfig",
    "EvalExpectations",
    "EvalKnowledgeConfig",
    "EvalLogicalToolRef",
    "EvalToolFailure",
    "EvalToolFailureKind",
    "EvalMCPServerConfig",
    "EvalScenario",
    "EvalScopeConfig",
    "EvalTargetCatalogEntry",
    "EvalToolBehavior",
    "EvalToolResponder",
    "EvalToolsConfig",
    "ExecutionLane",
    "KnowledgeMode",
    "LLMMode",
    "ReviewStatus",
    "ScenarioProvenance",
    "SourceKind",
]
