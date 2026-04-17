"""Eval reporting helpers and compatibility exports.

The canonical Phase 0 report and artifact schema lives in
`redis_sre_agent.evaluation.report_schema`. This module remains as the
higher-level import surface so follow-on runtime work can migrate
incrementally without duplicating the contract.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence

from redis_sre_agent.evaluation.assertions import flatten_structured_assertions
from redis_sre_agent.evaluation.judge import EvaluationResult
from redis_sre_agent.evaluation.report_schema import (
    AssertionStatus,
    EvalArtifactBundle,
    EvalArtifactFiles,
    EvalAssertionResult,
    EvalBaselinePolicy,
    EvalReportBundle,
    JudgeRubricScores,
    JudgeSummary,
    RetrievedSourceEntry,
    StructuredAssertionResult,
    StructuredAssertionResults,
    ToolIdentityReportRow,
    ToolTraceEntry,
)
from redis_sre_agent.evaluation.scenarios import EvalScenario
from redis_sre_agent.evaluation.tool_identity import ConcreteToolIdentity, ToolIdentityCatalog


class ToolIdentityMapEntry(ToolIdentityReportRow):
    """Compatibility view over the canonical tool identity report row."""

    @property
    def provider_family(self) -> str:
        return self.logical.provider_family

    @property
    def operation(self) -> str:
        return self.logical.operation

    @property
    def target_handle(self) -> str | None:
        return self.logical.target_handle

    @property
    def concrete_tool_name(self) -> str:
        return self.concrete_name


def _normalize_judge_scores(
    judge_scores: JudgeSummary | EvaluationResult | dict[str, Any] | None,
    *,
    pass_threshold: float | None = None,
) -> JudgeSummary | None:
    if judge_scores is None:
        return None
    if isinstance(judge_scores, JudgeSummary):
        return judge_scores
    if isinstance(judge_scores, EvaluationResult):
        return JudgeSummary.from_evaluation_result(
            judge_scores,
            pass_threshold=pass_threshold,
        )
    return JudgeSummary.model_validate(judge_scores)


def _normalize_tool_identity_map(
    tool_identity_map: Sequence[ToolIdentityReportRow | ConcreteToolIdentity | dict[str, Any]]
    | None = None,
    *,
    tool_identity_catalog: ToolIdentityCatalog | None = None,
) -> list[ToolIdentityReportRow]:
    if tool_identity_catalog is not None:
        return [
            ToolIdentityReportRow.from_concrete(entry) for entry in tool_identity_catalog.entries()
        ]

    rows: list[ToolIdentityReportRow] = []
    for entry in tool_identity_map or []:
        if isinstance(entry, ToolIdentityReportRow):
            rows.append(entry)
        elif isinstance(entry, ConcreteToolIdentity):
            rows.append(ToolIdentityReportRow.from_concrete(entry))
        else:
            rows.append(ToolIdentityReportRow.model_validate(entry))
    return rows


def build_eval_artifact_bundle(
    *,
    scenario: EvalScenario,
    git_sha: str,
    final_answer: str | None,
    startup_context_snapshot: dict[str, Any] | list[Any] | str | None = None,
    tool_trace: Sequence[ToolTraceEntry | dict[str, Any]] | None = None,
    retrieved_source_trace: Sequence[RetrievedSourceEntry | dict[str, Any]] | None = None,
    structured_assertion_results: StructuredAssertionResults | dict[str, Any] | None = None,
    structured_assertions: Sequence[StructuredAssertionResult | dict[str, Any]] | None = None,
    judge_scores: JudgeSummary | EvaluationResult | dict[str, Any] | None = None,
    judge_pass_threshold: float | None = None,
    tool_identity_map: Sequence[ToolIdentityReportRow | ConcreteToolIdentity | dict[str, Any]]
    | None = None,
    tool_identity_catalog: ToolIdentityCatalog | None = None,
    agent_type: str | None = None,
    model: str | None = None,
    system_prompt_digest: str | None = None,
    baseline_policy: EvalBaselinePolicy | dict[str, Any] | str | None = None,
    overall_pass: bool | None = None,
) -> EvalArtifactBundle:
    """Construct the canonical Phase 5 report bundle for one scenario run."""

    normalized_assertion_results = (
        structured_assertion_results
        if isinstance(structured_assertion_results, StructuredAssertionResults)
        else StructuredAssertionResults.model_validate(structured_assertion_results)
        if structured_assertion_results is not None
        else None
    )
    flat_assertions = [
        assertion
        if isinstance(assertion, StructuredAssertionResult)
        else StructuredAssertionResult.model_validate(assertion)
        for assertion in (structured_assertions or [])
    ]
    if normalized_assertion_results is not None and not flat_assertions:
        flat_assertions = flatten_structured_assertions(normalized_assertion_results)

    return EvalArtifactBundle(
        scenario_id=scenario.id,
        scenario_name=scenario.name,
        git_sha=git_sha,
        execution_lane=scenario.execution.lane,
        scenario_provenance=scenario.provenance,
        agent_type=agent_type or scenario.execution.agent,
        model=model,
        system_prompt_digest=system_prompt_digest,
        knowledge_mode=scenario.knowledge.mode,
        corpus_version=scenario.knowledge.version,
        llm_mode=scenario.execution.llm_mode,
        baseline_policy=baseline_policy or EvalBaselinePolicy(),
        startup_context_snapshot=startup_context_snapshot,
        final_answer=final_answer,
        tool_trace=list(tool_trace or []),
        retrieved_source_trace=list(retrieved_source_trace or []),
        structured_assertions=flat_assertions,
        structured_assertion_results=normalized_assertion_results,
        judge_scores=_normalize_judge_scores(
            judge_scores,
            pass_threshold=judge_pass_threshold,
        ),
        tool_identity_map=_normalize_tool_identity_map(
            tool_identity_map,
            tool_identity_catalog=tool_identity_catalog,
        ),
        overall_pass=overall_pass,
    )


def write_eval_artifact_bundle(
    bundle: EvalArtifactBundle,
    output_dir: str | Path,
) -> dict[str, Path]:
    """Persist an eval artifact bundle and its sidecar trace files."""

    bundle_dir = Path(output_dir).expanduser().resolve() / bundle.scenario_id
    bundle_dir.mkdir(parents=True, exist_ok=True)
    artifacts = bundle.artifacts

    paths = {
        "bundle_dir": bundle_dir,
        "report_json": bundle_dir / artifacts.report_json,
        "report_markdown": bundle_dir / artifacts.report_markdown,
        "tool_trace_json": bundle_dir / artifacts.tool_trace_json,
        "retrieved_sources_json": bundle_dir / artifacts.retrieved_sources_json,
        "startup_context_json": bundle_dir / artifacts.startup_context_json,
    }

    paths["report_json"].write_text(
        bundle.model_dump_json(indent=2),
        encoding="utf-8",
    )
    paths["report_markdown"].write_text(
        bundle.to_markdown_summary() + "\n",
        encoding="utf-8",
    )
    paths["tool_trace_json"].write_text(
        json.dumps([entry.model_dump(mode="json") for entry in bundle.tool_trace], indent=2),
        encoding="utf-8",
    )
    paths["retrieved_sources_json"].write_text(
        json.dumps(
            [entry.model_dump(mode="json") for entry in bundle.retrieved_source_trace],
            indent=2,
        ),
        encoding="utf-8",
    )
    paths["startup_context_json"].write_text(
        json.dumps(bundle.startup_context_snapshot, indent=2),
        encoding="utf-8",
    )
    return paths


__all__ = [
    "AssertionStatus",
    "EvalArtifactBundle",
    "EvalArtifactFiles",
    "EvalAssertionResult",
    "EvalBaselinePolicy",
    "EvalReportBundle",
    "JudgeRubricScores",
    "JudgeSummary",
    "RetrievedSourceEntry",
    "StructuredAssertionResult",
    "StructuredAssertionResults",
    "ToolIdentityMapEntry",
    "ToolIdentityReportRow",
    "ToolTraceEntry",
    "build_eval_artifact_bundle",
    "write_eval_artifact_bundle",
]
