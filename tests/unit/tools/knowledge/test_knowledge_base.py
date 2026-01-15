"""Tests for KnowledgeBaseToolProvider."""

import pytest

from redis_sre_agent.tools.knowledge.knowledge_base import KnowledgeBaseToolProvider
from redis_sre_agent.tools.models import ToolDefinition
from redis_sre_agent.tools.protocols import ToolCapability


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
    assert len(schemas) == 4  # search, ingest, get_all_fragments, get_related_fragments

    # All should be ToolDefinition objects
    for schema in schemas:
        assert isinstance(schema, ToolDefinition)
        assert schema.capability == ToolCapability.KNOWLEDGE

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
    props = search_schema.parameters["properties"]
    assert "category" not in props
    assert "limit" in props
    assert "distance_threshold" in props


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
async def test_knowledge_provider_context_manager():
    """Test that KnowledgeBaseToolProvider works as async context manager."""
    async with KnowledgeBaseToolProvider() as provider:
        assert provider is not None
        assert provider.provider_name == "knowledge"

        # Should be able to create schemas
        schemas = provider.create_tool_schemas()
        assert len(schemas) == 4  # search, ingest, get_all_fragments, get_related_fragments


class TestKnowledgeProviderProperties:
    """Test KnowledgeBaseToolProvider properties."""

    def test_requires_redis_instance_is_false(self):
        """Test that requires_redis_instance returns False."""
        provider = KnowledgeBaseToolProvider()
        assert provider.requires_redis_instance is False

    def test_provider_name_is_knowledge(self):
        """Test provider_name is 'knowledge'."""
        provider = KnowledgeBaseToolProvider()
        assert provider.provider_name == "knowledge"

    def test_redis_instance_is_none_by_default(self):
        """Test redis_instance is None by default."""
        provider = KnowledgeBaseToolProvider()
        assert provider.redis_instance is None

    def test_config_is_none_by_default(self):
        """Test config is None by default."""
        provider = KnowledgeBaseToolProvider()
        assert provider.config is None


class TestKnowledgeProviderGetAllFragmentsSchema:
    """Test get_all_fragments tool schema."""

    def test_get_all_fragments_schema_exists(self):
        """Test get_all_fragments tool schema exists."""
        provider = KnowledgeBaseToolProvider()
        schemas = provider.create_tool_schemas()

        fragment_schemas = [s for s in schemas if "get_all_fragments" in s.name]
        assert len(fragment_schemas) == 1

    def test_get_all_fragments_has_required_params(self):
        """Test get_all_fragments has required parameters."""
        provider = KnowledgeBaseToolProvider()
        schemas = provider.create_tool_schemas()

        schema = next(s for s in schemas if "get_all_fragments" in s.name)
        assert "document_hash" in schema.parameters["required"]


class TestKnowledgeProviderGetRelatedFragmentsSchema:
    """Test get_related_fragments tool schema."""

    def test_get_related_fragments_schema_exists(self):
        """Test get_related_fragments tool schema exists."""
        provider = KnowledgeBaseToolProvider()
        schemas = provider.create_tool_schemas()

        related_schemas = [s for s in schemas if "get_related_fragments" in s.name]
        assert len(related_schemas) == 1

    def test_get_related_fragments_has_required_params(self):
        """Test get_related_fragments has required parameters."""
        provider = KnowledgeBaseToolProvider()
        schemas = provider.create_tool_schemas()

        schema = next(s for s in schemas if "get_related_fragments" in s.name)
        assert "document_hash" in schema.parameters["required"]
        assert "chunk_index" in schema.parameters["required"]


class TestKnowledgeProviderToolCapabilities:
    """Test knowledge tool capabilities."""

    def test_all_tools_have_knowledge_capability(self):
        """Test all tools have KNOWLEDGE capability."""
        provider = KnowledgeBaseToolProvider()
        schemas = provider.create_tool_schemas()

        for schema in schemas:
            assert schema.capability == ToolCapability.KNOWLEDGE

    def test_tool_count_is_four(self):
        """Test there are exactly 4 tools."""
        provider = KnowledgeBaseToolProvider()
        schemas = provider.create_tool_schemas()
        assert len(schemas) == 4
