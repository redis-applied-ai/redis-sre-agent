"""Tests for ingestion processor."""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from redis_sre_agent.pipelines.ingestion.processor import DocumentProcessor, IngestionPipeline
from redis_sre_agent.pipelines.scraper.base import (
    ArtifactStorage,
    DocumentCategory,
    DocumentType,
    ScrapedDocument,
    SeverityLevel,
)


class TestDocumentProcessor:
    """Test document processing functionality."""

    @pytest.fixture
    def processor(self):
        """Create document processor with test configuration."""
        config = {
            "chunk_size": 500,
            "chunk_overlap": 100,
            "min_chunk_size": 50,
            "max_chunks_per_doc": 5,
        }
        return DocumentProcessor(config)

    @pytest.fixture
    def sample_document(self):
        """Create sample document for testing."""
        return ScrapedDocument(
            title="Redis Performance Optimization Guide",
            content="This is a comprehensive guide to Redis performance optimization. " * 50,
            source_url="https://redis.io/docs/performance",
            category=DocumentCategory.OSS,
            doc_type=DocumentType.DOCUMENTATION,
            severity=SeverityLevel.HIGH,
            metadata={"author": "Redis Team", "version": "1.0"},
        )

    def test_init_with_default_config(self):
        """Test processor initialization with default configuration."""
        processor = DocumentProcessor()

        assert processor.config["chunk_size"] == 1000
        assert processor.config["chunk_overlap"] == 200
        assert processor.config["min_chunk_size"] == 100
        assert processor.config["max_chunks_per_doc"] == 10

    def test_init_with_custom_config(self, processor):
        """Test processor initialization with custom configuration."""
        assert processor.config["chunk_size"] == 500
        assert processor.config["chunk_overlap"] == 100
        assert processor.config["min_chunk_size"] == 50
        assert processor.config["max_chunks_per_doc"] == 5

    def test_chunk_small_document(self, processor):
        """Test chunking a document smaller than chunk size."""
        small_doc = ScrapedDocument(
            title="Small Doc",
            content="This is a small document.",
            source_url="https://test.com",
            category=DocumentCategory.OSS,
            doc_type=DocumentType.DOCUMENTATION,
            severity=SeverityLevel.MEDIUM,
        )

        chunks = processor.chunk_document(small_doc)

        assert len(chunks) == 1
        chunk = chunks[0]

        assert chunk["title"] == "Small Doc"
        assert chunk["content"] == "This is a small document."
        assert chunk["chunk_index"] == 0
        assert chunk["category"] == "oss"
        assert chunk["doc_type"] == "documentation"
        assert chunk["severity"] == "medium"

    def test_chunk_large_document(self, processor, sample_document):
        """Test chunking a large document into multiple chunks."""
        chunks = processor.chunk_document(sample_document)

        # Should create multiple chunks
        assert len(chunks) > 1
        assert len(chunks) <= processor.config["max_chunks_per_doc"]

        # Check first chunk
        first_chunk = chunks[0]
        assert first_chunk["title"] == "Redis Performance Optimization Guide"
        assert first_chunk["chunk_index"] == 0
        assert "id" in first_chunk
        assert len(first_chunk["id"]) > 0  # ULID should be generated

        # Check subsequent chunk
        if len(chunks) > 1:
            second_chunk = chunks[1]
            assert second_chunk["title"] == "Redis Performance Optimization Guide (Part 2)"
            assert second_chunk["chunk_index"] == 1
            assert first_chunk["id"] != second_chunk["id"]  # Different IDs

    def test_chunk_document_respects_max_chunks(self, processor):
        """Test that chunking respects maximum chunks limit."""
        # Create a very long document that would exceed max chunks
        very_long_content = "This is a very long document. " * 1000  # ~30KB
        long_doc = ScrapedDocument(
            title="Very Long Doc",
            content=very_long_content,
            source_url="https://test.com",
            category=DocumentCategory.OSS,
            doc_type=DocumentType.DOCUMENTATION,
            severity=SeverityLevel.MEDIUM,
        )

        chunks = processor.chunk_document(long_doc)

        # Should not exceed max chunks
        assert len(chunks) <= processor.config["max_chunks_per_doc"]

    def test_chunk_document_respects_min_size(self, processor):
        """Test that chunks respect minimum size requirement."""
        # Create document with content that would create tiny chunks
        content_with_breaks = "Short. " * 200  # Many sentence breaks
        doc = ScrapedDocument(
            title="Fragmented Doc",
            content=content_with_breaks,
            source_url="https://test.com",
            category=DocumentCategory.OSS,
            doc_type=DocumentType.DOCUMENTATION,
            severity=SeverityLevel.MEDIUM,
        )

        chunks = processor.chunk_document(doc)

        # All chunks should meet minimum size
        for chunk in chunks:
            assert len(chunk["content"]) >= processor.config["min_chunk_size"]

    def test_create_chunk_structure(self, processor, sample_document):
        """Test chunk creation has correct structure."""
        chunk = processor._create_chunk(sample_document, "Test content", 0)

        required_fields = [
            "id",
            "document_hash",
            "title",
            "content",
            "source",
            "category",
            "doc_type",
            "severity",
            "chunk_index",
            "metadata",
        ]

        for field in required_fields:
            assert field in chunk

        assert chunk["content"] == "Test content"
        assert chunk["chunk_index"] == 0
        assert chunk["category"] == "oss"
        assert chunk["source"] == sample_document.source_url
        assert "processed_at" in chunk["metadata"]
        assert chunk["metadata"]["original_title"] == sample_document.title

    def test_chunk_boundary_detection(self, processor):
        """Test that chunking finds good boundary points."""
        # Create content with clear sentence boundaries
        content = (
            "First sentence about Redis configuration. "
            "Second sentence covers memory management in detail. "
            "Third sentence explains replication setup. "
            "Fourth sentence discusses performance monitoring. "
        ) * 10  # Repeat to make it long enough for chunking

        doc = ScrapedDocument(
            title="Test Doc",
            content=content,
            source_url="https://test.com",
            category=DocumentCategory.OSS,
            doc_type=DocumentType.DOCUMENTATION,
            severity=SeverityLevel.MEDIUM,
        )

        chunks = processor.chunk_document(doc)

        if len(chunks) > 1:
            # Check that chunks end at reasonable boundaries
            first_chunk_content = chunks[0]["content"]

            # Should end with sentence boundary or word boundary
            assert (
                first_chunk_content.endswith(".")
                or first_chunk_content.endswith(" ")
                or not first_chunk_content.endswith(content[-1])
            )


class TestIngestionPipeline:
    """Test ingestion pipeline functionality."""

    @pytest.fixture
    def storage(self, tmp_path):
        """Create test storage."""
        return ArtifactStorage(tmp_path)

    @pytest.fixture
    def pipeline(self, storage):
        """Create ingestion pipeline instance."""
        config = {"chunk_size": 300, "min_chunk_size": 50}
        return IngestionPipeline(storage, config)

    @pytest.fixture
    def mock_redis_components(self):
        """Mock Redis components for testing."""
        mock_index = AsyncMock()
        mock_vectorizer = AsyncMock()

        # Set up proper Redis client mock for the index
        mock_redis_client = AsyncMock()

        # Mock scan_iter to return an async iterator instead of a coroutine
        def mock_scan_iter(match=None):
            # Return empty async iterator - no existing keys to deduplicate
            async def empty_async_iter():
                if False:  # Never executes, but makes this an async generator
                    yield

            return empty_async_iter()

        # Mock hgetall to return a proper dict instead of a coroutine
        async def mock_hgetall(key):
            return {}  # Return empty dict for document metadata

        # Mock delete operation
        async def mock_delete(*keys):
            return len(keys)  # Return number of keys deleted

        # Mock hset operation for metadata
        async def mock_hset(key, mapping=None):
            return 1  # Return success

        mock_redis_client.scan_iter = mock_scan_iter
        mock_redis_client.hgetall = mock_hgetall
        mock_redis_client.delete = mock_delete
        mock_redis_client.hset = mock_hset

        # Set the client attribute on the mock index
        mock_index.client = mock_redis_client

        # Dynamic embeddings based on input size
        async def mock_embed_many(texts, as_buffer=False):
            if as_buffer:
                return [b"\x01\x02\x03" for _ in texts]
            return [[0.1, 0.2, 0.3] for _ in texts]

        def mock_embed(text, as_buffer=False):
            if as_buffer:
                return b"\x01\x02\x03"  # Mock binary embedding
            return [0.1, 0.2, 0.3]

        mock_vectorizer.aembed_many = AsyncMock(side_effect=mock_embed_many)
        mock_vectorizer.aembed = AsyncMock(side_effect=mock_embed)
        # Keep sync-compatible mocks in case other code uses them
        mock_vectorizer.embed_many = AsyncMock(side_effect=mock_embed_many)
        mock_vectorizer.embed = mock_embed

        with patch(
            "redis_sre_agent.pipelines.ingestion.processor.get_knowledge_index"
        ) as mock_get_index:
            with patch(
                "redis_sre_agent.pipelines.ingestion.processor.get_skills_index"
            ) as mock_get_skills_index:
                with patch(
                    "redis_sre_agent.pipelines.ingestion.processor.get_support_tickets_index"
                ) as mock_get_support_tickets_index:
                    with patch(
                        "redis_sre_agent.pipelines.ingestion.processor.get_vectorizer"
                    ) as mock_get_vectorizer:
                        mock_get_index.return_value = mock_index
                        mock_get_skills_index.return_value = mock_index
                        mock_get_support_tickets_index.return_value = mock_index
                        mock_get_vectorizer.return_value = mock_vectorizer

                        yield mock_index, mock_vectorizer

    def test_init(self, pipeline, storage):
        """Test pipeline initialization."""
        assert pipeline.storage == storage
        assert isinstance(pipeline.processor, DocumentProcessor)
        assert pipeline.processor.config["chunk_size"] == 300
        assert pipeline.processor.config["min_chunk_size"] == 50

    def test_create_scraped_document_from_markdown_uses_doc_type_frontmatter_key(
        self, pipeline, tmp_path
    ):
        """Test canonical doc_type front matter key is used for document type."""
        md_file = tmp_path / "test-doc.md"
        md_file.write_text(
            (
                "---\n"
                'title: "Front Matter Title"\n'
                "category: shared\n"
                "severity: high\n"
                "doc_type: support_ticket\n"
                "---\n\n"
                "# Body Heading\n\n"
                "Some content.\n"
            ),
            encoding="utf-8",
        )

        document = pipeline._create_scraped_document_from_markdown(md_file)

        assert document.title == "Front Matter Title"
        assert document.doc_type == DocumentType.SUPPORT_TICKET
        assert document.metadata["original_doc_type"] == "support_ticket"
        assert document.metadata["doc_type"] == "support_ticket"

    def test_create_scraped_document_from_markdown_applies_adr_defaults(self, pipeline, tmp_path):
        """Test ADR metadata defaults for source docs without frontmatter."""
        md_file = tmp_path / "no-frontmatter.md"
        md_file.write_text("# Test Title\n\nSome content.\n", encoding="utf-8")

        document = pipeline._create_scraped_document_from_markdown(md_file)

        assert document.doc_type == DocumentType.KNOWLEDGE
        assert document.metadata["doc_type"] == "knowledge"
        assert document.metadata["priority"] == "normal"
        assert document.metadata["pinned"] is False
        assert document.metadata["name"] == "no-frontmatter"
        assert document.metadata["summary"] is None

    def test_create_scraped_document_from_markdown_tracks_source_document_identity(
        self, pipeline, tmp_path
    ):
        """Source docs should carry a stable path relative to source_documents root."""
        source_root = tmp_path / "source_documents"
        source_dir = source_root / "shared"
        source_dir.mkdir(parents=True)
        md_file = source_dir / "nested" / "tracked.md"
        md_file.parent.mkdir(parents=True)
        md_file.write_text("# Tracked\n\nSome content.\n", encoding="utf-8")

        document = pipeline._create_scraped_document_from_markdown(md_file, source_dir)

        assert document.metadata["source_document_path"] == "shared/nested/tracked.md"
        assert document.metadata["source_document_scope"] == "shared/"

    @pytest.mark.asyncio
    async def test_prepare_source_artifacts_preserves_source_document_identity(
        self, pipeline, tmp_path
    ):
        """Prepared artifacts should keep the stable source path metadata."""
        source_root = tmp_path / "source_documents"
        md_file = source_root / "shared" / "nested" / "tracked.md"
        md_file.parent.mkdir(parents=True)
        md_file.write_text("# Tracked\n\nSome content.\n", encoding="utf-8")

        saved_documents = []

        with (
            patch.object(
                pipeline.storage,
                "save_document",
                side_effect=lambda document: saved_documents.append(document),
            ),
            patch.object(pipeline.storage, "save_batch_manifest") as mock_save_manifest,
        ):
            prepared_count = await pipeline.prepare_source_artifacts(
                source_root,
                "2025-01-20",
            )

        assert prepared_count == 1
        assert len(saved_documents) == 1
        assert saved_documents[0].metadata["source_document_path"] == "shared/nested/tracked.md"
        assert saved_documents[0].metadata["source_document_scope"] == ""
        mock_save_manifest.assert_called_once_with(saved_documents)

    def test_create_scraped_document_from_markdown_parses_adr_frontmatter_fields(
        self, pipeline, tmp_path
    ):
        """Test pinned/priority/name/summary frontmatter fields are preserved."""
        md_file = tmp_path / "with-frontmatter.md"
        md_file.write_text(
            (
                "---\n"
                "doc_type: support_ticket\n"
                "priority: critical\n"
                "pinned: true\n"
                "name: Incident Triage\n"
                "summary: Step-by-step triage process.\n"
                "---\n\n"
                "# Test Title\n"
            ),
            encoding="utf-8",
        )

        document = pipeline._create_scraped_document_from_markdown(md_file)

        assert document.doc_type == DocumentType.SUPPORT_TICKET
        assert document.metadata["doc_type"] == "support_ticket"
        assert document.metadata["priority"] == "critical"
        assert document.metadata["pinned"] is True
        assert document.metadata["name"] == "Incident Triage"
        assert document.metadata["summary"] == "Step-by-step triage process."

    def test_create_scraped_document_from_markdown_reserved_metadata_cannot_be_overridden(
        self, pipeline, tmp_path
    ):
        """Computed ingestion metadata should not be overridden by frontmatter."""
        md_file = tmp_path / "reserved-keys.md"
        md_file.write_text(
            (
                "---\n"
                "doc_type: support_ticket\n"
                "file_path: injected-path\n"
                "file_size: 1\n"
                "original_category: injected-category\n"
                "original_severity: injected-severity\n"
                "original_doc_type: injected-doc-type\n"
                "determined_category: injected-determined-category\n"
                "source_document_path: injected-source-path\n"
                "source_document_scope: injected-source-scope\n"
                "---\n\n"
                "# Test Title\n"
            ),
            encoding="utf-8",
        )

        document = pipeline._create_scraped_document_from_markdown(md_file)

        assert document.metadata["file_path"] == str(md_file)
        assert document.metadata["file_size"] == md_file.stat().st_size
        assert document.metadata["original_category"] == "shared"
        assert document.metadata["original_severity"] == "normal"
        assert document.metadata["original_doc_type"] == "support_ticket"
        assert document.metadata["determined_category"] == "shared"
        assert document.metadata["source_document_path"] == ""
        assert document.metadata["source_document_scope"] == ""

    def test_parse_markdown_metadata_normalizes_spaced_keys(self, pipeline):
        """Test metadata keys with spaces normalize to snake_case."""
        content = "---\npriority level: high\n---\n\n# Test Title\n**Doc Type**: skill\n"

        metadata = pipeline._parse_markdown_metadata(content)

        assert metadata["priority_level"] == "high"
        assert metadata["doc_type"] == "skill"
        assert metadata["title"] == "Test Title"

    def test_parse_markdown_metadata_frontmatter_takes_precedence(self, pipeline):
        """Frontmatter values should not be overridden by body metadata lines."""
        content = (
            "---\n"
            "priority: critical\n"
            "doc_type: skill\n"
            "---\n\n"
            "# Test Title\n"
            "**Priority**: low\n"
            "**Doc Type**: support_ticket\n"
        )

        metadata = pipeline._parse_markdown_metadata(content)

        assert metadata["priority"] == "critical"
        assert metadata["doc_type"] == "skill"

    @pytest.mark.asyncio
    async def test_ingest_batch_missing_manifest(self, pipeline):
        """Test ingestion fails gracefully with missing manifest."""
        batch_date = "2025-01-20"

        with pytest.raises(ValueError, match="No manifest found"):
            await pipeline.ingest_batch(batch_date)

    @pytest.mark.asyncio
    async def test_ingest_batch_missing_directory(self, pipeline, tmp_path):
        """Test ingestion fails gracefully with missing batch directory."""
        batch_date = "2025-01-20"

        # Create manifest but no directory
        manifest = {"batch_date": batch_date, "documents": []}
        manifest_path = tmp_path / f"{batch_date}_manifest.json"
        with open(manifest_path, "w") as f:
            json.dump(manifest, f)

        with patch.object(pipeline.storage, "get_batch_manifest") as mock_get_manifest:
            mock_get_manifest.return_value = manifest

            with pytest.raises(ValueError, match="Batch directory not found"):
                await pipeline.ingest_batch(batch_date)

    @pytest.mark.asyncio
    async def test_ingest_batch_success(self, pipeline, tmp_path, mock_redis_components):
        """Test successful batch ingestion."""
        mock_index, mock_vectorizer = mock_redis_components

        batch_date = "2025-01-20"
        batch_path = tmp_path / batch_date
        batch_path.mkdir()

        # Create category directories and sample documents
        categories = ["oss", "enterprise", "shared"]
        for category in categories:
            category_path = batch_path / category
            category_path.mkdir()

            # Create sample document
            doc_data = {
                "title": f"Test {category} Document",
                "content": f"This is test content for {category} category. " * 10,
                "source_url": f"https://test.com/{category}",
                "category": category,
                "doc_type": "documentation",
                "severity": "medium",
                "metadata": {"test": True},
            }

            doc_path = category_path / f"doc_{category}.json"
            with open(doc_path, "w") as f:
                json.dump(doc_data, f)

        # Create manifest
        manifest = {
            "batch_date": batch_date,
            "documents": [{"category": cat} for cat in categories],
        }

        with patch.object(pipeline.storage, "get_batch_manifest") as mock_get_manifest:
            mock_get_manifest.return_value = manifest

            with patch.object(pipeline, "_save_ingestion_manifest") as mock_save_manifest:
                result = await pipeline.ingest_batch(batch_date)

        assert result["success"] is True
        assert result["batch_date"] == batch_date
        assert result["documents_processed"] == 3  # One per category
        assert result["chunks_created"] > 0
        assert result["chunks_indexed"] > 0
        assert len(result["categories_processed"]) == 3

        # Verify Redis components were called
        mock_index.load.assert_called()
        mock_save_manifest.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_category_success(self, pipeline, tmp_path, mock_redis_components):
        """Test successful category processing."""
        mock_index, mock_vectorizer = mock_redis_components

        category = "oss"
        category_path = tmp_path / category
        category_path.mkdir()

        # Create multiple test documents
        for i in range(3):
            doc_data = {
                "title": f"Test Document {i}",
                "content": f"Content for document {i}. " * 20,
                "source_url": f"https://test.com/doc{i}",
                "category": category,
                "doc_type": "documentation",
                "severity": "medium",
                "metadata": {},
            }

            doc_path = category_path / f"doc_{i}.json"
            with open(doc_path, "w") as f:
                json.dump(doc_data, f)

        mock_deduplicator = AsyncMock()
        mock_deduplicator.replace_document_chunks.return_value = (
            3  # Return number of chunks indexed
        )

        result = await pipeline._process_category(
            category_path,
            category,
            mock_vectorizer,
            {"knowledge": mock_deduplicator},
        )

        assert result["category"] == category
        assert result["documents_processed"] == 3
        assert result["chunks_created"] > 0
        assert result["chunks_indexed"] > 0
        assert len(result["errors"]) == 0

    @pytest.mark.asyncio
    async def test_process_category_uses_source_document_path_tracking(self, pipeline, tmp_path):
        """Source-document artifacts should route through path-based replacement."""
        category_path = tmp_path / "shared"
        category_path.mkdir()

        doc_data = {
            "title": "Tracked Source Document",
            "content": "Tracked content. " * 20,
            "source_url": "file:///tmp/source_documents/shared/tracked.md",
            "category": "shared",
            "doc_type": "knowledge",
            "severity": "medium",
            "metadata": {
                "source_document_path": "shared/tracked.md",
                "source_document_scope": "",
            },
        }

        with open(category_path / "tracked.json", "w") as f:
            json.dump(doc_data, f)

        mock_deduplicator = AsyncMock()
        mock_deduplicator.replace_source_document_chunks.return_value = {
            "action": "update",
            "indexed_count": 2,
        }

        result = await pipeline._process_category(
            category_path,
            "shared",
            MagicMock(),
            {"knowledge": mock_deduplicator},
            tracked_source_documents={
                "shared/tracked.md": [
                    {"deduplicator_key": "knowledge", "document_hash": "old-hash"}
                ]
            },
        )

        mock_deduplicator.replace_source_document_chunks.assert_awaited_once()
        assert result["source_document_changes"] == [
            {
                "path": "shared/tracked.md",
                "action": "update",
                "title": "Tracked Source Document",
                "doc_type": "knowledge",
            }
        ]

    @pytest.mark.asyncio
    async def test_process_category_deletes_cross_index_source_document_before_replacing(
        self, pipeline, tmp_path
    ):
        """Changing doc_type should remove the old indexed copy before re-indexing."""
        category_path = tmp_path / "shared"
        category_path.mkdir()

        doc_data = {
            "title": "Moved Source Document",
            "content": "Tracked content. " * 20,
            "source_url": "file:///tmp/source_documents/shared/moved.md",
            "category": "shared",
            "doc_type": "skill",
            "severity": "medium",
            "metadata": {
                "source_document_path": "shared/moved.md",
                "source_document_scope": "",
            },
        }

        with open(category_path / "moved.json", "w") as f:
            json.dump(doc_data, f)

        knowledge_deduplicator = AsyncMock()
        skill_deduplicator = AsyncMock()
        skill_deduplicator.replace_source_document_chunks.return_value = {
            "action": "add",
            "indexed_count": 1,
        }

        result = await pipeline._process_category(
            category_path,
            "shared",
            MagicMock(),
            {"knowledge": knowledge_deduplicator, "skill": skill_deduplicator},
            tracked_source_documents={
                "shared/moved.md": [
                    {"deduplicator_key": "knowledge", "document_hash": "old-knowledge-hash"}
                ]
            },
        )

        knowledge_deduplicator.delete_tracked_source_document.assert_awaited_once_with(
            "old-knowledge-hash", "shared/moved.md"
        )
        skill_deduplicator.replace_source_document_chunks.assert_awaited_once()
        assert result["source_document_changes"][0]["action"] == "update"

    @pytest.mark.asyncio
    async def test_process_category_with_errors(self, pipeline, tmp_path, mock_redis_components):
        """Test category processing handles document errors gracefully."""
        mock_index, mock_vectorizer = mock_redis_components

        category = "oss"
        category_path = tmp_path / category
        category_path.mkdir()

        # Create valid document
        valid_doc = {
            "title": "Valid Document",
            "content": "Valid content",
            "source_url": "https://test.com/valid",
            "category": category,
            "doc_type": "documentation",
            "severity": "medium",
            "metadata": {},
        }

        with open(category_path / "valid_doc.json", "w") as f:
            json.dump(valid_doc, f)

        # Create invalid document (missing required fields)
        with open(category_path / "invalid_doc.json", "w") as f:
            json.dump({"incomplete": "data"}, f)

        mock_deduplicator = AsyncMock()
        mock_deduplicator.replace_document_chunks.return_value = (
            1  # Return number of chunks indexed
        )

        result = await pipeline._process_category(
            category_path,
            category,
            mock_vectorizer,
            {"knowledge": mock_deduplicator},
        )

        assert result["documents_processed"] == 1  # Only valid document
        assert len(result["errors"]) == 1  # One error for invalid document
        assert "invalid_doc.json" in result["errors"][0]

    @pytest.mark.asyncio
    async def test_index_chunks_success(self, pipeline, mock_redis_components):
        """Test successful chunk indexing."""
        mock_index, mock_vectorizer = mock_redis_components

        chunks = [
            {
                "id": "chunk_1",
                "content": "First chunk content",
                "title": "Test Doc",
                "source": "https://test.com",
            },
            {
                "id": "chunk_2",
                "content": "Second chunk content",
                "title": "Test Doc",
                "source": "https://test.com",
            },
        ]

        result = await pipeline._index_chunks(chunks, mock_index, mock_vectorizer)

        assert result == 2  # Two chunks indexed

        # Verify embeddings were generated
        mock_vectorizer.aembed_many.assert_called_once_with(
            ["First chunk content", "Second chunk content"]
        )

        # Verify index.load was called with correct parameters
        mock_index.load.assert_called_once()
        call_args = mock_index.load.call_args

        from redis_sre_agent.core.keys import RedisKeys

        assert call_args[1]["id_field"] == "id"
        assert len(call_args[1]["keys"]) == 2
        assert all(key.startswith(RedisKeys.PREFIX_KNOWLEDGE + ":") for key in call_args[1]["keys"])

        # Check that embeddings were added to documents
        indexed_docs = call_args[1]["data"]
        assert len(indexed_docs) == 2
        assert all("vector" in doc for doc in indexed_docs)
        assert all("created_at" in doc for doc in indexed_docs)

    @pytest.mark.asyncio
    async def test_index_chunks_empty_list(self, pipeline, mock_redis_components):
        """Test indexing with empty chunk list."""
        mock_index, mock_vectorizer = mock_redis_components

        result = await pipeline._index_chunks([], mock_index, mock_vectorizer)

        assert result == 0
        mock_vectorizer.aembed_many.assert_not_called()
        mock_index.load.assert_not_called()

    @pytest.mark.asyncio
    async def test_save_ingestion_manifest(self, pipeline, tmp_path):
        """Test ingestion manifest saving."""
        batch_date = "2025-01-20"
        batch_path = tmp_path / batch_date
        batch_path.mkdir()

        stats = {
            "batch_date": batch_date,
            "documents_processed": 10,
            "chunks_indexed": 25,
            "success": True,
            "started_at": datetime.now(timezone.utc).isoformat(),
        }

        await pipeline._save_ingestion_manifest(batch_date, stats)

        manifest_path = batch_path / "ingestion_manifest.json"
        assert manifest_path.exists()

        with open(manifest_path) as f:
            saved_stats = json.load(f)

        assert saved_stats == stats

    @pytest.mark.asyncio
    async def test_list_ingested_batches(self, pipeline, tmp_path):
        """Test listing ingested batches."""
        # Create batch directories with manifests
        batch_dates = ["2025-01-20", "2025-01-19", "2025-01-18"]

        for i, batch_date in enumerate(batch_dates):
            batch_path = tmp_path / batch_date
            batch_path.mkdir()

            if i < 2:  # First two batches have ingestion manifests
                manifest = {
                    "batch_date": batch_date,
                    "success": i == 0,  # First batch successful, second failed
                    "documents_processed": 5 if i == 0 else 0,
                }

                manifest_path = batch_path / "ingestion_manifest.json"
                with open(manifest_path, "w") as f:
                    json.dump(manifest, f)

        with patch.object(pipeline.storage, "list_available_batches") as mock_list:
            mock_list.return_value = batch_dates

            batches = await pipeline.list_ingested_batches()

        assert len(batches) == 3

        # Check sorting (most recent first)
        assert batches[0]["batch_date"] == "2025-01-20"
        assert batches[-1]["batch_date"] == "2025-01-18"

        # Check ingestion status
        assert batches[0]["success"] is True  # First batch succeeded
        assert batches[1]["success"] is False  # Second batch failed
        assert batches[2]["ingested"] is False  # Third batch not ingested

    @pytest.mark.asyncio
    async def test_reindex_batch(self, pipeline):
        """Test batch re-indexing."""
        batch_date = "2025-01-20"

        with patch.object(pipeline, "ingest_batch") as mock_ingest:
            mock_result = {"success": True, "batch_date": batch_date}
            mock_ingest.return_value = mock_result

            result = await pipeline.reindex_batch(batch_date)

        assert result == mock_result
        mock_ingest.assert_called_once_with(batch_date)

    @pytest.mark.asyncio
    async def test_ingest_batch_ignores_empty_scope_from_non_source_documents(
        self, pipeline, tmp_path
    ):
        """Non-source docs must not widen stale-source cleanup scope."""
        batch_date = "2025-01-20"
        batch_path = tmp_path / batch_date
        shared_path = batch_path / "shared"
        shared_path.mkdir(parents=True)

        doc_data = {
            "title": "Regular Batch Document",
            "content": "Regular content. " * 20,
            "source_url": "https://example.com/regular-doc",
            "category": "shared",
            "doc_type": "knowledge",
            "severity": "medium",
            "metadata": {},
        }
        with open(shared_path / "regular.json", "w") as f:
            json.dump(doc_data, f)

        manifest = {"batch_date": batch_date, "documents": [{"category": "shared"}]}
        knowledge_deduplicator = AsyncMock()
        knowledge_deduplicator.replace_document_chunks.return_value = 1

        with patch.object(pipeline.storage, "get_batch_manifest", return_value=manifest):
            with patch.object(
                pipeline, "_build_deduplicators", return_value={"knowledge": knowledge_deduplicator}
            ):
                with patch(
                    "redis_sre_agent.pipelines.ingestion.processor.get_vectorizer",
                    return_value=MagicMock(),
                ):
                    with patch.object(
                        pipeline,
                        "_list_tracked_source_documents",
                        return_value={
                            "shared/tracked.md": [
                                {
                                    "deduplicator_key": "knowledge",
                                    "document_hash": "tracked-hash",
                                    "title": "Tracked Doc",
                                    "doc_type": "knowledge",
                                }
                            ]
                        },
                    ):
                        with patch.object(pipeline, "_save_ingestion_manifest") as mock_save:
                            result = await pipeline.ingest_batch(batch_date)

        knowledge_deduplicator.delete_tracked_source_document.assert_not_awaited()
        assert result["source_document_changes"]["deleted"] == 0
        assert result["categories_processed"]["shared"]["source_document_scopes"] == []
        mock_save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_ingest_batch_keeps_failed_source_documents_out_of_stale_deletes(
        self, pipeline, tmp_path
    ):
        """Failed source-doc artifacts should not be deleted as if they were removed."""
        batch_date = "2025-01-20"
        batch_path = tmp_path / batch_date
        shared_path = batch_path / "shared"
        shared_path.mkdir(parents=True)

        current_doc = {
            "title": "Current Source Document",
            "content": "Current content. " * 20,
            "source_url": "file:///tmp/source_documents/shared/current.md",
            "category": "shared",
            "doc_type": "knowledge",
            "severity": "medium",
            "metadata": {
                "source_document_path": "shared/current.md",
                "source_document_scope": "",
            },
        }
        failed_doc = {
            "title": "Failed Source Document",
            "content": "Failed content. " * 20,
            "source_url": "file:///tmp/source_documents/shared/failed.md",
            "category": "shared",
            "doc_type": "knowledge",
            "severity": "medium",
            "metadata": {
                "source_document_path": "shared/failed.md",
                "source_document_scope": "",
            },
        }

        with open(shared_path / "current.json", "w") as f:
            json.dump(current_doc, f)
        with open(shared_path / "failed.json", "w") as f:
            json.dump(failed_doc, f)

        manifest = {"batch_date": batch_date, "documents": [{"category": "shared"}]}
        knowledge_deduplicator = AsyncMock()
        knowledge_deduplicator.replace_source_document_chunks.return_value = {
            "action": "update",
            "indexed_count": 1,
        }

        original_chunk_document = pipeline.processor.chunk_document

        def chunk_or_fail(document):
            if document.title == "Failed Source Document":
                raise RuntimeError("simulated failure")
            return original_chunk_document(document)

        with patch.object(pipeline.storage, "get_batch_manifest", return_value=manifest):
            with patch.object(
                pipeline, "_build_deduplicators", return_value={"knowledge": knowledge_deduplicator}
            ):
                with patch(
                    "redis_sre_agent.pipelines.ingestion.processor.get_vectorizer",
                    return_value=MagicMock(),
                ):
                    with patch.object(
                        pipeline,
                        "_list_tracked_source_documents",
                        return_value={
                            "shared/current.md": [
                                {
                                    "deduplicator_key": "knowledge",
                                    "document_hash": "current-hash",
                                    "title": "Current Source Document",
                                    "doc_type": "knowledge",
                                }
                            ],
                            "shared/failed.md": [
                                {
                                    "deduplicator_key": "knowledge",
                                    "document_hash": "failed-hash",
                                    "title": "Failed Source Document",
                                    "doc_type": "knowledge",
                                }
                            ],
                        },
                    ):
                        with patch.object(
                            pipeline.processor,
                            "chunk_document",
                            side_effect=chunk_or_fail,
                        ):
                            with patch.object(pipeline, "_save_ingestion_manifest") as mock_save:
                                result = await pipeline.ingest_batch(batch_date)

        knowledge_deduplicator.delete_tracked_source_document.assert_not_awaited()
        assert result["source_document_changes"]["deleted"] == 0
        assert any("failed.json" in error for error in result["errors"])
        assert {change["path"] for change in result["source_document_changes"]["files"]} == {
            "shared/current.md"
        }
        mock_save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_ingest_batch_reports_deleted_source_documents(self, pipeline, tmp_path):
        """Prepared source batches should report files removed from the current scope."""
        batch_date = "2025-01-20"
        batch_path = tmp_path / batch_date
        (batch_path / "shared").mkdir(parents=True)

        manifest = {"batch_date": batch_date, "documents": [{"category": "shared"}]}
        knowledge_deduplicator = AsyncMock()

        with patch.object(pipeline.storage, "get_batch_manifest", return_value=manifest):
            with patch.object(
                pipeline, "_build_deduplicators", return_value={"knowledge": knowledge_deduplicator}
            ):
                with patch(
                    "redis_sre_agent.pipelines.ingestion.processor.get_vectorizer",
                    return_value=MagicMock(),
                ):
                    with patch.object(
                        pipeline,
                        "_list_tracked_source_documents",
                        return_value={
                            "shared/current.md": [
                                {"deduplicator_key": "knowledge", "document_hash": "current-hash"}
                            ],
                            "shared/deleted.md": [
                                {
                                    "deduplicator_key": "knowledge",
                                    "document_hash": "deleted-hash",
                                    "title": "Deleted Doc",
                                    "doc_type": "knowledge",
                                }
                            ],
                        },
                    ):
                        with patch.object(
                            pipeline,
                            "_process_category",
                            return_value={
                                "category": "shared",
                                "documents_processed": 1,
                                "chunks_created": 2,
                                "chunks_indexed": 2,
                                "source_document_changes": [
                                    {
                                        "path": "shared/current.md",
                                        "action": "update",
                                        "title": "Current Doc",
                                        "doc_type": "knowledge",
                                    }
                                ],
                                "source_document_paths": ["shared/current.md"],
                                "source_document_scopes": [""],
                                "errors": [],
                            },
                        ):
                            with patch.object(pipeline, "_save_ingestion_manifest") as mock_save:
                                result = await pipeline.ingest_batch(batch_date)

        knowledge_deduplicator.delete_tracked_source_document.assert_awaited_once_with(
            "deleted-hash", "shared/deleted.md"
        )
        assert result["source_document_changes"]["updated"] == 1
        assert result["source_document_changes"]["deleted"] == 1
        assert {change["path"] for change in result["source_document_changes"]["files"]} == {
            "shared/current.md",
            "shared/deleted.md",
        }
        mock_save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_ingest_source_documents_keeps_failed_files_out_of_stale_deletes(
        self, pipeline, tmp_path
    ):
        """A failed source markdown should not be treated as deleted from the source tree."""
        source_root = tmp_path / "source_documents"
        current_md = source_root / "shared" / "current.md"
        failed_md = source_root / "shared" / "failed.md"
        current_md.parent.mkdir(parents=True)
        current_md.write_text("# Current\n\nCurrent content.\n", encoding="utf-8")
        failed_md.write_text("# Failed\n\nFailed content.\n", encoding="utf-8")

        knowledge_deduplicator = AsyncMock()
        knowledge_deduplicator.replace_source_document_chunks.return_value = {
            "action": "update",
            "indexed_count": 1,
        }

        original_chunk_document = pipeline.processor.chunk_document

        def chunk_or_fail(document):
            if document.title == "Failed":
                raise RuntimeError("simulated failure")
            return original_chunk_document(document)

        with patch.object(
            pipeline, "_build_deduplicators", return_value={"knowledge": knowledge_deduplicator}
        ):
            with patch(
                "redis_sre_agent.pipelines.ingestion.processor.get_vectorizer",
                return_value=MagicMock(),
            ):
                with patch.object(
                    pipeline,
                    "_list_tracked_source_documents",
                    return_value={
                        "shared/current.md": [
                            {
                                "deduplicator_key": "knowledge",
                                "document_hash": "current-hash",
                                "title": "Current",
                                "doc_type": "knowledge",
                            }
                        ],
                        "shared/failed.md": [
                            {
                                "deduplicator_key": "knowledge",
                                "document_hash": "failed-hash",
                                "title": "Failed",
                                "doc_type": "knowledge",
                            }
                        ],
                    },
                ):
                    with patch.object(
                        pipeline.processor,
                        "chunk_document",
                        side_effect=chunk_or_fail,
                    ):
                        results = await pipeline.ingest_source_documents(source_root)

        knowledge_deduplicator.delete_tracked_source_document.assert_not_awaited()
        actions = {result["file"]: result["status"] for result in results}
        assert actions["shared/current.md"] == "success"
        assert actions["shared/failed.md"] == "error"
        assert "shared/failed.md" not in {
            result["file"] for result in results if result.get("action") == "delete"
        }
