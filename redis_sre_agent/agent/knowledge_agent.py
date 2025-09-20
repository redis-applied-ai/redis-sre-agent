"""
Knowledge-only SRE Agent optimized for general questions and knowledge base search.

This agent is designed for queries that don't require specific Redis instance access,
focusing on general SRE guidance, best practices, and knowledge base search.
"""

import logging
from typing import Any, Dict, List, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from redis_sre_agent.core.config import settings
from redis_sre_agent.tools.sre_functions import (
    get_all_document_fragments,
    get_related_document_fragments,
    ingest_sre_document,
    search_knowledge_base,
)

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
    """LangGraph-based Knowledge-only SRE Agent optimized for general questions."""

    def __init__(self, progress_callback=None):
        """Initialize the Knowledge-only SRE agent."""
        self.settings = settings
        self.progress_callback = progress_callback

        # LLM optimized for knowledge tasks
        self.llm = ChatOpenAI(
            model=self.settings.openai_model,
            openai_api_key=self.settings.openai_api_key,
        )

        # Knowledge-focused tools only
        self.knowledge_tools = [
            search_knowledge_base,
            ingest_sre_document,
            get_all_document_fragments,
            get_related_document_fragments,
        ]

        # Bind tools to LLM
        self.llm_with_tools = self.llm.bind_tools(self.knowledge_tools)

        # Build the workflow
        self.workflow = self._build_workflow()

        logger.info("Knowledge-only SRE agent initialized")

    def _build_workflow(self) -> StateGraph:
        """Build the LangGraph workflow for knowledge-only queries."""

        async def agent_node(state: KnowledgeAgentState) -> KnowledgeAgentState:
            """Main agent node for knowledge queries."""
            messages = state["messages"]
            iteration_count = state.get("iteration_count", 0)

            # Add system message if this is the first interaction
            if len(messages) == 1 and isinstance(messages[0], HumanMessage):
                system_message = AIMessage(content=KNOWLEDGE_SYSTEM_PROMPT)
                messages = [system_message] + messages

            # Generate response with knowledge tools
            try:
                response = await self.llm_with_tools.ainvoke(messages)

                # Update iteration count
                state["iteration_count"] = iteration_count + 1

                # Add response to messages
                state["messages"] = messages + [response]

                # Store tool calls for potential execution
                if hasattr(response, 'tool_calls') and response.tool_calls:
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
                        "agent_processing"
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

        def should_continue(state: KnowledgeAgentState) -> str:
            """Determine if we should continue with tool calls or end."""
            messages = state["messages"]
            last_message = messages[-1] if messages else None

            # Check iteration limit
            if state.get("iteration_count", 0) >= state.get("max_iterations", 5):
                return END

            # If the last message has tool calls, execute them
            if (hasattr(last_message, 'tool_calls') and
                last_message.tool_calls and
                len(last_message.tool_calls) > 0):
                return "tools"

            return END

        # Create the workflow
        workflow = StateGraph(KnowledgeAgentState)

        # Add nodes
        workflow.add_node("agent", agent_node)
        workflow.add_node("tools", ToolNode(self.knowledge_tools))

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
    ) -> str:
        """
        Process a knowledge-only query.
        
        Args:
            query: User's question or request
            user_id: User identifier
            session_id: Session identifier
            max_iterations: Maximum number of agent iterations
            progress_callback: Optional callback for progress updates
            
        Returns:
            Agent's response as a string
        """
        logger.info(f"Processing knowledge query for user {user_id}")

        # Set progress callback for this query
        if progress_callback:
            self.progress_callback = progress_callback

        # Create initial state
        initial_state: KnowledgeAgentState = {
            "messages": [HumanMessage(content=query)],
            "session_id": session_id,
            "user_id": user_id,
            "current_tool_calls": [],
            "iteration_count": 0,
            "max_iterations": max_iterations,
        }

        # Create isolated memory for this query
        checkpointer = MemorySaver()
        app = self.workflow.compile(checkpointer=checkpointer)

        # Configure thread for session persistence
        thread_config = {"configurable": {"thread_id": session_id}}

        try:
            # Progress callback for start
            if self.progress_callback:
                await self.progress_callback(
                    "Knowledge agent starting to process your query...",
                    "agent_start"
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
                    "Knowledge agent has completed processing your query.",
                    "agent_complete"
                )

            logger.info(f"Knowledge query completed for user {user_id}")
            return response

        except Exception as e:
            logger.error(f"Knowledge agent processing failed: {e}")
            error_response = f"I encountered an error while processing your knowledge query: {str(e)}. Please try asking a more specific question about SRE practices, troubleshooting methodologies, or system reliability concepts."

            if self.progress_callback:
                await self.progress_callback(
                    f"Knowledge agent encountered an error: {str(e)}",
                    "agent_error"
                )

            return error_response


# Singleton instance for reuse
_knowledge_agent = None


def get_knowledge_agent() -> KnowledgeOnlyAgent:
    """Get or create the knowledge-only agent singleton."""
    global _knowledge_agent
    if _knowledge_agent is None:
        _knowledge_agent = KnowledgeOnlyAgent()
    return _knowledge_agent
