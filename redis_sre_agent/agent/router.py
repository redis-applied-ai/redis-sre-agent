"""
Agent routing logic for intelligent selection between Redis-focused and knowledge-only agents.

This module uses a fast LLM (nano model) to categorize queries and determine
which agent should handle them based on context and query content.
"""

import logging
from enum import Enum
from typing import Any, Dict, List, Optional

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from redis_sre_agent.core.llm_helpers import create_nano_llm

logger = logging.getLogger(__name__)


class AgentType(Enum):
    """Types of available agents."""

    REDIS_TRIAGE = "redis_triage"  # Full triage/health check agent
    REDIS_CHAT = "redis_chat"  # Lightweight chat agent for quick Q&A
    KNOWLEDGE_ONLY = "knowledge_only"  # No instance, general knowledge

    # Keep old value for backward compatibility
    REDIS_FOCUSED = "redis_triage"  # Alias for REDIS_TRIAGE


def _format_conversation_context(
    conversation_history: Optional[List[BaseMessage]], max_messages: int = 4
) -> str:
    """Format recent conversation history for the router to understand context."""
    if not conversation_history:
        return ""

    # Take last N messages for context
    recent = conversation_history[-max_messages:]
    if not recent:
        return ""

    lines = ["\n\nRecent conversation context:"]
    for msg in recent:
        role = "User" if isinstance(msg, HumanMessage) else "Assistant"
        # Truncate long messages
        content = msg.content[:500] + "..." if len(msg.content) > 500 else msg.content
        lines.append(f"{role}: {content}")

    return "\n".join(lines)


async def route_to_appropriate_agent(
    query: str,
    context: Optional[Dict[str, Any]] = None,
    user_preferences: Optional[Dict[str, Any]] = None,
    conversation_history: Optional[List[BaseMessage]] = None,
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
        conversation_history: Previous messages in the conversation for context

    Returns:
        AgentType indicating which agent should handle the query
    """
    logger.info(f"Routing query: {query[:100]}...")

    has_instance = context and context.get("instance_id")
    has_support_package = context and context.get("support_package_path")

    # 1. Has support package - route to triage (needs diagnostic tools)
    if has_support_package:
        logger.info("Support package provided - routing to REDIS_TRIAGE for diagnostic tools")
        return AgentType.REDIS_TRIAGE

    # 2. No instance context - route to knowledge agent
    if not has_instance:
        # Use LLM to decide if query needs instance access or is knowledge-only
        try:
            llm = create_nano_llm(timeout=10.0)

            # Include conversation context if available
            context_str = _format_conversation_context(conversation_history)

            system_prompt = """You are a query categorization system for a Redis SRE agent.

Categorize if this query requires access to a live Redis instance or is just seeking general knowledge.
Consider the conversation context if provided - a follow-up like "yes" or "check that" refers to the previous discussion.

1. NEEDS_INSTANCE: Queries that require access to a specific Redis instance for diagnostics, monitoring, or troubleshooting.
   Examples: "Check my Redis memory", "Why is Redis slow?", "Show me the slowlog"

2. KNOWLEDGE_ONLY: Queries seeking general knowledge, best practices, or guidance.
   Examples: "What are Redis best practices?", "How does Redis replication work?"

Respond with ONLY one word: either "NEEDS_INSTANCE" or "KNOWLEDGE_ONLY"."""

            query_with_context = f"Categorize this query: {query}{context_str}"
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=query_with_context),
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
        llm = create_nano_llm(timeout=10.0)

        # Include conversation context if available
        context_str = _format_conversation_context(conversation_history)

        system_prompt = """You are a query categorization system for a Redis SRE agent.

The user has a Redis instance available. Determine what kind of agent should handle their query.
Consider the conversation context if provided - a follow-up like "yes", "sure", or "check that" refers to the previous discussion.

1. DEEP_TRIAGE: ONLY use this for explicit requests for deep, comprehensive, or multi-topic analysis.
   Trigger phrases (must explicitly appear):
   - "deep triage", "deep research", "deep analysis", "deep dive"
   - "go deep", "dig deep", "investigate deeply"
   - "comprehensive triage", "full triage"
   - "exhaustive analysis", "thorough investigation"

   Examples that REQUIRE deep triage:
   - "Do a deep triage on my Redis"
   - "Go deep on this issue"
   - "I need a comprehensive triage"
   - "Deep dive into what's happening"

2. CHAT: Use for ALL other queries, including:
   - Quick questions: "What's the memory usage?"
   - General health checks: "Check my Redis", "Is everything okay?"
   - Specific lookups: "Show me the slowlog", "How many connections?"
   - Status checks: "What's happening with this instance?"
   - Troubleshooting: "Why is Redis slow?", "Help me debug this"
   - Even broad questions like "full health check" or "check everything"
   - Follow-up questions like "yes", "sure", "do it", "check them out"

   The chat agent has ALL the same tools as deep triage - it can do a lot!
   Only use DEEP_TRIAGE when the user explicitly asks for deep/exhaustive analysis.

DEFAULT TO CHAT unless you see explicit deep/exhaustive keywords.

Respond with ONLY one word: either "DEEP_TRIAGE" or "CHAT"."""

        query_with_context = f"Categorize this query: {query}{context_str}"
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=query_with_context),
        ]

        response = await llm.ainvoke(messages)
        category = response.content.strip().upper()

        if "DEEP_TRIAGE" in category:
            logger.info("LLM categorized query as REDIS_TRIAGE (deep triage requested)")
            return AgentType.REDIS_TRIAGE
        else:
            logger.info("LLM categorized query as REDIS_CHAT (default agent)")
            return AgentType.REDIS_CHAT

    except Exception as e:
        logger.error(f"Error during LLM routing: {e}, defaulting to REDIS_CHAT")
        return AgentType.REDIS_CHAT
