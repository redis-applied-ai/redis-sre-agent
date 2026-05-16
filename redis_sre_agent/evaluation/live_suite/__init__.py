"""Live-model eval suite helpers for scheduled and manual workflows."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any, Iterable, Sequence

import yaml
from pydantic import BaseModel, ConfigDict, Field

from redis_sre_agent.agent.models import AgentResponse
from redis_sre_agent.evaluation.agent_only import run_agent_only_scenario
from redis_sre_agent.evaluation.assertions import score_structured_assertions
from redis_sre_agent.evaluation.fake_mcp import build_fixture_mcp_runtime
from redis_sre_agent.evaluation.injection import eval_injection_scope
from redis_sre_agent.evaluation.judge import (
    EvaluationCriteria,
    SREAgentJudge,
    build_default_eval_criteria,
    evaluate_eval_scenario_response,
)
from redis_sre_agent.evaluation.knowledge_backend import build_fixture_knowledge_backend
from redis_sre_agent.evaluation.live_policy import (
    ensure_live_eval_allowed,
    load_eval_baseline_policy,
    materialize_eval_baseline_policy,
)
from redis_sre_agent.evaluation.report_schema import EvalBaselinePolicy, EvalReportBundle
from redis_sre_agent.evaluation.reporting import (
    build_eval_artifact_bundle,
    write_eval_artifact_bundle,
)
from redis_sre_agent.evaluation.runtime import load_eval_scenario, run_full_turn_scenario
from redis_sre_agent.evaluation.runtime_overrides import EvalRuntimeOverrides
from redis_sre_agent.evaluation.scenarios import EvalScenario, ExecutionLane, LLMMode
from redis_sre_agent.evaluation.tool_identity import (
    concrete_provider_family_prefixes,
    normalize_provider_family,
)
from redis_sre_agent.evaluation.tool_runtime import FixtureBehaviorState, build_fixture_tool_runtime


class EvalLiveSuite(BaseModel):
    """Single live-eval suite definition."""

    model_config = ConfigDict(extra="forbid")

    name: str
    description: str | None = None
    scenarios: list[str] = Field(default_factory=list, min_length=1)
    policy_file: str | None = None
    baseline_profile: str = "scheduled_live"
    baseline_policy: EvalBaselinePolicy = Field(default_factory=EvalBaselinePolicy)
    judge_pass_threshold: float | None = None
    output_subdir: str | None = None

    @classmethod
    def from_file(
        cls,
        path: str | Path,
        *,
        baseline_profile: str | None = None,
    ) -> "EvalLiveSuite":
        suite_path = Path(path).expanduser().resolve()
        payload = yaml.safe_load(suite_path.read_text(encoding="utf-8")) or {}
        if not isinstance(payload, dict):
            raise ValueError(f"live eval suite must deserialize to a mapping: {suite_path}")

        suites_payload = payload.get("suites")
        if isinstance(suites_payload, dict):
            if len(suites_payload) != 1:
                available = ", ".join(sorted(str(name) for name in suites_payload))
                raise ValueError(
                    "EvalLiveSuite.from_file only supports single-suite manifests; "
                    f"available suites: {available}"
                )
            suite_name, suite_payload = next(iter(suites_payload.items()))
            if not isinstance(suite_payload, dict):
                raise ValueError(f"live eval suite '{suite_name}' must deserialize to a mapping")
            normalized = _normalize_suite_payload(
                suite_path,
                suite_payload,
                default_suite_name=str(suite_name),
                baseline_profile=baseline_profile,
                resolve_scenarios=True,
            )
            return cls.model_validate(normalized)

        normalized = _normalize_suite_payload(
            suite_path,
            payload,
            default_suite_name=str(
                payload.get("suite_name") or payload.get("name") or suite_path.stem
            ),
            baseline_profile=baseline_profile,
            resolve_scenarios=True,
        )
        return cls.model_validate(normalized)


LiveEvalSuiteDefinition = EvalLiveSuite


class LiveEvalSuiteConfig(BaseModel):
    """Config wrapper for one or more live-eval suites."""

    model_config = ConfigDict(extra="forbid")

    suites: dict[str, EvalLiveSuite]


class LiveEvalScenarioResult(BaseModel):
    """Persisted result for one scenario in a live suite."""

    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    execution_lane: ExecutionLane
    overall_pass: bool
    report_json: str
    report_markdown: str


class LiveEvalSuiteSummary(BaseModel):
    """Suite-level summary written for live-model eval runs."""

    model_config = ConfigDict(extra="forbid")

    suite_name: str
    config_path: str
    trigger: str
    git_sha: str
    baseline_policy: EvalBaselinePolicy
    total_scenarios: int
    failed_scenarios: int
    allowed_failed_scenarios: int
    all_passed: bool
    output_dir: str
    results: list[LiveEvalScenarioResult] = Field(default_factory=list)

    @property
    def overall_pass(self) -> bool:
        return self.all_passed


class LiveEvalComparisonRow(BaseModel):
    """Comparison result for one scenario report against a baseline."""

    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    baseline_score: float | None = None
    candidate_score: float | None = None
    passed: bool
    violations: list[str] = Field(default_factory=list)


class LiveEvalComparisonSummary(BaseModel):
    """Comparison summary across two live-eval report directories."""

    model_config = ConfigDict(extra="forbid")

    baseline_dir: str
    candidate_dir: str
    passed: bool
    rows: list[LiveEvalComparisonRow] = Field(default_factory=list)


def _resolve_path(owner_path: Path, candidate: str) -> Path:
    path = Path(candidate).expanduser()
    if path.is_absolute():
        return path.resolve()
    owner_relative = owner_path.parent / path
    if owner_relative.exists():
        return owner_relative.resolve()
    if path.exists():
        return path.resolve()
    return owner_relative.resolve()


def load_baseline_policy(path: str | Path, *, profile: str | None = None) -> EvalBaselinePolicy:
    """Compatibility wrapper for the dedicated live-eval baseline-policy loader."""

    return load_eval_baseline_policy(path, profile=profile)


def _resolve_relative_path(config_path: Path, ref: str | Path) -> Path:
    return _resolve_path(config_path, str(ref))


def _normalize_suite_payload(
    config_path: Path,
    suite_payload: dict[str, Any],
    *,
    default_suite_name: str,
    baseline_profile: str | None,
    resolve_scenarios: bool = True,
) -> dict[str, Any]:
    normalized = dict(suite_payload)
    normalized["name"] = str(
        normalized.get("suite_name") or normalized.get("name") or default_suite_name
    )
    if resolve_scenarios:
        normalized["scenarios"] = [
            str(_resolve_path(config_path, str(scenario_ref)))
            for scenario_ref in normalized.get("scenarios", [])
        ]
    else:
        normalized["scenarios"] = [
            str(scenario_ref) for scenario_ref in normalized.get("scenarios", [])
        ]
    policy_file = normalized.get("policy_file")
    if policy_file and normalized.get("baseline_policy") in (None, {}):
        resolved_policy = _resolve_path(config_path, str(policy_file))
        profile = baseline_profile or normalized.get("baseline_profile") or "scheduled_live"
        normalized["policy_file"] = str(resolved_policy)
        normalized["baseline_profile"] = profile
        normalized["baseline_policy"] = load_baseline_policy(resolved_policy, profile=profile)
    return normalized


def load_live_eval_suite_config(
    config_path: str | Path,
    *,
    baseline_profile: str | None = None,
) -> LiveEvalSuiteConfig:
    """Load either a single-suite manifest or a multi-suite config file."""

    path = Path(config_path).expanduser().resolve()
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"live eval suite config must deserialize to a mapping: {path}")

    suites_payload = payload.get("suites")
    if isinstance(suites_payload, dict):
        suites: dict[str, EvalLiveSuite] = {}
        for suite_name, suite_payload in suites_payload.items():
            if not isinstance(suite_payload, dict):
                raise ValueError(f"live eval suite '{suite_name}' must deserialize to a mapping")
            suites[str(suite_name)] = EvalLiveSuite.model_validate(
                _normalize_suite_payload(
                    path,
                    suite_payload,
                    default_suite_name=str(suite_name),
                    baseline_profile=baseline_profile,
                    resolve_scenarios=False,
                )
            )
        return LiveEvalSuiteConfig(suites=suites)

    suite_name = str(payload.get("suite_name") or payload.get("name") or path.stem)
    suite = EvalLiveSuite.model_validate(
        _normalize_suite_payload(
            path,
            payload,
            default_suite_name=suite_name,
            baseline_profile=baseline_profile,
            resolve_scenarios=False,
        )
    )
    return LiveEvalSuiteConfig(suites={suite_name: suite})


def resolve_live_eval_trigger(trigger: str | None = None) -> str:
    """Resolve the active live-eval trigger from an argument or CI env."""

    if trigger:
        return str(trigger)
    return str(os.getenv("GITHUB_EVENT_NAME") or "workflow_dispatch")


def _normalize_policy_event_name(trigger: str | None) -> str | None:
    if trigger is None:
        return None
    normalized = str(trigger).strip()
    if normalized == "manual":
        return "workflow_dispatch"
    return normalized


def validate_live_eval_trigger(policy: EvalBaselinePolicy, *, trigger: str | None = None) -> str:
    """Raise when a live eval is attempted outside the allowed trigger policy."""

    resolved_trigger = _normalize_policy_event_name(resolve_live_eval_trigger(trigger))
    try:
        ensure_live_eval_allowed(policy, event_name=resolved_trigger)
    except ValueError as exc:
        raise ValueError(str(exc)) from exc
    return str(resolved_trigger or "workflow_dispatch")


def live_eval_git_sha() -> str:
    """Return the current git sha for live-eval artifact metadata."""

    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True,
        check=False,
        text=True,
    )
    if result.returncode == 0:
        return result.stdout.strip()
    return "unknown"


def _current_git_sha() -> str:
    """Compatibility wrapper so callers can patch either git-sha helper name."""

    return live_eval_git_sha()


def normalize_agent_response_payload(
    response: Any,
) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    """Normalize agent output into response text, tool traces, and retrieved sources."""

    payload = (
        response.response
        if hasattr(response, "response") and not isinstance(response, AgentResponse)
        else response
    )
    if isinstance(payload, AgentResponse):
        return (
            payload.response,
            list(payload.tool_envelopes or []),
            list(payload.search_results or []),
        )
    return (
        str(getattr(payload, "response", "") or ""),
        list(getattr(payload, "tool_envelopes", []) or []),
        list(getattr(payload, "search_results", []) or []),
    )


def _normalize_tool_name_token(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _infer_live_trace_logical_identity(
    scenario: EvalScenario,
    concrete_name: str,
) -> dict[str, Any] | None:
    normalized_name = _normalize_tool_name_token(concrete_name)
    if not normalized_name:
        return None
    if normalized_name == "knowledge.pinned_context":
        return {
            "provider_family": "knowledge",
            "operation": "pinned_context",
        }

    candidate_operations: list[tuple[int, str, str, str | None]] = []
    for provider_family, operation_map in scenario.tools.providers.items():
        raw_provider = _normalize_tool_name_token(provider_family)
        normalized_provider = normalize_provider_family(raw_provider)
        provider_prefixes = {
            f"{provider_prefix}_"
            for provider_prefix in concrete_provider_family_prefixes(raw_provider)
        }
        if not any(normalized_name.startswith(prefix) for prefix in provider_prefixes):
            continue
        for operation in operation_map:
            normalized_operation = _normalize_tool_name_token(operation)
            if normalized_name.endswith(f"_{normalized_operation}"):
                candidate_operations.append(
                    (len(normalized_operation), normalized_provider, normalized_operation, None)
                )

    for server_name, server_config in scenario.tools.mcp_servers.items():
        raw_server_name = str(server_name or "").strip()
        normalized_server = _normalize_tool_name_token(raw_server_name)
        if not normalized_server:
            continue
        if not normalized_name.startswith(f"mcp_{normalized_server}_"):
            continue
        for operation in server_config.tools:
            normalized_operation = _normalize_tool_name_token(operation)
            if normalized_name.endswith(f"_{normalized_operation}"):
                candidate_operations.append(
                    (len(normalized_operation), "mcp", normalized_operation, raw_server_name)
                )

    if not candidate_operations:
        return None

    _length, provider_family, operation, server_name = max(
        candidate_operations, key=lambda item: item[0]
    )
    target_handle = (
        scenario.scope.bound_targets[0] if len(scenario.scope.bound_targets) == 1 else None
    )
    logical_identity: dict[str, Any] = {
        "provider_family": provider_family,
        "operation": operation,
    }
    if server_name is not None:
        logical_identity["server_name"] = server_name
    elif target_handle and provider_family not in {
        "knowledge",
        "mcp",
        "target_discovery",
        "utilities",
    }:
        logical_identity["target_handle"] = target_handle
    return logical_identity


def _normalize_tool_trace(
    tool_envelopes: Sequence[dict[str, Any]],
    *,
    scenario: EvalScenario,
) -> list[dict[str, Any]]:
    trace: list[dict[str, Any]] = []
    for envelope in tool_envelopes:
        concrete_name = envelope.get("tool_key") or envelope.get("name") or "unknown"
        trace.append(
            {
                "concrete_name": concrete_name,
                "logical": _infer_live_trace_logical_identity(scenario, str(concrete_name)),
                "status": envelope.get("status") or "success",
                "args": dict(envelope.get("args") or {}),
                "result_preview": envelope.get("summary")
                if envelope.get("summary") is not None
                else envelope.get("data") or {},
            }
        )
    return trace


def _normalize_retrieved_sources(search_results: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for rank, row in enumerate(search_results, start=1):
        source_id = str(
            row.get("document_hash")
            or row.get("ticket_id")
            or row.get("source_id")
            or row.get("id")
            or row.get("name")
            or f"source-{rank}"
        )
        source_kind = str(
            row.get("source_kind") or row.get("retrieval_kind") or row.get("doc_type") or "unknown"
        )
        score = row.get("score")
        if not isinstance(score, (int, float)):
            score = row.get("distance")
        normalized.append(
            {
                "source_id": source_id,
                "source_kind": source_kind,
                "title": row.get("title") or row.get("name"),
                "rank": rank,
                "score": score if isinstance(score, (int, float)) else None,
                "metadata": dict(row),
            }
        )
    return normalized


def _coerce_live_scenario(scenario: EvalScenario) -> EvalScenario:
    execution = scenario.execution.model_copy(update={"llm_mode": LLMMode.LIVE})
    return scenario.model_copy(update={"execution": execution})


def _mechanical_assertion_scenario(scenario: EvalScenario) -> EvalScenario:
    """Drop free-form text assertions for live suites.

    Live-model evals should use hard assertions only for mechanical outputs
    such as tool calls, retrieved sources, and routing. Text quality,
    semantic correctness, and narrative wording belong in the judge path
    because they depend on live-model phrasing and query formulation.
    """

    expectations = scenario.expectations.model_copy(
        update={
            "required_findings": [],
            "forbidden_claims": [],
        }
    )
    return scenario.model_copy(update={"expectations": expectations})


async def _run_scenario_live(
    scenario: EvalScenario,
    *,
    user_id: str,
    session_id_prefix: str,
    output_dir: Path,
    git_sha: str,
    baseline_policy: EvalBaselinePolicy,
    judge: SREAgentJudge | None = None,
    judge_criteria: Iterable[EvaluationCriteria] | None = None,
    judge_pass_threshold: float | None = None,
    model_name: str | None = None,
) -> LiveEvalScenarioResult:
    session_id = f"{session_id_prefix}::{scenario.id.replace('/', '::')}"
    behavior_state = FixtureBehaviorState()
    knowledge_backend = build_fixture_knowledge_backend(scenario)
    mcp_runtime = build_fixture_mcp_runtime(scenario, state=behavior_state)
    tool_runtime = build_fixture_tool_runtime(scenario, state=behavior_state)
    mcp_servers = mcp_runtime.get_server_configs() if mcp_runtime is not None else {}

    with eval_injection_scope(
        knowledge_backend=knowledge_backend,
        mcp_servers=mcp_servers,
        mcp_runtime=mcp_runtime,
        tool_runtime=tool_runtime,
    ):
        if scenario.execution.lane is ExecutionLane.FULL_TURN:
            runtime_overrides = EvalRuntimeOverrides(
                knowledge_backend=knowledge_backend,
                mcp_servers=mcp_servers,
                mcp_runtime=mcp_runtime,
                tool_runtime=tool_runtime,
            )
            run_result = await run_full_turn_scenario(
                scenario,
                session_id=session_id,
                user_id=user_id,
                runtime_overrides=runtime_overrides,
                allow_live_llm=True,
            )
            startup_context_snapshot: dict[str, Any] | list[Any] | str | None = (
                run_result.turn_context
            )
            response_text = str(run_result.turn_result.get("response") or "")
            tool_envelopes = list(run_result.turn_result.get("tool_envelopes") or [])
            search_results = list(run_result.turn_result.get("search_results") or [])
            actual_agent = str(
                (run_result.turn_result.get("metadata") or {}).get("agent_type")
                or scenario.execution.agent
                or ""
            )
        else:
            run_result = await run_agent_only_scenario(
                scenario,
                session_id=session_id,
                user_id=user_id,
            )
            startup_context_snapshot = run_result.context
            response_text, tool_envelopes, search_results = normalize_agent_response_payload(
                run_result.response
            )
            actual_agent = run_result.agent_name

    tool_trace = _normalize_tool_trace(tool_envelopes, scenario=scenario)
    retrieved_sources = _normalize_retrieved_sources(search_results)
    assertion_scenario = _mechanical_assertion_scenario(scenario)
    assertion_results = score_structured_assertions(
        assertion_scenario,
        tool_trace=tool_trace,
        retrieved_sources=retrieved_sources,
        final_answer=response_text,
        actual_routing_decision=actual_agent or scenario.execution.agent,
    )

    should_judge = True
    judge_result = None
    if should_judge:
        active_criteria = list(judge_criteria or build_default_eval_criteria())
        judge_result = await evaluate_eval_scenario_response(
            scenario=scenario,
            agent_response=response_text,
            judge=judge,
            criteria=active_criteria,
            startup_context=startup_context_snapshot,
            tool_trace=tool_trace,
            retrieved_sources=retrieved_sources,
            structured_assertions=assertion_results,
            actual_routing_decision=actual_agent or scenario.execution.agent,
        )

    bundle = build_eval_artifact_bundle(
        scenario=scenario,
        git_sha=git_sha,
        final_answer=response_text,
        startup_context_snapshot=startup_context_snapshot,
        tool_trace=tool_trace,
        retrieved_source_trace=retrieved_sources,
        structured_assertion_results=assertion_results,
        judge_scores=judge_result,
        judge_pass_threshold=judge_pass_threshold,
        baseline_policy=baseline_policy,
        agent_type=actual_agent or scenario.execution.agent,
        model=model_name,
    )
    written = write_eval_artifact_bundle(bundle, output_dir)
    return LiveEvalScenarioResult(
        scenario_id=scenario.id,
        execution_lane=scenario.execution.lane,
        overall_pass=bool(bundle.overall_pass),
        report_json=str(written["report_json"]),
        report_markdown=str(written["report_markdown"]),
    )


async def run_live_eval_suite(
    suite_or_name: str | Path,
    *,
    config_path: str | Path | None = None,
    output_dir: str | Path | None = None,
    report_dir: str | Path | None = None,
    trigger: str | None = None,
    event_name: str | None = None,
    model_name: str | None = None,
    user_id: str = "github-actions-live-eval",
    session_id_prefix: str = "live-eval",
    baseline_profile: str | None = None,
    update_baseline: bool = False,
    judge: SREAgentJudge | None = None,
    judge_criteria: Iterable[EvaluationCriteria] | None = None,
    judge_pass_threshold: float | None = None,
) -> LiveEvalSuiteSummary:
    """Run a live-model eval suite from either a manifest path or config entry."""

    active_trigger = resolve_live_eval_trigger(event_name or trigger)
    normalized_event = _normalize_policy_event_name(active_trigger)

    if config_path is None:
        resolved_config_path = Path(suite_or_name).expanduser().resolve()
        suite = EvalLiveSuite.from_file(
            resolved_config_path,
            baseline_profile=baseline_profile,
        )
    else:
        resolved_config_path = Path(config_path).expanduser().resolve()
        config = load_live_eval_suite_config(
            resolved_config_path,
            baseline_profile=baseline_profile,
        )
        suite = config.suites[str(suite_or_name)]

    effective_threshold = (
        judge_pass_threshold if judge_pass_threshold is not None else suite.judge_pass_threshold
    )
    baseline_policy = materialize_eval_baseline_policy(
        suite.baseline_policy,
        event_name=normalized_event,
        update_baseline=update_baseline,
    )
    validated_trigger = validate_live_eval_trigger(baseline_policy, trigger=active_trigger)

    target_output_dir = Path(output_dir or report_dir or ".artifacts/evals").expanduser().resolve()
    target_output_dir = target_output_dir / (suite.output_subdir or suite.name)
    target_output_dir.mkdir(parents=True, exist_ok=True)

    git_sha = _current_git_sha()
    results: list[LiveEvalScenarioResult] = []
    for scenario_ref in suite.scenarios:
        scenario_path = (
            Path(scenario_ref)
            if config_path is None
            else _resolve_relative_path(resolved_config_path, scenario_ref)
        )
        scenario = _coerce_live_scenario(load_eval_scenario(scenario_path))
        results.append(
            await _run_scenario_live(
                scenario,
                user_id=user_id,
                session_id_prefix=session_id_prefix,
                output_dir=target_output_dir,
                git_sha=git_sha,
                baseline_policy=baseline_policy,
                judge=judge,
                judge_criteria=judge_criteria,
                judge_pass_threshold=effective_threshold,
                model_name=model_name,
            )
        )

    failed_scenarios = sum(1 for result in results if not result.overall_pass)
    allowed_failed_scenarios = baseline_policy.max_failed_scenarios or 0
    summary = LiveEvalSuiteSummary(
        suite_name=suite.name,
        config_path=str(resolved_config_path),
        trigger=validated_trigger,
        git_sha=git_sha,
        baseline_policy=baseline_policy,
        total_scenarios=len(results),
        failed_scenarios=failed_scenarios,
        allowed_failed_scenarios=allowed_failed_scenarios,
        all_passed=failed_scenarios <= allowed_failed_scenarios,
        output_dir=str(target_output_dir),
        results=results,
    )
    (target_output_dir / "summary.json").write_text(
        summary.model_dump_json(indent=2),
        encoding="utf-8",
    )
    return summary


def _load_report_bundles(root: str | Path) -> dict[str, EvalReportBundle]:
    report_root = Path(root).expanduser().resolve()
    bundles: dict[str, EvalReportBundle] = {}
    for report_path in sorted(report_root.rglob("report.json")):
        bundle = EvalReportBundle.model_validate_json(report_path.read_text(encoding="utf-8"))
        bundles[bundle.scenario_id] = bundle
    return bundles


def compare_live_eval_reports(
    baseline_dir: str | Path,
    candidate_dir: str | Path,
    *,
    baseline_policy: EvalBaselinePolicy | None = None,
) -> LiveEvalComparisonSummary:
    """Compare candidate live-eval results against a baseline report directory."""

    baseline_bundles = _load_report_bundles(baseline_dir)
    candidate_bundles = _load_report_bundles(candidate_dir)
    rows: list[LiveEvalComparisonRow] = []
    policy = baseline_policy or EvalBaselinePolicy()
    allowed_drop = (
        policy.max_judge_score_drop
        if policy.max_judge_score_drop is not None
        else policy.judge_score_variance_band
        if policy.judge_score_variance_band is not None
        else 0.0
    )

    for scenario_id in sorted(set(baseline_bundles) | set(candidate_bundles)):
        baseline = baseline_bundles.get(scenario_id)
        candidate = candidate_bundles.get(scenario_id)
        violations: list[str] = []
        baseline_score = (
            baseline.judge_scores.overall_score
            if baseline is not None and baseline.judge_scores
            else None
        )
        candidate_score = (
            candidate.judge_scores.overall_score
            if candidate is not None and candidate.judge_scores
            else None
        )

        if baseline is None:
            violations.append("missing baseline report")
        if candidate is None:
            violations.append("missing candidate report")
        if baseline is not None and candidate is not None:
            if not bool(candidate.overall_pass):
                violations.append("candidate report failed")
            if (
                baseline_score is not None
                and candidate_score is not None
                and candidate_score < (baseline_score - allowed_drop)
            ):
                violations.append(
                    "judge score drop exceeded allowed variance "
                    f"({baseline_score} -> {candidate_score}, allowed {allowed_drop})"
                )

        rows.append(
            LiveEvalComparisonRow(
                scenario_id=scenario_id,
                baseline_score=baseline_score,
                candidate_score=candidate_score,
                passed=not violations,
                violations=violations,
            )
        )

    return LiveEvalComparisonSummary(
        baseline_dir=str(Path(baseline_dir).expanduser().resolve()),
        candidate_dir=str(Path(candidate_dir).expanduser().resolve()),
        passed=all(row.passed for row in rows),
        rows=rows,
    )


__all__ = [
    "EvalLiveSuite",
    "LiveEvalComparisonRow",
    "LiveEvalComparisonSummary",
    "LiveEvalScenarioResult",
    "LiveEvalSuiteConfig",
    "LiveEvalSuiteSummary",
    "LiveEvalSuiteDefinition",
    "compare_live_eval_reports",
    "load_baseline_policy",
    "load_live_eval_suite_config",
    "normalize_agent_response_payload",
    "resolve_live_eval_trigger",
    "run_live_eval_suite",
    "validate_live_eval_trigger",
    "live_eval_git_sha",
]
