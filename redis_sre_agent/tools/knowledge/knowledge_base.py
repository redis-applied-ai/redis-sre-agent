"""Knowledge Base tool provider.

This provider wraps the knowledge base functions from core.tasks and exposes
them as tools for the LLM to use.
"""

import logging
from typing import Any, Dict, List, Optional

from opentelemetry import trace

from redis_sre_agent.core.docket_tasks import (
    ingest_sre_document as _ingest_sre_document,
)
from redis_sre_agent.core.knowledge_helpers import (
    _coerce_non_negative_int,
    _coerce_positive_int,
    get_all_document_fragments,
    get_related_document_fragments,
    get_skill_helper,
    get_skill_resource_helper,
    get_support_ticket_helper,
    search_knowledge_base_helper,
    search_support_tickets_helper,
    skills_check_helper,
)
from redis_sre_agent.tools.decorators import status_update
from redis_sre_agent.tools.models import ToolCapability, ToolDefinition
from redis_sre_agent.tools.protocols import ToolProvider

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


class KnowledgeBaseToolProvider(ToolProvider):
    """Provides knowledge base search and ingestion tools.

    This provider is always enabled and provides access to the SRE knowledge base
    which contains runbooks, Redis documentation, troubleshooting guides, and
    SRE procedures.
    """

    @property
    def provider_name(self) -> str:
        return "knowledge"

    @property
    def requires_redis_instance(self) -> bool:
        """Knowledge base tools do not require a Redis instance."""
        return False

    def create_tool_schemas(self) -> List[ToolDefinition]:
        """Create tool schemas for knowledge base operations."""
        return [
            ToolDefinition(
                name=self._make_tool_name("search"),
                description=(
                    "Search the general knowledge base for relevant information including "
                    "runbooks, Redis documentation, troubleshooting guides, and SRE procedures. "
                    "Use this to find solutions to problems, understand Redis features, or get "
                    "guidance on SRE best practices. Always cite the source document and title "
                    "when using information from search results. This search excludes pinned "
                    "documents, skills, and support tickets. By default, returns only the "
                    "latest version of documentation to avoid duplicates."
                ),
                capability=ToolCapability.KNOWLEDGE,
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query describing what you're looking for",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of results to return (default: 10)",
                            "default": 10,
                            "minimum": 1,
                            "maximum": 50,
                        },
                        "offset": {
                            "type": "integer",
                            "description": "Number of results to skip for pagination (default: 0)",
                            "default": 0,
                            "minimum": 0,
                        },
                        "version": {
                            "type": "string",
                            "description": (
                                "Redis documentation version filter. Defaults to 'latest' which "
                                "returns only the most current documentation. Available versions: "
                                "'latest' (default, recommended), '7.8', '7.4', '7.2'. "
                                "Set to null to return all versions (may include duplicates)."
                            ),
                            "default": "latest",
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
                capability=ToolCapability.KNOWLEDGE,
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
                        "doc_type": {
                            "type": "string",
                            "description": (
                                "Document type (e.g., 'skill', 'support_ticket', 'runbook', "
                                "'documentation')."
                            ),
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
                capability=ToolCapability.KNOWLEDGE,
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
                capability=ToolCapability.KNOWLEDGE,
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
            ToolDefinition(
                name=self._make_tool_name("skills_check"),
                description=(
                    "Run a skills check to list relevant skills from the knowledge base. "
                    "Use query context whenever possible and then request a full skill "
                    "with get_skill."
                ),
                capability=ToolCapability.KNOWLEDGE,
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": (
                                "Optional task query for relevance-ranked skill matching. "
                                "If omitted, returns a deterministic skills table of contents."
                            ),
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of skills to return (default: 20)",
                            "default": 20,
                            "minimum": 1,
                            "maximum": 100,
                        },
                        "offset": {
                            "type": "integer",
                            "description": "Number of skills to skip for pagination (default: 0)",
                            "default": 0,
                            "minimum": 0,
                        },
                        "version": {
                            "type": "string",
                            "description": (
                                "Optional Redis documentation version filter. "
                                "Defaults to 'latest'. Set to null to include all versions."
                            ),
                            "default": "latest",
                        },
                    },
                },
            ),
            ToolDefinition(
                name=self._make_tool_name("get_skill"),
                description=(
                    "Retrieve the complete content of a skill by skill name. "
                    "Use the name returned by skills_check."
                ),
                capability=ToolCapability.KNOWLEDGE,
                parameters={
                    "type": "object",
                    "properties": {
                        "skill_name": {
                            "type": "string",
                            "description": "Skill name from skills_check results",
                        },
                    },
                    "required": ["skill_name"],
                },
            ),
            ToolDefinition(
                name=self._make_tool_name("get_skill_resource"),
                description=(
                    "Retrieve one packaged skill resource by path. "
                    "Use this after get_skill identifies a reference, script, or asset path."
                ),
                capability=ToolCapability.KNOWLEDGE,
                parameters={
                    "type": "object",
                    "properties": {
                        "skill_name": {
                            "type": "string",
                            "description": "Skill name from skills_check or get_skill",
                        },
                        "resource_path": {
                            "type": "string",
                            "description": "Relative resource path from get_skill, such as references/foo.md",
                        },
                    },
                    "required": ["skill_name", "resource_path"],
                },
            ),
            ToolDefinition(
                name=self._make_tool_name("search_support_tickets"),
                description=(
                    "Search support tickets only. "
                    "Use this for historical or active support-case context. "
                    "Use this instead of general knowledge search when the user asks about "
                    "support tickets, prior incidents, or case history because general knowledge "
                    "search excludes support tickets."
                ),
                capability=ToolCapability.TICKETS,
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Support ticket search query",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of results to return (default: 10)",
                            "default": 10,
                            "minimum": 1,
                            "maximum": 50,
                        },
                        "offset": {
                            "type": "integer",
                            "description": "Number of results to skip for pagination (default: 0)",
                            "default": 0,
                            "minimum": 0,
                        },
                        "version": {
                            "type": "string",
                            "description": (
                                "Redis documentation version filter. Defaults to 'latest'. "
                                "Set to null to include all versions."
                            ),
                            "default": "latest",
                        },
                        "distance_threshold": {
                            "type": "number",
                            "description": (
                                "Optional cosine distance threshold. Set to null for pure KNN."
                            ),
                            "default": 0.8,
                        },
                    },
                    "required": ["query"],
                },
            ),
            ToolDefinition(
                name=self._make_tool_name("get_support_ticket"),
                description=(
                    "Retrieve the complete content of a support ticket by ticket id. "
                    "Use this after search_support_tickets returns a likely match."
                ),
                capability=ToolCapability.TICKETS,
                parameters={
                    "type": "object",
                    "properties": {
                        "ticket_id": {
                            "type": "string",
                            "description": "Ticket id from search_support_tickets results",
                        }
                    },
                    "required": ["ticket_id"],
                },
            ),
        ]

    @status_update("I'm searching the knowledge base for {query}.")
    async def search(
        self,
        query: str,
        limit: int = 10,
        offset: int = 0,
        version: Optional[str] = "latest",
        distance_threshold: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Search the knowledge base.

        Args:
            query: Search query
            limit: Maximum number of results
            offset: Number of results to skip for pagination
            version: Version filter - "latest" (default), specific version like "7.8",
                     or None to return all versions
            distance_threshold: Optional cosine distance threshold. If provided, overrides the backend default.

        Returns:
            Search results with relevant knowledge base content
        """
        limit = _coerce_positive_int(limit, default=10)
        offset = _coerce_non_negative_int(offset, default=0)
        logger.info(
            f"Knowledge base search: {query} (limit={limit}, offset={offset}, version={version})"
        )
        kwargs = {
            "query": query,
            "limit": limit,
            "offset": offset,
            "version": version,
            "distance_threshold": distance_threshold,
        }
        # OTel: instrument knowledge search without leaking raw query
        import hashlib as _hl

        _qhash = ""
        try:
            _qhash = _hl.sha1((query or "").encode("utf-8")).hexdigest()
        except Exception:
            _qhash = ""
        with tracer.start_as_current_span(
            "tool.knowledge.search",
            attributes={
                "query.len": len(query or ""),
                "query.sha1": _qhash,
                "limit": int(limit),
                "offset": int(offset),
                "version": version or "all",
                "distance_threshold.set": distance_threshold is not None,
            },
        ):
            return await search_knowledge_base_helper(**kwargs)

    async def ingest(
        self,
        title: str,
        content: str,
        source: str,
        category: str,
        severity: Optional[str] = None,
        doc_type: Optional[str] = None,
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
        if doc_type:
            kwargs["doc_type"] = doc_type
        if product_labels:
            kwargs["product_labels"] = product_labels

        # OTel: instrument ingestion
        with tracer.start_as_current_span(
            "tool.knowledge.ingest",
            attributes={
                "title.len": len(title or ""),
                "category": str(category or ""),
                "doc_type": str(doc_type or ""),
                "has.labels": bool(product_labels),
                "has.severity": bool(severity),
            },
        ):
            return await _ingest_sre_document(**kwargs)

    async def get_all_fragments(self, document_hash: str) -> Dict[str, Any]:
        """Get all fragments of a document.

        Args:
            document_hash: Hash of the document

        Returns:
            Dictionary with all document fragments
        """
        logger.info(f"Getting all fragments for document: {document_hash}")
        with tracer.start_as_current_span(
            "tool.knowledge.get_all_fragments",
            attributes={"document_hash": str(document_hash)[:16]},
        ):
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
        with tracer.start_as_current_span(
            "tool.knowledge.get_related_fragments",
            attributes={
                "document_hash": str(document_hash)[:16],
                "chunk_index": int(chunk_index),
                "limit": int(limit),
            },
        ):
            return await get_related_document_fragments(document_hash, chunk_index, limit)

    @status_update("I'm checking the available skills in the knowledge base.")
    async def skills_check(
        self,
        query: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
        version: Optional[str] = "latest",
    ) -> Dict[str, Any]:
        """List available skills from the knowledge base."""
        limit = _coerce_positive_int(limit, default=20)
        offset = _coerce_non_negative_int(offset, default=0)
        logger.info(
            "Checking skills (query=%s, limit=%s, offset=%s, version=%s)",
            bool(query),
            limit,
            offset,
            version,
        )
        with tracer.start_as_current_span(
            "tool.knowledge.skills_check",
            attributes={
                "query.len": len(query or ""),
                "limit": int(limit),
                "offset": int(offset),
                "version": version or "all",
            },
        ):
            return await skills_check_helper(
                query=query,
                limit=limit,
                offset=offset,
                version=version,
            )

    async def get_skill(self, skill_name: str) -> Dict[str, Any]:
        """Get complete content for a single skill document."""
        logger.info("Getting full skill document by name: %s", skill_name)
        with tracer.start_as_current_span(
            "tool.knowledge.get_skill",
            attributes={"skill_name.len": len(skill_name or "")},
        ):
            return await get_skill_helper(skill_name=skill_name)

    async def get_skill_resource(self, skill_name: str, resource_path: str) -> Dict[str, Any]:
        """Get one named resource from a skill package."""
        logger.info("Getting skill resource %s from %s", resource_path, skill_name)
        with tracer.start_as_current_span(
            "tool.knowledge.get_skill_resource",
            attributes={
                "skill_name.len": len(skill_name or ""),
                "resource_path.len": len(resource_path or ""),
            },
        ):
            return await get_skill_resource_helper(
                skill_name=skill_name,
                resource_path=resource_path,
            )

    @status_update("I'm searching support tickets for {query}.")
    async def search_support_tickets(
        self,
        query: str,
        limit: int = 10,
        offset: int = 0,
        version: Optional[str] = "latest",
        distance_threshold: Optional[float] = 0.8,
    ) -> Dict[str, Any]:
        """Search support tickets only."""
        limit = _coerce_positive_int(limit, default=10)
        offset = _coerce_non_negative_int(offset, default=0)
        logger.info(
            "Searching support tickets: %s (limit=%s, offset=%s, version=%s)",
            query,
            limit,
            offset,
            version,
        )
        with tracer.start_as_current_span(
            "tool.knowledge.search_support_tickets",
            attributes={
                "query.len": len(query or ""),
                "limit": int(limit),
                "offset": int(offset),
                "version": version or "all",
                "distance_threshold.set": distance_threshold is not None,
            },
        ):
            return await search_support_tickets_helper(
                query=query,
                limit=limit,
                offset=offset,
                version=version,
                distance_threshold=distance_threshold,
            )

    async def get_support_ticket(self, ticket_id: str) -> Dict[str, Any]:
        """Get complete content for a support ticket."""
        logger.info("Getting support ticket: %s", ticket_id)
        with tracer.start_as_current_span(
            "tool.knowledge.get_support_ticket",
            attributes={"ticket_id": str(ticket_id)[:32]},
        ):
            return await get_support_ticket_helper(ticket_id=ticket_id)
