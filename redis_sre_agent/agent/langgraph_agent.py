"""LangGraph-based SRE Agent implementation.

This module implements a LangGraph workflow for SRE operations, providing
multi-turn conversation handling, tool calling integration, and state management.
"""

import json
import logging
from typing import Any, Dict, List, Optional, TypedDict
from uuid import uuid4

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field

from ..core.config import settings
from ..tools.sre_functions import (
    analyze_system_metrics,
    check_service_health,
    get_detailed_redis_diagnostics,
    ingest_sre_document,
    search_runbook_knowledge,
)

logger = logging.getLogger(__name__)

# SRE-focused system prompt
SRE_SYSTEM_PROMPT = """You are an expert Redis SRE (Site Reliability Engineering) agent. Your role is to help with Redis infrastructure monitoring, troubleshooting, performance optimization, and incident response.

## Your Core Capabilities

You have access to specialized SRE tools for:
- **System Monitoring**: Analyze system metrics, performance data, and health indicators
- **Knowledge Base**: Search runbook procedures, best practices, and troubleshooting guides
- **Health Checks**: Verify service status, connectivity, and operational readiness
- **Documentation**: Ingest and manage SRE knowledge for the team

## CRITICAL: Tool Usage Requirements

**YOU MUST EXTENSIVELY USE YOUR TOOLS** to ground your responses in factual data:

1. **ALWAYS start with knowledge search**: Before making ANY technical claims about Redis, search your runbook knowledge base first using `search_runbook_knowledge` to verify facts and get authoritative information.

2. **Use comprehensive health checks**: For ANY Redis troubleshooting scenario, IMMEDIATELY run `check_service_health` to get complete diagnostic data before making recommendations.

3. **Search multiple knowledge categories**: When searching runbooks, try different categories (incident_response, monitoring, performance, troubleshooting, maintenance) to get comprehensive coverage.

4. **Verify technical claims**: If you need to explain how Redis works internally (memory management, keyspace operations, replication, etc.), search the knowledge base first to ensure accuracy.

5. **Use metrics analysis**: When discussing performance or capacity issues, use `analyze_system_metrics` to get current data rather than making assumptions.

## MANDATORY: Response Structure with Tool Audit Trail

**EVERY RESPONSE MUST END WITH THIS STRUCTURED SECTION** except for brief acknowledgments (e.g., quick thanks/confirmations under 12 words with no technical content). For those cases, reply briefly without the structured section.

---

## 🔍 Investigation Summary

### Tools Used:
- **Knowledge Search**: [List each search_runbook_knowledge call with query terms]
- **Health Check**: [Describe check_service_health usage and key findings]
- **Metrics Analysis**: [Detail analyze_system_metrics calls and results]
- **Other Tools**: [List any additional tools used]

### Knowledge Sources:
- **Runbook References**: [Cite specific runbooks/documents found, with titles]
- **Best Practices**: [Reference official Redis documentation sources]
- **Diagnostic Data**: [Summarize current system state from health checks]

### Investigation Methodology:
1. [Describe step-by-step approach taken]
2. [Explain tool selection reasoning]
3. [Note any limitations or assumptions]

This structured reporting ensures transparency in your diagnostic process and allows verification of your tool usage and knowledge sources.

## Response Guidelines

1. **Evidence-First**: NEVER make claims about Redis behavior without first checking your tools
2. **Tool-Grounded**: Show your work - reference the specific data from tool calls
3. **Fact-Check Yourself**: If you're unsure about any technical detail, search for it
4. **Safety First**: Always consider impact and safety when suggesting operational changes
5. **Escalation Path**: Know when to suggest escalating issues or seeking additional help
6. **Complete Tool Audit**: ALWAYS include the investigation summary section

## Knowledge Base Search Strategy

When using `search_runbook_knowledge`, be strategic:
- Search for specific Redis concepts: "keyspace hit rate", "memory fragmentation", "replication lag"
- Look up operational procedures: "Redis memory pressure response", "Redis performance troubleshooting"
- Verify configuration details: "Redis eviction policies", "Redis persistence options"
- Check best practices: "Redis monitoring guidelines", "Redis capacity planning"

## Communication Style

- Use technical precision while remaining clear
- Provide step-by-step procedures when appropriate
- Include relevant metrics, thresholds, and monitoring points
- Suggest prevention strategies alongside reactive measures
- **ALWAYS cite tool results** when making technical claims
- **MANDATORY**: End with structured investigation summary

Remember: Your credibility depends on factual accuracy AND transparency. Use your tools extensively and document your investigation process to ensure every technical statement is grounded in authoritative knowledge and verifiable through your tool audit trail.
"""

# Fact-checker system prompt
FACT_CHECKER_PROMPT = """You are a Redis technical fact-checker. Your role is to review SRE agent responses for factual accuracy about Redis concepts, metrics, and operations.

## Your Task

Review the provided SRE agent response and identify any statements that are:
1. **Technically incorrect** about Redis internals, operations, or behavior
2. **Misleading interpretations** of Redis metrics or diagnostic data
3. **Unsupported claims** that lack evidence from the diagnostic data provided
4. **Contradictions** between stated facts and the actual data shown

## Common Redis Fact-Check Areas

- **Memory Operations**: Redis is entirely in-memory; no disk access for data retrieval
- **Keyspace Hit Rate**: Measures key existence (hits) vs non-existence (misses), not memory vs disk
- **Replication**: Master/slave terminology, replication lag implications
- **Persistence**: RDB vs AOF, when disk I/O actually occurs
- **Eviction Policies**: How different policies work and when they trigger
- **Configuration**: Default values, valid options, and their implications

## Response Format

If you find factual errors, respond with:
```json
{
  "has_errors": true,
  "errors": [
    {
      "claim": "exact text of the incorrect claim",
      "issue": "explanation of why it's wrong",
      "category": "redis_internals|metrics_interpretation|configuration|other"
    }
  ],
  "suggested_research": [
    "specific topics the agent should research to correct the errors"
  ]
}
```

If no errors are found, respond with:
```json
{
  "has_errors": false,
  "validation_notes": "brief note about what was verified"
}
```

Be strict but fair - flag clear technical inaccuracies, not minor wording choices or style preferences.
"""


class AgentState(TypedDict):
    """State schema for the SRE LangGraph agent."""

    messages: List[BaseMessage]
    session_id: str
    user_id: str
    current_tool_calls: List[Dict[str, Any]]
    iteration_count: int
    max_iterations: int


class SREToolCall(BaseModel):
    """Model for SRE tool call requests."""

    tool_name: str = Field(..., description="Name of the SRE tool to call")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="Tool arguments")
    tool_call_id: str = Field(
        default_factory=lambda: str(uuid4()), description="Unique tool call ID"
    )


class SRELangGraphAgent:
    """LangGraph-based SRE Agent with multi-turn conversation and tool calling."""

    def __init__(self, progress_callback=None):
        """Initialize the SRE LangGraph agent."""
        self.settings = settings
        self.progress_callback = progress_callback
        self.llm = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0.1,
            openai_api_key=self.settings.openai_api_key,
        )

        # Bind SRE tools to the LLM
        self.llm_with_tools = self.llm.bind_tools(
            [
                {
                    "type": "function",
                    "function": {
                        "name": "analyze_system_metrics",
                        "description": "Analyze system metrics and performance data for Redis infrastructure",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "metric_query": {
                                    "type": "string",
                                    "description": "Query or description of metrics to analyze",
                                },
                                "time_range": {
                                    "type": "string",
                                    "description": "Time range for analysis (e.g., 'last 1h', 'last 24h')",
                                    "default": "last 1h",
                                },
                            },
                            "required": ["metric_query"],
                        },
                    },
                },
                {
                    "type": "function",
                    "function": {
                        "name": "search_runbook_knowledge",
                        "description": "Search SRE runbooks and knowledge base for procedures and troubleshooting",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "query": {
                                    "type": "string",
                                    "description": "Search query for runbook procedures or troubleshooting steps",
                                },
                                "category": {
                                    "type": "string",
                                    "description": "Category to focus search on",
                                    "enum": [
                                        "incident_response",
                                        "monitoring",
                                        "performance",
                                        "troubleshooting",
                                        "maintenance",
                                    ],
                                    "default": "troubleshooting",
                                },
                            },
                            "required": ["query"],
                        },
                    },
                },
                {
                    "type": "function",
                    "function": {
                        "name": "check_service_health",
                        "description": "ALWAYS use this tool first when investigating concerning Redis behavior. Provides comprehensive health diagnostics including memory usage, performance metrics, connection patterns, slow queries, configuration issues, and operational status. This tool will identify specific problem areas such as memory pressure, high latency, connection issues, performance degradation, configuration problems, or slow operations. Run this immediately for any Redis troubleshooting scenario.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "service_name": {
                                    "type": "string",
                                    "description": "Name of the service to check (use 'redis' for Redis diagnostics)",
                                },
                                "endpoints": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "List of health check endpoints to test",
                                    "default": ["http://localhost:8000/health"],
                                },
                                "timeout": {
                                    "type": "integer",
                                    "description": "Request timeout in seconds",
                                    "default": 30,
                                },
                            },
                            "required": ["service_name"],
                        },
                    },
                },
                {
                    "type": "function",
                    "function": {
                        "name": "ingest_sre_document",
                        "description": "Add new SRE documentation, runbooks, or procedures to knowledge base",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string", "description": "Title of the document"},
                                "content": {
                                    "type": "string",
                                    "description": "Content of the SRE document",
                                },
                                "source": {
                                    "type": "string",
                                    "description": "Source system or file for the document",
                                    "default": "agent_ingestion",
                                },
                                "category": {
                                    "type": "string",
                                    "description": "Document category",
                                    "enum": [
                                        "runbook",
                                        "procedure",
                                        "troubleshooting",
                                        "best_practice",
                                        "incident_report",
                                    ],
                                    "default": "procedure",
                                },
                                "severity": {
                                    "type": "string",
                                    "description": "Severity or priority level",
                                    "enum": ["info", "warning", "critical"],
                                    "default": "info",
                                },
                            },
                            "required": ["title", "content"],
                        },
                    },
                },
                {
                    "type": "function",
                    "function": {
                        "name": "get_detailed_redis_diagnostics",
                        "description": "Get detailed Redis diagnostic data for deep analysis. Returns raw metrics without pre-calculated assessments, enabling agent to perform its own calculations and severity analysis. Use this for targeted investigation of specific Redis areas (memory, performance, clients, slowlog, etc.) when you need to analyze actual metric values rather than status summaries.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "sections": {
                                    "type": "string",
                                    "description": "Comma-separated diagnostic sections: 'memory', 'performance', 'clients', 'slowlog', 'configuration', 'keyspace', 'replication', 'persistence', 'cpu'. Use 'all' or leave empty for comprehensive diagnostics.",
                                },
                                "time_window_seconds": {
                                    "type": "integer",
                                    "description": "Time window for metrics analysis (future enhancement)",
                                },
                            },
                            "required": [],
                        },
                    },
                },
            ]
        )

        # Build the LangGraph workflow
        self.workflow = self._build_workflow()
        self.memory = MemorySaver()
        self.app = self.workflow.compile(checkpointer=self.memory)

        # SRE tool mapping
        self.sre_tools = {
            "analyze_system_metrics": analyze_system_metrics,
            "search_runbook_knowledge": search_runbook_knowledge,
            "check_service_health": check_service_health,
            "ingest_sre_document": ingest_sre_document,
            "get_detailed_redis_diagnostics": get_detailed_redis_diagnostics,
        }

        logger.info("SRE LangGraph agent initialized with tool bindings")

    def _build_workflow(self) -> StateGraph:
        """Build the LangGraph workflow for SRE operations."""

        def agent_node(state: AgentState) -> AgentState:
            """Main agent node that processes user input and decides on tool calls."""
            messages = state["messages"]
            iteration_count = state.get("iteration_count", 0)
            # max_iterations = state.get("max_iterations", 10)  # Not used in this function

            # Add system message if this is the first interaction
            if len(messages) == 1 and isinstance(messages[0], HumanMessage):
                system_message = AIMessage(content=SRE_SYSTEM_PROMPT)
                messages = [system_message] + messages

            # Generate response with tool calling capability
            response = self.llm_with_tools.invoke(messages)

            # Update state
            new_messages = messages + [response]
            state["messages"] = new_messages
            state["iteration_count"] = iteration_count + 1

            # Track tool calls if any
            if hasattr(response, "tool_calls") and response.tool_calls:
                state["current_tool_calls"] = [
                    {
                        "tool_call_id": tc.get("id", str(uuid4())),
                        "name": tc.get("name", ""),
                        "args": tc.get("args", {}),
                    }
                    for tc in response.tool_calls
                ]
                logger.info(f"Agent requested {len(response.tool_calls)} tool calls")
            else:
                state["current_tool_calls"] = []

            return state

        async def tool_node(state: AgentState) -> AgentState:
            """Execute SRE tools and return results."""
            messages = state["messages"]
            tool_calls = state.get("current_tool_calls", [])

            tool_messages = []

            for tool_call in tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call["args"]
                tool_call_id = tool_call["tool_call_id"]

                logger.info(f"Executing SRE tool: {tool_name} with args: {tool_args}")

                # Send progress update if callback available
                if self.progress_callback:
                    await self.progress_callback(f"Executing tool: {tool_name}", "tool_start")

                try:
                    # Execute the SRE tool (async call)
                    if tool_name in self.sre_tools:
                        # Call the async SRE function
                        result = await self.sre_tools[tool_name](**tool_args)

                        # Send progress update for successful tool execution
                        if self.progress_callback:
                            await self.progress_callback(
                                f"Tool {tool_name} completed successfully", "tool_complete"
                            )

                        # Format result as a readable string
                        if isinstance(result, dict):
                            formatted_result = json.dumps(result, indent=2, default=str)
                            tool_content = f"Tool '{tool_name}' executed successfully.\n\nResult:\n{formatted_result}"
                        else:
                            tool_content = (
                                f"Tool '{tool_name}' executed successfully.\nResult: {result}"
                            )
                    else:
                        tool_content = f"Error: Unknown SRE tool '{tool_name}'"
                        logger.error(f"Unknown tool requested: {tool_name}")

                except Exception as e:
                    tool_content = f"Error executing tool '{tool_name}': {str(e)}"
                    logger.error(f"Tool execution error for {tool_name}: {e}")

                # Create tool message
                tool_message = ToolMessage(content=tool_content, tool_call_id=tool_call_id)
                tool_messages.append(tool_message)

            # Update messages with tool results
            state["messages"] = messages + tool_messages
            state["current_tool_calls"] = []  # Clear tool calls

            return state

        def should_continue(state: AgentState) -> str:
            """Decide whether to continue with tools or end the conversation."""
            messages = state["messages"]
            iteration_count = state.get("iteration_count", 0)
            max_iterations = state.get("max_iterations", 10)

            # Check iteration limit
            if iteration_count >= max_iterations:
                logger.warning(f"Reached max iterations ({max_iterations})")
                return END

            # Check if the last message has tool calls
            if messages and hasattr(messages[-1], "tool_calls"):
                if messages[-1].tool_calls:
                    return "tools"

            # Check if we have pending tool calls in state
            if state.get("current_tool_calls"):
                return "tools"

            return END

        # Build the state graph
        workflow = StateGraph(AgentState)

        # Add nodes
        workflow.add_node("agent", agent_node)
        workflow.add_node("tools", tool_node)

        # Add edges
        workflow.set_entry_point("agent")
        workflow.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
        workflow.add_edge("tools", "agent")

        return workflow

    async def process_query(
        self, query: str, session_id: str, user_id: str, max_iterations: int = 10
    ) -> str:
        """Process a single SRE query through the LangGraph workflow.

        Args:
            query: User's SRE question or request
            session_id: Session identifier for conversation context
            user_id: User identifier
            max_iterations: Maximum number of workflow iterations

        Returns:
            Agent's response as a string
        """
        logger.info(f"Processing SRE query for user {user_id}, session {session_id}")

        # Create initial state
        initial_state: AgentState = {
            "messages": [HumanMessage(content=query)],
            "session_id": session_id,
            "user_id": user_id,
            "current_tool_calls": [],
            "iteration_count": 0,
            "max_iterations": max_iterations,
        }

        # Configure thread for session persistence
        thread_config = {"configurable": {"thread_id": session_id}}

        try:
            # Run the workflow
            final_state = await self.app.ainvoke(initial_state, config=thread_config)

            # Extract the final response
            messages = final_state["messages"]
            if messages and isinstance(messages[-1], AIMessage):
                response_content = messages[-1].content
                logger.info(
                    f"SRE agent completed processing with {final_state['iteration_count']} iterations"
                )

                class AgentResponseStr(str):
                    def get(self, key: str, default: Any = None):
                        if key == "content":
                            return str(self)
                        return default

                return AgentResponseStr(response_content)
            else:
                logger.warning("No valid response generated by SRE agent")

                class AgentResponseStr(str):
                    def get(self, key: str, default: Any = None):
                        if key == "content":
                            return str(self)
                        return default

                return AgentResponseStr(
                    "I apologize, but I couldn't generate a proper response. Please try rephrasing your question."
                )

        except Exception as e:
            logger.error(f"Error processing SRE query: {e}")

            class AgentResponseStr(str):
                def get(self, key: str, default: Any = None):
                    if key == "content":
                        return str(self)
                    return default

            return AgentResponseStr(
                f"I encountered an error while processing your request: {str(e)}. Please try again or contact support if the issue persists."
            )

    async def get_conversation_history(self, session_id: str) -> List[Dict[str, Any]]:
        """Get conversation history for a session.

        Args:
            session_id: Session identifier

        Returns:
            List of conversation messages
        """
        try:
            thread_config = {"configurable": {"thread_id": session_id}}

            # Get the current state for the thread
            current_state = await self.app.aget_state(config=thread_config)

            if current_state and "messages" in current_state.values:
                messages = current_state.values["messages"]

                # Convert messages to serializable format
                history = []
                for msg in messages:
                    if isinstance(msg, HumanMessage):
                        history.append({"role": "user", "content": msg.content})
                    elif isinstance(msg, AIMessage):
                        history.append({"role": "assistant", "content": msg.content})
                    elif isinstance(msg, ToolMessage):
                        history.append({"role": "tool", "content": msg.content})

                return history

        except Exception as e:
            logger.error(f"Error retrieving conversation history: {e}")

        return []

    async def get_thread_state(self, session_id: str) -> Dict[str, Any]:
        """Return internal thread state compatible with evaluation helper.

        The evaluator expects a dict containing a ``messages`` list with
        LangChain message objects that may include ``tool_calls`` metadata.
        """
        try:
            thread_config = {"configurable": {"thread_id": session_id}}
            current_state = await self.app.aget_state(config=thread_config)
            if current_state and hasattr(current_state, "values"):
                return {"messages": current_state.values.get("messages", [])}
        except Exception as e:
            logger.error(f"Error getting thread state: {e}")
        return {"messages": []}

    def clear_conversation(self, session_id: str) -> bool:
        """Clear conversation history for a session.

        Args:
            session_id: Session identifier

        Returns:
            True if cleared successfully, False otherwise
        """
        try:
            # Note: MemorySaver doesn't have a direct clear method
            # In production, you'd want to use a more sophisticated checkpointer
            # For now, we'll rely on the natural expiration of memory
            logger.info(f"Conversation clear requested for session {session_id}")
            return True
        except Exception as e:
            logger.error(f"Error clearing conversation: {e}")
            return False

    async def _fact_check_response(
        self, response: str, diagnostic_data: str = None
    ) -> Dict[str, Any]:
        """Fact-check an agent response for technical accuracy.

        Args:
            response: The agent's response to fact-check
            diagnostic_data: Optional diagnostic data that informed the response

        Returns:
            Dict containing fact-check results
        """
        try:
            # Create fact-checker LLM (separate from main agent)
            fact_checker = ChatOpenAI(
                model="gpt-4o-mini",
                temperature=0.0,  # Zero temperature for consistent fact-checking
                openai_api_key=self.settings.openai_api_key,
            )

            # Prepare fact-check prompt
            fact_check_input = f"""
## Agent Response to Fact-Check:
{response}

## Diagnostic Data (if available):
{diagnostic_data if diagnostic_data else "No diagnostic data provided"}

Please review this Redis SRE agent response for factual accuracy and provide your assessment.
"""

            messages = [
                {"role": "system", "content": FACT_CHECKER_PROMPT},
                {"role": "user", "content": fact_check_input},
            ]

            fact_check_response = await fact_checker.ainvoke(messages)

            # Parse JSON response
            try:
                import json

                # Handle markdown code blocks if present
                response_text = fact_check_response.content.strip()
                if response_text.startswith("```json"):
                    response_text = response_text[7:]  # Remove ```json
                if response_text.endswith("```"):
                    response_text = response_text[:-3]  # Remove ```
                response_text = response_text.strip()

                result = json.loads(response_text)
                logger.info(
                    f"Fact-check completed: {'errors found' if result.get('has_errors') else 'no errors'}"
                )
                return result
            except json.JSONDecodeError:
                logger.error("Fact-checker returned invalid JSON")
                return {
                    "has_errors": False,
                    "validation_notes": "Fact-checker response parsing failed",
                }

        except Exception as e:
            logger.error(f"Error during fact-checking: {e}")
            return {"has_errors": False, "validation_notes": "Fact-checking failed due to error"}

    async def process_query_with_fact_check(
        self, query: str, session_id: str, user_id: str, max_iterations: int = 10
    ) -> str:
        """Process a query with fact-checking and potential retry.

        Args:
            query: User's SRE question or request
            session_id: Session identifier for conversation context
            user_id: User identifier
            max_iterations: Maximum number of workflow iterations

        Returns:
            Agent's response as a string
        """
        # First attempt - normal processing
        response = await self.process_query(query, session_id, user_id, max_iterations)

        # Fact-check the response
        fact_check_result = await self._fact_check_response(response)

        if fact_check_result.get("has_errors"):
            logger.warning("Fact-check identified errors in agent response")

            # Create research query based on suggested topics
            research_topics = fact_check_result.get("suggested_research", [])
            if research_topics:
                research_query = f"""I need to correct my previous response. Please help me research these specific topics to provide accurate information:

{chr(10).join(f"- {topic}" for topic in research_topics)}

My original query was: {query}

Please use the search_runbook_knowledge tool extensively to find authoritative information about these Redis concepts, then provide a corrected and more accurate response."""

                logger.info("Initiating corrective research query")
                # Process the corrective query
                corrected_response = await self.process_query(
                    research_query, session_id, user_id, max_iterations
                )

                # Add a note about the correction
                final_response = f"""## Corrected Response

{corrected_response}

---
*Note: This response has been fact-checked and corrected to ensure technical accuracy.*
"""
                return final_response

        return response

    async def process_query_with_diagnostics(
        self,
        query: str,
        session_id: str,
        user_id: str,
        baseline_diagnostics: Optional[Dict[str, Any]] = None,
        max_iterations: int = 10,
    ) -> str:
        """
        Process query with optional baseline diagnostic context.

        This method enables realistic evaluation scenarios where external tools
        provide baseline diagnostic context, simulating production workflows
        where both external systems and agents use the same diagnostic functions.

        Args:
            query: User's SRE question or request
            session_id: Session identifier for conversation context
            user_id: User identifier
            baseline_diagnostics: Optional baseline diagnostic data captured externally
            max_iterations: Maximum number of workflow iterations

        Returns:
            Agent's response as a string
        """
        logger.info(
            f"Processing SRE query with diagnostic context for user {user_id}, session {session_id}"
        )

        # Enhance query with baseline context if provided
        enhanced_query = query
        if baseline_diagnostics:
            logger.info("Including baseline diagnostic context in query")

            # Format diagnostic summary for context
            diagnostic_summary = self._format_diagnostic_context(baseline_diagnostics)

            enhanced_query = f"""## Baseline Diagnostic Context

The following Redis diagnostic data was captured as baseline context for this investigation:

{diagnostic_summary}

## User Query

{query}

Please analyze this situation using your diagnostic tools to perform follow-up investigation as needed, calculate your own assessments from the raw data, and provide recommendations based on your analysis."""

            logger.debug(
                f"Enhanced query with diagnostic context: {len(enhanced_query)} characters"
            )

        # Process the enhanced query
        return await self.process_query(enhanced_query, session_id, user_id, max_iterations)

    def _format_diagnostic_context(self, diagnostics: Dict[str, Any]) -> str:
        """Format diagnostic data as readable context for the agent."""
        lines = []

        # Header information
        lines.append(f"**Capture Time**: {diagnostics.get('timestamp', 'Unknown')}")
        lines.append(
            f"**Sections Captured**: {', '.join(diagnostics.get('sections_captured', []))}"
        )
        lines.append(f"**Status**: {diagnostics.get('capture_status', 'Unknown')}")
        lines.append("")

        diagnostic_data = diagnostics.get("diagnostics", {})

        # Connection status
        connection = diagnostic_data.get("connection", {})
        if connection and "error" not in connection:
            lines.append("### Connection Status")
            lines.append(f"- Ping Response: {connection.get('ping_response', 'N/A')}")
            lines.append(f"- Ping Duration: {connection.get('ping_duration_ms', 'N/A')} ms")
            lines.append(
                f"- Basic Operations: {'✓' if connection.get('basic_operations_test') else '✗'}"
            )
            lines.append("")

        # Memory metrics (raw data only)
        memory = diagnostic_data.get("memory", {})
        if memory and "error" not in memory:
            lines.append("### Memory Metrics (Raw Data)")
            lines.append(f"- Used Memory: {memory.get('used_memory_bytes', 0)} bytes")
            lines.append(f"- Max Memory: {memory.get('maxmemory_bytes', 0)} bytes")
            lines.append(f"- RSS Memory: {memory.get('used_memory_rss_bytes', 0)} bytes")
            lines.append(f"- Peak Memory: {memory.get('used_memory_peak_bytes', 0)} bytes")
            lines.append(f"- Fragmentation Ratio: {memory.get('mem_fragmentation_ratio', 1.0)}")
            lines.append(f"- Memory Allocator: {memory.get('mem_allocator', 'N/A')}")
            lines.append("")

        # Performance metrics (raw data only)
        performance = diagnostic_data.get("performance", {})
        if performance and "error" not in performance:
            lines.append("### Performance Metrics (Raw Data)")
            lines.append(f"- Ops/Second: {performance.get('instantaneous_ops_per_sec', 0)}")
            lines.append(f"- Total Commands: {performance.get('total_commands_processed', 0)}")
            lines.append(f"- Keyspace Hits: {performance.get('keyspace_hits', 0)}")
            lines.append(f"- Keyspace Misses: {performance.get('keyspace_misses', 0)}")
            lines.append(f"- Expired Keys: {performance.get('expired_keys', 0)}")
            lines.append(f"- Evicted Keys: {performance.get('evicted_keys', 0)}")
            lines.append("")

        # Client metrics (raw data only)
        clients = diagnostic_data.get("clients", {})
        if clients and "error" not in clients:
            lines.append("### Client Connection Metrics (Raw Data)")
            lines.append(f"- Connected Clients: {clients.get('connected_clients', 0)}")
            lines.append(f"- Blocked Clients: {clients.get('blocked_clients', 0)}")

            client_connections = clients.get("client_connections", [])
            if client_connections:
                lines.append(f"- Total Client Records: {len(client_connections)}")
                # Sample some client data
                sample_clients = client_connections[:3]
                for i, client in enumerate(sample_clients, 1):
                    idle = client.get("idle_seconds", 0)
                    lines.append(f"  - Client {i}: {client.get('addr', 'N/A')}, idle {idle}s")
            lines.append("")

        # Slowlog data (raw entries)
        slowlog = diagnostic_data.get("slowlog", {})
        if slowlog and "error" not in slowlog:
            lines.append("### Slowlog Data (Raw Entries)")
            lines.append(f"- Slowlog Length: {slowlog.get('slowlog_length', 0)}")

            entries = slowlog.get("slowlog_entries", [])
            if entries:
                lines.append(f"- Recent Entries: {len(entries)}")
                # Show sample entries
                for i, entry in enumerate(entries[:3], 1):
                    duration_us = entry.get("duration_microseconds", 0)
                    lines.append(
                        f"  - Entry {i}: {entry.get('command', 'Unknown')} ({duration_us} μs)"
                    )
            lines.append("")

        lines.append("---")
        lines.append(
            "**Note**: This is raw diagnostic data. Agent should analyze values, calculate percentages/ratios, and determine operational severity levels."
        )

        return "\n".join(lines)


# Singleton instance
_sre_agent: Optional[SRELangGraphAgent] = None


def get_sre_agent() -> SRELangGraphAgent:
    """Get or create the singleton SRE agent instance."""
    global _sre_agent
    if _sre_agent is None:
        _sre_agent = SRELangGraphAgent()
    return _sre_agent
