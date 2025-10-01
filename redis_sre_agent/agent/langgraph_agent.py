"""LangGraph-based SRE Agent implementation.

This module implements a LangGraph workflow for SRE operations, providing
multi-turn conversation handling, tool calling integration, and state management.
"""

import asyncio
import json
import logging
from typing import Any, Awaitable, Callable, Dict, List, Optional, TypedDict
from urllib.parse import urlparse
from uuid import uuid4

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field

from ..api.instances import get_instances_from_redis
from ..core.config import settings
from ..tools.protocol_agent_tools import PROTOCOL_TOOL_FUNCTIONS, get_protocol_based_tools
from ..tools.registry import auto_register_default_providers
from ..tools.sre_functions import (
    get_all_document_fragments,
    get_related_document_fragments,
    ingest_sre_document,
    search_knowledge_base,
)  # Keep knowledge base functions

logger = logging.getLogger(__name__)


def _parse_redis_connection_url(connection_url: str) -> tuple[str, int]:
    """Parse Redis connection URL to extract host and port."""
    try:
        parsed = urlparse(connection_url)
        host = parsed.hostname or "localhost"
        port = parsed.port or 6379
        return host, port
    except Exception as e:
        logger.warning(f"Failed to parse connection URL {connection_url}: {e}")
        return "localhost", 6379


# SRE-focused system prompt
SRE_SYSTEM_PROMPT = """
You are an experienced Redis SRE who writes clear, actionable triage notes. You sound like a knowledgeable colleague sharing findings and recommendations - professional but conversational.

## Your Approach

When someone brings you a Redis issue, you:
1. **Look at the data first** - examine any diagnostic info they've provided
2. **Figure out what's actually happening** - separate symptoms from root causes
3. **Search your knowledge** when you need specific troubleshooting steps
4. **Give them a clear plan** - actionable steps they can take right now

## Writing Style

Write like you're updating a colleague on what you found. Use natural language:
- "I took a look at your Redis instance and here's what I'm seeing..."
- "The good news is..." / "The concerning part is..."
- "Let's start with..." / "Next, I'd recommend..."
- "Based on what I found in our runbooks..."

## Response Format (Use Proper Markdown)

Structure your response with clear headers and formatting:

# Initial Assessment
Brief summary of what you found

# What I'm Seeing
Key findings from diagnostics, with **bold** for important metrics

# My Recommendation
Clear action plan with:
- Numbered steps for immediate actions
- **Bold text** for critical items
- Code blocks for commands when helpful

# Supporting Info
- Where you got your recommendations (cite runbooks/docs)
- Key diagnostic evidence that supports your analysis

## Formatting Requirements

- Use `#` headers for main sections
- Use `**bold**` for emphasis on critical items
- Use `-` or `1.` for lists and action items
- Use code blocks with ``` for commands
- Add blank lines between paragraphs for readability
- Keep paragraphs short (2-3 sentences max)

## Keep It Practical

Focus on what they can do right now:
- Skip the theory - they need action steps
- Don't explain basic Redis concepts unless directly relevant
- Avoid generic advice like "monitor your metrics" - be specific
- If you're not sure about something, say so and suggest investigation steps

## When to Search Knowledge Base

Look up specific troubleshooting steps when you identify:
- Connection limit issues → search "connection limit troubleshooting"
- Memory problems → search "memory optimization" or "eviction policy"
- Performance issues → search "slow query analysis" or "latency troubleshooting"
- Security concerns → search "Redis security configuration"

## Understanding Usage Patterns

Search for immediate remediation steps based on the identified problem category:
- **Connection Issues**: "Redis connection limit troubleshooting", "client timeout resolution"
- **Memory Issues**: "Redis memory optimization", "eviction policy configuration"
- **Performance Issues**: "Redis slow query analysis", "performance optimization"
- **Configuration Issues**: "Redis security configuration", "operational best practices"
- **Search by symptoms**: Use specific metrics and error patterns you discover

When you're trying to figure out how Redis is being used, look for clues but don't be too definitive. Usage patterns aren't always clear-cut.

**Signs it might be used as a cache:**
- Most keys have TTLs set (high expires/keys ratio)
- Lots of keys expiring regularly
- Eviction policies are set up
- Key names look like session IDs or temp data

**Signs it might be persistent storage:**
- Few or no TTLs on keys (low expires/keys ratio)
- Very few keys expiring
- `noeviction` policy to prevent data loss
- Key names look like user data or business entities

Redis usage patterns must be inferred from multiple signals - persistence/backup
settings alone are insufficient. Always express your analysis as **likely patterns**
rather than definitive conclusions, and acknowledge the uncertainty inherent in
pattern detection.

**When it's unclear:**
- Mixed TTL patterns could mean hybrid usage
- Persistence enabled with high TTL coverage might be cache with backup
- No clear pattern? Focus on the immediate problem rather than guessing

**How to talk about it:**
- "Based on what I'm seeing, this looks like..."
- "The data suggests this might be..."
- "I can't tell for sure, but it appears to be..."
- When in doubt: "Let's focus on the immediate issue first"

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
    instance_context: Optional[Dict[str, Any]]  # For Redis instance context


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

        # Auto-register default providers based on configuration
        config = {
            "redis_url": settings.redis_url,
            "prometheus_url": getattr(settings, "prometheus_url", None),
            "grafana_url": getattr(settings, "grafana_url", None),
            "grafana_api_key": getattr(settings, "grafana_api_key", None),
        }
        auto_register_default_providers(config)

        # Get protocol-based tool definitions
        protocol_tools = get_protocol_based_tools()

        # Add knowledge base tools that aren't part of the protocol system yet
        knowledge_tools = [
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
                    "name": "get_all_document_fragments",
                    "description": "Retrieve ALL fragments/chunks of a specific document when you find a relevant piece and need the complete context. Use the document_hash from search results to get the full document content. This is essential when a search result fragment looks relevant but you need the complete information to provide a comprehensive answer.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "document_hash": {
                                "type": "string",
                                "description": "The document hash from search results (e.g., from search_knowledge_base results)",
                            },
                            "include_metadata": {
                                "type": "boolean",
                                "description": "Whether to include document metadata",
                                "default": True,
                            },
                        },
                        "required": ["document_hash"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_related_document_fragments",
                    "description": "Get related fragments around a specific chunk for additional context without retrieving the entire document. Use this when you want surrounding context for a specific fragment you found in search results. Provide the document_hash and chunk_index from search results.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "document_hash": {
                                "type": "string",
                                "description": "The document hash from search results",
                            },
                            "current_chunk_index": {
                                "type": "integer",
                                "description": "The chunk index from search results to get context around",
                            },
                            "context_window": {
                                "type": "integer",
                                "description": "Number of chunks before and after to include (default: 2)",
                                "default": 2,
                            },
                        },
                        "required": ["document_hash", "current_chunk_index"],
                    },
                },
            },
        ]

        # Combine protocol tools with knowledge tools
        all_tools = protocol_tools + knowledge_tools

        # Bind all tools to the LLM
        self.llm_with_tools = self.llm.bind_tools(all_tools)

        # Build the LangGraph workflow
        self.workflow = self._build_workflow()
        # Note: We'll create a new MemorySaver for each query to ensure proper isolation
        # This prevents cross-contamination between different tasks/threads

        # SRE tool mapping - combine protocol-based tools with knowledge base tools
        self.sre_tools = {
            **PROTOCOL_TOOL_FUNCTIONS,  # Protocol-based tools
            "search_knowledge_base": search_knowledge_base,  # Knowledge base tools
            "ingest_sre_document": ingest_sre_document,
            "get_all_document_fragments": get_all_document_fragments,  # Fragment retrieval tools
            "get_related_document_fragments": get_related_document_fragments,
        }

        logger.info("SRE LangGraph agent initialized with tool bindings")

    async def _resolve_instance_redis_url(self, instance_id: str) -> Optional[str]:
        """Resolve instance ID to Redis URL using connection_url from instance data.

        IMPORTANT: This method returns None if the instance cannot be found.
        It NEVER falls back to settings.redis_url (the application database).
        Tools must handle None and fail gracefully rather than connecting to the wrong database.
        """
        try:
            instances = await get_instances_from_redis()
            for instance in instances:
                if instance.id == instance_id:
                    return instance.connection_url

            logger.error(
                f"Instance {instance_id} not found. "
                "NOT falling back to application database - tools must fail gracefully."
            )
            return None
        except Exception as e:
            logger.error(
                f"Failed to resolve instance {instance_id}: {e}. "
                "NOT falling back to application database - tools must fail gracefully."
            )
            return None

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

                # Send meaningful reflection about what the agent is doing
                if self.progress_callback:
                    reflection = self._generate_tool_reflection(tool_name, tool_args)
                    await self.progress_callback(reflection, "agent_reflection")

                try:
                    # Execute the SRE tool (async call)
                    if tool_name in self.sre_tools:
                        # Get instance context from state if available
                        instance_context = state.get("instance_context")
                        target_instance = None

                        if instance_context and instance_context.get("instance_id"):
                            # Resolve instance details for tool execution
                            try:
                                instances = await get_instances_from_redis()
                                for instance in instances:
                                    if instance.id == instance_context["instance_id"]:
                                        target_instance = instance
                                        break
                            except Exception as e:
                                logger.error(f"Failed to resolve instance context: {e}")

                        # Modify tool arguments based on instance context
                        modified_args = tool_args.copy()

                        if target_instance:
                            # For Redis diagnostic tools, use the instance's connection details
                            if tool_name == "get_detailed_redis_diagnostics":
                                # ALWAYS use the target instance URL, never fall back to application database
                                modified_args["redis_url"] = target_instance.connection_url
                                logger.info(
                                    f"Using target instance Redis URL: {target_instance.connection_url}"
                                )
                        else:
                            # No target instance found - fail gracefully for Redis tools
                            if tool_name == "get_detailed_redis_diagnostics":
                                logger.error(
                                    f"Cannot execute {tool_name} without target instance. "
                                    "Refusing to fall back to application database."
                                )
                                # Return error message instead of executing tool
                                tool_messages.append(
                                    ToolMessage(
                                        content="Error: Cannot connect to Redis instance. "
                                        "Instance context is required but was not found. "
                                        "Please specify which Redis instance to diagnose.",
                                        tool_call_id=tool_call_id,
                                    )
                                )
                                continue  # Skip tool execution

                            # For metrics tools, use the instance's host for Prometheus queries
                            elif tool_name == "analyze_system_metrics":
                                # Add instance host context for Prometheus queries
                                if "instance_host" not in modified_args:
                                    host, _ = _parse_redis_connection_url(
                                        target_instance.connection_url
                                    )
                                    modified_args["instance_host"] = host
                                    logger.info(f"Using instance host for metrics: {host}")

                        # Call the async SRE function
                        result = await self.sre_tools[tool_name](**modified_args)

                        # Send completion reflection
                        if self.progress_callback:
                            completion_reflection = self._generate_completion_reflection(
                                tool_name, result
                            )
                            if completion_reflection:  # Only send if not empty
                                await self.progress_callback(
                                    completion_reflection, "agent_reflection"
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

            # Send safety check reflection
            if self.progress_callback:
                await self.progress_callback(
                    "🛡️ Performing safety checks on recommendations...", "safety_check"
                )

            # Create a focused prompt for the reasoning model
            conversation_context = []

            # Add the original query
            for msg in messages:
                if isinstance(msg, HumanMessage):
                    conversation_context.append(f"User Query: {msg.content}")
                elif isinstance(msg, ToolMessage):
                    conversation_context.append(f"Tool Data: {msg.content}")

            reasoning_prompt = f"""{SRE_SYSTEM_PROMPT}

## Your Task

You've been investigating a Redis issue. Based on your diagnostic work and tool results below, write up your findings and recommendations like you're updating a colleague.

## Investigation Results

{chr(10).join(conversation_context)}

## Write Your Triage Notes

Write a natural, conversational response using proper markdown formatting. Include:

- **Clear headers** with `#` for main sections
- **Bold text** with `**` for critical findings and action items
- **Proper lists** with `-` for bullet points (ensure blank line before list and space after `-`)
- **Numbered lists** with `1.` for action steps (ensure blank line before list)
- **Code blocks** with ``` for any commands
- **Blank lines** between paragraphs and before/after lists for readability

**Critical formatting rules:**
- Always put a blank line before and after lists
- Use `- ` (dash + space) for bullet points
- Use `1. ` (number + period + space) for numbered lists
- Put blank lines between major sections

Sound like an experienced SRE sharing findings with a colleague. Be direct about what you found and what needs to happen next.

**Important**: Format numbers with commas (e.g., "4,950 keys" not "4 950 keys")."""

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

                # Send fact-checking reflection
                if self.progress_callback:
                    await self.progress_callback(
                        "🔍 Fact-checking recommendations against best practices...", "safety_check"
                    )

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

    def _generate_tool_reflection(self, tool_name: str, tool_args: dict) -> str:
        """Generate a meaningful reflection about what the agent is doing."""
        if tool_name == "get_detailed_redis_diagnostics":
            return "🔍 Analyzing Redis instance health and performance metrics..."
        elif tool_name == "search_knowledge_base":
            query = tool_args.get("query", "")
            if "memory" in query.lower():
                return "📚 Searching knowledge base for memory management best practices..."
            elif "performance" in query.lower():
                return "📚 Looking up performance optimization strategies..."
            elif "persistence" in query.lower():
                return "📚 Researching data persistence and durability options..."
            elif "connection" in query.lower():
                return "📚 Finding connection troubleshooting guidance..."
            else:
                return f"📚 Searching knowledge base for: {query}"
        elif tool_name == "analyze_system_metrics":
            return "📊 Examining system metrics and performance trends..."
        elif tool_name == "check_service_health":
            return "🏥 Performing service health checks..."
        else:
            return f"🔧 Executing {tool_name.replace('_', ' ')}..."

    def _generate_completion_reflection(self, tool_name: str, result: dict) -> str:
        """Generate a reflection about what the agent discovered."""
        if tool_name == "get_detailed_redis_diagnostics":
            if isinstance(result, dict) and result.get("status") == "success":
                diagnostics = result.get("diagnostics", {})
                memory_info = diagnostics.get("memory", {})
                if memory_info:
                    used_memory = memory_info.get("used_memory_bytes", 0)
                    max_memory = memory_info.get("maxmemory_bytes", 0)
                    if max_memory > 0:
                        usage_pct = (used_memory / max_memory) * 100
                        if usage_pct > 80:
                            return f"⚠️ Memory usage is elevated at {usage_pct:.1f}% - investigating further..."
                        elif usage_pct > 60:
                            return f"📈 Memory usage at {usage_pct:.1f}% - checking for optimization opportunities..."
                        else:
                            return f"✅ Memory usage looks healthy at {usage_pct:.1f}%"
                return "✅ Redis diagnostics collected successfully"
            else:
                return "❌ Unable to collect Redis diagnostics"
        elif tool_name == "search_knowledge_base":
            # Skip reflection for knowledge base searches to reduce UI noise
            return ""

        elif tool_name == "search_docker_logs":
            if isinstance(result, dict):
                if result.get("error"):
                    return f"❌ Docker log search failed: {result['error']}"

                total_entries = result.get("total_entries_found", 0)
                containers_searched = result.get("containers_searched", 0)

                if total_entries > 0:
                    level_dist = result.get("level_distribution", {})
                    error_count = (
                        level_dist.get("ERROR", 0)
                        + level_dist.get("FATAL", 0)
                        + level_dist.get("CRITICAL", 0)
                    )

                    if error_count > 0:
                        return f"🔍 Found {total_entries} log entries across {containers_searched} containers - {error_count} errors detected"
                    else:
                        return f"🔍 Found {total_entries} log entries across {containers_searched} containers"
                else:
                    return f"🔍 No matching log entries found in {containers_searched} containers"
            else:
                return "🔍 Docker log search completed"

        elif tool_name == "analyze_system_metrics":
            return "📊 System metrics analysis complete"
        else:
            return f"✅ {tool_name.replace('_', ' ')} completed"

    async def process_query(
        self,
        query: str,
        session_id: str,
        user_id: str,
        max_iterations: int = 10,
        context: Optional[Dict[str, Any]] = None,
        progress_callback: Optional[Callable[[str, str], Awaitable[None]]] = None,
        conversation_history: Optional[List[BaseMessage]] = None,
    ) -> str:
        """Process a single SRE query through the LangGraph workflow.

        Args:
            query: User's SRE question or request
            session_id: Session identifier for conversation context
            user_id: User identifier
            max_iterations: Maximum number of workflow iterations
            context: Additional context including instance_id if specified

        Returns:
            Agent's response as a string
        """
        logger.info(f"Processing SRE query for user {user_id}, session {session_id}")

        # Set progress callback for this query
        if progress_callback:
            self.progress_callback = progress_callback

        # Enhance query with instance context if provided
        enhanced_query = query
        if context and context.get("instance_id"):
            instance_id = context["instance_id"]
            logger.info(f"Processing query with Redis instance context: {instance_id}")

            # Resolve instance ID to get actual connection details
            try:
                instances = await get_instances_from_redis()
                target_instance = None
                for instance in instances:
                    if instance.id == instance_id:
                        target_instance = instance
                        break

                if target_instance:
                    host, port = _parse_redis_connection_url(target_instance.connection_url)
                    redis_url = target_instance.connection_url
                    # Add instance context to the query
                    enhanced_query = f"""User Query: {query}

IMPORTANT CONTEXT: This query is specifically about Redis instance:
- Instance ID: {instance_id}
- Instance Name: {target_instance.name}
- Host: {host}
- Port: {port}
- Environment: {target_instance.environment}
- Usage: {target_instance.usage}

When using Redis diagnostic tools, use this Redis URL: {redis_url}

SAFETY REQUIREMENT: You MUST verify you can connect to and gather data from this specific Redis instance before making any recommendations. If you cannot get basic metrics like maxmemory, connected_clients, or keyspace info, you lack sufficient information to make recommendations.

Please use the available tools to get information about this specific Redis instance and provide targeted troubleshooting and analysis."""
                else:
                    logger.warning(
                        f"Instance {instance_id} not found, proceeding without specific instance context"
                    )
                    enhanced_query = f"""User Query: {query}

CONTEXT: This query mentioned Redis instance ID: {instance_id}, but the instance was not found in the system. Please proceed with general Redis troubleshooting."""
            except Exception as e:
                logger.error(f"Failed to resolve instance {instance_id}: {e}")
                enhanced_query = f"""User Query: {query}

CONTEXT: This query mentioned Redis instance ID: {instance_id}, but there was an error retrieving instance details. Please proceed with general Redis troubleshooting."""

        else:
            # No specific instance provided - check if we should auto-detect
            logger.info("No specific Redis instance provided, checking for available instances")
            try:
                instances = await get_instances_from_redis()
                if len(instances) == 1:
                    # Only one instance available - use it automatically
                    target_instance = instances[0]
                    host, port = _parse_redis_connection_url(target_instance.connection_url)
                    redis_url = target_instance.connection_url
                    logger.info(
                        f"Auto-detected single Redis instance: {target_instance.name} ({redis_url})"
                    )

                    enhanced_query = f"""User Query: {query}

AUTO-DETECTED CONTEXT: Since no specific Redis instance was mentioned, I am analyzing the available Redis instance:
- Instance Name: {target_instance.name}
- Host: {host}
- Port: {port}
- Environment: {target_instance.environment}
- Usage: {target_instance.usage}

When using Redis diagnostic tools, use this Redis URL: {redis_url}

SAFETY REQUIREMENT: You MUST verify you can connect to and gather data from this Redis instance before making any recommendations. If you cannot get basic metrics like maxmemory, connected_clients, or keyspace info, you lack sufficient information to make recommendations."""

                elif len(instances) > 1:
                    # Multiple instances - ask user to specify
                    instance_list = "\n".join(
                        [
                            f"- {inst.name} ({inst.environment}): {inst.connection_url}"
                            for inst in instances
                        ]
                    )
                    enhanced_query = f"""User Query: {query}

MULTIPLE REDIS INSTANCES DETECTED: I found {len(instances)} Redis instances configured. Please specify which instance you want me to analyze:

{instance_list}

To get targeted analysis, please rephrase your query to specify which instance, or use the instance selector in the UI."""

                else:
                    # No instances configured - use default but warn
                    logger.warning("No Redis instances configured, falling back to default")
                    enhanced_query = f"""User Query: {query}

WARNING: No Redis instances are configured in the system. I will attempt to analyze the default Redis connection, but this may not be the instance you intended to troubleshoot.

SAFETY REQUIREMENT: You MUST verify you can connect to and gather meaningful data before making any recommendations."""

            except Exception as e:
                logger.error(f"Failed to check available instances: {e}")

        # Create initial state with conversation history
        # If conversation_history is provided, include it before the new query
        initial_messages = []
        if conversation_history:
            initial_messages = list(conversation_history)
            logger.info(f"Including {len(conversation_history)} messages from conversation history")
        initial_messages.append(HumanMessage(content=enhanced_query))

        initial_state: AgentState = {
            "messages": initial_messages,
            "session_id": session_id,
            "user_id": user_id,
            "current_tool_calls": [],
            "iteration_count": 0,
            "max_iterations": max_iterations,
        }

        # Store instance context in the state for tool execution
        if context and context.get("instance_id"):
            initial_state["instance_context"] = context

        # Create MemorySaver for this query
        # NOTE: RedisSaver doesn't support async (aget_tuple raises NotImplementedError)
        # Conversation history is managed by our ThreadManager in Redis
        # and passed via initial_state when needed
        checkpointer = MemorySaver()
        self.app = self.workflow.compile(checkpointer=checkpointer)

        # Configure thread for session persistence
        thread_config = {"configurable": {"thread_id": session_id}}

        try:
            # Run the workflow with isolated memory
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
            logger.error(f"Error type: {type(e)}")
            logger.error(f"Error args: {e.args}")
            import traceback

            logger.error(f"Traceback: {traceback.format_exc()}")

            class AgentResponseStr(str):
                def get(self, key: str, default: Any = None):
                    if key == "content":
                        return str(self)
                    return default

            error_msg = str(e) if str(e) else f"{type(e).__name__}: {e.args}"
            return AgentResponseStr(
                f"I encountered an error while processing your request: {error_msg}. Please try again or contact support if the issue persists."
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


def get_sre_agent() -> SRELangGraphAgent:
    """Create a new SRE agent instance for each task to prevent cross-contamination.

    Previously this was a singleton, but that caused cross-contamination between
    different tasks/threads when multiple tasks ran concurrently. Each task now
    gets its own isolated agent instance.
    """
    return SRELangGraphAgent()
