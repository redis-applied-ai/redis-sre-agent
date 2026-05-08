"""Default local PII remediator backed by OpenAI Privacy Filter weights."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence

from redis_sre_agent.core.config import settings
from redis_sre_agent.core.pii_remediation import (
    PIIFinding,
    PIIRemediationDecision,
    PIIRemediationMode,
    PIIRemediationRequest,
    PIIRemediationResult,
    PIITextBlock,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _SpanDetection:
    category: str
    start: int
    end: int
    text: str
    confidence: Optional[float]
    raw_entity: Optional[str]


def _normalize_category(raw: Optional[str]) -> str:
    value = str(raw or "").strip()
    if not value:
        return ""
    value = value.replace("B-", "").replace("I-", "").replace("b-", "").replace("i-", "")
    return value.lower()


class DefaultPrivacyFilterPIIRemediator:
    """Default implementation using a local token-classification pipeline."""

    detector_name = "openai_privacy_filter"

    def __init__(
        self,
        *,
        model_name: Optional[str] = None,
        categories: Optional[Sequence[str]] = None,
    ) -> None:
        self.model_name = model_name or settings.pii_remediation_model
        self.categories = {
            _normalize_category(item)
            for item in (categories or settings.pii_remediation_categories)
        }
        self._pipeline: Any = None

    def _get_pipeline(self) -> Any:
        if self._pipeline is not None:
            return self._pipeline

        try:
            from transformers import pipeline
        except ImportError as exc:
            raise RuntimeError(
                "transformers is required for the default local Privacy Filter remediator"
            ) from exc

        self._pipeline = pipeline(
            task="token-classification",
            model=self.model_name,
            tokenizer=self.model_name,
            aggregation_strategy="simple",
        )
        return self._pipeline

    def _detect_spans(self, text: str) -> List[_SpanDetection]:
        if not text:
            return []

        classifier = self._get_pipeline()
        raw_results = classifier(text)
        detections: List[_SpanDetection] = []

        for item in raw_results or []:
            category = _normalize_category(
                item.get("entity_group") or item.get("entity") or item.get("label")
            )
            if not category or (self.categories and category not in self.categories):
                continue
            start = item.get("start")
            end = item.get("end")
            if start is None or end is None:
                continue
            start_i = int(start)
            end_i = int(end)
            if start_i < 0 or end_i <= start_i or end_i > len(text):
                continue
            detections.append(
                _SpanDetection(
                    category=category,
                    start=start_i,
                    end=end_i,
                    text=text[start_i:end_i],
                    confidence=float(item["score"]) if item.get("score") is not None else None,
                    raw_entity=item.get("entity_group") or item.get("entity") or item.get("label"),
                )
            )

        detections.sort(key=lambda span: (span.start, span.end))
        return self._dedupe_overlaps(detections)

    @staticmethod
    def _dedupe_overlaps(detections: Iterable[_SpanDetection]) -> List[_SpanDetection]:
        filtered: List[_SpanDetection] = []
        last_end = -1
        for item in detections:
            if item.start < last_end:
                continue
            filtered.append(item)
            last_end = item.end
        return filtered

    @staticmethod
    def _category_tag(category: str) -> str:
        return category.upper().replace("PRIVATE_", "").replace("-", "_")

    @classmethod
    def _build_placeholders(
        cls,
        spans_by_block: Dict[str, List[_SpanDetection]],
    ) -> Dict[tuple[str, str], str]:
        placeholders: Dict[tuple[str, str], str] = {}
        counters: Dict[str, int] = {}

        for spans in spans_by_block.values():
            for span in spans:
                key = (span.category, span.text)
                if key in placeholders:
                    continue
                counters[span.category] = counters.get(span.category, 0) + 1
                placeholders[key] = (
                    f"[PII:{cls._category_tag(span.category)}:{counters[span.category]}]"
                )

        return placeholders

    @staticmethod
    def _render_redacted_text(
        text: str,
        spans: Sequence[_SpanDetection],
        placeholders: Dict[tuple[str, str], str],
    ) -> str:
        if not spans:
            return text

        redacted = text
        for span in sorted(spans, key=lambda item: item.start, reverse=True):
            placeholder = placeholders[(span.category, span.text)]
            redacted = f"{redacted[: span.start]}{placeholder}{redacted[span.end :]}"
        return redacted

    async def remediate(self, request: PIIRemediationRequest) -> PIIRemediationResult:
        start = time.perf_counter()
        spans_by_block: Dict[str, List[_SpanDetection]] = {}
        findings: List[PIIFinding] = []

        for block in request.blocks:
            spans = await asyncio.to_thread(self._detect_spans, block.text or "")
            spans_by_block[block.block_id] = spans
            for span in spans:
                findings.append(
                    PIIFinding(
                        category=span.category,
                        block_id=block.block_id,
                        confidence=span.confidence,
                        span_start=span.start,
                        span_end=span.end,
                        text=span.text,
                        metadata={"raw_entity": span.raw_entity} if span.raw_entity else {},
                    )
                )

        if request.mode == PIIRemediationMode.DETECT or not findings:
            decision = (
                PIIRemediationDecision.ALLOW if not findings else PIIRemediationDecision.ALLOW
            )
            return PIIRemediationResult(
                decision=decision,
                blocks=request.blocks,
                findings=findings,
                detector_name=self.detector_name,
                detector_model=self.model_name,
                latency_ms=(time.perf_counter() - start) * 1000,
            )

        if request.mode == PIIRemediationMode.BLOCK:
            return PIIRemediationResult(
                decision=PIIRemediationDecision.BLOCKED,
                blocks=request.blocks,
                findings=findings,
                detector_name=self.detector_name,
                detector_model=self.model_name,
                latency_ms=(time.perf_counter() - start) * 1000,
                reason="PII remediation blocked outbound request text",
            )

        placeholders = self._build_placeholders(spans_by_block)
        redacted_blocks: List[PIITextBlock] = []
        for block in request.blocks:
            spans = spans_by_block.get(block.block_id, [])
            rendered = self._render_redacted_text(block.text or "", spans, placeholders)
            redacted_blocks.append(block.model_copy(update={"text": rendered}))

        for finding in findings:
            key = (finding.category, finding.text or "")
            finding.placeholder = placeholders.get(key)

        return PIIRemediationResult(
            decision=PIIRemediationDecision.REDACTED,
            blocks=redacted_blocks,
            findings=findings,
            detector_name=self.detector_name,
            detector_model=self.model_name,
            latency_ms=(time.perf_counter() - start) * 1000,
        )
