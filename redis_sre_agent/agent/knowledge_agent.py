"""
Knowledge-only SRE Agent optimized for general questions and knowledge base search.

This agent is designed for queries that don't require specific Redis instance access,
focusing on general SRE guidance, best practices, and knowledge base search.

This agent uses the same ToolManager system as the main agent, but only loads
knowledge-related tools (no instance-specific tools like Redis CLI or Prometheus).
"""

import logging
from typing import Any, Awaitable, Callable, Dict, List, Optional, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from opentelemetry import trace

from redis_sre_agent.core.config import settings
from redis_sre_agent.core.llm_helpers import create_llm
from redis_sre_agent.core.progress import (
    CallbackEmitter,
    NullEmitter,
    ProgressEmitter,
)
from redis_sre_agent.tools.manager import ToolManager

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


# Knowledge-focused system prompt
KNOWLEDGE_SYSTEM_PROMPT = """You are a specialized SRE (Site Reliability Engineering) Knowledge Assistant. Your primary role is to provide expert guidance on SRE practices, troubleshooting methodologies, and general system reliability principles.

## Your Capabilities:
- Search and retrieve information from the SRE knowledge base
- Provide general SRE best practices and guidance
- Help with troubleshooting methodologies and approaches
- Explain SRE concepts and principles
- Suggest documentation and learning resources

## Your Approach:
1. **Knowledge-First**: Always search the knowledge base for relevant information before providing answers
2. **Educational**: Explain concepts clearly and provide context for your recommendations
3. **Practical**: Focus on actionable advice and real-world applications
4. **Comprehensive**: Use multiple knowledge base searches if needed to provide complete answers

## Important Guidelines:
- You do NOT have access to specific Redis instances or live system data
- For instance-specific troubleshooting, recommend using the full SRE agent with instance context
- Focus on general principles, methodologies, and documented best practices
- Always cite knowledge base sources when available
- If you don't find relevant information in the knowledge base, provide general SRE guidance based on industry best practices

## Response Style:
- Be concise but thorough
- Use clear headings and bullet points for complex topics
- Provide step-by-step guidance when appropriate
- Include relevant examples and use cases
- Suggest follow-up questions or related topics when helpful

## Command Guidance:
- When suggesting actions involving commands, use real user-facing CLI commands or API requests.
- Do NOT reference internal agent tool names (e.g., "run get_cluster_info"). Instead, show an equivalent `redis-cli` command or a `curl` example for a REST API where appropriate.

Remember: You are the knowledge specialist - make the most of the available documentation and provide educational, actionable guidance."""


class KnowledgeAgentState(TypedDict):
    """State for the knowledge-only agent."""

    messages: List[BaseMessage]
    session_id: str
    user_id: str
    current_tool_calls: List[Dict[str, Any]]
    iteration_count: int
    max_iterations: int
    tool_calls_executed: int


class KnowledgeOnlyAgent:
    """LangGraph-based Knowledge-only SRE Agent optimized for general questions.

    This agent uses ToolManager to load only knowledge-related tools (no instance-specific tools).
    It's designed for general Q&A when no Redis instance is specified.
    """

    def __init__(
        self,
        progress_emitter: Optional[ProgressEmitter] = None,
        progress_callback: Optional[Callable[[str, str], Awaitable[None]]] = None,
    ):
        """Initialize the Knowledge-only SRE agent.

        Args:
            progress_emitter: Emitter for progress/notification updates
            progress_callback: DEPRECATED - use progress_emitter instead
        """
        self.settings = settings

        # Handle emitter (prefer progress_emitter, fall back to callback wrapper)
        if progress_emitter is not None:
            self._emitter = progress_emitter
        elif progress_callback is not None:
            self._emitter = CallbackEmitter(progress_callback)
        else:
            self._emitter = NullEmitter()

        # LLM optimized for knowledge tasks
        self.llm = create_llm()

        # Tools will be loaded per-query using ToolManager (without redis_instance)
        # This loads only the always-on providers (knowledge, utilities)
        self.llm_with_tools = self.llm  # Will be rebound with tools per query

        logger.info("Knowledge-only agent initialized (tools loaded per-query)")

    def _build_workflow(
        self, tool_mgr: ToolManager, llm_with_tools: ChatOpenAI, emitter: ProgressEmitter
    ) -> StateGraph:
        """Build the LangGraph workflow for knowledge-only queries.

        Args:
            tool_mgr: ToolManager instance with knowledge tools loaded
            llm_with_tools: LLM with tools bound
            emitter: Emitter for progress notifications
        """

        async def agent_node(state: KnowledgeAgentState) -> KnowledgeAgentState:
            """Main agent node for knowledge queries."""
            messages = state["messages"]
            iteration_count = state.get("iteration_count", 0)

            # Add system message if this is the first interaction
            if len(messages) == 1 and isinstance(messages[0], HumanMessage):
                system_message = SystemMessage(content=KNOWLEDGE_SYSTEM_PROMPT)
                messages = [system_message] + messages

            # Generate response with knowledge tools
            # Sanitize message order to avoid sending orphan tool messages to OpenAI
            def _sanitize_messages_for_llm(msgs: list[BaseMessage]) -> list[BaseMessage]:
                if not msgs:
                    return msgs
                from langchain_core.messages import ToolMessage as _TM  # noqa: N814

                seen_tool_ids = set()
                clean: list[BaseMessage] = []
                for m in msgs:
                    if isinstance(m, AIMessage):
                        try:
                            for tc in m.tool_calls or []:
                                if isinstance(tc, dict):
                                    tid = tc.get("id") or tc.get("tool_call_id")
                                    if tid:
                                        seen_tool_ids.add(tid)
                        except Exception:
                            pass
                        clean.append(m)
                    elif isinstance(m, _TM) or m.type == "tool":
                        tid = m.tool_call_id
                        if tid and tid in seen_tool_ids:
                            clean.append(m)
                        else:
                            continue
                    else:
                        clean.append(m)
                while clean and (isinstance(clean[0], _TM) or clean[0].type == "tool"):
                    clean = clean[1:]
                return clean

            # OTel: capture sanitize phase
            _pre_count = len(messages)
            with tracer.start_as_current_span(
                "knowledge.agent.sanitize", attributes={"messages.pre": _pre_count}
            ):
                messages = _sanitize_messages_for_llm(messages)

            try:
                import time as _time

                from redis_sre_agent.observability.llm_metrics import record_llm_call_metrics

                _t0 = _time.perf_counter()
                with tracer.start_as_current_span(
                    "llm.call", attributes={"llm.component": "knowledge"}
                ):
                    response = await llm_with_tools.ainvoke(messages)
                record_llm_call_metrics(
                    component="knowledge", llm=llm_with_tools, response=response, start_time=_t0
                )
                # Coerce non-Message responses (e.g., simple mocks) into AIMessage
                if not isinstance(response, BaseMessage):
                    content = response.content
                    tool_calls = response.tool_calls
                    response = AIMessage(
                        content=str(content) if content is not None else "", tool_calls=tool_calls
                    )

                # Update iteration count
                state["iteration_count"] = iteration_count + 1

                # Add response to messages
                state["messages"] = messages + [response]

                # Store tool calls for potential execution
                if response.tool_calls:
                    state["current_tool_calls"] = [
                        {
                            "id": tc.get("id", ""),
                            "name": tc.get("name", ""),
                            "args": tc.get("args", {}),
                        }
                        for tc in response.tool_calls
                    ]
                else:
                    state["current_tool_calls"] = []

                # No per-iteration progress message; providers will emit status updates
                return state

            except Exception as e:
                logger.error(f"Knowledge agent error: {e}")
                error_message = AIMessage(
                    content=f"I encountered an error while processing your request: {str(e)}. Please try rephrasing your question or ask for general SRE guidance."
                )
                state["messages"] = messages + [error_message]
                state["current_tool_calls"] = []
                return state

        async def safe_tool_node(state: KnowledgeAgentState) -> KnowledgeAgentState:
            """Execute tools with error handling using ToolManager."""
            messages = state["messages"]
            last_message = messages[-1] if messages else None

            # Verify we have tool calls to execute
            if not (last_message and last_message.tool_calls):
                logger.warning("safe_tool_node called without tool_calls in last message")
                return state

            try:
                # Emit provider-supplied status updates before executing tools
                try:
                    pending = last_message.tool_calls or []
                    if self.progress_callback:
                        for tc in pending:
                            tool_name = tc.get("name")
                            tool_args = tc.get("args") or {}
                            if tool_name:
                                status_msg = tool_mgr.get_status_update(tool_name, tool_args)
                                if status_msg:
                                    await self.progress_callback(status_msg, "agent_reflection")
                except Exception:
                    pass

                # Execute tools using ToolManager (wrapped in OTel span)
                _tool_names = [tc.get("name", "") for tc in (last_message.tool_calls or [])]
                with tracer.start_as_current_span(
                    "knowledge.tools.execute",
                    attributes={
                        "tool_calls.count": len(_tool_names),
                        "tool_calls.names": ",".join(_tool_names),
                    },
                ):
                    tool_results = await tool_mgr.execute_tool_calls(last_message.tool_calls)

                # Convert results to ToolMessage format expected by LangGraph
                from langchain_core.messages import ToolMessage

                # Track budget usage for tool calls
                prev_exec = state.get("tool_calls_executed", 0)
                state["tool_calls_executed"] = prev_exec + len(tool_results or [])

                tool_messages = []
                for tool_call, result in zip(last_message.tool_calls, tool_results):
                    # Record knowledge sources when a knowledge search tool returns results
                    try:
                        tool_name = str(tool_call.get("name", ""))
                        if tool_name.startswith("knowledge_") and "search" in tool_name:
                            if isinstance(result, dict):
                                res_list = result.get("results") or []
                                fragments = []
                                for doc in res_list:
                                    if isinstance(doc, dict):
                                        fragments.append(
                                            {
                                                "id": doc.get("id"),
                                                "document_hash": doc.get("document_hash"),
                                                "chunk_index": doc.get("chunk_index"),
                                                "title": doc.get("title"),
                                                "source": doc.get("source"),
                                            }
                                        )
                                if fragments:
                                    await emitter.emit(
                                        f"Found {len(fragments)} knowledge fragments",
                                        "knowledge_sources",
                                        {"fragments": fragments},
                                    )
                    except Exception:
                        # Don't let telemetry failures break tool handling
                        pass

                    # Prefer JSON content to help the LLM consume results
                    try:
                        import json as _json

                        _content = _json.dumps(result, default=str)
                    except Exception:
                        _content = str(result)

                    tool_messages.append(
                        ToolMessage(
                            content=_content,
                            tool_call_id=tool_call["id"],
                        )
                    )

                state["messages"] = messages + tool_messages
                return state

            except Exception as e:
                logger.error(f"Tool execution failed: {e}")
                # Add an AI message explaining the error
                error_message = AIMessage(
                    content=f"I encountered an error while searching the knowledge base: {str(e)}. "
                    "This may be because Redis is not available. Please ensure Redis is running, "
                    "or ask me a general question that doesn't require knowledge base access."
                )
                state["messages"] = messages + [error_message]
                state["current_tool_calls"] = []
                return state

        def should_continue(state: KnowledgeAgentState) -> str:
            """Determine if we should continue with tool calls or end."""
            messages = state["messages"]
            last_message = messages[-1] if messages else None

            # Check iteration limit
            if state.get("iteration_count", 0) >= state.get("max_iterations", 5):
                return END

            # Enforce a tool call budget to avoid runaway loops
            try:
                from redis_sre_agent.core.config import settings as _settings

                _budget = int(_settings.max_tool_calls_per_stage)
            except Exception:
                _budget = 3
            prev_exec = int(state.get("tool_calls_executed", 0) or 0)
            pending = int(len(state.get("current_tool_calls", []) or []))
            if prev_exec >= _budget:
                return END
            # If executing the pending calls would exceed budget, stop before entering tools
            if pending and (prev_exec + pending) > _budget:
                return END

            # If the last message has tool calls, execute them
            if last_message.tool_calls and len(last_message.tool_calls) > 0:
                return "tools"

            return END

        # Create the workflow
        workflow = StateGraph(KnowledgeAgentState)

        # Lightweight OTel wrapper to trace per-node execution
        def _trace_node(node_name: str):
            def _decorator(fn):
                async def _wrapped(state: KnowledgeAgentState) -> KnowledgeAgentState:
                    with tracer.start_as_current_span(
                        "langgraph.node",
                        attributes={
                            "langgraph.graph": "knowledge",
                            "langgraph.node": node_name,
                        },
                    ):
                        return await fn(state)

                return _wrapped

            return _decorator

        # Add nodes (wrapped with per-node tracing spans)
        workflow.add_node("agent", _trace_node("agent")(agent_node))
        workflow.add_node("tools", _trace_node("tools")(safe_tool_node))

        # Set entry point
        workflow.set_entry_point("agent")

        # Add conditional edges
        workflow.add_conditional_edges("agent", should_continue)
        workflow.add_edge("tools", "agent")

        return workflow

    async def process_query(
        self,
        query: str,
        session_id: str,
        user_id: str,
        max_iterations: int = 5,
        context: Optional[Dict[str, Any]] = None,
        progress_emitter: Optional[ProgressEmitter] = None,
        progress_callback: Optional[Callable[[str, str], Awaitable[None]]] = None,
        conversation_history: Optional[List[BaseMessage]] = None,
    ) -> str:
        """
        Process a knowledge-only query.

        Args:
            query: User's question or request
            session_id: Session identifier
            user_id: User identifier
            max_iterations: Maximum number of agent iterations
            context: Additional context (currently ignored for knowledge-only agent)
            progress_emitter: Emitter for progress/notification updates
            progress_callback: DEPRECATED - use progress_emitter instead
            conversation_history: Optional list of previous messages for context

        Returns:
            Agent's response as a string
        """
        logger.info(f"Processing knowledge query for user {user_id}")

        # Use provided emitter, or fall back to instance emitter
        if progress_emitter is not None:
            emitter = progress_emitter
        elif progress_callback is not None:
            emitter = CallbackEmitter(progress_callback)
        else:
            emitter = self._emitter

        # Create ToolManager with Redis instance-independent tools
        async with ToolManager(redis_instance=None) as tool_mgr:
            tools = tool_mgr.get_tools()
            logger.info(f"Loaded {len(tools)} tools usable without Redis instance details")

            # Build StructuredTool adapters and bind them to the LLM
            from .helpers import build_adapters_for_tooldefs as _build_adapters

            adapters = await _build_adapters(tool_mgr, tools)
            llm_with_tools = self.llm.bind_tools(adapters)

            # Build workflow with tools and bound LLM
            workflow = self._build_workflow(tool_mgr, llm_with_tools, emitter)

            # Create initial state with conversation history
            initial_messages = []
            if conversation_history:
                initial_messages = list(conversation_history)
                logger.info(
                    f"Including {len(conversation_history)} messages from conversation history"
                )
            initial_messages.append(HumanMessage(content=query))

            initial_state: KnowledgeAgentState = {
                "messages": initial_messages,
                "session_id": session_id,
                "user_id": user_id,
                "current_tool_calls": [],
                "iteration_count": 0,
                "max_iterations": max_iterations,
                "tool_calls_executed": 0,
            }

            # Create MemorySaver for this query
            # Conversation history is managed by ThreadManager and passed via messages
            checkpointer = MemorySaver()
            app = workflow.compile(checkpointer=checkpointer)

            # Configure thread for session persistence and recursion safety
            thread_config = {
                "configurable": {"thread_id": session_id},
                "recursion_limit": self.settings.recursion_limit,
            }

            try:
                # Emit start notification
                await emitter.emit(
                    "Knowledge agent starting to process your query...", "agent_start"
                )

                # Run the workflow (with recursion limit to match settings)
                final_state = await app.ainvoke(initial_state, config=thread_config)

                # Extract the final response
                messages = final_state.get("messages", [])

                if messages:
                    last_message = messages[-1]
                    if isinstance(last_message, AIMessage):
                        response = last_message.content
                    else:
                        response = str(last_message.content)
                else:
                    response = "I apologize, but I wasn't able to process your query. Please try asking a more specific question about SRE practices or troubleshooting."

                # Emit completion notification
                await emitter.emit(
                    "Knowledge agent has completed processing your query.", "agent_complete"
                )

                logger.info(f"Knowledge query completed for user {user_id}")
                return response

            except Exception as e:
                logger.error(f"Knowledge agent processing failed: {e}")
                error_response = f"I encountered an error while processing your knowledge query: {str(e)}. Please try asking a more specific question about SRE practices, troubleshooting methodologies, or system reliability concepts."

                await emitter.emit(f"Knowledge agent encountered an error: {str(e)}", "agent_error")

                return error_response


# Singleton instance for reuse
_knowledge_agent = None


def get_knowledge_agent() -> KnowledgeOnlyAgent:
    """Get or create the knowledge-only agent singleton."""
    global _knowledge_agent
    if _knowledge_agent is None:
        _knowledge_agent = KnowledgeOnlyAgent()
    return _knowledge_agent
