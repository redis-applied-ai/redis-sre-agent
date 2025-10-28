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
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from redis_sre_agent.core.config import settings
from redis_sre_agent.tools.manager import ToolManager

logger = logging.getLogger(__name__)


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


class KnowledgeOnlyAgent:
    """LangGraph-based Knowledge-only SRE Agent optimized for general questions.

    This agent uses ToolManager to load only knowledge-related tools (no instance-specific tools).
    It's designed for general Q&A when no Redis instance is specified.
    """

    def __init__(self, progress_callback: Optional[Callable[[str, str], Awaitable[None]]] = None):
        """Initialize the Knowledge-only SRE agent."""
        self.settings = settings
        self.progress_callback = progress_callback

        # LLM optimized for knowledge tasks
        self.llm = ChatOpenAI(
            model=self.settings.openai_model,
            openai_api_key=self.settings.openai_api_key,
        )

        # Tools will be loaded per-query using ToolManager (without redis_instance)
        # This loads only the always-on providers (knowledge, utilities)
        self.llm_with_tools = self.llm  # Will be rebound with tools per query

        logger.info("Knowledge-only agent initialized (tools loaded per-query)")

    def _build_workflow(self, tool_mgr: ToolManager) -> StateGraph:
        """Build the LangGraph workflow for knowledge-only queries.

        Args:
            tool_mgr: ToolManager instance with knowledge tools loaded
        """

        # Bind tools to LLM for this workflow
        tools = tool_mgr.get_tools()
        tool_schemas = [tool.to_openai_schema() for tool in tools]
        llm_with_tools = self.llm.bind_tools(tool_schemas)

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
                            for tc in getattr(m, "tool_calls", []) or []:
                                if isinstance(tc, dict):
                                    tid = tc.get("id") or tc.get("tool_call_id")
                                    if tid:
                                        seen_tool_ids.add(tid)
                        except Exception:
                            pass
                        clean.append(m)
                    elif isinstance(m, _TM) or getattr(m, "type", "") == "tool":
                        tid = getattr(m, "tool_call_id", None)
                        if tid and tid in seen_tool_ids:
                            clean.append(m)
                        else:
                            continue
                    else:
                        clean.append(m)
                while clean and (
                    isinstance(clean[0], _TM) or getattr(clean[0], "type", "") == "tool"
                ):
                    clean = clean[1:]
                return clean

            messages = _sanitize_messages_for_llm(messages)

            try:
                response = await llm_with_tools.ainvoke(messages)
                # Coerce non-Message responses (e.g., simple mocks) into AIMessage
                if not isinstance(response, BaseMessage):
                    content = getattr(response, "content", None)
                    tool_calls = getattr(response, "tool_calls", None)
                    response = AIMessage(
                        content=str(content) if content is not None else "", tool_calls=tool_calls
                    )

                # Update iteration count
                state["iteration_count"] = iteration_count + 1

                # Add response to messages
                state["messages"] = messages + [response]

                # Store tool calls for potential execution
                if hasattr(response, "tool_calls") and response.tool_calls:
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

                # Progress callback
                if self.progress_callback:
                    await self.progress_callback(
                        f"Knowledge agent processing query (iteration {iteration_count + 1})",
                        "agent_processing",
                    )

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
            if not (hasattr(last_message, "tool_calls") and last_message.tool_calls):
                logger.warning("safe_tool_node called without tool_calls in last message")
                return state

            try:
                # Execute tools using ToolManager
                tool_results = await tool_mgr.execute_tool_calls(last_message.tool_calls)

                # Convert results to ToolMessage format expected by LangGraph
                from langchain_core.messages import ToolMessage

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
                                if fragments and self.progress_callback:
                                    await self.progress_callback(
                                        f"Found {len(fragments)} knowledge fragments",  # message
                                        "knowledge_sources",  # update_type
                                        {"fragments": fragments},  # metadata
                                    )
                    except Exception:
                        # Don't let telemetry failures break tool handling
                        pass

                    tool_messages.append(
                        ToolMessage(
                            content=str(result),
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

            # If the last message has tool calls, execute them
            if (
                hasattr(last_message, "tool_calls")
                and last_message.tool_calls
                and len(last_message.tool_calls) > 0
            ):
                return "tools"

            return END

        # Create the workflow
        workflow = StateGraph(KnowledgeAgentState)

        # Add nodes
        workflow.add_node("agent", agent_node)
        workflow.add_node("tools", safe_tool_node)

        # Set entry point
        workflow.set_entry_point("agent")

        # Add conditional edges
        workflow.add_conditional_edges("agent", should_continue)
        workflow.add_edge("tools", "agent")

        return workflow

    async def process_query(
        self,
        query: str,
        user_id: str = "knowledge-user",
        session_id: str = "knowledge-session",
        max_iterations: int = 5,
        progress_callback=None,
        conversation_history: Optional[List[BaseMessage]] = None,
    ) -> str:
        """
        Process a knowledge-only query.

        Args:
            query: User's question or request
            user_id: User identifier
            session_id: Session identifier
            max_iterations: Maximum number of agent iterations
            progress_callback: Optional callback for progress updates
            conversation_history: Optional list of previous messages for context

        Returns:
            Agent's response as a string
        """
        logger.info(f"Processing knowledge query for user {user_id}")

        # Set progress callback for this query
        if progress_callback:
            self.progress_callback = progress_callback

        # Create ToolManager with only knowledge tools (no redis_instance)
        tool_mgr = ToolManager(redis_instance=None)
        logger.info(f"Loaded {len(tool_mgr.get_tools())} knowledge tools")

        # Build workflow with tools
        workflow = self._build_workflow(tool_mgr)

        # Create initial state with conversation history
        initial_messages = []
        if conversation_history:
            initial_messages = list(conversation_history)
            logger.info(f"Including {len(conversation_history)} messages from conversation history")
        initial_messages.append(HumanMessage(content=query))

        initial_state: KnowledgeAgentState = {
            "messages": initial_messages,
            "session_id": session_id,
            "user_id": user_id,
            "current_tool_calls": [],
            "iteration_count": 0,
            "max_iterations": max_iterations,
        }

        # Create MemorySaver for this query
        # Conversation history is managed by ThreadManager and passed via messages
        checkpointer = MemorySaver()
        app = workflow.compile(checkpointer=checkpointer)

        # Configure thread for session persistence
        thread_config = {"configurable": {"thread_id": session_id}}

        try:
            # Progress callback for start
            if self.progress_callback:
                await self.progress_callback(
                    "Knowledge agent starting to process your query...", "agent_start"
                )

            # Run the workflow
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

            # Progress callback for completion
            if self.progress_callback:
                await self.progress_callback(
                    "Knowledge agent has completed processing your query.", "agent_complete"
                )

            logger.info(f"Knowledge query completed for user {user_id}")
            return response

        except Exception as e:
            logger.error(f"Knowledge agent processing failed: {e}")
            error_response = f"I encountered an error while processing your knowledge query: {str(e)}. Please try asking a more specific question about SRE practices, troubleshooting methodologies, or system reliability concepts."

            if self.progress_callback:
                await self.progress_callback(
                    f"Knowledge agent encountered an error: {str(e)}", "agent_error"
                )

            return error_response

    async def process_query_with_fact_check(
        self,
        query: str,
        session_id: str,
        user_id: str,
        max_iterations: int = 5,
        context: Optional[Dict[str, Any]] = None,
        progress_callback=None,
        conversation_history: Optional[List[BaseMessage]] = None,
    ) -> str:
        """Process a query with the same signature as the main agent.

        This method exists for compatibility with the task system that expects
        both agents to have the same interface. For the knowledge-only agent,
        we don't need fact-checking since it only provides general guidance.

        Args:
            query: User's question or request
            session_id: Session identifier
            user_id: User identifier
            max_iterations: Maximum number of agent iterations
            context: Additional context (ignored for knowledge-only agent)
            progress_callback: Optional callback for progress updates
            conversation_history: Optional list of previous messages for context

        Returns:
            Agent's response as a string
        """
        # Simply delegate to process_query (no fact-checking needed for knowledge queries)
        return await self.process_query(
            query=query,
            user_id=user_id,
            session_id=session_id,
            max_iterations=max_iterations,
            progress_callback=progress_callback,
            conversation_history=conversation_history,
        )


# Singleton instance for reuse
_knowledge_agent = None


def get_knowledge_agent() -> KnowledgeOnlyAgent:
    """Get or create the knowledge-only agent singleton."""
    global _knowledge_agent
    if _knowledge_agent is None:
        _knowledge_agent = KnowledgeOnlyAgent()
    return _knowledge_agent
