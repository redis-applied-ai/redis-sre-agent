"""Knowledge Base tool provider.

This provider wraps the knowledge base functions from core.tasks and exposes
them as tools for the LLM to use.
"""

import logging
from typing import Any, Dict, List, Optional

from redis_sre_agent.core.tasks import (
    ingest_sre_document as _ingest_sre_document,
)
from redis_sre_agent.core.tasks import (
    search_knowledge_base as _search_knowledge_base,
)
from redis_sre_agent.tools.protocols import ToolProvider
from redis_sre_agent.tools.tool_definition import ToolDefinition

logger = logging.getLogger(__name__)


class KnowledgeBaseToolProvider(ToolProvider):
    """Provides knowledge base search and ingestion tools.

    This provider is always enabled and provides access to the SRE knowledge base
    which contains runbooks, Redis documentation, troubleshooting guides, and
    SRE procedures.
    """

    provider_name = "knowledge"

    def create_tool_schemas(self) -> List[ToolDefinition]:
        """Create tool schemas for knowledge base operations."""
        return [
            ToolDefinition(
                name=self._make_tool_name("search"),
                description=(
                    "Search the comprehensive knowledge base for relevant information including "
                    "runbooks, Redis documentation, troubleshooting guides, and SRE procedures. "
                    "Use this to find solutions to problems, understand Redis features, or get "
                    "guidance on SRE best practices. Always cite the source document and title "
                    "when using information from search results."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query describing what you're looking for",
                        },
                        "category": {
                            "type": "string",
                            "description": (
                                "Optional category filter (incident, runbook, monitoring, "
                                "redis_commands, redis_config, etc.)"
                            ),
                            "enum": [
                                "incident",
                                "runbook",
                                "monitoring",
                                "redis_commands",
                                "redis_config",
                                "troubleshooting",
                                "best_practices",
                            ],
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of results to return (default: 5)",
                            "default": 5,
                            "minimum": 1,
                            "maximum": 20,
                        },
                    },
                    "required": ["query"],
                },
            ),
            ToolDefinition(
                name=self._make_tool_name("ingest"),
                description=(
                    "Ingest a new document into the knowledge base. Use this to add runbooks, "
                    "troubleshooting guides, or other SRE documentation. The document will be "
                    "chunked, embedded, and indexed for future searches."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "Document title"},
                        "content": {
                            "type": "string",
                            "description": "Document content (markdown or plain text)",
                        },
                        "source": {
                            "type": "string",
                            "description": "Source of the document (URL, file path, or description)",
                        },
                        "category": {
                            "type": "string",
                            "description": "Document category",
                            "enum": [
                                "incident",
                                "runbook",
                                "monitoring",
                                "redis_commands",
                                "redis_config",
                                "troubleshooting",
                                "best_practices",
                            ],
                        },
                        "severity": {
                            "type": "string",
                            "description": "Severity level (for incidents/alerts)",
                            "enum": ["critical", "high", "medium", "low", "info"],
                        },
                        "product_labels": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": (
                                "Redis product labels (e.g., 'Redis Enterprise Software', "
                                "'Redis Cloud', 'Redis CE and Stack')"
                            ),
                        },
                    },
                    "required": ["title", "content", "source", "category"],
                },
            ),
        ]

    async def resolve_tool_call(self, tool_name: str, args: Dict[str, Any]) -> Any:
        """Execute a knowledge base tool call.

        The tool_name includes the provider name and instance hash that we created,
        so we just need to match the operation suffix.
        """
        # Remove the provider prefix and hash to get the operation name
        # Format: knowledge_{hash}_search -> search
        parts = tool_name.split("_")
        if len(parts) >= 3:
            operation = "_".join(parts[2:])  # Everything after provider_hash
        else:
            operation = tool_name

        if operation == "search":
            return await self.search(**args)
        elif operation == "ingest":
            return await self.ingest(**args)
        else:
            raise ValueError(f"Unknown operation: {operation} (from tool: {tool_name})")

    async def search(
        self, query: str, category: Optional[str] = None, limit: int = 5
    ) -> Dict[str, Any]:
        """Search the knowledge base.

        Args:
            query: Search query
            category: Optional category filter
            limit: Maximum number of results

        Returns:
            Search results with relevant knowledge base content
        """
        logger.info(f"Knowledge base search: {query} (category={category}, limit={limit})")
        return await _search_knowledge_base(query=query, category=category, limit=limit)

    async def ingest(
        self,
        title: str,
        content: str,
        source: str,
        category: str,
        severity: Optional[str] = None,
        product_labels: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Ingest a document into the knowledge base.

        Args:
            title: Document title
            content: Document content
            source: Document source
            category: Document category
            severity: Optional severity level
            product_labels: Optional product labels

        Returns:
            Ingestion result with document hash and chunk count
        """
        logger.info(f"Ingesting document: {title} (category={category})")
        return await _ingest_sre_document(
            title=title,
            content=content,
            source=source,
            category=category,
            severity=severity,
            product_labels=product_labels or [],
        )
