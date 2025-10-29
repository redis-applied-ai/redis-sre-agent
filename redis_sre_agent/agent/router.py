"""
Agent routing logic for intelligent selection between Redis-focused and knowledge-only agents.

This module uses a fast LLM (nano model) to categorize queries and determine
which agent should handle them based on context and query content.
"""

import logging
from enum import Enum
from typing import Any, Dict, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from redis_sre_agent.core.config import settings

logger = logging.getLogger(__name__)


class AgentType(Enum):
    """Types of available agents."""

    REDIS_FOCUSED = "redis_focused"
    KNOWLEDGE_ONLY = "knowledge_only"


async def route_to_appropriate_agent(
    query: str,
    context: Optional[Dict[str, Any]] = None,
    user_preferences: Optional[Dict[str, Any]] = None,
) -> AgentType:
    """
    Route a query to the appropriate agent using a fast LLM categorization.

    Args:
        query: The user's query text
        context: Additional context including instance_id, priority, etc.
        user_preferences: User preferences for agent selection

    Returns:
        AgentType indicating which agent should handle the query
    """
    logger.info(f"Routing query: {query[:100]}...")

    # 1. Check for explicit Redis instance context
    if context and context.get("instance_id"):
        logger.info("Query has explicit Redis instance context - routing to Redis-focused agent")
        return AgentType.REDIS_FOCUSED

    # 2. Check user preferences
    if user_preferences and user_preferences.get("preferred_agent"):
        preferred = user_preferences["preferred_agent"]
        if preferred in [agent.value for agent in AgentType]:
            logger.info(f"Using user preference: {preferred}")
            return AgentType(preferred)

    # 3. Use fast LLM to categorize the query
    try:
        llm = ChatOpenAI(
            model=settings.openai_model_nano,
            api_key=settings.openai_api_key,
            timeout=10.0,  # Fast timeout for categorization
            temperature=0,  # Deterministic categorization
        )

        system_prompt = """You are a query categorization system for a Redis SRE agent.

Your task is to categorize user queries into one of two categories:

1. REDIS_FOCUSED: Queries that require access to a specific Redis instance for diagnostics, monitoring, or troubleshooting.
   Examples:
   - "Check the memory usage of my Redis instance"
   - "Why is Redis slow?"
   - "Show me the slowlog"
   - "What's the current connection count?"
   - "Diagnose performance issues"

2. KNOWLEDGE_ONLY: Queries seeking general knowledge, best practices, or guidance that don't require instance access.
   Examples:
   - "What are Redis best practices?"
   - "How does Redis replication work?"
   - "Explain Redis persistence options"
   - "What is an SRE runbook?"
   - "How should I configure Redis for high availability?"

Respond with ONLY one word: either "REDIS_FOCUSED" or "KNOWLEDGE_ONLY"."""

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"Categorize this query: {query}"),
        ]

        response = await llm.ainvoke(messages)
        category = response.content.strip().upper()

        if "REDIS_FOCUSED" in category:
            logger.info("LLM categorized query as REDIS_FOCUSED")
            return AgentType.REDIS_FOCUSED
        elif "KNOWLEDGE_ONLY" in category:
            logger.info("LLM categorized query as KNOWLEDGE_ONLY")
            return AgentType.KNOWLEDGE_ONLY
        else:
            logger.warning(
                f"LLM returned unexpected category: {category}, defaulting to KNOWLEDGE_ONLY"
            )
            return AgentType.KNOWLEDGE_ONLY

    except Exception as e:
        logger.error(f"Error during LLM routing: {e}, defaulting to KNOWLEDGE_ONLY")
        return AgentType.KNOWLEDGE_ONLY
