"""Structured hard-assertion scoring for eval scenarios."""

from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

from redis_sre_agent.evaluation.report_schema import (
    AssertionStatus,
    EvalAssertionResult,
    RetrievedSourceEntry,
    StructuredAssertionResult,
    StructuredAssertionResults,
    ToolIdentityReportRow,
    ToolTraceEntry,
)
from redis_sre_agent.evaluation.scenarios import EvalScenario
from redis_sre_agent.evaluation.tool_identity import (
    LogicalToolIdentity,
    concrete_provider_family_prefixes,
    normalize_provider_family,
    normalize_tool_name_token,
)

_TOKEN_RE = re.compile(r"[a-z0-9]+(?:[-'][a-z0-9]+)*")
_NEGATION_PREFIXES: tuple[tuple[str, ...], ...] = (
    ("do", "not"),
    ("did", "not"),
    ("does", "not"),
    ("is", "not"),
    ("are", "not"),
    ("was", "not"),
    ("were", "not"),
    ("have", "not"),
    ("has", "not"),
    ("had", "not"),
    ("can", "not"),
    ("cannot",),
    ("can't",),
    ("don't",),
    ("doesn't",),
    ("didn't",),
    ("never",),
    ("no",),
    ("without",),
    ("avoid",),
)
_ROUTING_ALIASES = {
    "redis_chat": "chat",
    "chat": "chat",
    "redis_triage": "triage",
    "triage": "triage",
    "knowledge_only": "knowledge",
    "knowledge": "knowledge",
}


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _normalize_routing_decision(value: Any) -> str:
    normalized = _normalize_text(value)
    return _ROUTING_ALIASES.get(normalized, normalized)


def _tokenize_text(value: Any) -> list[str]:
    return _TOKEN_RE.findall(_normalize_text(value))


def _has_negation_prefix(tokens: Sequence[str], start_index: int) -> bool:
    prefix = tuple(tokens[max(0, start_index - 3) : start_index])
    return any(
        len(prefix) >= len(pattern) and prefix[-len(pattern) :] == pattern
        for pattern in _NEGATION_PREFIXES
    )


def _normalize_logical_identity(
    identity: LogicalToolIdentity | Mapping[str, Any] | Any,
) -> LogicalToolIdentity:
    return (
        identity
        if isinstance(identity, LogicalToolIdentity)
        else LogicalToolIdentity.model_validate(identity)
    )


def _normalize_expected_tool_ref(expected: Any) -> LogicalToolIdentity:
    if hasattr(expected, "model_dump"):
        return _normalize_logical_identity(expected.model_dump())
    return _normalize_logical_identity(expected)


def _infer_trace_logical_identity(
    scenario: EvalScenario,
    concrete_name: str,
) -> LogicalToolIdentity | None:
    normalized_name = normalize_tool_name_token(concrete_name)
    if not normalized_name:
        return None
    if normalized_name == "knowledge.pinned_context":
        return LogicalToolIdentity(
            provider_family="knowledge",
            operation="pinned_context",
        )

    candidate_operations: list[tuple[int, LogicalToolIdentity]] = []
    for provider_family, operation_map in scenario.tools.providers.items():
        raw_provider = normalize_tool_name_token(provider_family)
        canonical_provider = normalize_provider_family(raw_provider)
        provider_prefixes = {
            f"{provider_prefix}_"
            for provider_prefix in concrete_provider_family_prefixes(raw_provider)
        }
        if not any(normalized_name.startswith(prefix) for prefix in provider_prefixes):
            continue
        for operation in operation_map:
            normalized_operation = normalize_tool_name_token(operation)
            if not normalized_name.endswith(f"_{normalized_operation}"):
                continue
            payload: dict[str, Any] = {
                "provider_family": canonical_provider,
                "operation": normalized_operation,
            }
            if len(scenario.scope.bound_targets) == 1 and canonical_provider not in {
                "knowledge",
                "mcp",
                "target_discovery",
                "utilities",
            }:
                payload["target_handle"] = scenario.scope.bound_targets[0]
            candidate_operations.append(
                (
                    len(normalized_operation),
                    LogicalToolIdentity.model_validate(payload),
                )
            )

    for server_name, server_config in scenario.tools.mcp_servers.items():
        normalized_server_name = normalize_tool_name_token(server_name)
        provider_prefix = f"mcp_{normalized_server_name}_"
        if not normalized_name.startswith(provider_prefix):
            continue
        for operation in server_config.tools:
            normalized_operation = normalize_tool_name_token(operation)
            if not normalized_name.endswith(f"_{normalized_operation}"):
                continue
            candidate_operations.append(
                (
                    len(normalized_operation),
                    LogicalToolIdentity.model_validate(
                        {
                            "provider_family": "mcp",
                            "server_name": server_name,
                            "operation": normalized_operation,
                        }
                    ),
                )
            )

    if not candidate_operations:
        return None
    return max(candidate_operations, key=lambda item: item[0])[1]


def _match_logical_identity(
    expected: LogicalToolIdentity,
    actual: LogicalToolIdentity,
) -> bool:
    if expected.provider_family != actual.provider_family:
        return False
    if expected.operation != actual.operation:
        return False
    if expected.server_name is not None and expected.server_name != actual.server_name:
        return False
    if expected.target_handle is not None and expected.target_handle != actual.target_handle:
        return False
    return True


def _identity_map_by_concrete(
    tool_identity_map: Sequence[ToolIdentityReportRow | dict[str, Any]] | None,
) -> dict[str, LogicalToolIdentity]:
    mapping: dict[str, LogicalToolIdentity] = {}
    for row in tool_identity_map or []:
        normalized = (
            row
            if isinstance(row, ToolIdentityReportRow)
            else ToolIdentityReportRow.model_validate(row)
        )
        mapping[normalized.concrete_name] = normalized.logical
    return mapping


def _normalize_tool_trace(
    tool_trace: Sequence[ToolTraceEntry | dict[str, Any]] | None,
    *,
    scenario: EvalScenario,
    tool_identity_map: Sequence[ToolIdentityReportRow | dict[str, Any]] | None = None,
) -> list[ToolTraceEntry]:
    identity_by_concrete = _identity_map_by_concrete(tool_identity_map)
    normalized: list[ToolTraceEntry] = []
    for entry in tool_trace or []:
        if isinstance(entry, dict) and "concrete_name" not in entry and "tool_key" in entry:
            trace = ToolTraceEntry.from_result_envelope(entry)
        elif hasattr(entry, "tool_key") and not isinstance(entry, ToolTraceEntry):
            trace = ToolTraceEntry.from_result_envelope(entry)
        else:
            trace = (
                entry if isinstance(entry, ToolTraceEntry) else ToolTraceEntry.model_validate(entry)
            )
        if trace.logical is None and trace.concrete_name in identity_by_concrete:
            trace = trace.model_copy(update={"logical": identity_by_concrete[trace.concrete_name]})
        if trace.logical is None:
            inferred = _infer_trace_logical_identity(scenario, trace.concrete_name)
            if inferred is not None:
                trace = trace.model_copy(update={"logical": inferred})
        normalized.append(trace)
    return normalized


def _normalize_sources(
    retrieved_sources: Sequence[RetrievedSourceEntry | dict[str, Any]] | None,
) -> list[RetrievedSourceEntry]:
    return [
        entry
        if isinstance(entry, RetrievedSourceEntry)
        else RetrievedSourceEntry.model_validate(entry)
        for entry in (retrieved_sources or [])
    ]


def _source_candidates(entry: RetrievedSourceEntry) -> set[str]:
    candidates = {
        _normalize_text(entry.source_id),
        _normalize_text(entry.title),
    }
    for key in ("document_hash", "name", "id", "ticket_id", "source_id"):
        value = entry.metadata.get(key)
        if value is not None:
            candidates.add(_normalize_text(value))
    return {candidate for candidate in candidates if candidate}


def _contains_phrase(text: str, phrase: str) -> bool:
    text_tokens = _tokenize_text(text)
    phrase_tokens = _tokenize_text(phrase)
    if not phrase_tokens or len(text_tokens) < len(phrase_tokens):
        return False

    last_start = len(text_tokens) - len(phrase_tokens) + 1
    for start_index in range(last_start):
        if text_tokens[start_index : start_index + len(phrase_tokens)] != phrase_tokens:
            continue
        if _has_negation_prefix(text_tokens, start_index):
            continue
        return True
    return False


def _matches_response_pattern(text: str, pattern: str) -> bool:
    try:
        return re.search(pattern, text) is not None
    except re.error:
        return False


def _pass(message: str, *, expected: Any = None, actual: Any = None) -> EvalAssertionResult:
    return EvalAssertionResult(
        status=AssertionStatus.PASSED,
        message=message,
        expected=expected,
        actual=actual,
    )


def _fail(message: str, *, expected: Any = None, actual: Any = None) -> EvalAssertionResult:
    return EvalAssertionResult(
        status=AssertionStatus.FAILED,
        message=message,
        expected=expected,
        actual=actual,
    )


def score_structured_assertions(
    scenario: EvalScenario,
    *,
    tool_trace: Sequence[ToolTraceEntry | dict[str, Any]] | None = None,
    retrieved_sources: Sequence[RetrievedSourceEntry | dict[str, Any]] | None = None,
    final_answer: str | None = None,
    actual_routing_decision: str | None = None,
    tool_identity_map: Sequence[ToolIdentityReportRow | dict[str, Any]] | None = None,
) -> StructuredAssertionResults:
    """Score one scenario's hard assertions against trace and output evidence."""

    normalized_trace = _normalize_tool_trace(
        tool_trace,
        scenario=scenario,
        tool_identity_map=tool_identity_map,
    )
    normalized_sources = _normalize_sources(retrieved_sources)
    answer = final_answer or ""

    trace_by_logical: list[tuple[LogicalToolIdentity, ToolTraceEntry]] = [
        (entry.logical, entry) for entry in normalized_trace if entry.logical is not None
    ]
    source_candidates = [(_source_candidates(entry), entry) for entry in normalized_sources]
    required_tool_refs = [
        _normalize_expected_tool_ref(expected)
        for expected in scenario.expectations.required_tool_calls
    ]
    forbidden_tool_refs = [
        _normalize_expected_tool_ref(expected)
        for expected in scenario.expectations.forbidden_tool_calls
    ]

    required_tool_calls: list[EvalAssertionResult] = []
    for expected, normalized_expected in zip(
        scenario.expectations.required_tool_calls,
        required_tool_refs,
        strict=False,
    ):
        match = next(
            (
                trace
                for logical, trace in trace_by_logical
                if _match_logical_identity(normalized_expected, logical)
            ),
            None,
        )
        if match is not None:
            required_tool_calls.append(
                _pass(
                    f"Observed required tool call {expected.model_dump()}",
                    expected=expected.model_dump(),
                    actual=match.concrete_name,
                )
            )
        else:
            required_tool_calls.append(
                _fail(
                    f"Missing required tool call {expected.model_dump()}",
                    expected=expected.model_dump(),
                    actual=[entry.concrete_name for entry in normalized_trace],
                )
            )

    forbidden_tool_calls: list[EvalAssertionResult] = []
    for expected, normalized_expected in zip(
        scenario.expectations.forbidden_tool_calls,
        forbidden_tool_refs,
        strict=False,
    ):
        match = next(
            (
                trace
                for logical, trace in trace_by_logical
                if _match_logical_identity(normalized_expected, logical)
            ),
            None,
        )
        if match is not None:
            forbidden_tool_calls.append(
                _fail(
                    f"Observed forbidden tool call {expected.model_dump()}",
                    expected=expected.model_dump(),
                    actual=match.concrete_name,
                )
            )
        else:
            forbidden_tool_calls.append(
                _pass(
                    f"Forbidden tool call not observed for {expected.model_dump()}",
                    expected=expected.model_dump(),
                )
            )

    required_sources: list[EvalAssertionResult] = []
    for expected in scenario.expectations.required_sources:
        normalized_expected = _normalize_text(expected)
        match = next(
            (
                entry
                for candidates, entry in source_candidates
                if any(
                    normalized_expected == candidate or normalized_expected in candidate
                    for candidate in candidates
                )
            ),
            None,
        )
        if match is not None:
            required_sources.append(
                _pass(
                    f"Observed required source '{expected}'",
                    expected=expected,
                    actual=match.source_id,
                )
            )
        else:
            required_sources.append(
                _fail(
                    f"Missing required source '{expected}'",
                    expected=expected,
                    actual=[entry.source_id for entry in normalized_sources],
                )
            )

    required_response_patterns: list[EvalAssertionResult] = []
    for expected in scenario.expectations.required_response_patterns:
        if _matches_response_pattern(final_answer, expected):
            required_response_patterns.append(
                _pass(
                    "Observed required response pattern in final answer",
                    expected=expected,
                    actual=final_answer,
                )
            )
        else:
            required_response_patterns.append(
                _fail(
                    "Missing required response pattern in final answer",
                    expected=expected,
                    actual=final_answer,
                )
            )

    forbidden_claims: list[EvalAssertionResult] = []
    for expected in scenario.expectations.forbidden_claims:
        if _contains_phrase(answer, expected):
            forbidden_claims.append(
                _fail(
                    f"Observed forbidden claim '{expected}' in final answer",
                    expected=expected,
                    actual=final_answer,
                )
            )
        else:
            forbidden_claims.append(
                _pass(
                    f"Forbidden claim '{expected}' was absent from the final answer",
                    expected=expected,
                )
            )

    required_findings: list[EvalAssertionResult] = []
    for expected in scenario.expectations.required_findings:
        if _contains_phrase(answer, expected):
            required_findings.append(
                _pass(
                    f"Observed required finding '{expected}' in final answer",
                    expected=expected,
                    actual=final_answer,
                )
            )
        else:
            required_findings.append(
                _fail(
                    f"Missing required finding '{expected}' in final answer",
                    expected=expected,
                    actual=final_answer,
                )
            )

    expected_routing_decision = None
    if scenario.expectations.expected_routing_decision is not None:
        expected = _normalize_routing_decision(scenario.expectations.expected_routing_decision)
        actual = _normalize_routing_decision(actual_routing_decision)
        if actual and actual == expected:
            expected_routing_decision = _pass(
                f"Observed expected routing decision '{scenario.expectations.expected_routing_decision}'",
                expected=scenario.expectations.expected_routing_decision,
                actual=actual_routing_decision,
            )
        else:
            expected_routing_decision = _fail(
                f"Expected routing decision '{scenario.expectations.expected_routing_decision}'",
                expected=scenario.expectations.expected_routing_decision,
                actual=actual_routing_decision,
            )

    return StructuredAssertionResults(
        required_tool_calls=required_tool_calls,
        forbidden_tool_calls=forbidden_tool_calls,
        required_sources=required_sources,
        required_response_patterns=required_response_patterns,
        forbidden_claims=forbidden_claims,
        required_findings=required_findings,
        expected_routing_decision=expected_routing_decision,
    )


def flatten_structured_assertions(
    results: StructuredAssertionResults,
) -> list[StructuredAssertionResult]:
    """Convert grouped assertion results into flat persisted rows."""

    rows: list[StructuredAssertionResult] = []
    grouped = {
        "required_tool_call": results.required_tool_calls,
        "forbidden_tool_call": results.forbidden_tool_calls,
        "required_source": results.required_sources,
        "required_response_pattern": results.required_response_patterns,
        "forbidden_claim": results.forbidden_claims,
        "required_finding": results.required_findings,
    }
    for assertion_type, entries in grouped.items():
        for entry in entries:
            rows.append(
                StructuredAssertionResult(
                    assertion_type=assertion_type,
                    passed=entry.passed,
                    details=entry.message,
                    expected=entry.expected,
                    observed=entry.actual,
                )
            )

    if results.expected_routing_decision is not None:
        rows.append(
            StructuredAssertionResult(
                assertion_type="expected_routing_decision",
                passed=results.expected_routing_decision.passed,
                details=results.expected_routing_decision.message,
                expected=results.expected_routing_decision.expected,
                observed=results.expected_routing_decision.actual,
            )
        )
    return rows


__all__ = [
    "flatten_structured_assertions",
    "score_structured_assertions",
]
