"""
Lightweight Chat Agent for fast Redis instance interaction.

This agent is designed for quick Q&A when a Redis instance is available
but the user doesn't need a full health check or triage. It has access
to all Redis tools but uses a simpler workflow without deep research
or safety-evaluation chains.
"""

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Dict, List, Optional, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode as LGToolNode
from opentelemetry import trace

from redis_sre_agent.core.config import settings
from redis_sre_agent.core.instances import RedisInstance
from redis_sre_agent.core.llm_helpers import create_llm, create_mini_llm
from redis_sre_agent.core.progress import (
    CallbackEmitter,
    NullEmitter,
    ProgressEmitter,
)
from redis_sre_agent.tools.manager import ToolManager
from redis_sre_agent.tools.models import ToolCapability

if TYPE_CHECKING:
    from pathlib import Path

from .helpers import build_result_envelope

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


CHAT_SYSTEM_PROMPT = """You are a Redis SRE agent. A user is asking about a specific Redis deployment.
You have access to the full toolset needed to inspect the deployment and answer questions about how Redis behaves in this context.

## Your Approach
- Respond quickly and directly to the user's question
- Use tools to gather the specific information needed
- Don't perform exhaustive diagnostics unless asked
- Focus on answering what was asked, not a full health assessment

## Tool Usage - BATCH YOUR CALLS
**CRITICAL: Call multiple tools in a single response whenever possible.**

When you need to gather information, request ALL relevant tools at once:
- ❌ WRONG: Call one tool, wait, call another, wait...
- ✅ CORRECT: Call get_detailed_redis_diagnostics, get_cluster_info, and search_knowledge_base together in one turn

Think about what information you'll need and request it all at once. This is much faster.

## Guidelines
- Call tools as needed to answer the question
- Keep responses concise and actionable
- Cite specific data from tool results
- If the user wants a comprehensive health check, suggest they ask for a "full triage" instead

## Redis Enterprise / Redis Cloud Notes
- For managed Redis (Enterprise or Cloud), INFO output can be misleading
- Use the Admin REST API tools for accurate configuration details
- Don't suggest CONFIG SET for managed deployments
"""


class ChatAgentState(TypedDict):
    """State for the chat agent."""

    messages: List[BaseMessage]
    session_id: str
    user_id: str
    current_tool_calls: List[Dict[str, Any]]
    iteration_count: int
    max_iterations: int
    # Accumulated tool result envelopes for context management
    signals_envelopes: List[Dict[str, Any]]


class ChatAgent:
    """Lightweight LangGraph-based agent for quick Redis Q&A.

    This agent has access to all Redis tools but uses a simpler workflow
    optimized for fast, targeted responses rather than comprehensive triage.
    """

    # Threshold for summarizing tool outputs (chars)
    ENVELOPE_SUMMARY_THRESHOLD = 500

    def __init__(
        self,
        redis_instance: Optional[RedisInstance] = None,
        progress_emitter: Optional[ProgressEmitter] = None,
        progress_callback: Optional[Callable[[str, str], Awaitable[None]]] = None,
        exclude_mcp_categories: Optional[List["ToolCapability"]] = None,
        support_package_path: Optional["Path"] = None,
    ):
        """Initialize the Chat agent.

        Args:
            redis_instance: Optional Redis instance for context
            progress_emitter: Emitter for progress/notification updates
            progress_callback: DEPRECATED - use progress_emitter instead
            exclude_mcp_categories: Optional list of MCP tool capability categories to exclude.
                Use this to filter out specific types of MCP tools. Common categories:
                METRICS, LOGS, TICKETS, REPOS, TRACES, DIAGNOSTICS, KNOWLEDGE, UTILITIES.
            support_package_path: Optional path to an extracted support package.
                When provided, loads tools for analyzing logs, diagnostics, and
                Redis data from the package.
        """
        self.settings = settings
        self.redis_instance = redis_instance
        self.exclude_mcp_categories = exclude_mcp_categories
        self.support_package_path = support_package_path

        # Handle emitter (prefer progress_emitter, fall back to callback wrapper)
        if progress_emitter is not None:
            self._emitter = progress_emitter
        elif progress_callback is not None:
            self._emitter = CallbackEmitter(progress_callback)
        else:
            self._emitter = NullEmitter()

        self.llm = create_llm()
        self.mini_llm = create_mini_llm()

        logger.info(
            f"Chat agent initialized (instance: {redis_instance.name if redis_instance else 'none'})"
        )

    def _build_expand_evidence_tool(
        self,
        original_envelopes: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Build a tool that allows the LLM to retrieve full tool output details.

        When we summarize tool outputs, the LLM only sees condensed versions.
        This tool lets the LLM request the full original output for any tool_key
        if it needs more detail.

        Args:
            original_envelopes: The original (unsummarized) envelopes

        Returns:
            A dict with name, description, func, and parameters for creating a tool
        """
        originals_by_key = {e.get("tool_key"): e for e in original_envelopes}
        available_keys = list(originals_by_key.keys())

        def expand_evidence(tool_key: str) -> Dict[str, Any]:
            """Retrieve the full, unsummarized output from a previous tool call."""
            if tool_key not in originals_by_key:
                return {
                    "status": "error",
                    "error": f"Unknown tool_key: {tool_key}. Available: {available_keys}",
                }
            original = originals_by_key[tool_key]
            return {
                "status": "success",
                "tool_key": tool_key,
                "name": original.get("name"),
                "full_data": original.get("data"),
            }

        return {
            "name": "expand_evidence",
            "description": (
                "Retrieve the full, unsummarized output from a previous tool call. "
                "Use this when the summary doesn't have enough detail. "
                f"Available tool_keys: {available_keys}"
            ),
            "func": expand_evidence,
            "parameters": {
                "type": "object",
                "properties": {
                    "tool_key": {
                        "type": "string",
                        "description": "The tool_key from a summarized evidence item",
                    }
                },
                "required": ["tool_key"],
            },
        }

    def _summarize_envelope_sync(self, env: Dict[str, Any]) -> Dict[str, Any]:
        """Synchronously truncate large envelope data (simple fallback).

        For chat agent, we use simple truncation rather than LLM summarization
        to keep things fast.
        """
        data_str = json.dumps(env.get("data", {}), default=str)
        if len(data_str) <= self.ENVELOPE_SUMMARY_THRESHOLD:
            return env

        # Truncate large data
        return {
            "tool_key": env.get("tool_key"),
            "name": env.get("name"),
            "description": env.get("description"),
            "args": env.get("args"),
            "status": env.get("status"),
            "data": {
                "summary": data_str[: self.ENVELOPE_SUMMARY_THRESHOLD] + "...",
                "note": "Data truncated. Use expand_evidence tool to get full output.",
            },
        }

    def _build_workflow(
        self,
        tool_mgr: ToolManager,
        llm_with_tools: ChatOpenAI,
        adapters: List[Any],
        emitter: Optional[ProgressEmitter] = None,
    ) -> StateGraph:
        """Build the LangGraph workflow for chat interactions.

        Args:
            tool_mgr: ToolManager instance for resolving tool calls
            llm_with_tools: LLM instance with tools bound
            adapters: List of tool adapters for the ToolNode
            emitter: Optional progress emitter for status updates
        """
        tooldefs_by_name = {t.name: t for t in tool_mgr.get_tools()}

        # We'll dynamically add expand_evidence tool when envelopes are available
        # For now, track state needed for dynamic tool injection
        expand_tool_added = {"value": False}
        current_adapters = list(adapters)

        async def agent_node(state: ChatAgentState) -> Dict[str, Any]:
            """Main agent node - invokes LLM with tools."""
            messages = state["messages"]
            iteration_count = state.get("iteration_count", 0)
            envelopes = state.get("signals_envelopes") or []

            # If we have envelopes and haven't added expand_evidence yet, add it
            nonlocal current_adapters, expand_tool_added
            if envelopes and not expand_tool_added["value"]:
                expand_spec = self._build_expand_evidence_tool(envelopes)
                expand_tool = StructuredTool.from_function(
                    func=expand_spec["func"],
                    name=expand_spec["name"],
                    description=expand_spec["description"],
                )
                current_adapters = list(adapters) + [expand_tool]
                expand_tool_added["value"] = True
                # Rebind tools to LLM with expand_evidence
                bound_llm = self.llm.bind_tools(current_adapters)
            else:
                bound_llm = llm_with_tools

            with tracer.start_as_current_span("chat_agent_node"):
                response = await bound_llm.ainvoke(messages)

            new_messages = list(messages) + [response]
            return {
                "messages": new_messages,
                "iteration_count": iteration_count + 1,
                "current_tool_calls": response.tool_calls
                if hasattr(response, "tool_calls")
                else [],
            }

        async def tool_node(state: ChatAgentState) -> Dict[str, Any]:
            """Execute tool calls from the agent."""
            messages = state["messages"]
            envelopes = list(state.get("signals_envelopes") or [])

            # Get pending tool calls from the last AI message
            last_msg = messages[-1] if messages else None
            tool_calls = []
            if isinstance(last_msg, AIMessage) and hasattr(last_msg, "tool_calls"):
                tool_calls = last_msg.tool_calls or []

            # Emit progress updates for each tool call
            if emitter and tool_calls:
                for tc in tool_calls:
                    tool_name = (
                        tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", None)
                    )
                    tool_args = (
                        tc.get("args") if isinstance(tc, dict) else getattr(tc, "args", {})
                    ) or {}
                    if tool_name:
                        # Try to get provider-supplied status message
                        status_msg = tool_mgr.get_status_update(tool_name, tool_args)
                        if status_msg:
                            await emitter.emit(status_msg, "tool_call")
                        else:
                            # Default status message
                            await emitter.emit(f"Executing tool: {tool_name}", "tool_call")

            with tracer.start_as_current_span("chat_tool_node"):
                nonlocal current_adapters
                lg_tool_node = LGToolNode(current_adapters)
                out = await lg_tool_node.ainvoke({"messages": messages})
                out_messages = out.get("messages", [])
                new_tool_messages = [m for m in out_messages if isinstance(m, ToolMessage)]

                # Build envelopes for each tool call result
                for idx, tc in enumerate(tool_calls):
                    tool_name = (
                        tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", None)
                    )
                    tool_args = (
                        tc.get("args") if isinstance(tc, dict) else getattr(tc, "args", {})
                    ) or {}

                    # Skip expand_evidence calls - they don't need envelope tracking
                    if tool_name == "expand_evidence":
                        continue

                    tm = new_tool_messages[idx] if idx < len(new_tool_messages) else None
                    env_dict = build_result_envelope(
                        tool_name or f"tool_{idx + 1}", tool_args, tm, tooldefs_by_name
                    )
                    # Summarize if large
                    env_dict = self._summarize_envelope_sync(env_dict)
                    envelopes.append(env_dict)

            return {
                "messages": list(messages) + new_tool_messages,
                "current_tool_calls": [],
                "signals_envelopes": envelopes,
            }

        def should_continue(state: ChatAgentState) -> str:
            """Decide whether to continue with tools or end."""
            messages = state["messages"]
            iteration_count = state.get("iteration_count", 0)
            max_iterations = state.get("max_iterations", 10)

            if iteration_count >= max_iterations:
                logger.warning(f"Chat agent reached max iterations ({max_iterations})")
                return END

            if messages and isinstance(messages[-1], AIMessage) and messages[-1].tool_calls:
                return "tools"

            if state.get("current_tool_calls"):
                return "tools"

            return END

        workflow = StateGraph(ChatAgentState)
        workflow.add_node("agent", agent_node)
        workflow.add_node("tools", tool_node)
        workflow.set_entry_point("agent")
        workflow.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
        workflow.add_edge("tools", "agent")

        return workflow

    async def process_query(
        self,
        query: str,
        session_id: str,
        user_id: str,
        max_iterations: int = 10,
        context: Optional[Dict[str, Any]] = None,
        progress_emitter: Optional[ProgressEmitter] = None,
        progress_callback: Optional[Callable[[str, str], Awaitable[None]]] = None,
        conversation_history: Optional[List[BaseMessage]] = None,
    ) -> str:
        """Process a query with quick tool access.

        Args:
            query: User's question
            session_id: Session identifier
            user_id: User identifier
            max_iterations: Maximum agent iterations (default 10)
            context: Additional context (e.g., instance_id)
            progress_emitter: Emitter for progress/notification updates
            progress_callback: DEPRECATED - use progress_emitter instead
            conversation_history: Optional previous messages for context

        Returns:
            Agent's response as a string
        """
        logger.info(f"Chat agent processing query for user {user_id}")

        # Use provided emitter, or fall back to instance emitter
        if progress_emitter is not None:
            emitter = progress_emitter
        elif progress_callback is not None:
            emitter = CallbackEmitter(progress_callback)
        else:
            emitter = self._emitter

        # Create ToolManager with Redis instance for full tool access
        async with ToolManager(
            redis_instance=self.redis_instance,
            exclude_mcp_categories=self.exclude_mcp_categories,
            support_package_path=self.support_package_path,
        ) as tool_mgr:
            tools = tool_mgr.get_tools()
            logger.info(f"Chat agent loaded {len(tools)} tools")

            from .helpers import build_adapters_for_tooldefs as _build_adapters

            adapters = await _build_adapters(tool_mgr, tools)
            llm_with_tools = self.llm.bind_tools(adapters)

            workflow = self._build_workflow(tool_mgr, llm_with_tools, adapters, emitter)

            checkpointer = MemorySaver()
            app = workflow.compile(checkpointer=checkpointer)

            # Build initial messages with instance context
            initial_messages: List[BaseMessage] = [SystemMessage(content=CHAT_SYSTEM_PROMPT)]

            # Add instance context to the query if available
            enhanced_query = query
            if self.redis_instance:
                repo_context = ""
                if self.redis_instance.repo_url:
                    repo_context = f"""- Repository URL: {self.redis_instance.repo_url}

If you have GitHub tools available, you can search the repository for code, configuration, or documentation related to this Redis instance.
"""
                instance_context = f"""
INSTANCE CONTEXT: This query is about Redis instance:
- Instance Name: {self.redis_instance.name}
- Environment: {self.redis_instance.environment}
- Usage: {self.redis_instance.usage}
- Instance Type: {self.redis_instance.instance_type}
{repo_context}
Your diagnostic tools are PRE-CONFIGURED for this instance.

User Query: {query}"""
                enhanced_query = instance_context

            if conversation_history:
                initial_messages.extend(conversation_history)

            initial_messages.append(HumanMessage(content=enhanced_query))

            initial_state: ChatAgentState = {
                "messages": initial_messages,
                "session_id": session_id,
                "user_id": user_id,
                "current_tool_calls": [],
                "iteration_count": 0,
                "max_iterations": max_iterations,
                "signals_envelopes": [],  # Track tool outputs for expand_evidence
            }

            thread_config = {"configurable": {"thread_id": session_id}}

            try:
                await emitter.emit("Chat agent processing your question...", "agent_start")

                final_state = await app.ainvoke(initial_state, config=thread_config)

                messages = final_state.get("messages", [])
                if messages:
                    last_message = messages[-1]
                    if isinstance(last_message, AIMessage):
                        return last_message.content
                    return str(last_message.content)

                return "I couldn't process that query. Please try rephrasing."

            except Exception as e:
                logger.exception(f"Chat agent error: {e}")
                return f"Error processing query: {e}"


# Singleton cache keyed by instance name
_chat_agents: Dict[str, ChatAgent] = {}


def get_chat_agent(redis_instance: Optional[RedisInstance] = None) -> ChatAgent:
    """Get or create a chat agent, optionally for a specific Redis instance.

    Args:
        redis_instance: Optional Redis instance for context

    Returns:
        ChatAgent instance
    """
    global _chat_agents
    key = redis_instance.name if redis_instance else "__no_instance__"

    if key not in _chat_agents:
        _chat_agents[key] = ChatAgent(redis_instance=redis_instance)

    return _chat_agents[key]
