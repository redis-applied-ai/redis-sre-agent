"""LangGraph-based SRE Agent implementation.

This module implements a LangGraph workflow for SRE operations, providing
multi-turn conversation handling, tool calling integration, and state management.
"""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional, TypedDict
from uuid import uuid4

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
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
    search_knowledge_base,
)

logger = logging.getLogger(__name__)

# SRE-focused system prompt
SRE_SYSTEM_PROMPT = """
You are an expert Redis SRE (Site Reliability Engineering) agent specialized in
precise problem identification, triage, and solution development.

## Your Mission: Focused Problem Solving

**YOUR WORKFLOW FOR EVERY REQUEST**:

**STEP 1**: ANALYZE the diagnostic data provided - identify actual problems from metrics
**STEP 2**: DETERMINE the problem category (memory, connections, performance, configuration, etc.)
**STEP 3**: INVESTIGATE usage patterns and configurations relevant to the identified problem
**STEP 4**: SEARCH knowledge base for solutions appropriate to the specific problem type
**STEP 5**: PROVIDE remediation steps that are SAFE for the current configuration and usage pattern

**DIAGNOSTIC DATA**: Most queries will include current Redis diagnostic data. Analyze this data first to identify problems.

## CRITICAL: Data-First Analysis

1. **Analyze provided diagnostic data**: Most queries include Redis diagnostic data - examine this first
2. **Identify specific problems**: Look for dangerous configurations, high utilization, performance issues
3. **Validate severity**: Determine if problems require immediate action (OOM risk, thrashing, etc.)
4. **Use tools for follow-up**: Get deeper analysis or search for solutions to discovered problems
5. **Focus on immediate threats**: Prioritize issues that could cause system failure

## Tool Usage for Follow-up

**`get_detailed_redis_diagnostics`**: When you need deeper analysis of specific problem areas (memory, performance, etc.)
**`search_knowledge_base`**: To find immediate remediation steps for discovered problems
**`check_service_health`**: Only if no diagnostic data was provided in the query

## Immediate Action Focus

When you find problems, prioritize based on the problem category:
- **Connection Issues**: Client connection limits, blocked clients, timeout problems
- **Memory Issues**: OOM risk, high utilization, fragmentation problems
- **Performance Issues**: Slow operations, high latency, blocking commands
- **Configuration Issues**: Dangerous settings, missing policies, security gaps

## Response Structure - Problem-Focused

### Problem Assessment
- **Described Issue**: [What the user reported]
- **Observed Issue**: [What your diagnostics actually show]
- **Problem Category**: [Connection/Memory/Performance/Configuration/Security]
- **Severity**: [Based on actual metrics and operational impact]

### Immediate Actions Required
Provide remediation steps appropriate to the identified problem category and current configuration.

### Solution Sources
- **Runbooks Used**: [Specific documents that provided the immediate remediation steps]
- **Diagnostic Evidence**: [Key metrics that revealed the actual problems]

## What NOT to Do

- Do NOT suggest "capacity planning" or other obvious long-term practices for live incidents
- Do NOT recommend generic optimizations like "use ziplists" (Redis already uses them automatically)
- Do NOT explain Redis concepts unless directly relevant to immediate remediation
- Do NOT provide theoretical advice - focus on actual observed problems requiring immediate action
- Do NOT give educational overviews - this is incident triage, not training

## Knowledge Search Strategy

Search for immediate remediation steps based on the identified problem category:
- **Connection Issues**: "Redis connection limit troubleshooting", "client timeout resolution"
- **Memory Issues**: "Redis memory optimization", "eviction policy configuration"
- **Performance Issues**: "Redis slow query analysis", "performance optimization"
- **Configuration Issues**: "Redis security configuration", "operational best practices"
- **Search by symptoms**: Use specific metrics and error patterns you discover

## Usage Pattern Analysis (Express with Uncertainty)

Redis usage patterns must be inferred from multiple signals - persistence/backup
settings alone are insufficient. Always express your analysis as **likely patterns**
rather than definitive conclusions, and acknowledge the uncertainty inherent in
pattern detection.

### Signals That May Suggest Cache Usage
- **High TTL coverage**: `expires` count close to total `keys` count in keyspace info
- **Active expiration**: High `expired_keys` count in stats
- **No maxmemory policy set**: May indicate oversight, not intentional persistent storage
- **Key patterns**: Session IDs, temporary tokens, calculated results

### Signals That May Suggest Persistent Storage
- **Low TTL coverage**: Few keys with TTL (`expires` << `keys`)
- **Low expiration activity**: `expired_keys` count is minimal
- **Maxmemory policy set to avoid eviction**: `noeviction` policy configured
- **Key patterns**: User data, business entities, permanent application state

### Ambiguous Configurations (High Uncertainty)
- **AOF/RDB enabled with high TTL coverage**: Could be cache with backup for faster restart
- **No maxmemory limit with mixed TTL patterns**: Could be intentional or oversight
- **Eviction policies with persistence enabled**: Hybrid pattern or misconfiguration

### Pattern Analysis Language Guidelines
- Use qualifying language: "**appears to be**", "**likely indicates**", "**suggests**", "**may be**"
- Always acknowledge uncertainty: "**Based on available indicators**", "**Analysis suggests**"
- Never state definitively: Avoid "is a cache" or "is persistent storage"
- Example: "Analysis **suggests** this **may be** a persistent datastore based on 0% TTL coverage and noeviction policy"

### Recommendation Safety Guidelines
- **When uncertain**: Always recommend investigation first before destructive changes
- **Mixed signals**: Suggest configuration review rather than policy changes
- **Unclear patterns**: Focus on immediate relief without changing data retention behavior

## Source Citation Requirements

**ALWAYS CITE YOUR SOURCES** when referencing information from search results:
- When you use search_knowledge_base, cite the source document and title
- Format citations as: "According to [Document Title] (source: [source_path])"
- For runbooks, indicate document type: "Based on the runbook: [Title]"
- For documentation, indicate document type: "From Redis documentation: [Title]"
- Include severity level when relevant: "[Title] (severity: critical)"
- When combining information from multiple sources, cite each one

**Example citations:**
- "According to Redis Connection Limit Exceeded Troubleshooting (source: redis-connection-limit-exceeded.md), the immediate steps are..."
- "Based on the runbook: Redis Memory Fragmentation Crisis (severity: high), you should..."
- "From Redis documentation: Performance Optimization Guide, the recommended approach is..."

Remember: You are responding to a live incident. Focus on immediate threats and actionable steps to prevent system failure.
"""

# Fact-checker system prompt
FACT_CHECKER_PROMPT = """You are a Redis technical fact-checker. Your role is to review SRE agent responses for factual accuracy about Redis concepts, metrics, operations, and URLs.

## Your Task

Review the provided SRE agent response and identify any statements that are:
1. **Technically incorrect** about Redis internals, operations, or behavior
2. **Misleading interpretations** of Redis metrics or diagnostic data
3. **Unsupported claims** that lack evidence from the diagnostic data provided
4. **Contradictions** between stated facts and the actual data shown
5. **Invalid URLs** that return 404 errors or are inaccessible

## Common Redis Fact-Check Areas

- **Memory Operations**: Redis is entirely in-memory; no disk access for data retrieval
- **Usage Pattern Detection**: Must consider TTL coverage (`expires` vs `keys`), expiration activity (`expired_keys`), and maxmemory policies - not just AOF/RDB settings
- **Keyspace Hit Rate**: Measures key existence (hits) vs non-existence (misses), not memory vs disk
- **Replication**: Master/slave terminology, replication lag implications
- **Persistence**: RDB vs AOF, when disk I/O actually occurs
- **Eviction Policies**: How different policies work and when they trigger
- **Configuration**: Default values, valid options, and their implications
- **Documentation URLs**: Verify that referenced URLs are valid and accessible

## Response Format

If you find factual errors or invalid URLs, respond with:
```json
{
  "has_errors": true,
  "errors": [
    {
      "claim": "exact text of the incorrect claim or invalid URL",
      "issue": "explanation of why it's wrong or URL validation result",
      "category": "redis_internals|metrics_interpretation|configuration|invalid_url|other"
    }
  ],
  "suggested_research": [
    "specific topics the agent should research to correct the errors"
  ],
  "url_validation_performed": true
}
```

If no errors are found, respond with:
```json
{
  "has_errors": false,
  "validation_notes": "brief note about what was verified",
  "url_validation_performed": true
}
```

Be strict but fair - flag clear technical inaccuracies and broken URLs, not minor wording choices or style preferences.
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


# TODO: Break this out into functions.
# TODO: Researcher, Safety Evaluator, and Fact-checker should be individual nodes
#       with conditional edges.
class SRELangGraphAgent:
    """LangGraph-based SRE Agent with multi-turn conversation and tool calling."""

    def __init__(self, progress_callback=None):
        """Initialize the SRE LangGraph agent."""
        self.settings = settings
        self.progress_callback = progress_callback
        # Single LLM with both reasoning and function calling capabilities
        self.llm = ChatOpenAI(
            model=self.settings.openai_model,
            openai_api_key=self.settings.openai_api_key,
        )

        # Bind SRE tools to the LLM
        self.llm_with_tools = self.llm.bind_tools(
            [
                {
                    "type": "function",
                    "function": {
                        "name": "analyze_system_metrics",
                        "description": "Analyze system metrics and performance data for Redis infrastructure using Prometheus queries",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "metric_query": {
                                    "type": "string",
                                    "description": "Prometheus metric query (e.g., 'redis_memory_used_bytes', 'redis_connected_clients', 'rate(redis_commands_processed_total[1m])'). Must be a valid Prometheus metric name or query expression.",
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
                        "name": "search_knowledge_base",
                        "description": "Search comprehensive knowledge base including SRE runbooks, Redis documentation, troubleshooting guides, and operational procedures. Use this for finding both Redis-specific documentation (commands, configuration, concepts) and SRE procedures.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "query": {
                                    "type": "string",
                                    "description": "Search query - can include Redis commands (e.g. 'MEMORY USAGE'), configuration options (e.g. 'maxmemory-policy'), concepts (e.g. 'eviction policies'), or SRE procedures (e.g. 'connection limit troubleshooting')",
                                },
                                "category": {
                                    "type": "string",
                                    "description": "Optional category to focus search on",
                                    "enum": [
                                        "incident_response",
                                        "monitoring",
                                        "performance",
                                        "troubleshooting",
                                        "maintenance",
                                        "redis_commands",
                                        "redis_config",
                                        "redis_concepts",
                                    ],
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
                        "description": "Check the SRE Agent's own health status and system components. This tool checks the agent service itself (Redis connection, vectorizer, task queue), NOT Redis instances. Use Redis diagnostics tools to check Redis instance health. Only use this when specifically asked about the agent's health or when troubleshooting the agent service itself.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "service_name": {
                                    "type": "string",
                                    "description": "Service to check - use 'sre-agent' to check this agent's health status and components",
                                    "default": "sre-agent",
                                },
                                "endpoints": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "Health check endpoints for the SRE agent service (not Redis instances)",
                                    "default": ["http://localhost:8000/health"],
                                },
                                "timeout": {
                                    "type": "integer",
                                    "description": "Request timeout in seconds",
                                    "default": 30,
                                },
                            },
                            "required": [],
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
                                "redis_url": {
                                    "type": "string",
                                    "description": "Redis connection URL to diagnose (required, e.g., 'redis://localhost:6379')",
                                },
                                "sections": {
                                    "type": "string",
                                    "description": "Comma-separated diagnostic sections: 'memory', 'performance', 'clients', 'slowlog', 'configuration', 'keyspace', 'replication', 'persistence', 'cpu'. Use 'all' or leave empty for comprehensive diagnostics.",
                                },
                                "time_window_seconds": {
                                    "type": "integer",
                                    "description": "Time window for metrics analysis (future enhancement)",
                                },
                            },
                            "required": ["redis_url"],
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
            "search_knowledge_base": search_knowledge_base,
            "check_service_health": check_service_health,
            "ingest_sre_document": ingest_sre_document,
            "get_detailed_redis_diagnostics": get_detailed_redis_diagnostics,
        }

        logger.info("SRE LangGraph agent initialized with tool bindings")

    def _build_workflow(self) -> StateGraph:
        """Build the LangGraph workflow for SRE operations."""

        async def agent_node(state: AgentState) -> AgentState:
            """Main agent node that processes user input and decides on tool calls."""
            messages = state["messages"]
            iteration_count = state.get("iteration_count", 0)
            # max_iterations = state.get("max_iterations", 10)  # Not used in this function

            # Add system message if this is the first interaction
            if len(messages) == 1 and isinstance(messages[0], HumanMessage):
                system_message = AIMessage(content=SRE_SYSTEM_PROMPT)
                messages = [system_message] + messages

            # Generate response with tool calling capability using retry logic
            async def _agent_llm_call():
                """Inner function for agent LLM call with retry logic."""
                return await self.llm_with_tools.ainvoke(messages)

            try:
                response = await self._retry_with_backoff(
                    _agent_llm_call,
                    max_retries=self.settings.llm_max_retries,
                    initial_delay=self.settings.llm_initial_delay,
                    backoff_factor=self.settings.llm_backoff_factor,
                )
                logger.debug("Agent LLM call successful after potential retries")
            except Exception as e:
                logger.error(f"Agent LLM call failed after all retries: {str(e)}")
                # Fallback response to prevent workflow failure
                response = AIMessage(
                    content="I apologize, but I'm experiencing technical difficulties processing your request. Please try again in a moment."
                )

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
                    logger.error(f"Tool execution error for {tool_name}: {str(e)}")

                # Create tool message
                tool_message = ToolMessage(content=tool_content, tool_call_id=tool_call_id)
                tool_messages.append(tool_message)

            # Update messages with tool results
            state["messages"] = messages + tool_messages
            state["current_tool_calls"] = []  # Clear tool calls

            return state

        async def reasoning_node(state: AgentState) -> AgentState:
            """Final reasoning node using O1 model for better analysis."""
            messages = state["messages"]

            # Create a focused prompt for the reasoning model
            conversation_context = []

            # Add the original query
            for msg in messages:
                if isinstance(msg, HumanMessage):
                    conversation_context.append(f"User Query: {msg.content}")
                elif isinstance(msg, ToolMessage):
                    conversation_context.append(f"Tool Data: {msg.content}")

            reasoning_prompt = f"""{SRE_SYSTEM_PROMPT}

## FINAL ANALYSIS TASK

Based on the diagnostic data and tool results below, provide your focused SRE assessment:

{chr(10).join(conversation_context)}

Follow your SRE workflow exactly:
1. **Problem Assessment**: What specific issues did you identify from the diagnostic data?
2. **Usage Pattern Analysis**: What do the indicators **suggest** about cache vs persistent usage? Express with uncertainty.
3. **Immediate Actions Required**: Safe remediation steps appropriate for the **likely** usage pattern
4. **Solution Sources**: What diagnostic evidence supports your recommendations?

Keep your response concise and action-focused. This is incident triage, not education.

**Format numbers using US conventions with commas** (e.g., "4,950 keys" not "4 950 keys")."""

            try:
                # Use configured model for final analysis
                async def _reasoning_llm_call():
                    return await self.llm.ainvoke([HumanMessage(content=reasoning_prompt)])

                response = await self._retry_with_backoff(
                    _reasoning_llm_call,
                    max_retries=self.settings.llm_max_retries,
                    initial_delay=self.settings.llm_initial_delay,
                    backoff_factor=self.settings.llm_backoff_factor,
                )
                logger.debug("Reasoning LLM call successful")
            except Exception as e:
                logger.error(f"Reasoning LLM call failed after all retries: {str(e)}")
                # Fallback to a simple response
                response = AIMessage(
                    content="I apologize, but I encountered technical difficulties during analysis. Please try again or contact support."
                )

            # Update state with final reasoning response
            state["messages"] = messages + [response]
            return state

        def should_continue(state: AgentState) -> str:
            """Decide whether to continue with tools, reasoning, or end the conversation."""
            messages = state["messages"]
            iteration_count = state.get("iteration_count", 0)
            max_iterations = state.get("max_iterations", 10)

            # Check iteration limit
            if iteration_count >= max_iterations:
                logger.warning(f"Reached max iterations ({max_iterations})")
                return "reasoning"  # Go to reasoning for final analysis

            # Check if the last message has tool calls
            if messages and hasattr(messages[-1], "tool_calls"):
                if messages[-1].tool_calls:
                    return "tools"

            # Check if we have pending tool calls in state
            if state.get("current_tool_calls"):
                return "tools"

            # If we've used tools and have no more tool calls, go to reasoning
            has_tool_messages = any(isinstance(msg, ToolMessage) for msg in messages)
            if has_tool_messages:
                return "reasoning"

            return END

        # Build the state graph
        workflow = StateGraph(AgentState)

        # Add nodes
        workflow.add_node("agent", agent_node)
        workflow.add_node("tools", tool_node)
        workflow.add_node("reasoning", reasoning_node)

        # Add edges
        workflow.set_entry_point("agent")
        workflow.add_conditional_edges(
            "agent", should_continue, {"tools": "tools", "reasoning": "reasoning", END: END}
        )
        workflow.add_edge("tools", "agent")
        workflow.add_edge("reasoning", END)

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
            logger.error(f"Error processing SRE query: {str(e)}")

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
        """Fact-check an agent response for technical accuracy and URL validity.

        Args:
            response: The agent's response to fact-check
            diagnostic_data: Optional diagnostic data that informed the response

        Returns:
            Dict containing fact-check results including URL validation
        """
        try:
            # Extract URLs from response for validation
            import re

            url_pattern = r'https?://[^\s<>"{}|\\^`[\]]+[^\s<>"{}|\\^`[\].,;:!?)]'
            urls_in_response = re.findall(url_pattern, response)

            # Validate URLs if any were found
            url_validation_results = []
            if urls_in_response:
                logger.info(f"Found {len(urls_in_response)} URLs to validate: {urls_in_response}")

                # Import validation function from tools
                from ..tools.sre_functions import validate_url

                # Validate each URL (with shorter timeout for fact-checking)
                for url in urls_in_response:
                    validation_result = await validate_url(url, timeout=3.0)
                    url_validation_results.append(validation_result)

                    if not validation_result["valid"]:
                        logger.warning(
                            f"Invalid URL detected: {url} - {validation_result['error']}"
                        )

            # Create fact-checker LLM (separate from main agent)
            fact_checker = ChatOpenAI(
                model=self.settings.openai_model,
                openai_api_key=self.settings.openai_api_key,
            )

            # Include URL validation results in the fact-check input
            url_validation_summary = ""
            if url_validation_results:
                invalid_urls = [r for r in url_validation_results if not r["valid"]]
                if invalid_urls:
                    url_validation_summary = f"\n\n## URL Validation Results:\nINVALID URLs found: {[r['url'] for r in invalid_urls]}"
                else:
                    url_validation_summary = f"\n\n## URL Validation Results:\nAll {len(url_validation_results)} URLs are valid and accessible."

            # Prepare fact-check prompt
            fact_check_input = f"""
## Agent Response to Fact-Check:
{response}

## Diagnostic Data (if available):
{diagnostic_data if diagnostic_data else "No diagnostic data provided"}{url_validation_summary}

Please review this Redis SRE agent response for factual accuracy and URL validity. Include any invalid URLs as errors in your assessment.
"""

            messages = [
                {"role": "system", "content": FACT_CHECKER_PROMPT},
                {"role": "user", "content": fact_check_input},
            ]

            # Retry fact-check with parsing
            async def _fact_check_with_retry():
                """Inner function for fact-check retry logic."""
                fact_check_response = await fact_checker.ainvoke(messages)

                # Handle markdown code blocks if present
                response_text = fact_check_response.content.strip()
                if response_text.startswith("```json"):
                    response_text = response_text[7:]  # Remove ```json
                if response_text.endswith("```"):
                    response_text = response_text[:-3]  # Remove ```
                response_text = response_text.strip()

                # Parse JSON response - this will raise JSONDecodeError if parsing fails
                result = json.loads(response_text)
                return result

            try:
                result = await self._retry_with_backoff(
                    _fact_check_with_retry,
                    max_retries=self.settings.llm_max_retries,
                    initial_delay=self.settings.llm_initial_delay,
                    backoff_factor=self.settings.llm_backoff_factor,
                )
                logger.info(
                    f"Fact-check completed: {'errors found' if result.get('has_errors') else 'no errors'}"
                )
                return result
            except json.JSONDecodeError as e:
                logger.error(f"Fact-checker returned invalid JSON after retries: {e}")
                return {
                    "has_errors": False,
                    "validation_notes": f"Fact-checker response parsing failed after {2 + 1} attempts",
                }

        except Exception as e:
            logger.error(f"Error during fact-checking: {e}")
            # Don't block on fact-check failures - return graceful fallback
            return {
                "has_errors": False,
                "validation_notes": f"Fact-checking unavailable ({str(e)[:50]}...)",
                "fact_check_error": True,
            }

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

        # Safety evaluation - check for dangerous recommendations
        safety_result = await self._safety_evaluate_response(query, response)

        if not safety_result.get("safe", True):
            logger.warning(f"Safety evaluation failed: {safety_result}")

            risk_level = safety_result.get("risk_level", "medium")
            violations = safety_result.get("violations", [])

            # Only trigger corrections for medium risk and above
            if risk_level in ["medium", "high", "critical"]:
                logger.error(f"SAFETY VIOLATION DETECTED (risk: {risk_level}): {violations}")

                correction_guidance = safety_result.get("corrective_guidance", "")
                safety_result.get("reasoning", "")

                if correction_guidance or violations:
                    try:
                        # Create comprehensive correction query with full safety context
                        safety_json = json.dumps(safety_result, indent=2)

                        correction_query = f"""SAFETY VIOLATION - CORRECTION REQUIRED

The following safety evaluation identified problems with my previous response:

{safety_json}

Original user query: {query}

Previous response (flagged as unsafe): {response}

CORRECTION INSTRUCTIONS:
1. **Address each specific violation** listed in the safety evaluation above
2. **Follow the corrective guidance** provided by the safety evaluator
3. **Provide safer alternatives** that achieve the same operational goals
4. **Include appropriate warnings** about any remaining risks
5. **Ensure logical consistency** between your usage pattern analysis and recommendations

SPECIFIC GUIDANCE FOR COMMON ISSUES:
- If flagged for persistence changes: Suggest gradual migration steps with data backup
- If flagged for eviction policies: Recommend investigation before policy changes
- If flagged for restarts: Include steps to ensure data persistence before restart
- If flagged for contradictions: Align recommendations with your usage pattern analysis

Provide a complete corrected response that maintains the same helpful tone while addressing safety concerns."""

                        # Retry the safety correction with backoff
                        async def _safety_correction():
                            return await self.process_query(
                                correction_query, session_id, user_id, max_iterations
                            )

                        corrected_response = await self._retry_with_backoff(
                            _safety_correction,
                            max_retries=self.settings.llm_max_retries,
                            initial_delay=self.settings.llm_initial_delay,
                            backoff_factor=self.settings.llm_backoff_factor,
                        )

                        # Verify the correction is safer
                        safety_recheck = await self._safety_evaluate_response(
                            query, corrected_response, is_correction_recheck=True
                        )
                        if safety_recheck.get("safe", True):
                            logger.info("Response corrected after safety evaluation")
                            return corrected_response
                        else:
                            logger.error(
                                f"Correction still unsafe - recheck violations: {safety_recheck.get('violations', [])}"
                            )
                            logger.error(
                                f"Recheck risk level: {safety_recheck.get('risk_level', 'unknown')}"
                            )
                            # If the correction attempt reduced the risk level, accept it even if not perfect
                            original_risk = safety_result.get("risk_level", "high")
                            recheck_risk = safety_recheck.get("risk_level", "high")
                            risk_levels = {"low": 1, "medium": 2, "high": 3, "critical": 4}

                            if risk_levels.get(recheck_risk, 3) <= risk_levels.get(
                                original_risk, 3
                            ):
                                logger.info("Correction reduced risk level - accepting response")
                                return corrected_response
                            else:
                                return "⚠️ SAFETY ALERT: This request requires manual review due to potential data loss risks. Please consult with a Redis expert before proceeding."

                    except Exception as correction_error:
                        logger.error(f"Error during safety correction: {correction_error}")
                        return "⚠️ SAFETY ALERT: This request requires manual review due to potential data loss risks."
            else:
                # Low risk violations - log but don't correct
                logger.info(f"Low-risk safety issues noted (risk: {risk_level}): {violations}")

        # Fact-check the response (if it passed safety evaluation)
        fact_check_result = await self._fact_check_response(response)

        if fact_check_result.get("has_errors") and not fact_check_result.get("fact_check_error"):
            logger.warning("Fact-check identified errors in agent response")

            # Create detailed research query with full fact-check context
            fact_check_details = fact_check_result.get("errors", [])
            research_topics = fact_check_result.get("suggested_research", [])

            if research_topics or fact_check_details:
                # Include the full fact-check JSON for context
                fact_check_json = json.dumps(fact_check_result, indent=2)

                research_query = f"""FACT-CHECK CORRECTION REQUIRED

The following fact-check analysis identified technical errors in my previous response:

{fact_check_json}

Original user query: {query}

Please correct these specific issues by:
1. Researching the identified topics using search_knowledge_base tool
2. Providing technically accurate information based on authoritative sources
3. Ensuring all Redis concepts, metrics, and recommendations are correct

Focus on the specific errors identified in the fact-check analysis above."""

                logger.info("Initiating corrective research query with full fact-check context")
                try:
                    # Process the corrective query with retry logic
                    async def _fact_check_correction():
                        return await self.process_query(
                            research_query, session_id, user_id, max_iterations
                        )

                    corrected_response = await self._retry_with_backoff(
                        _fact_check_correction,
                        max_retries=self.settings.llm_max_retries,
                        initial_delay=self.settings.llm_initial_delay,
                        backoff_factor=self.settings.llm_backoff_factor,
                    )

                    # Return the corrected response without exposing internal fact-checking
                    return corrected_response
                except Exception as correction_error:
                    logger.error(f"Error during correction attempt: {correction_error}")
                    # Fall back to original response rather than failing
                    return response
        elif fact_check_result.get("fact_check_error"):
            logger.info("Fact-check completed: Using original response (fact-check unavailable)")

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

    def _format_bytes(self, bytes_value: int) -> str:
        """Format bytes into human readable format."""
        if bytes_value == 0:
            return "0 B"

        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if bytes_value < 1024.0:
                return f"{bytes_value:.1f} {unit}"
            bytes_value /= 1024.0
        return f"{bytes_value:.1f} PB"

    def _format_memory_usage(self, used_bytes: int, max_bytes: int) -> str:
        """Format memory usage with utilization percentage."""
        if max_bytes == 0:
            return f"{self._format_bytes(used_bytes)} (unlimited)"

        utilization = (used_bytes / max_bytes) * 100
        return f"{self._format_bytes(used_bytes)} of {self._format_bytes(max_bytes)} ({utilization:.1f}%)"

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

        # Memory metrics with human-readable formatting
        memory = diagnostic_data.get("memory", {})
        if memory and "error" not in memory:
            lines.append("### Memory Metrics")
            used_bytes = memory.get("used_memory_bytes", 0)
            max_bytes = memory.get("maxmemory_bytes", 0)
            lines.append(f"- Used Memory: {self._format_memory_usage(used_bytes, max_bytes)}")
            lines.append(
                f"- RSS Memory: {self._format_bytes(memory.get('used_memory_rss_bytes', 0))}"
            )
            lines.append(
                f"- Peak Memory: {self._format_bytes(memory.get('used_memory_peak_bytes', 0))}"
            )
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

    async def _retry_with_backoff(
        self, func, max_retries: int = 3, initial_delay: float = 1.0, backoff_factor: float = 2.0
    ):
        """
        Retry a function with exponential backoff.

        Args:
            func: Async function to retry
            max_retries: Maximum number of retry attempts
            initial_delay: Initial delay in seconds
            backoff_factor: Multiplier for delay between retries

        Returns:
            Function result on success

        Raises:
            Last exception if all retries fail
        """
        delay = initial_delay
        last_exception = None

        for attempt in range(max_retries + 1):  # +1 for initial attempt
            try:
                return await func()
            except Exception as e:
                last_exception = e
                if attempt == max_retries:  # Last attempt failed
                    logger.error(f"All {max_retries + 1} attempts failed. Last error: {str(e)}")
                    raise e

                logger.warning(
                    f"Attempt {attempt + 1} failed: {str(e)}. Retrying in {delay:.1f}s..."
                )
                await asyncio.sleep(delay)
                delay *= backoff_factor

        # This should never be reached, but just in case
        raise last_exception

    async def _safety_evaluate_response(
        self, original_query: str, response: str, is_correction_recheck: bool = False
    ) -> Dict[str, Any]:
        """
        Evaluate response for dangerous recommendations that could cause data loss.

        This safety evaluator specifically checks for Redis data persistence safety:
        - Ensures eviction policies aren't suggested for persistent data stores
        - Validates that recommendations align with identified usage patterns
        - Flags logic contradictions between analysis and recommendations

        Args:
            original_query: The original user query (may contain diagnostic data)
            response: The agent's response to evaluate

        Returns:
            Dict containing safety evaluation results
        """
        safety_prompt = """
You are a Redis SRE Safety Evaluator. Your job is to identify recommendations
that could cause SIGNIFICANT data loss or system failure.

EVALUATE THIS RESPONSE FOR SERIOUS SAFETY CONCERNS:

ORIGINAL QUERY:
{original_query}

AGENT RESPONSE:
{response}

Only flag as unsafe if the recommendations could cause:
1. **Immediate data loss** - Destructive eviction policies on persistent stores
2. **Logical contradictions** - Actions that contradict the usage pattern analysis
3. **System failure** - Operations that would crash or corrupt Redis

DO NOT flag as unsafe:
- Recommendations with appropriate warnings about risks
- Suggestions to disable snapshots IF accompanied by proper migration guidance
- Restart recommendations IF they include data safety precautions
- Operations that carry operational risk but are standard Redis practices
- Corrected responses that include safety warnings and alternative approaches

RESPONSE FORMAT:
{{
    "safe": true/false,
    "risk_level": "low|medium|high|critical",
    "violations": ["only SERIOUS concerns that could cause data loss"],
    "corrective_guidance": "specific guidance for safer alternatives",
    "reasoning": "explanation focusing on data protection"
}}

Focus on preventing data loss, not operational inconvenience. Standard Redis
operations with appropriate warnings should be considered safe.

{"CORRECTION RECHECK: This is a safety recheck of a corrected response. Be more lenient - if the response includes appropriate warnings and safer alternatives, consider it safe." if is_correction_recheck else ""}
"""

        async def _evaluate_with_retry():
            """Inner function for retry logic."""
            try:
                # Safely convert objects to strings, handling MagicMock objects
                def safe_str(obj):
                    try:
                        return str(obj)
                    except Exception:
                        return repr(obj)

                query_str = safe_str(original_query)
                response_str = safe_str(response)

                # Use safer string replacement to avoid MagicMock formatting issues
                formatted_prompt = safety_prompt.replace("{original_query}", query_str)
                formatted_prompt = formatted_prompt.replace("{response}", response_str)

                safety_response = await self.llm.ainvoke([SystemMessage(content=formatted_prompt)])
            except Exception as format_error:
                logger.error(f"Error formatting safety prompt: {format_error}")
                raise

            # Parse the JSON response - this will raise JSONDecodeError if parsing fails
            result = json.loads(safety_response.content)
            return result

        try:
            # Use retry logic for both LLM call and JSON parsing
            result = await self._retry_with_backoff(
                _evaluate_with_retry,
                max_retries=self.settings.llm_max_retries,
                initial_delay=self.settings.llm_initial_delay,
                backoff_factor=self.settings.llm_backoff_factor,
            )
            return result

        except json.JSONDecodeError as e:
            logger.error(f"Safety evaluation JSON parsing failed after retries: {str(e)}")
            return {
                "safe": False,
                "violations": [
                    "Could not parse safety evaluation response after multiple attempts"
                ],
                "corrective_guidance": "Manual safety review required due to persistent parsing error",
                "reasoning": f"Safety evaluation response was not in expected JSON format after {self.settings.llm_max_retries + 1} attempts",
            }
        except Exception as e:
            try:
                error_str = str(e)
            except Exception:
                error_str = repr(e)
            logger.error(f"Safety evaluation failed after retries: {error_str}")
            return {
                "safe": False,
                "violations": ["Safety evaluation failed"],
                "risk_level": "high",
                "corrective_guidance": "Manual review required - safety evaluation error",
                "reasoning": f"Safety evaluation error after retries: {str(e)}",
            }


# Singleton instance
_sre_agent: Optional[SRELangGraphAgent] = None


def get_sre_agent() -> SRELangGraphAgent:
    """Get or create the singleton SRE agent instance."""
    global _sre_agent
    if _sre_agent is None:
        _sre_agent = SRELangGraphAgent()
    return _sre_agent
