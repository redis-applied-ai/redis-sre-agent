"""Core contracts and loading helpers for outbound PII remediation."""

from __future__ import annotations

import importlib
import logging
from enum import StrEnum
from typing import Any, Dict, List, Optional, Protocol

from pydantic import BaseModel, Field

from redis_sre_agent.core.config import settings

logger = logging.getLogger(__name__)


class PIIRemediationMode(StrEnum):
    """Policy mode for outbound request inspection."""

    OFF = "off"
    DETECT = "detect"
    REDACT = "redact"
    BLOCK = "block"


class PIIRemediationDecision(StrEnum):
    """Resulting action after PII inspection."""

    ALLOW = "allow"
    REDACTED = "redacted"
    BLOCKED = "blocked"


class PIITextBlock(BaseModel):
    """One text-bearing fragment from an outbound request."""

    block_id: str
    path: str
    role: str = "user"
    text: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)


class PIIFinding(BaseModel):
    """A detected sensitive span or grouped finding."""

    category: str
    block_id: str
    placeholder: Optional[str] = None
    confidence: Optional[float] = None
    span_start: Optional[int] = None
    span_end: Optional[int] = None
    text: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class PIIRemediationRequest(BaseModel):
    """Normalized request passed to a PII remediator."""

    mode: PIIRemediationMode
    request_kind: str
    blocks: List[PIITextBlock]
    categories: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class PIIRemediationResult(BaseModel):
    """Outcome returned by a PII remediator."""

    decision: PIIRemediationDecision
    blocks: List[PIITextBlock]
    findings: List[PIIFinding] = Field(default_factory=list)
    detector_name: str = "unknown"
    detector_model: Optional[str] = None
    latency_ms: Optional[float] = None
    reason: Optional[str] = None


class PIIRemediationFactory(Protocol):
    """Factory protocol for custom PIIRemediator construction."""

    def __call__(self) -> "PIIRemediator": ...


class PIIRemediator(Protocol):
    """Protocol for outbound request PII remediators."""

    async def remediate(self, request: PIIRemediationRequest) -> PIIRemediationResult: ...


_pii_remediator_factory: Optional[PIIRemediationFactory] = None
_pii_remediator_factory_initialized = False
_pii_remediator_instance: Optional[PIIRemediator] = None


def is_pii_remediation_enabled(mode: Optional[str] = None) -> bool:
    """Return True when outbound remediation should run."""

    effective_mode = mode or settings.pii_remediation_mode
    return str(effective_mode or "").strip().lower() != PIIRemediationMode.OFF.value


def reset_pii_remediator_factory() -> None:
    """Reset cached factory and singleton instance.

    Primarily intended for tests.
    """

    global _pii_remediator_factory, _pii_remediator_factory_initialized, _pii_remediator_instance
    _pii_remediator_factory = None
    _pii_remediator_factory_initialized = False
    _pii_remediator_instance = None


def set_pii_remediator_factory(factory: Optional[PIIRemediationFactory]) -> None:
    """Register a custom PII remediator factory."""

    global _pii_remediator_factory, _pii_remediator_factory_initialized, _pii_remediator_instance
    _pii_remediator_factory = factory
    _pii_remediator_factory_initialized = True
    _pii_remediator_instance = None


def _load_pii_remediator_factory_from_config() -> None:
    """Load the PII remediator factory from configuration if specified."""

    global _pii_remediator_factory, _pii_remediator_factory_initialized

    if _pii_remediator_factory_initialized:
        return

    factory_path = getattr(settings, "pii_remediation_factory", None)
    if not factory_path or not isinstance(factory_path, str):
        _pii_remediator_factory_initialized = True
        return

    try:
        module_path, _, func_name = factory_path.rpartition(".")
        if not module_path:
            raise ValueError(
                f"Invalid PII_REMEDIATION_FACTORY path '{factory_path}': "
                "must be a dot-path like 'mypackage.module.factory_func'"
            )

        module = importlib.import_module(module_path)
        factory = getattr(module, func_name)
        if not callable(factory):
            raise ValueError(f"PII_REMEDIATION_FACTORY '{factory_path}' is not callable")

        _pii_remediator_factory = factory
        _pii_remediator_factory_initialized = True
        logger.info("Loaded custom PII remediator factory from %s", factory_path)
    except Exception as exc:
        logger.error("Failed to load PII remediator factory from '%s': %s", factory_path, exc)
        raise


def _default_pii_remediator_factory() -> PIIRemediator:
    """Return the default local Privacy Filter remediator."""

    from redis_sre_agent.core.default_pii_remediator import DefaultPrivacyFilterPIIRemediator

    return DefaultPrivacyFilterPIIRemediator()


def get_pii_remediator() -> PIIRemediator:
    """Return a singleton PII remediator instance."""

    global _pii_remediator_instance

    if _pii_remediator_instance is not None:
        return _pii_remediator_instance

    _load_pii_remediator_factory_from_config()
    factory = _pii_remediator_factory or _default_pii_remediator_factory
    _pii_remediator_instance = factory()
    return _pii_remediator_instance
