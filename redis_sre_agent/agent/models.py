from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class ResultEnvelope(BaseModel):
    """Structured record of a tool execution for downstream reasoning.

    This preserves the full tool description and raw JSON data so that
    subsequent LLMs have complete, faithful evidence to reason about.
    """

    tool_key: str = Field(..., description="Fully-qualified tool name used to route the call")
    name: Optional[str] = Field(None, description="Short operation name if available")
    description: Optional[str] = Field(None, description="Tool description shown to the LLM")
    args: Dict[str, Any] = Field(default_factory=dict)
    status: str = Field(..., description="'success' or 'error'")
    data: Dict[str, Any] = Field(default_factory=dict, description="Raw tool result JSON")
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
    """Response from an agent including the answer and any knowledge search results used."""

    response: str = Field(..., description="The agent's response text")
    search_results: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Knowledge base search results used to generate the response",
    )
    tool_envelopes: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Tool execution envelopes for decision tracing",
    )


class ToolCallTrace(BaseModel):
    """Record of a single tool call for decision tracing."""

    tool_key: str = Field(..., description="Fully-qualified tool name")
    name: Optional[str] = Field(None, description="Short operation name")
    args: Dict[str, Any] = Field(default_factory=dict, description="Arguments passed to tool")
    status: str = Field("success", description="'success' or 'error'")
    timestamp: Optional[str] = Field(None, description="ISO timestamp of execution")
    duration_ms: Optional[int] = Field(None, description="Execution duration in milliseconds")


class CitationTrace(BaseModel):
    """Record of a knowledge source citation."""

    document_id: Optional[str] = Field(None, description="Document ID")
    document_hash: Optional[str] = Field(None, description="Document content hash")
    chunk_index: Optional[int] = Field(None, description="Chunk index within document")
    title: Optional[str] = Field(None, description="Document title")
    source: Optional[str] = Field(None, description="Source URL or path")
    content_preview: Optional[str] = Field(None, description="Preview of content")
    score: Optional[float] = Field(None, description="Relevance score")


class DecisionTrace(BaseModel):
    """Complete trace of an agent's decision process for a single task/answer.

    This captures tool calls and knowledge citations without consuming LLM context,
    enabling:
    - CLI inspection via `task trace <task_id>`
    - Correlation with OTel traces via otel_trace_id
    - Audit trails for compliance
    """

    task_id: str = Field(..., description="Task ID this trace belongs to")
    tool_calls: List[ToolCallTrace] = Field(
        default_factory=list, description="Tool executions during this task"
    )
    citations: List[CitationTrace] = Field(
        default_factory=list, description="Knowledge sources used"
    )
    otel_trace_id: Optional[str] = Field(
        None, description="OpenTelemetry trace ID for correlation with Tempo"
    )
    created_at: Optional[str] = Field(None, description="ISO timestamp when trace was created")
