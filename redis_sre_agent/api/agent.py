"""Agent API endpoints for SRE operations."""

import logging
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from ..agent import get_sre_agent

# Import will be done dynamically to avoid circular imports

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/agent", tags=["agent"])


# Request/Response models
class AgentQuery(BaseModel):
    """Single query request model."""

    query: str = Field(..., description="User's SRE question or request", min_length=1)
    user_id: str = Field(..., description="User identifier for session management")
    session_id: Optional[str] = Field(
        default=None, description="Optional session ID (generated if not provided)"
    )
    max_iterations: int = Field(default=10, description="Maximum agent iterations", ge=1, le=25)


class AgentChatMessage(BaseModel):
    """Chat message model."""

    role: str = Field(..., description="Message role (user, assistant, tool)")
    content: str = Field(..., description="Message content")
    timestamp: Optional[str] = Field(default=None, description="Message timestamp")


class AgentChatRequest(BaseModel):
    """Multi-turn chat request model."""

    message: str = Field(..., description="User's message", min_length=1)
    session_id: str = Field(..., description="Session ID for conversation continuity")
    user_id: str = Field(..., description="User identifier")
    max_iterations: int = Field(default=10, description="Maximum agent iterations", ge=1, le=25)


class AgentResponse(BaseModel):
    """Agent response model."""

    response: str = Field(..., description="Agent's response")
    session_id: str = Field(..., description="Session ID used for the interaction")
    user_id: str = Field(..., description="User ID")
    iterations_used: int = Field(..., description="Number of agent iterations used")
    tools_called: List[str] = Field(
        default_factory=list, description="List of tools called during processing"
    )


class ConversationHistory(BaseModel):
    """Conversation history model."""

    session_id: str = Field(..., description="Session identifier")
    messages: List[AgentChatMessage] = Field(
        default_factory=list, description="Conversation messages"
    )
    total_messages: int = Field(..., description="Total number of messages in conversation")


# API endpoints
@router.post("/query", response_model=AgentResponse)
async def process_query(request: AgentQuery) -> AgentResponse:
    """
    Process a single SRE query using the LangGraph agent.

    This endpoint handles one-off questions and creates a new session
    or uses the provided session ID for context.
    """
    try:
        # Generate session ID if not provided
        session_id = request.session_id or str(uuid4())

        logger.info(f"Processing agent query for user {request.user_id}, session {session_id}")

        # Get the SRE agent
        agent = get_sre_agent()

        # Process the query
        response = await agent.process_query(
            query=request.query,
            session_id=session_id,
            user_id=request.user_id,
            max_iterations=request.max_iterations,
        )

        # For now, we'll track iterations and tools in a simple way
        # In a more sophisticated implementation, this would be extracted from the agent state

        return AgentResponse(
            response=response,
            session_id=session_id,
            user_id=request.user_id,
            iterations_used=1,  # Placeholder - would need to be tracked in agent
            tools_called=[],  # Placeholder - would need to be tracked in agent
        )

    except Exception as e:
        logger.error(f"Error processing agent query: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing query: {str(e)}",
        )


@router.post("/chat", response_model=AgentResponse)
async def process_chat_message(request: AgentChatRequest) -> AgentResponse:
    """
    Process a chat message in an ongoing conversation.

    This endpoint handles multi-turn conversations using the provided
    session ID to maintain context.
    """
    try:
        logger.info(
            f"Processing chat message for user {request.user_id}, session {request.session_id}"
        )

        # Get the SRE agent
        agent = get_sre_agent()

        # Process the chat message (same as query processing since LangGraph handles state)
        response = await agent.process_query(
            query=request.message,
            session_id=request.session_id,
            user_id=request.user_id,
            max_iterations=request.max_iterations,
        )

        return AgentResponse(
            response=response,
            session_id=request.session_id,
            user_id=request.user_id,
            iterations_used=1,  # Placeholder
            tools_called=[],  # Placeholder
        )

    except Exception as e:
        logger.error(f"Error processing chat message: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing chat message: {str(e)}",
        )


@router.get("/sessions/{session_id}/history", response_model=ConversationHistory)
async def get_conversation_history(
    session_id: str, user_id: Optional[str] = None
) -> ConversationHistory:
    """
    Get conversation history for a session.

    Retrieves the message history for the specified session ID.
    """
    try:
        logger.info(f"Retrieving conversation history for session {session_id}")

        # Get the SRE agent
        agent = get_sre_agent()

        # Get conversation history
        messages_data = await agent.get_conversation_history(session_id)

        # Convert to AgentChatMessage format
        messages = [
            AgentChatMessage(
                role=msg["role"],
                content=msg["content"],
                timestamp=None,  # Would need to be tracked in a real implementation
            )
            for msg in messages_data
        ]

        return ConversationHistory(
            session_id=session_id, messages=messages, total_messages=len(messages)
        )

    except Exception as e:
        logger.error(f"Error retrieving conversation history: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving conversation history: {str(e)}",
        )


@router.delete("/sessions/{session_id}")
async def clear_conversation(session_id: str) -> Dict[str, Any]:
    """
    Clear conversation history for a session.

    Removes all messages and state for the specified session ID.
    """
    try:
        logger.info(f"Clearing conversation for session {session_id}")

        # Get the SRE agent
        agent = get_sre_agent()

        # Clear the conversation
        success = agent.clear_conversation(session_id)

        return {
            "session_id": session_id,
            "cleared": success,
            "message": (
                "Conversation cleared successfully" if success else "Failed to clear conversation"
            ),
        }

    except Exception as e:
        logger.error(f"Error clearing conversation: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error clearing conversation: {str(e)}",
        )


@router.get("/status")
async def get_agent_status() -> Dict[str, Any]:
    """
    Get the current status of the SRE agent system.

    Returns information about agent availability, tool status, and system health.
    """
    try:
        # Check if the agent can be initialized
        agent = get_sre_agent()

        # Check worker availability (required for agent to process tasks)
        workers_available = False
        try:
            from docket.docket import Docket

            from redis_sre_agent.core.config import settings

            async with Docket(url=settings.redis_url, name="sre_docket") as docket:
                workers = await docket.workers()
                workers_available = len(workers) > 0
        except Exception as e:
            logger.warning(f"Worker status check failed: {e}")
            workers_available = False

        # Get system health status (avoid circular import)
        try:
            from . import app

            startup_state = app.get_app_startup_state()
            system_health = {
                "redis_connection": startup_state.get("redis_connection", False),
                "vectorizer": startup_state.get("vectorizer", False),
                "vector_search": startup_state.get("vector_search", False),
                "task_queue": startup_state.get("task_queue", False),
            }
        except (ImportError, AttributeError):
            system_health = {"status": "unknown"}

        # Agent is only available if workers are running
        agent_available = workers_available

        # Get tool information from the agent
        tool_count = len(agent.current_tools) if hasattr(agent, "current_tools") else 0
        tool_names = (
            [tool.name for tool in agent.current_tools] if hasattr(agent, "current_tools") else []
        )

        return {
            "agent_available": agent_available,
            "tools_registered": tool_count,
            "tool_names": tool_names,
            "system_health": system_health,
            "workers_available": workers_available,
            "model": "gpt-4o-mini",
            "status": "operational" if agent_available else "degraded",
        }

    except Exception as e:
        logger.error(f"Error checking agent status: {e}")
        return {"agent_available": False, "error": str(e), "status": "error"}
