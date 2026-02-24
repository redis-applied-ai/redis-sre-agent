"""Pydantic models for Redis SRE agent data structures.

This module defines the core data models used throughout the agent:
- ResultEnvelope: Structured tool execution records
- Topic/TopicExtraction: LLM structured output for topic analysis
- AgentResponse: Agent execution responses with tool envelopes and citations
- DecisionTrace: Complete trace of agent decision processes
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class ResultEnvelope(BaseModel):
    """Structured record of a tool execution for downstream reasoning.

    This preserves the full tool description and raw JSON data so that
    subsequent LLMs have complete, faithful evidence to reason about.

    The `data` field always contains the full tool result.
    The `summary` field contains a truncated preview when data is large,
    allowing LLM context to stay manageable while preserving full data for:
    - Decision traces (`task trace` CLI)
    - The `expand_evidence` tool
    - Future JQ-like query capabilities
    """

    tool_key: str = Field(..., description="Fully-qualified tool name used to route the call")
    name: Optional[str] = Field(None, description="Short operation name if available")
    description: Optional[str] = Field(None, description="Tool description shown to the LLM")
    args: Dict[str, Any] = Field(default_factory=dict)
    status: str = Field(..., description="'success' or 'error'")
    data: Dict[str, Any] = Field(default_factory=dict, description="Full tool result JSON (always preserved)")
    summary: Optional[str] = Field(
        None,
        description="Summary or preview for LLM context when data is large. "
        "If set, LLM sees this; if None, data is small enough to use directly.",
    )
    timestamp: Optional[str] = None


# Topic extraction outputs (LLM structured output)
class TopicEvidence(BaseModel):
    tool_key: str


class Topic(BaseModel):
    id: str
    title: str
    category: Literal[
        "Availability",
        "Replication",
        "Configuration",
        "Performance",
        "Persistence",
        "Security",
        "Networking",
        "Observability",
        "Other",
    ] = "Other"
    severity: Literal["critical", "high", "medium", "low"] = "medium"
    scope: str = "cluster"
    narrative: str = ""
    evidence_keys: List[str] = Field(default_factory=list)


# Recommendation worker outputs (LLM structured output)
class Citation(BaseModel):
    source: str
    snippet: str = ""


class RecommendationStep(BaseModel):
    description: str
    commands: Optional[List[str]] = None
    api_examples: Optional[List[str]] = None
    citations: List[Citation] = Field(default_factory=list)


class Recommendation(BaseModel):
    topic_id: str
    title: Optional[str] = None
    steps: List[RecommendationStep] = Field(default_factory=list)
    risks: Optional[List[str]] = None
    verification: Optional[List[str]] = None


# Wrapper for structured-output list of topics
class TopicsList(BaseModel):
    items: List[Topic] = Field(default_factory=list)


class CorrectionResult(BaseModel):
    """Structured output for the safety/fact correction stage."""

    edited_response: str = Field(..., description="The minimally edited response text")
    edits_applied: List[str] = Field(
        default_factory=list, description="Short bullet list of edits/cautions applied"
    )


class AgentResponse(BaseModel):
    """Response from an agent including the answer and any knowledge search results used.

    The search_results field is derived from tool_envelopes when not explicitly provided.
    This eliminates the need for separate citation tracking - citations are just
    knowledge tool results extracted from the tool envelopes.
    """

    response: str = Field(..., description="The agent's response text")
    search_results: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Knowledge base search results used to generate the response. "
        "Derived from tool_envelopes if not explicitly provided.",
    )
    tool_envelopes: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Tool execution envelopes for decision tracing",
    )

    def model_post_init(self, __context: Any) -> None:
        """Derive search_results from tool_envelopes if not explicitly set."""
        # Only derive if search_results is empty AND we have tool_envelopes
        if not self.search_results and self.tool_envelopes:
            # Import here to avoid circular imports
            from redis_sre_agent.agent.helpers import extract_citations

            # Use object.__setattr__ to bypass Pydantic's frozen model protection
            object.__setattr__(self, "search_results", extract_citations(self.tool_envelopes))


class DecisionTrace(BaseModel):
    """Complete trace of an agent's decision process for a single task/answer.

    Stores full tool envelopes as the single source of truth. This enables:
    - CLI inspection via `task trace <task_id>` (with full tool results)
    - Correlation with OTel traces via otel_trace_id
    - Audit trails for compliance
    - Citations derived from knowledge tool envelopes
    - Future JQ-like query capabilities

    The `tool_envelopes` field contains full ResultEnvelope dicts with:
    - tool_key, name, description, args, status
    - data (full tool result, always preserved)
    - summary (optional, for large outputs)
    """

    task_id: str = Field(..., description="Task ID this trace belongs to")

    tool_envelopes: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Full tool execution envelopes including data and optional summary",
    )

    otel_trace_id: Optional[str] = Field(
        None, description="OpenTelemetry trace ID for correlation with Tempo"
    )
    created_at: Optional[str] = Field(None, description="ISO timestamp when trace was created")
