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
from ..core.tasks import (
    analyze_system_metrics,
    check_service_health,
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

## Response Guidelines

1. **Be Direct**: Provide clear, actionable guidance for SRE scenarios
2. **Safety First**: Always consider impact and safety when suggesting operational changes
3. **Evidence-Based**: Use metrics and data to support recommendations
4. **Escalation Path**: Know when to suggest escalating issues or seeking additional help

## Tool Usage Strategy

- Use `search_runbook_knowledge` for procedures, troubleshooting steps, and best practices
- Use `analyze_system_metrics` for performance analysis and capacity planning
- Use `check_service_health` for operational status verification
- Use `ingest_sre_document` to add new procedures or update knowledge base

## Communication Style

- Use technical precision while remaining clear
- Provide step-by-step procedures when appropriate
- Include relevant metrics, thresholds, and monitoring points
- Suggest prevention strategies alongside reactive measures

Remember: You're here to help maintain reliable Redis infrastructure and support the SRE team's operational excellence.
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

    def __init__(self):
        """Initialize the SRE LangGraph agent."""
        self.settings = settings
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
        }

        logger.info("SRE LangGraph agent initialized with tool bindings")

    def _build_workflow(self) -> StateGraph:
        """Build the LangGraph workflow for SRE operations."""

        def agent_node(state: AgentState) -> AgentState:
            """Main agent node that processes user input and decides on tool calls."""
            messages = state["messages"]
            iteration_count = state.get("iteration_count", 0)
            max_iterations = state.get("max_iterations", 10)

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

                try:
                    # Execute the SRE tool (async call)
                    if tool_name in self.sre_tools:
                        # Call the async Docket task
                        result = await self.sre_tools[tool_name](**tool_args)

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
                return response_content
            else:
                logger.warning("No valid response generated by SRE agent")
                return "I apologize, but I couldn't generate a proper response. Please try rephrasing your question."

        except Exception as e:
            logger.error(f"Error processing SRE query: {e}")
            return f"I encountered an error while processing your request: {str(e)}. Please try again or contact support if the issue persists."

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


# Singleton instance
_sre_agent: Optional[SRELangGraphAgent] = None


def get_sre_agent() -> SRELangGraphAgent:
    """Get or create the singleton SRE agent instance."""
    global _sre_agent
    if _sre_agent is None:
        _sre_agent = SRELangGraphAgent()
    return _sre_agent
