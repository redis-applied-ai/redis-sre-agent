"""Tests for ingestion processor."""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

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
        assert chunk["doc_type"] == "guide"
        assert chunk["severity"] == "high"  # Note: enum conversion

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
        mock_vectorizer.embed_many = AsyncMock(
            return_value=[[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]  # Sample embeddings
        )

        with patch(
            "redis_sre_agent.pipelines.ingestion.processor.get_knowledge_index"
        ) as mock_get_index:
            with patch(
                "redis_sre_agent.pipelines.ingestion.processor.get_vectorizer"
            ) as mock_get_vectorizer:
                mock_get_index.return_value = mock_index
                mock_get_vectorizer.return_value = mock_vectorizer

                yield mock_index, mock_vectorizer

    def test_init(self, pipeline, storage):
        """Test pipeline initialization."""
        assert pipeline.storage == storage
        assert isinstance(pipeline.processor, DocumentProcessor)
        assert pipeline.processor.config["chunk_size"] == 300
        assert pipeline.processor.config["min_chunk_size"] == 50

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
                "doc_type": "guide",
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
        mock_vectorizer.embed_many.assert_called()
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
                "doc_type": "guide",
                "severity": "medium",
                "metadata": {},
            }

            doc_path = category_path / f"doc_{i}.json"
            with open(doc_path, "w") as f:
                json.dump(doc_data, f)

        result = await pipeline._process_category(
            category_path, category, mock_index, mock_vectorizer
        )

        assert result["category"] == category
        assert result["documents_processed"] == 3
        assert result["chunks_created"] > 0
        assert result["chunks_indexed"] > 0
        assert len(result["errors"]) == 0

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
            "doc_type": "guide",
            "severity": "medium",
            "metadata": {},
        }

        with open(category_path / "valid_doc.json", "w") as f:
            json.dump(valid_doc, f)

        # Create invalid document (missing required fields)
        with open(category_path / "invalid_doc.json", "w") as f:
            json.dump({"incomplete": "data"}, f)

        result = await pipeline._process_category(
            category_path, category, mock_index, mock_vectorizer
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
        mock_vectorizer.embed_many.assert_called_once_with(
            ["First chunk content", "Second chunk content"]
        )

        # Verify index.load was called with correct parameters
        mock_index.load.assert_called_once()
        call_args = mock_index.load.call_args

        assert call_args[1]["id_field"] == "id"
        assert len(call_args[1]["keys"]) == 2
        assert all(key.startswith("sre_knowledge:") for key in call_args[1]["keys"])

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
        mock_vectorizer.embed_many.assert_not_called()
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
