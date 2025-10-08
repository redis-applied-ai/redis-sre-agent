"""Knowledge base tool definitions.

This module provides ToolDefinition objects for knowledge base operations.
"""

from typing import List

from ..tools.sre_functions import (
    get_all_document_fragments,
    get_related_document_fragments,
    ingest_sre_document,
    search_knowledge_base,
)
from .tool_definition import ToolDefinition


def get_knowledge_tools() -> List[ToolDefinition]:
    """Get knowledge base tool definitions.

    Returns:
        List of ToolDefinition objects for knowledge base operations
    """
    return [
        ToolDefinition(
            name="search_knowledge_base",
            description="Search comprehensive knowledge base including SRE runbooks, Redis documentation, troubleshooting guides, and operational procedures. Use this for finding both Redis-specific documentation (commands, configuration, concepts) and SRE procedures.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query - can include Redis commands (e.g. 'MEMORY USAGE'), configuration options (e.g. 'maxmemory-policy'), concepts (e.g. 'eviction policies'), or SRE procedures (e.g. 'connection limit troubleshooting')",
                    },
                    "category": {
                        "type": "string",
                        "description": "Optional category to focus search on",
                        "enum": [
                            "incident_response",
                            "monitoring",
                            "performance",
                            "troubleshooting",
                            "maintenance",
                            "redis_commands",
                            "redis_config",
                            "redis_concepts",
                        ],
                    },
                },
                "required": ["query"],
            },
            function=search_knowledge_base,
        ),
        ToolDefinition(
            name="ingest_sre_document",
            description="Add new SRE documentation, runbooks, or procedures to knowledge base",
            parameters={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Title of the document"},
                    "content": {
                        "type": "string",
                        "description": "Content of the SRE document",
                    },
                    "source": {
                        "type": "string",
                        "description": "Source system or file for the document",
                        "default": "agent_ingestion",
                    },
                    "category": {
                        "type": "string",
                        "description": "Document category",
                        "enum": [
                            "runbook",
                            "procedure",
                            "troubleshooting",
                            "best_practice",
                            "incident_report",
                        ],
                        "default": "procedure",
                    },
                    "severity": {
                        "type": "string",
                        "description": "Severity or priority level",
                        "enum": ["info", "warning", "critical"],
                        "default": "info",
                    },
                },
                "required": ["title", "content"],
            },
            function=ingest_sre_document,
        ),
        ToolDefinition(
            name="get_all_document_fragments",
            description="Retrieve ALL fragments/chunks of a specific document when you find a relevant piece and need the complete context. Use the document_hash from search results to get the full document content. This is essential when a search result fragment looks relevant but you need the complete information to provide a comprehensive answer.",
            parameters={
                "type": "object",
                "properties": {
                    "document_hash": {
                        "type": "string",
                        "description": "The document hash from search results (e.g., from search_knowledge_base results)",
                    },
                    "include_metadata": {
                        "type": "boolean",
                        "description": "Whether to include document metadata",
                        "default": True,
                    },
                },
                "required": ["document_hash"],
            },
            function=get_all_document_fragments,
        ),
        ToolDefinition(
            name="get_related_document_fragments",
            description="Get related fragments around a specific chunk for additional context without retrieving the entire document. Use this when you want surrounding context for a specific fragment you found in search results. Provide the document_hash and chunk_index from search results.",
            parameters={
                "type": "object",
                "properties": {
                    "document_hash": {
                        "type": "string",
                        "description": "The document hash from search results",
                    },
                    "current_chunk_index": {
                        "type": "integer",
                        "description": "The chunk index from search results to get context around",
                    },
                    "context_window": {
                        "type": "integer",
                        "description": "Number of chunks before and after to include (default: 2)",
                        "default": 2,
                    },
                },
                "required": ["document_hash", "current_chunk_index"],
            },
            function=get_related_document_fragments,
        ),
    ]
