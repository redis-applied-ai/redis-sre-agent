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

    REDIS_TRIAGE = "redis_triage"  # Full triage/health check agent
    REDIS_CHAT = "redis_chat"  # Lightweight chat agent for quick Q&A
    KNOWLEDGE_ONLY = "knowledge_only"  # No instance, general knowledge

    # Keep old value for backward compatibility
    REDIS_FOCUSED = "redis_triage"  # Alias for REDIS_TRIAGE


async def route_to_appropriate_agent(
    query: str,
    context: Optional[Dict[str, Any]] = None,
    user_preferences: Optional[Dict[str, Any]] = None,
) -> AgentType:
    """
    Route a query to the appropriate agent using a fast LLM categorization.

    Routing logic:
    - No Redis instance: KNOWLEDGE_ONLY (general knowledge questions)
    - Has Redis instance + asks for full/comprehensive health check or triage: REDIS_TRIAGE
    - Has Redis instance + quick question: REDIS_CHAT (fast diagnostic loop)

    Args:
        query: The user's query text
        context: Additional context including instance_id, priority, etc.
        user_preferences: User preferences for agent selection

    Returns:
        AgentType indicating which agent should handle the query
    """
    logger.info(f"Routing query: {query[:100]}...")

    has_instance = context and context.get("instance_id")

    # 1. No instance context - route to knowledge agent
    if not has_instance:
        # Use LLM to decide if query needs instance access or is knowledge-only
        try:
            llm = ChatOpenAI(
                model=settings.openai_model_nano,
                api_key=settings.openai_api_key,
                timeout=10.0,
                temperature=0,
            )

            system_prompt = """You are a query categorization system for a Redis SRE agent.

Categorize if this query requires access to a live Redis instance or is just seeking general knowledge.

1. NEEDS_INSTANCE: Queries that require access to a specific Redis instance for diagnostics, monitoring, or troubleshooting.
   Examples: "Check my Redis memory", "Why is Redis slow?", "Show me the slowlog"

2. KNOWLEDGE_ONLY: Queries seeking general knowledge, best practices, or guidance.
   Examples: "What are Redis best practices?", "How does Redis replication work?"

Respond with ONLY one word: either "NEEDS_INSTANCE" or "KNOWLEDGE_ONLY"."""

            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=f"Categorize this query: {query}"),
            ]

            response = await llm.ainvoke(messages)
            category = response.content.strip().upper()

            if "NEEDS_INSTANCE" in category:
                logger.info("Query needs instance but none provided - routing to KNOWLEDGE_ONLY")
            else:
                logger.info("LLM categorized query as KNOWLEDGE_ONLY")

            return AgentType.KNOWLEDGE_ONLY

        except Exception as e:
            logger.error(f"Error during LLM routing: {e}, defaulting to KNOWLEDGE_ONLY")
            return AgentType.KNOWLEDGE_ONLY

    # 2. Has instance - decide between triage (full) and chat (quick)
    # Check user preferences first
    if user_preferences and user_preferences.get("preferred_agent"):
        preferred = user_preferences["preferred_agent"]
        if preferred in [agent.value for agent in AgentType]:
            logger.info(f"Using user preference: {preferred}")
            return AgentType(preferred)

    # 3. Use LLM to categorize triage vs chat
    try:
        llm = ChatOpenAI(
            model=settings.openai_model_nano,
            api_key=settings.openai_api_key,
            timeout=10.0,
            temperature=0,
        )

        system_prompt = """You are a query categorization system for a Redis SRE agent.

The user has a Redis instance available. Determine what kind of agent should handle their query:

1. TRIAGE: Full health check, comprehensive diagnostics, or in-depth analysis.
   Trigger words: "full health check", "triage", "comprehensive", "full analysis", "complete diagnostic", "thorough check", "audit"
   Examples:
   - "Run a full health check on my Redis"
   - "I need a comprehensive triage of this instance"
   - "Do a complete diagnostic"
   - "Give me a thorough analysis"

2. CHAT: Quick questions, specific lookups, or targeted queries.
   Examples:
   - "What do you know about this instance?"
   - "Check the memory usage"
   - "Show me the slowlog"
   - "How many connections are there?"
   - "What's the current ops/sec?"
   - "Is replication working?"

Respond with ONLY one word: either "TRIAGE" or "CHAT"."""

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"Categorize this query: {query}"),
        ]

        response = await llm.ainvoke(messages)
        category = response.content.strip().upper()

        if "TRIAGE" in category:
            logger.info("LLM categorized query as REDIS_TRIAGE (full health check)")
            return AgentType.REDIS_TRIAGE
        else:
            logger.info("LLM categorized query as REDIS_CHAT (quick Q&A)")
            return AgentType.REDIS_CHAT

    except Exception as e:
        logger.error(f"Error during LLM routing: {e}, defaulting to REDIS_CHAT")
        return AgentType.REDIS_CHAT
