"""Tests for KnowledgeBaseToolProvider."""

import pytest

from redis_sre_agent.tools.knowledge.knowledge_base import KnowledgeBaseToolProvider
from redis_sre_agent.tools.tool_definition import ToolDefinition


def test_knowledge_provider_initialization():
    """Test that KnowledgeBaseToolProvider can be initialized."""
    provider = KnowledgeBaseToolProvider()
    assert provider.provider_name == "knowledge"
    assert provider.redis_instance is None
    assert provider.config is None


def test_knowledge_provider_tool_schemas():
    """Test that KnowledgeBaseToolProvider creates correct tool schemas."""
    provider = KnowledgeBaseToolProvider()
    schemas = provider.create_tool_schemas()

    # Should have 2 tools
    assert len(schemas) == 2

    # All should be ToolDefinition objects
    for schema in schemas:
        assert isinstance(schema, ToolDefinition)

    # Check tool names
    tool_names = [s.name for s in schemas]
    assert any("search" in name for name in tool_names)
    assert any("ingest" in name for name in tool_names)

    # All tool names should include provider name and hash
    for name in tool_names:
        assert name.startswith("knowledge_")


def test_knowledge_provider_search_schema():
    """Test search tool schema."""
    provider = KnowledgeBaseToolProvider()
    schemas = provider.create_tool_schemas()

    search_schema = next(s for s in schemas if "search" in s.name)

    # Check required fields
    assert "query" in search_schema.parameters["properties"]
    assert "query" in search_schema.parameters["required"]

    # Check optional fields
    assert "category" in search_schema.parameters["properties"]
    assert "limit" in search_schema.parameters["properties"]


def test_knowledge_provider_ingest_schema():
    """Test ingest tool schema."""
    provider = KnowledgeBaseToolProvider()
    schemas = provider.create_tool_schemas()

    ingest_schema = next(s for s in schemas if "ingest" in s.name)

    # Check required fields
    required = ingest_schema.parameters["required"]
    assert "title" in required
    assert "content" in required
    assert "source" in required
    assert "category" in required


def test_knowledge_provider_tool_name_uniqueness():
    """Test that tool names include instance hash."""
    provider1 = KnowledgeBaseToolProvider()

    schemas1 = provider1.create_tool_schemas()
    names1 = [s.name for s in schemas1]

    # All names should include the provider name and a hash
    for name in names1:
        assert name.startswith("knowledge_")
        # Should have format: knowledge_{hash}_{operation}
        parts = name.split("_")
        assert len(parts) >= 3  # provider, hash, operation

        # Hash should be hex string
        hash_part = parts[1]
        assert len(hash_part) == 6  # hex(id(self))[2:8] gives 6 chars
        int(hash_part, 16)  # Should be valid hex


@pytest.mark.asyncio
async def test_knowledge_provider_resolve_unknown_tool():
    """Test that resolve_tool_call raises error for unknown tools."""
    provider = KnowledgeBaseToolProvider()

    with pytest.raises(ValueError, match="Unknown operation"):
        await provider.resolve_tool_call("unknown_tool", {})


@pytest.mark.asyncio
async def test_knowledge_provider_context_manager():
    """Test that KnowledgeBaseToolProvider works as async context manager."""
    async with KnowledgeBaseToolProvider() as provider:
        assert provider is not None
        assert provider.provider_name == "knowledge"

        # Should be able to create schemas
        schemas = provider.create_tool_schemas()
        assert len(schemas) == 2
