"""Prometheus and tracing helpers for outbound PII remediation."""

from __future__ import annotations

import time
from typing import Iterable, Optional

from opentelemetry import trace
from prometheus_client import Counter, Histogram

from redis_sre_agent.core.pii_remediation import PIIFinding, PIIRemediationDecision

PII_REMEDIATION_REQUESTS = Counter(
    "sre_agent_pii_remediation_requests_total",
    "Total outbound PII remediation requests",
    labelnames=("mode", "decision", "request_kind", "status"),
)
PII_REMEDIATION_FINDINGS = Counter(
    "sre_agent_pii_remediation_findings_total",
    "Total outbound PII remediation findings by category",
    labelnames=("category", "request_kind"),
)
PII_REMEDIATION_LATENCY = Histogram(
    "sre_agent_pii_remediation_duration_seconds",
    "Latency of outbound PII remediation in seconds",
    labelnames=("mode", "request_kind"),
)


def record_pii_remediation_metrics(
    *,
    request_kind: str,
    mode: str,
    decision: str,
    findings: Iterable[PIIFinding],
    start_time: float,
    status: str = "ok",
    detector_name: Optional[str] = None,
    detector_model: Optional[str] = None,
    changed_text: Optional[bool] = None,
) -> None:
    """Record metrics and tracing attributes for a remediation pass."""

    elapsed = max(0.0, time.perf_counter() - start_time)
    findings_list = list(findings)

    PII_REMEDIATION_REQUESTS.labels(
        mode=mode,
        decision=decision,
        request_kind=request_kind,
        status=status,
    ).inc()
    PII_REMEDIATION_LATENCY.labels(mode=mode, request_kind=request_kind).observe(elapsed)
    for finding in findings_list:
        PII_REMEDIATION_FINDINGS.labels(
            category=finding.category,
            request_kind=request_kind,
        ).inc()

    span = trace.get_current_span()
    if span and span.is_recording():
        span.set_attribute("pii.request_kind", request_kind)
        span.set_attribute("pii.mode", mode)
        span.set_attribute("pii.decision", decision)
        span.set_attribute("pii.status", status)
        span.set_attribute("pii.findings_count", len(findings_list))
        span.set_attribute(
            "pii.categories_present",
            ",".join(sorted({finding.category for finding in findings_list})),
        )
        if detector_name:
            span.set_attribute("pii.detector_name", detector_name)
        if detector_model:
            span.set_attribute("pii.detector_model", detector_model)
        if changed_text is not None:
            span.set_attribute("pii.changed_text", changed_text)


def decision_value(decision: PIIRemediationDecision | str) -> str:
    """Return a stable string value for a decision enum or raw string."""

    if isinstance(decision, PIIRemediationDecision):
        return decision.value
    return str(decision)
