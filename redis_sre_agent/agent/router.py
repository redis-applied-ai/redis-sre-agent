"""
Agent routing logic for intelligent selection between Redis-focused and knowledge-only agents.

This module determines which agent should handle a given query based on context,
user input patterns, and available Redis instance information.
"""

import logging
import re
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class AgentType(Enum):
    """Types of available agents."""

    REDIS_FOCUSED = "redis_focused"
    KNOWLEDGE_ONLY = "knowledge_only"


class AgentRouter:
    """Routes queries to the appropriate agent based on context and content analysis."""

    def __init__(self):
        """Initialize the agent router."""
        # Keywords that suggest Redis-specific queries
        self.redis_keywords = {
            "instance",
            "redis",
            "connection",
            "memory",
            "keys",
            "database",
            "db",
            "cluster",
            "sentinel",
            "replication",
            "persistence",
            "rdb",
            "aof",
            "eviction",
            "maxmemory",
            "timeout",
            "slowlog",
            "latency",
            "throughput",
            "cpu",
            "network",
            "port",
            "host",
            "auth",
            "password",
            "ssl",
            "tls",
        }

        # Keywords that suggest diagnostic/monitoring queries
        self.diagnostic_keywords = {
            "monitor",
            "metrics",
            "performance",
            "slow",
            "error",
            "crash",
            "down",
            "unavailable",
            "timeout",
            "latency",
            "memory usage",
            "cpu usage",
            "disk space",
            "logs",
            "debug",
            "troubleshoot",
            "diagnose",
            "health check",
        }

        # Keywords that suggest general knowledge queries
        self.knowledge_keywords = {
            "best practice",
            "how to",
            "what is",
            "explain",
            "guide",
            "tutorial",
            "documentation",
            "learn",
            "understand",
            "concept",
            "principle",
            "methodology",
            "approach",
            "strategy",
            "recommendation",
            "advice",
            "sre",
            "reliability",
            "availability",
            "scalability",
            "observability",
        }

        # Patterns that strongly indicate Redis-specific queries
        self.redis_patterns = [
            r"\b(?:redis|instance)\s+(?:is|was|has|shows|reports)\b",
            r"\b(?:connect|connecting)\s+to\s+redis\b",
            r"\b(?:redis|instance)\s+(?:error|problem|issue|failure)\b",
            r"\b(?:memory|cpu|disk)\s+(?:usage|utilization|consumption)\b",
            r"\b(?:slow|high|low)\s+(?:performance|latency|throughput)\b",
            r"\b(?:redis|instance)\s+(?:configuration|config|settings)\b",
        ]

        # Patterns that suggest knowledge-only queries
        self.knowledge_patterns = [
            r"\b(?:what|how|why|when|where)\s+(?:is|are|do|does|should|would|can|could)\b",
            r"\b(?:best\s+practice|recommended\s+approach|how\s+to)\b",
            r"\b(?:explain|describe|define|clarify)\b",
            r"\b(?:guide|tutorial|documentation|example)\b",
            r"\b(?:sre|reliability|observability)\s+(?:principle|concept|methodology)\b",
        ]

    def route_query(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
        user_preferences: Optional[Dict[str, Any]] = None,
    ) -> AgentType:
        """
        Route a query to the appropriate agent.

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
            logger.info(
                "Query has explicit Redis instance context - routing to Redis-focused agent"
            )
            return AgentType.REDIS_FOCUSED

        # 2. Check user preferences
        if user_preferences and user_preferences.get("preferred_agent"):
            preferred = user_preferences["preferred_agent"]
            if preferred in [agent.value for agent in AgentType]:
                logger.info(f"Using user preference: {preferred}")
                return AgentType(preferred)

        # 3. Analyze query content
        query_lower = query.lower()

        # Calculate keyword scores
        redis_score = self._calculate_keyword_score(query_lower, self.redis_keywords)
        diagnostic_score = self._calculate_keyword_score(query_lower, self.diagnostic_keywords)
        knowledge_score = self._calculate_keyword_score(query_lower, self.knowledge_keywords)

        # Calculate pattern scores
        redis_pattern_score = self._calculate_pattern_score(query_lower, self.redis_patterns)
        knowledge_pattern_score = self._calculate_pattern_score(
            query_lower, self.knowledge_patterns
        )

        # Combine scores
        total_redis_score = redis_score + diagnostic_score + redis_pattern_score
        total_knowledge_score = knowledge_score + knowledge_pattern_score

        logger.info(
            f"Routing scores - Redis: {total_redis_score}, Knowledge: {total_knowledge_score}"
        )

        # 4. Make routing decision
        if total_redis_score > total_knowledge_score and total_redis_score > 0:
            logger.info("Routing to Redis-focused agent based on content analysis")
            return AgentType.REDIS_FOCUSED
        elif total_knowledge_score > 0:
            logger.info("Routing to knowledge-only agent based on content analysis")
            return AgentType.KNOWLEDGE_ONLY
        else:
            # Default to knowledge-only for general queries
            logger.info("No strong indicators found - defaulting to knowledge-only agent")
            return AgentType.KNOWLEDGE_ONLY

    def _calculate_keyword_score(self, query: str, keywords: set) -> float:
        """Calculate score based on keyword matches."""
        matches = sum(1 for keyword in keywords if keyword in query)
        return matches / len(keywords) if keywords else 0

    def _calculate_pattern_score(self, query: str, patterns: List[str]) -> float:
        """Calculate score based on regex pattern matches."""
        matches = sum(1 for pattern in patterns if re.search(pattern, query, re.IGNORECASE))
        return matches / len(patterns) if patterns else 0

    def get_routing_explanation(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
        user_preferences: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Get detailed explanation of routing decision.

        Returns:
            Dictionary with routing decision and explanation
        """
        agent_type = self.route_query(query, context, user_preferences)

        explanation = {"selected_agent": agent_type.value, "reasoning": [], "scores": {}}

        # Check explicit context
        if context and context.get("instance_id"):
            explanation["reasoning"].append("Query includes specific Redis instance context")

        # Analyze content
        query_lower = query.lower()

        redis_score = self._calculate_keyword_score(query_lower, self.redis_keywords)
        diagnostic_score = self._calculate_keyword_score(query_lower, self.diagnostic_keywords)
        knowledge_score = self._calculate_keyword_score(query_lower, self.knowledge_keywords)
        redis_pattern_score = self._calculate_pattern_score(query_lower, self.redis_patterns)
        knowledge_pattern_score = self._calculate_pattern_score(
            query_lower, self.knowledge_patterns
        )

        explanation["scores"] = {
            "redis_keywords": redis_score,
            "diagnostic_keywords": diagnostic_score,
            "knowledge_keywords": knowledge_score,
            "redis_patterns": redis_pattern_score,
            "knowledge_patterns": knowledge_pattern_score,
            "total_redis": redis_score + diagnostic_score + redis_pattern_score,
            "total_knowledge": knowledge_score + knowledge_pattern_score,
        }

        # Add reasoning based on scores
        if explanation["scores"]["total_redis"] > explanation["scores"]["total_knowledge"]:
            explanation["reasoning"].append(
                "Query contains Redis-specific terminology and patterns"
            )
        elif explanation["scores"]["total_knowledge"] > 0:
            explanation["reasoning"].append(
                "Query appears to be seeking general knowledge or guidance"
            )
        else:
            explanation["reasoning"].append(
                "No strong indicators found, defaulting to knowledge-only agent"
            )

        return explanation

    def suggest_alternative_agent(
        self, current_agent: AgentType, query: str
    ) -> Optional[Dict[str, str]]:
        """
        Suggest alternative agent if the current one might not be optimal.

        Returns:
            Dictionary with suggestion or None if current agent is appropriate
        """
        alternative_agent = self.route_query(query)

        if alternative_agent != current_agent:
            suggestions = {
                AgentType.REDIS_FOCUSED: {
                    "agent": "Redis-focused agent",
                    "reason": "This query appears to be about specific Redis instance troubleshooting or diagnostics",
                },
                AgentType.KNOWLEDGE_ONLY: {
                    "agent": "Knowledge-only agent",
                    "reason": "This query appears to be seeking general SRE guidance or best practices",
                },
            }

            return {
                "suggested_agent": alternative_agent.value,
                "current_agent": current_agent.value,
                "reason": suggestions[alternative_agent]["reason"],
                "suggestion": f"Consider using the {suggestions[alternative_agent]['agent']} for better results",
            }

        return None


# Singleton instance
_router = None


def get_agent_router() -> AgentRouter:
    """Get or create the agent router singleton."""
    global _router
    if _router is None:
        _router = AgentRouter()
    return _router


def route_to_appropriate_agent(
    query: str,
    context: Optional[Dict[str, Any]] = None,
    user_preferences: Optional[Dict[str, Any]] = None,
) -> AgentType:
    """
    Convenience function to route a query to the appropriate agent.

    Args:
        query: The user's query text
        context: Additional context including instance_id, priority, etc.
        user_preferences: User preferences for agent selection

    Returns:
        AgentType indicating which agent should handle the query
    """
    router = get_agent_router()
    return router.route_query(query, context, user_preferences)
