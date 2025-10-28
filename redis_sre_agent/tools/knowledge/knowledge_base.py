"""Knowledge Base tool provider.

This provider wraps the knowledge base functions from core.tasks and exposes
them as tools for the LLM to use.
"""

import logging
from typing import Any, Dict, List, Optional

from redis_sre_agent.core.docket_tasks import (
    ingest_sre_document as _ingest_sre_document,
)
from redis_sre_agent.core.knowledge_helpers import (
    get_all_document_fragments,
    get_related_document_fragments,
    search_knowledge_base_helper,
)
from redis_sre_agent.tools.decorators import status_update
from redis_sre_agent.tools.protocols import ToolProvider
from redis_sre_agent.tools.tool_definition import ToolDefinition

logger = logging.getLogger(__name__)


class KnowledgeBaseToolProvider(ToolProvider):
    """Provides knowledge base search and ingestion tools.

    This provider is always enabled and provides access to the SRE knowledge base
    which contains runbooks, Redis documentation, troubleshooting guides, and
    SRE procedures.
    """

    @property
    def provider_name(self) -> str:
        return "knowledge"

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
                            "description": "Maximum number of results to return (default: 10)",
                            "default": 10,
                            "minimum": 1,
                            "maximum": 20,
                        },
                        "distance_threshold": {
                            "type": "number",
                            "description": (
                                "Optional semantic distance threshold (cosine distance).\n"
                                "When provided, a range query is used to filter by distance.\n"
                                "Omit to use the default threshold from the backend (on by default).\n"
                                "Set to null/not provided to avoid passing threshold and keep default;\n"
                                "set explicitly to a number to override; set to 0.0-2.0 range typical."
                            ),
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
            ToolDefinition(
                name=self._make_tool_name("get_all_fragments"),
                description=(
                    "Retrieve all fragments/chunks of a specific document from the knowledge base. "
                    "Use this when you need to see the complete content of a document that was "
                    "found via search. Requires the document_hash from a search result."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "document_hash": {
                            "type": "string",
                            "description": "Hash of the document to retrieve (from search results)",
                        },
                    },
                    "required": ["document_hash"],
                },
            ),
            ToolDefinition(
                name=self._make_tool_name("get_related_fragments"),
                description=(
                    "Find related document fragments based on a specific fragment. "
                    "Use this to explore related content or find additional context "
                    "around a specific piece of information."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "document_hash": {
                            "type": "string",
                            "description": "Hash of the source document",
                        },
                        "chunk_index": {
                            "type": "integer",
                            "description": "Index of the chunk to find related content for",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of related fragments to return (default: 10)",
                            "default": 10,
                            "minimum": 1,
                            "maximum": 20,
                        },
                    },
                    "required": ["document_hash", "chunk_index"],
                },
            ),
        ]

    def _operation_from_tool(self, tool_name: str) -> str:
        parts = tool_name.split("_")
        if len(parts) >= 3:
            return "_".join(parts[2:])
        return tool_name

    def resolve_operation(self, tool_name: str, args: Dict[str, Any]) -> Optional[str]:
        return self._operation_from_tool(tool_name)

    async def resolve_tool_call(self, tool_name: str, args: Dict[str, Any]) -> Any:
        """Execute a knowledge base tool call.

        The tool_name includes the provider name and instance hash that we created,
        so we just need to match the operation suffix.
        """
        operation = self._operation_from_tool(tool_name)

        if operation == "search":
            return await self.search(**args)
        elif operation == "ingest":
            return await self.ingest(**args)
        elif operation == "get_all_fragments":
            return await self.get_all_fragments(**args)
        elif operation == "get_related_fragments":
            return await self.get_related_fragments(**args)
        else:
            raise ValueError(f"Unknown operation: {operation} (from tool: {tool_name})")

    @status_update("I'm searching the knowledge base for {query}.")
    async def search(
        self,
        query: str,
        category: Optional[str] = None,
        limit: int = 10,
        distance_threshold: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Search the knowledge base.

        Args:
            query: Search query
            category: Optional category filter
            limit: Maximum number of results
            distance_threshold: Optional cosine distance threshold. If provided, overrides the backend default.

        Returns:
            Search results with relevant knowledge base content
        """
        logger.info(
            f"Knowledge base search: {query} (category={category}, limit={limit}, distance_threshold={distance_threshold})"
        )
        kwargs = {
            "query": query,
            "category": category,
            "limit": limit,
            "distance_threshold": distance_threshold,
        }
        return await search_knowledge_base_helper(**kwargs)

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
        kwargs = {
            "title": title,
            "content": content,
            "source": source,
            "category": category,
        }
        if severity:
            kwargs["severity"] = severity
        if product_labels:
            kwargs["product_labels"] = product_labels

        return await _ingest_sre_document(**kwargs)

    async def get_all_fragments(self, document_hash: str) -> Dict[str, Any]:
        """Get all fragments of a document.

        Args:
            document_hash: Hash of the document

        Returns:
            Dictionary with all document fragments
        """
        logger.info(f"Getting all fragments for document: {document_hash}")
        return await get_all_document_fragments(document_hash)

    async def get_related_fragments(
        self, document_hash: str, chunk_index: int, limit: int = 10
    ) -> Dict[str, Any]:
        """Get related fragments for a specific chunk.

        Args:
            document_hash: Hash of the document
            chunk_index: Index of the chunk
            limit: Maximum number of related fragments

        Returns:
            Dictionary with related fragments
        """
        logger.info(f"Getting related fragments for document {document_hash}, chunk {chunk_index}")
        return await get_related_document_fragments(document_hash, chunk_index, limit)
