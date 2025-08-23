#!/usr/bin/env python3
"""
LangGraph agent for generating Redis SRE runbooks with research and evaluation capabilities.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, TypedDict

import openai
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph

from redis_sre_agent.core.config import settings
from redis_sre_agent.tools.sre_functions import search_runbook_knowledge

logger = logging.getLogger(__name__)

# Initialize OpenAI client
openai.api_key = settings.openai_api_key


@dataclass
class RunbookRequest:
    """Request for generating a runbook."""

    topic: str
    scenario_description: str
    severity: str = "warning"  # critical, warning, info
    category: str = "operational_runbook"
    specific_requirements: Optional[List[str]] = None


@dataclass
class ResearchResult:
    """Result from research phase."""

    tavily_findings: List[Dict[str, Any]]
    knowledge_base_results: List[Dict[str, Any]]
    research_summary: str


@dataclass
class GeneratedRunbook:
    """Generated runbook with metadata."""

    title: str
    content: str
    category: str
    severity: str
    sources: List[str]
    generation_timestamp: str


@dataclass
class RunbookEvaluation:
    """Evaluation of a generated runbook."""

    overall_score: float
    technical_accuracy: int
    completeness: int
    actionability: int
    production_readiness: int
    strengths: List[str]
    weaknesses: List[str]
    recommendations: List[str]
    evaluation_summary: str


class RunbookAgentState(TypedDict):
    """State for the runbook generation agent."""

    request: RunbookRequest
    research: Optional[ResearchResult]
    generated_runbook: Optional[GeneratedRunbook]
    evaluation: Optional[RunbookEvaluation]
    messages: List[BaseMessage]
    iteration_count: int
    max_iterations: int
    status: str  # "researching", "generating", "evaluating", "completed", "failed"


class TavilySearchTool:
    """Mock Tavily search tool for research."""

    def __init__(self):
        self.name = "tavily_search"

    async def search(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        """Perform Tavily search (mock implementation)."""
        logger.info(f"🔍 Tavily Search: {query}")

        # Mock results for demonstration
        # In real implementation, this would call Tavily API
        mock_results = [
            {
                "title": f"Redis {query} - Production Guide",
                "url": "https://redis.io/docs/production-guide",
                "content": f"Comprehensive guide covering {query} in production environments...",
                "score": 0.95,
            },
            {
                "title": f"Stack Overflow: {query} Issues",
                "url": "https://stackoverflow.com/questions/redis-issues",
                "content": f"Community discussion about common {query} problems and solutions...",
                "score": 0.87,
            },
            {
                "title": f"Redis Best Practices for {query}",
                "url": "https://redis.com/blog/best-practices",
                "content": f"Best practices and operational procedures for handling {query}...",
                "score": 0.82,
            },
        ]

        logger.info(f"📄 Found {len(mock_results)} Tavily results")
        return mock_results[:max_results]


class RunbookGenerator:
    """LangGraph agent for generating Redis SRE runbooks."""

    def __init__(self):
        self.llm = ChatOpenAI(model="gpt-4o", temperature=0.1, api_key=settings.openai_api_key)
        self.tavily = TavilySearchTool()
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """Build the LangGraph workflow."""
        workflow = StateGraph(RunbookAgentState)

        # Add nodes
        workflow.add_node("research", self._research_node)
        workflow.add_node("generate", self._generate_node)
        workflow.add_node("evaluate", self._evaluate_node)
        workflow.add_node("refine", self._refine_node)

        # Add completion node
        workflow.add_node("complete", self._complete_node)

        # Add edges
        workflow.set_entry_point("research")
        workflow.add_edge("research", "generate")
        workflow.add_edge("generate", "evaluate")
        workflow.add_conditional_edges(
            "evaluate", self._should_refine, {"refine": "refine", "complete": "complete"}
        )
        workflow.add_edge("refine", "generate")
        workflow.add_edge("complete", END)

        return workflow.compile()

    async def _research_node(self, state: RunbookAgentState) -> RunbookAgentState:
        """Research phase: gather information from multiple sources."""
        logger.info(f"🔬 Research Phase: {state['request'].topic}")

        request = state["request"]

        # Search Tavily for external information
        tavily_query = f"Redis {request.topic} troubleshooting production issues best practices"
        tavily_results = await self.tavily.search(tavily_query, max_results=3)

        # Search internal knowledge base
        kb_query = f"Redis {request.topic} troubleshooting configuration monitoring"
        kb_result = await search_runbook_knowledge(kb_query, limit=5)
        kb_results = kb_result.get("results", [])

        # Generate research summary
        research_summary = await self._generate_research_summary(
            request, tavily_results, kb_results
        )

        research = ResearchResult(
            tavily_findings=tavily_results,
            knowledge_base_results=kb_results,
            research_summary=research_summary,
        )

        state["research"] = research
        state["status"] = "researched"
        logger.info(
            f"✅ Research completed: {len(tavily_results)} external + {len(kb_results)} internal sources"
        )

        return state

    async def _generate_research_summary(
        self, request: RunbookRequest, tavily_results: List[Dict], kb_results: List[Dict]
    ) -> str:
        """Generate a research summary from gathered sources."""

        prompt = f"""
Based on the research gathered for Redis {request.topic}, provide a concise research summary.

## Topic: {request.topic}
## Scenario: {request.scenario_description}

## External Sources (Tavily):
{self._format_tavily_results(tavily_results)}

## Internal Knowledge Base:
{self._format_kb_results(kb_results)}

Provide a 3-4 sentence research summary highlighting:
1. Key operational challenges related to this topic
2. Common symptoms and causes identified
3. Best practices or patterns found across sources
4. Any gaps in available information

Research Summary:
"""

        response = await self.llm.ainvoke([HumanMessage(content=prompt)])
        return response.content.strip()

    def _format_tavily_results(self, results: List[Dict]) -> str:
        """Format Tavily results for prompt inclusion."""
        formatted = []
        for i, result in enumerate(results, 1):
            formatted.append(f"{i}. {result['title']}\n   {result['content'][:200]}...")
        return "\n".join(formatted)

    def _format_kb_results(self, results: List[Dict]) -> str:
        """Format knowledge base results for prompt inclusion."""
        formatted = []
        for i, result in enumerate(results, 1):
            title = result.get("title", "Unknown")
            content = result.get("content", "")[:200]
            category = result.get("category", "Unknown")
            formatted.append(f"{i}. {title} ({category})\n   {content}...")
        return "\n".join(formatted)

    async def _generate_node(self, state: RunbookAgentState) -> RunbookAgentState:
        """Generation phase: create the runbook content."""
        logger.info(f"📝 Generation Phase: {state['request'].topic}")

        request = state["request"]
        research = state["research"]

        runbook_content = await self._generate_runbook_content(request, research)

        generated_runbook = GeneratedRunbook(
            title=f"Redis {request.topic} - Operational Runbook",
            content=runbook_content,
            category=request.category,
            severity=request.severity,
            sources=self._extract_sources(research),
            generation_timestamp=datetime.now().isoformat(),
        )

        state["generated_runbook"] = generated_runbook
        state["status"] = "generated"
        logger.info(f"✅ Runbook generated: {len(runbook_content)} characters")

        return state

    async def _generate_runbook_content(
        self, request: RunbookRequest, research: ResearchResult
    ) -> str:
        """Generate the actual runbook content using LLM."""

        requirements_text = ""
        if request.specific_requirements:
            requirements_text = "\n\n## Specific Requirements:\n" + "\n".join(
                f"- {req}" for req in request.specific_requirements
            )

        system_prompt = """You are an expert Redis Site Reliability Engineer with 15+ years of production experience. You specialize in creating comprehensive operational runbooks for Redis troubleshooting and maintenance.

Create detailed, actionable runbooks that follow this exact format:

# [Runbook Title]

**Category**: [category]
**Severity**: [severity]
**Source**: Generated runbook for Redis SRE Agent

## Symptoms
[List clear, observable symptoms that indicate this issue]

## Root Cause Analysis

### 1. [Diagnostic Step 1]
```bash
[commands to run]
# [explanation of what to look for]
```

### 2. [Diagnostic Step 2]
```bash
[commands to run]
# [explanation of what to look for]
```

## Immediate Remediation

### Option 1: [Quick Fix Name]
```bash
[commands to run]
# [explanation and warnings]
```

### Option 2: [Alternative Fix]
[procedural steps]

## Long-term Prevention

### 1. [Prevention Strategy 1]
[detailed steps]

### 2. [Prevention Strategy 2]
[detailed steps]

## Monitoring & Alerting

### Key Metrics to Track
```bash
[monitoring commands]
```

### Alert Thresholds
[specific thresholds and conditions]

## Production Checklist
- [ ] [Checklist item 1]
- [ ] [Checklist item 2]
- [ ] [Checklist item 3]

Focus on practical, production-ready guidance with specific commands, thresholds, and procedures."""

        user_prompt = f"""
Generate a comprehensive Redis SRE runbook for the following scenario:

## Topic: {request.topic}
## Scenario Description: {request.scenario_description}
## Severity: {request.severity}
## Category: {request.category}

{requirements_text}

## Research Summary:
{research.research_summary}

## Available Knowledge (for reference):
{self._format_research_for_generation(research)}

Create a detailed, production-ready runbook that SREs can use during real incidents. Include specific Redis commands, configuration examples, monitoring queries, and actionable procedures.
"""

        response = await self.llm.ainvoke(
            [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
        )

        return response.content.strip()

    def _format_research_for_generation(self, research: ResearchResult) -> str:
        """Format research results for generation prompt."""
        external = "\n".join(
            [f"- {r['title']}: {r['content'][:150]}..." for r in research.tavily_findings]
        )
        internal = "\n".join(
            [
                f"- {r.get('title', 'Unknown')}: {r.get('content', '')[:150]}..."
                for r in research.knowledge_base_results
            ]
        )

        return f"External Sources:\n{external}\n\nInternal Knowledge:\n{internal}"

    def _extract_sources(self, research: ResearchResult) -> List[str]:
        """Extract source references from research."""
        sources = []
        sources.extend([r.get("url", "External source") for r in research.tavily_findings])
        sources.extend(
            [f"Internal: {r.get('title', 'Unknown')}" for r in research.knowledge_base_results]
        )
        return sources

    async def _evaluate_node(self, state: RunbookAgentState) -> RunbookAgentState:
        """Evaluation phase: assess runbook quality."""
        logger.info(f"🔍 Evaluation Phase: {state['request'].topic}")

        runbook = state["generated_runbook"]
        evaluation = await self._evaluate_runbook(runbook)

        state["evaluation"] = evaluation
        state["status"] = "evaluated"

        logger.info(f"📊 Evaluation completed: {evaluation.overall_score:.1f}/5.0")

        return state

    async def _evaluate_runbook(self, runbook: GeneratedRunbook) -> RunbookEvaluation:
        """Evaluate the generated runbook quality."""

        system_prompt = """You are a senior Redis Site Reliability Engineering manager with 20+ years of experience reviewing operational runbooks. You evaluate runbooks for production readiness and operational effectiveness.

Assess the runbook on these criteria (1-5 scale):
1. **Technical Accuracy**: Are Redis commands and procedures correct?
2. **Completeness**: Does it cover all necessary aspects of the issue?
3. **Actionability**: Are steps clear and executable during incidents?
4. **Production Readiness**: Is it ready for real production use?

Provide specific, constructive feedback for improvement."""

        user_prompt = f"""
Evaluate this Redis SRE runbook:

## Runbook Title: {runbook.title}
## Category: {runbook.category}
## Severity: {runbook.severity}

## Content:
{runbook.content}

Provide your evaluation in this exact JSON format:
```json
{{
    "overall_score": <average of 4 criteria>,
    "technical_accuracy": <1-5>,
    "completeness": <1-5>,
    "actionability": <1-5>,
    "production_readiness": <1-5>,
    "strengths": ["strength 1", "strength 2"],
    "weaknesses": ["weakness 1", "weakness 2"],
    "recommendations": ["recommendation 1", "recommendation 2"],
    "evaluation_summary": "<2-3 sentence summary>"
}}
```
"""

        response = await self.llm.ainvoke(
            [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
        )

        # Parse JSON response
        try:
            import json

            response_text = response.content.strip()
            json_start = response_text.find("```json")
            json_end = response_text.find("```", json_start + 7)

            if json_start != -1 and json_end != -1:
                json_content = response_text[json_start + 7 : json_end].strip()
                eval_data = json.loads(json_content)
            else:
                eval_data = json.loads(response_text)

            return RunbookEvaluation(
                overall_score=eval_data["overall_score"],
                technical_accuracy=eval_data["technical_accuracy"],
                completeness=eval_data["completeness"],
                actionability=eval_data["actionability"],
                production_readiness=eval_data["production_readiness"],
                strengths=eval_data["strengths"],
                weaknesses=eval_data["weaknesses"],
                recommendations=eval_data["recommendations"],
                evaluation_summary=eval_data["evaluation_summary"],
            )

        except Exception as e:
            logger.error(f"Failed to parse evaluation response: {e}")
            # Return default evaluation on parse failure
            return RunbookEvaluation(
                overall_score=2.5,
                technical_accuracy=3,
                completeness=2,
                actionability=2,
                production_readiness=3,
                strengths=["Generated runbook structure"],
                weaknesses=["Evaluation parsing failed"],
                recommendations=["Review and improve evaluation format"],
                evaluation_summary="Evaluation failed to parse properly.",
            )

    def _should_refine(self, state: RunbookAgentState) -> str:
        """Determine if runbook should be refined or completed."""
        evaluation = state["evaluation"]
        iteration_count = state.get("iteration_count", 0)
        max_iterations = state.get("max_iterations", 2)

        # Refine if score is low and we haven't hit max iterations
        if evaluation.overall_score < 3.5 and iteration_count < max_iterations:
            logger.info(f"🔄 Refining runbook (score: {evaluation.overall_score:.1f})")
            return "refine"
        else:
            logger.info(f"✅ Completing runbook (score: {evaluation.overall_score:.1f})")
            return "complete"

    async def _refine_node(self, state: RunbookAgentState) -> RunbookAgentState:
        """Refinement phase: improve runbook based on evaluation."""
        logger.info(f"🔧 Refinement Phase: {state['request'].topic}")

        state["iteration_count"] = state.get("iteration_count", 0) + 1

        # Add refinement logic here
        # For now, just update status to trigger re-generation
        state["status"] = "refining"

        return state

    async def _complete_node(self, state: RunbookAgentState) -> RunbookAgentState:
        """Completion phase: finalize the runbook."""
        logger.info(f"🎯 Completion Phase: {state['request'].topic}")

        state["status"] = "completed"

        return state

    async def generate_runbook(
        self,
        topic: str,
        scenario_description: str,
        severity: str = "warning",
        category: str = "operational_runbook",
        specific_requirements: Optional[List[str]] = None,
        max_iterations: int = 2,
    ) -> Dict[str, Any]:
        """Generate a runbook for the specified topic."""

        logger.info(f"🚀 Starting runbook generation: {topic}")

        request = RunbookRequest(
            topic=topic,
            scenario_description=scenario_description,
            severity=severity,
            category=category,
            specific_requirements=specific_requirements,
        )

        initial_state: RunbookAgentState = {
            "request": request,
            "research": None,
            "generated_runbook": None,
            "evaluation": None,
            "messages": [],
            "iteration_count": 0,
            "max_iterations": max_iterations,
            "status": "starting",
        }

        # Run the workflow
        final_state = await self.graph.ainvoke(initial_state)

        return {
            "success": final_state["status"] == "completed",
            "runbook": final_state.get("generated_runbook"),
            "evaluation": final_state.get("evaluation"),
            "research": final_state.get("research"),
            "iterations": final_state.get("iteration_count", 0),
        }


async def main():
    """Test the runbook generator."""
    generator = RunbookGenerator()

    result = await generator.generate_runbook(
        topic="Cluster slot migration stuck",
        scenario_description="Redis Cluster slot migration stuck at 52% completion for 2 hours. Clients receiving MOVED redirections and some keys becoming inaccessible.",
        severity="critical",
        specific_requirements=[
            "Include specific CLUSTER commands for diagnosis",
            "Provide manual migration recovery procedures",
            "Add monitoring for migration progress",
        ],
    )

    if result["success"]:
        runbook = result["runbook"]
        evaluation = result["evaluation"]

        print(f"\n✅ Generated Runbook: {runbook.title}")
        print(f"📊 Quality Score: {evaluation.overall_score:.1f}/5.0")
        print(f"📝 Content Length: {len(runbook.content)} characters")
        print(f"🔄 Iterations: {result['iterations']}")

        print("\n" + "=" * 80)
        print(runbook.content)
        print("=" * 80)

        print("\n📊 Evaluation Summary:")
        print(f"   Technical Accuracy: {evaluation.technical_accuracy}/5")
        print(f"   Completeness: {evaluation.completeness}/5")
        print(f"   Actionability: {evaluation.actionability}/5")
        print(f"   Production Readiness: {evaluation.production_readiness}/5")
        print(f"\n💪 Strengths: {', '.join(evaluation.strengths)}")
        print(f"⚠️  Weaknesses: {', '.join(evaluation.weaknesses)}")
        print(f"💡 Recommendations: {', '.join(evaluation.recommendations)}")

    else:
        print("❌ Runbook generation failed")


if __name__ == "__main__":
    asyncio.run(main())
