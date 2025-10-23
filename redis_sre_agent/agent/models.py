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
