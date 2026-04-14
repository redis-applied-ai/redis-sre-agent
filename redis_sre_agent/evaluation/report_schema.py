"""Canonical report and artifact contracts for mocked eval runs."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from redis_sre_agent.evaluation.judge import EvaluationResult
from redis_sre_agent.evaluation.scenarios import ExecutionLane, KnowledgeMode, ScenarioProvenance
from redis_sre_agent.evaluation.tool_identity import ConcreteToolIdentity, LogicalToolIdentity


class EvalArtifactFiles(BaseModel):
    """Stable filenames emitted for one eval artifact bundle."""

    model_config = ConfigDict(extra="forbid")

    report_json: str = "report.json"
    report_markdown: str = "report.md"
    tool_trace_json: str = "tool_trace.json"
    retrieved_sources_json: str = "retrieved_sources.json"
    startup_context_json: str = "startup_context.json"


class ToolIdentityReportRow(BaseModel):
    """Logical-to-concrete tool identity mapping captured in a report."""

    model_config = ConfigDict(extra="forbid")

    logical: LogicalToolIdentity
    concrete_name: str
    provider_name: str
    capability: str | None = None
    requires_instance: bool = False

    @classmethod
    def from_concrete(cls, identity: ConcreteToolIdentity) -> "ToolIdentityReportRow":
        return cls(
            logical=identity.logical_identity,
            concrete_name=identity.concrete_name,
            provider_name=identity.provider_name,
            capability=identity.capability,
            requires_instance=identity.requires_instance,
        )


class ToolTraceEntry(BaseModel):
    """One tool call in the eval trace."""

    model_config = ConfigDict(extra="forbid")

    concrete_name: str
    logical: LogicalToolIdentity | None = None
    status: str
    args: dict[str, Any] = Field(default_factory=dict)
    duration_ms: int | None = Field(default=None, ge=0)
    result_preview: Any = None

    @classmethod
    def from_result_envelope(cls, envelope: Any) -> "ToolTraceEntry":
        if isinstance(envelope, dict):
            payload = envelope
        else:
            payload = {
                "tool_key": getattr(envelope, "tool_key"),
                "status": getattr(envelope, "status"),
                "args": getattr(envelope, "args", {}),
                "summary": getattr(envelope, "summary", None),
                "data": getattr(envelope, "data", {}),
            }
        return cls(
            concrete_name=payload["tool_key"],
            status=payload["status"],
            args=dict(payload.get("args", {})),
            result_preview=payload.get("summary")
            if payload.get("summary") is not None
            else payload.get("data", {}),
        )


class RetrievedSourceEntry(BaseModel):
    """One retrieved or pinned source captured during the eval run."""

    model_config = ConfigDict(extra="forbid")

    source_id: str
    source_kind: str
    title: str | None = None
    rank: int | None = Field(default=None, ge=1)
    score: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AssertionStatus(str, Enum):
    """Outcome for a single structured assertion."""

    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


class EvalAssertionResult(BaseModel):
    """Structured assertion outcome for one expectation."""

    model_config = ConfigDict(extra="forbid")

    status: AssertionStatus
    message: str | None = None
    expected: Any = None
    actual: Any = None

    @property
    def passed(self) -> bool:
        return self.status == AssertionStatus.PASSED


class StructuredAssertionResult(BaseModel):
    """Flat assertion row used by the persisted report bundle."""

    model_config = ConfigDict(extra="forbid")

    assertion_type: str
    passed: bool
    details: str | None = None
    expected: Any = None
    observed: Any = None


class StructuredAssertionResults(BaseModel):
    """Grouped structured assertions for one eval run."""

    model_config = ConfigDict(extra="forbid")

    required_tool_calls: list[EvalAssertionResult] = Field(default_factory=list)
    forbidden_tool_calls: list[EvalAssertionResult] = Field(default_factory=list)
    required_sources: list[EvalAssertionResult] = Field(default_factory=list)
    forbidden_claims: list[EvalAssertionResult] = Field(default_factory=list)
    required_findings: list[EvalAssertionResult] = Field(default_factory=list)
    expected_routing_decision: EvalAssertionResult | None = None
    all_passed: bool | None = None

    @model_validator(mode="after")
    def _derive_all_passed(self) -> "StructuredAssertionResults":
        outcomes = [
            *self.required_tool_calls,
            *self.forbidden_tool_calls,
            *self.required_sources,
            *self.forbidden_claims,
            *self.required_findings,
        ]
        if self.expected_routing_decision is not None:
            outcomes.append(self.expected_routing_decision)

        if self.all_passed is None:
            self.all_passed = all(outcome.status != AssertionStatus.FAILED for outcome in outcomes)
        return self


class JudgeSummary(BaseModel):
    """Judge output recorded alongside hard assertions."""

    model_config = ConfigDict(extra="forbid")

    overall_score: float
    criteria_scores: dict[str, float] = Field(default_factory=dict)
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    factual_errors: list[str] = Field(default_factory=list)
    missing_elements: list[str] = Field(default_factory=list)
    detailed_feedback: str
    passed: bool | None = None

    @classmethod
    def from_evaluation_result(
        cls,
        result: EvaluationResult,
        *,
        pass_threshold: float | None = None,
    ) -> "JudgeSummary":
        passed = None if pass_threshold is None else result.overall_score >= pass_threshold
        return cls(
            overall_score=result.overall_score,
            criteria_scores=dict(result.criteria_scores),
            strengths=list(result.strengths),
            weaknesses=list(result.weaknesses),
            factual_errors=list(result.factual_errors),
            missing_elements=list(result.missing_elements),
            detailed_feedback=result.detailed_feedback,
            passed=passed,
        )


JudgeRubricScores = JudgeSummary


class EvalBaselinePolicy(BaseModel):
    """Baseline comparison policy attached to an eval report."""

    model_config = ConfigDict(extra="forbid")

    mode: str | None = None
    baseline_id: str | None = None
    update_allowed: bool | None = None
    allowed_triggers: list[str] = Field(default_factory=list)
    update_allowed_events: list[str] = Field(default_factory=list)
    max_failed_scenarios: int | None = Field(default=None, ge=0)
    max_judge_score_drop: float | None = Field(default=None, ge=0)
    review_required: bool | None = None
    acceptable_variance: dict[str, Any] = Field(default_factory=dict)
    update_rule: str | None = None
    judge_score_variance_band: float | None = Field(default=None, ge=0)
    notes: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _normalize_compat_inputs(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value

        data = dict(value)
        acceptable_variance = data.get("acceptable_variance")
        if isinstance(acceptable_variance, dict):
            if "max_failed_scenarios" not in data and "max_failed_scenarios" in acceptable_variance:
                data["max_failed_scenarios"] = acceptable_variance["max_failed_scenarios"]
            if (
                "judge_score_variance_band" not in data
                and "max_judge_score_drop" in acceptable_variance
            ):
                data["judge_score_variance_band"] = acceptable_variance["max_judge_score_drop"]

        if "judge_score_variance_band" not in data and "max_judge_score_drop" in data:
            data["judge_score_variance_band"] = data["max_judge_score_drop"]

        notes = data.get("notes")
        if isinstance(notes, str):
            normalized_note = notes.strip()
            data["notes"] = [normalized_note] if normalized_note else []

        return data

    @model_validator(mode="before")
    @classmethod
    def _normalize_variance_fields(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value

        data = dict(value)
        acceptable_variance = data.get("acceptable_variance")
        if isinstance(acceptable_variance, dict):
            if (
                data.get("max_failed_scenarios") is None
                and acceptable_variance.get("max_failed_scenarios") is not None
            ):
                data["max_failed_scenarios"] = acceptable_variance["max_failed_scenarios"]
            if (
                data.get("max_judge_score_drop") is None
                and acceptable_variance.get("max_judge_score_drop") is not None
            ):
                data["max_judge_score_drop"] = acceptable_variance["max_judge_score_drop"]
            if (
                data.get("max_judge_score_drop") is None
                and acceptable_variance.get("overall_score_max_drop") is not None
            ):
                data["max_judge_score_drop"] = acceptable_variance["overall_score_max_drop"]

        if (
            data.get("judge_score_variance_band") is None
            and data.get("max_judge_score_drop") is not None
        ):
            data["judge_score_variance_band"] = data["max_judge_score_drop"]
        return data


class EvalReportBundle(BaseModel):
    """Canonical JSON and Markdown artifact contract for one eval run."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1"
    generated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    scenario_id: str
    scenario_name: str | None = None
    git_sha: str
    execution_lane: ExecutionLane | str
    overall_pass: bool | None = None
    scenario_provenance: ScenarioProvenance | dict[str, Any] = Field(default_factory=dict)
    agent_type: str | None = None
    agent: str | None = None
    model: str | None = None
    system_prompt_digest: str | None = None
    knowledge_mode: KnowledgeMode | str | None = None
    corpus_version: str | None = None
    llm_mode: str | None = None
    baseline_policy: EvalBaselinePolicy | str | None = Field(default_factory=EvalBaselinePolicy)
    golden_review_status: str | None = None
    startup_context_snapshot: dict[str, Any] | list[Any] | str | None = None
    final_answer: str | None = None
    tool_trace: list[ToolTraceEntry] = Field(default_factory=list)
    retrieved_source_trace: list[RetrievedSourceEntry] = Field(default_factory=list)
    structured_assertions: list[StructuredAssertionResult] = Field(default_factory=list)
    structured_assertion_results: StructuredAssertionResults | None = None
    judge_scores: JudgeSummary | None = None
    tool_identity_map: list[ToolIdentityReportRow] = Field(default_factory=list)
    artifacts: EvalArtifactFiles = Field(default_factory=EvalArtifactFiles)

    @model_validator(mode="before")
    @classmethod
    def _normalize_compat_inputs(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value

        data = dict(value)
        agent = data.get("agent")
        agent_type = data.get("agent_type")
        if agent_type is None and agent is not None:
            data["agent_type"] = agent
        if agent is None and agent_type is not None:
            data["agent"] = agent_type

        if isinstance(data.get("baseline_policy"), str):
            data["baseline_policy"] = {"mode": data["baseline_policy"]}

        tool_trace = data.get("tool_trace")
        if tool_trace is not None:
            normalized_trace: list[Any] = []
            for entry in tool_trace:
                if isinstance(entry, dict) and "concrete_name" not in entry and "tool_key" in entry:
                    normalized_trace.append(ToolTraceEntry.from_result_envelope(entry))
                    continue
                if hasattr(entry, "tool_key") and not isinstance(entry, ToolTraceEntry):
                    normalized_trace.append(ToolTraceEntry.from_result_envelope(entry))
                    continue
                normalized_trace.append(entry)
            data["tool_trace"] = normalized_trace

        retrieved_sources = data.get("retrieved_source_trace")
        if retrieved_sources is not None:
            normalized_sources: list[Any] = []
            for entry in retrieved_sources:
                if isinstance(entry, dict) and "source_id" not in entry and "id" in entry:
                    normalized_sources.append(
                        {
                            "source_id": entry["id"],
                            "source_kind": entry.get("source_kind", "unknown"),
                            "title": entry.get("title"),
                            "rank": entry.get("rank"),
                            "score": entry.get("score"),
                            "metadata": {
                                key: item
                                for key, item in entry.items()
                                if key not in {"id", "source_kind", "title", "rank", "score"}
                            },
                        }
                    )
                    continue
                normalized_sources.append(entry)
            data["retrieved_source_trace"] = normalized_sources

        return data

    @model_validator(mode="after")
    def _validate_and_derive(self) -> "EvalReportBundle":
        if self.execution_lane == ExecutionLane.FULL_TURN and self.judge_scores is None:
            raise ValueError("full_turn artifact bundles must include judge_scores")

        if self.golden_review_status is None and isinstance(
            self.scenario_provenance, ScenarioProvenance
        ):
            self.golden_review_status = self.scenario_provenance.golden.review_status.value

        assertion_pass = True
        if self.structured_assertions:
            assertion_pass = assertion_pass and all(
                item.passed for item in self.structured_assertions
            )
        if self.structured_assertion_results is not None:
            assertion_pass = assertion_pass and bool(self.structured_assertion_results.all_passed)

        judge_pass = self.judge_scores.passed if self.judge_scores is not None else None

        if self.overall_pass is None:
            overall = assertion_pass
            if judge_pass is not None:
                overall = overall and judge_pass
            self.overall_pass = overall
            return self

        if self.overall_pass and not assertion_pass:
            raise ValueError("overall_pass cannot be true when structured assertions fail")
        if self.overall_pass and judge_pass is False:
            raise ValueError("overall_pass cannot be true when judge_scores.passed is false")
        return self

    def _structured_assertion_count(self) -> int:
        if self.structured_assertions:
            return len(self.structured_assertions)
        if self.structured_assertion_results is None:
            return 0
        return (
            len(self.structured_assertion_results.required_tool_calls)
            + len(self.structured_assertion_results.forbidden_tool_calls)
            + len(self.structured_assertion_results.required_sources)
            + len(self.structured_assertion_results.forbidden_claims)
            + len(self.structured_assertion_results.required_findings)
            + (1 if self.structured_assertion_results.expected_routing_decision is not None else 0)
        )

    def to_markdown_summary(self) -> str:
        """Render a deterministic markdown summary for local review."""
        lines = [
            f"# Eval Report: {self.scenario_id}",
            "",
            f"- Pass: {'yes' if self.overall_pass else 'no'}",
            f"- Execution lane: {self.execution_lane}",
            f"- Git SHA: {self.git_sha}",
        ]
        if self.agent_type:
            lines.append(f"- Agent: {self.agent_type}")
        if self.model:
            lines.append(f"- Model: {self.model}")
        if self.knowledge_mode:
            lines.append(f"- Knowledge mode: {self.knowledge_mode}")
        if self.llm_mode:
            lines.append(f"- LLM mode: {self.llm_mode}")
        lines.extend(
            [
                "",
                "## Counts",
                "",
                f"- Tool trace entries: {len(self.tool_trace)}",
                f"- Retrieved sources: {len(self.retrieved_source_trace)}",
                f"- Structured assertions: {self._structured_assertion_count()}",
                f"- Tool identity mappings: {len(self.tool_identity_map)}",
            ]
        )
        if self.judge_scores is not None:
            lines.extend(
                [
                    "",
                    "## Judge",
                    "",
                    f"- Judge score: {self.judge_scores.overall_score}",
                ]
            )
        return "\n".join(lines)


EvalArtifactBundle = EvalReportBundle


__all__ = [
    "AssertionStatus",
    "EvalArtifactBundle",
    "EvalArtifactFiles",
    "EvalAssertionResult",
    "EvalBaselinePolicy",
    "EvalReportBundle",
    "JudgeRubricScores",
    "JudgeSummary",
    "StructuredAssertionResult",
    "StructuredAssertionResults",
    "ToolIdentityReportRow",
    "ToolTraceEntry",
    "RetrievedSourceEntry",
]
