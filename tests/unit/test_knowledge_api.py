"""Unit tests for Knowledge API endpoints."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient


class TestKnowledgeStats:
    """Test knowledge stats endpoint."""

    @pytest.mark.asyncio
    async def test_knowledge_stats_success(self, test_client):
        """Test knowledge stats endpoint returns correct data."""
        mock_index = AsyncMock()
        mock_index.__aenter__ = AsyncMock(return_value=mock_index)
        mock_index.__aexit__ = AsyncMock(return_value=None)

        # Mock Redis client for FT.SEARCH and FT.AGGREGATE commands
        mock_redis_client = AsyncMock()
        mock_index.client = mock_redis_client

        # Mock FT.SEARCH response for total chunks (returns [count, ...])
        mock_redis_client.execute_command.side_effect = [
            [12],  # FT.SEARCH returns 12 total chunks
            [3]    # FT.AGGREGATE returns 3 unique documents
        ]

        with patch("redis_sre_agent.api.knowledge.get_knowledge_index", return_value=mock_index):
            response = test_client.get("/api/v1/knowledge/stats")

            assert response.status_code == 200
            data = response.json()

            # Verify the response structure
            assert "total_documents" in data
            assert "total_chunks" in data
            assert "storage_size_mb" in data
            assert "document_types" in data
            assert "ingestion_status" in data

            # Verify the calculated values
            assert data["total_documents"] == 3   # From FT.AGGREGATE unique document_hash count
            assert data["total_chunks"] == 12     # From FT.SEARCH total entries count
            assert data["storage_size_mb"] == 0.024  # 12 chunks * 0.002 MB per chunk

            # Verify Redis commands were called correctly
            calls = mock_redis_client.execute_command.call_args_list
            assert len(calls) == 2

            # First call: FT.SEARCH for total chunks
            assert calls[0][0] == ("FT.SEARCH", "sre_knowledge", "*", "LIMIT", "0", "0")

            # Second call: FT.AGGREGATE for unique documents
            assert calls[1][0] == ("FT.AGGREGATE", "sre_knowledge", "*", "GROUPBY", "1", "@document_hash", "REDUCE", "COUNT", "0", "AS", "count")

    @pytest.mark.asyncio
    async def test_knowledge_stats_empty_index(self, test_client):
        """Test knowledge stats endpoint with empty index."""
        mock_index = AsyncMock()
        mock_index.__aenter__ = AsyncMock(return_value=mock_index)
        mock_index.__aexit__ = AsyncMock(return_value=None)

        # Mock Redis client for empty index
        mock_redis_client = AsyncMock()
        mock_index.client = mock_redis_client

        # Mock FT.SEARCH and FT.AGGREGATE responses for empty index
        mock_redis_client.execute_command.side_effect = [
            [0],  # FT.SEARCH returns 0 total chunks
            [0]   # FT.AGGREGATE returns 0 unique documents
        ]

        with patch("redis_sre_agent.api.knowledge.get_knowledge_index", return_value=mock_index):
            response = test_client.get("/api/v1/knowledge/stats")

            assert response.status_code == 200
            data = response.json()

            assert data["total_documents"] == 0
            assert data["total_chunks"] == 0
            assert data["storage_size_mb"] == 0.0

    @pytest.mark.asyncio
    async def test_knowledge_stats_query_failure(self, test_client):
        """Test knowledge stats endpoint handles query failures gracefully."""
        mock_index = AsyncMock()
        mock_index.__aenter__ = AsyncMock(return_value=mock_index)
        mock_index.__aexit__ = AsyncMock(return_value=None)
        mock_index.query = AsyncMock(side_effect=Exception("Query failed"))
        
        with (
            patch("redis_sre_agent.api.knowledge.get_knowledge_index", return_value=mock_index),
            patch("redis_sre_agent.api.knowledge.FilterQuery") as mock_filter_query,
        ):
            mock_filter_query.return_value = MagicMock()
            
            response = test_client.get("/api/v1/knowledge/stats")
            
            assert response.status_code == 200
            data = response.json()
            
            # Should return default values when query fails
            assert data["total_documents"] == 0
            assert data["total_chunks"] == 0
            assert data["storage_size_mb"] == 0.0


class TestKnowledgeIngestion:
    """Test knowledge ingestion endpoint."""

    @pytest.mark.asyncio
    async def test_ingest_document_success(self, test_client):
        """Test successful document ingestion."""
        document_data = {
            "title": "Test Document",
            "content": "This is test content for Redis troubleshooting.",
            "source": "test",
            "category": "general",
            "severity": "info"
        }
        
        mock_doc_id = "test_doc_123"
        
        with patch("redis_sre_agent.api.knowledge.ingest_sre_document", new_callable=AsyncMock) as mock_ingest:
            mock_ingest.return_value = mock_doc_id
            
            response = test_client.post("/api/v1/knowledge/ingest/document", json=document_data)
            
            assert response.status_code == 200
            data = response.json()
            
            assert data["status"] == "success"
            assert data["document_id"] == mock_doc_id
            assert "message" in data
            
            # Verify the ingest function was called with correct parameters
            mock_ingest.assert_called_once()
            call_args = mock_ingest.call_args[1]  # Get keyword arguments
            assert call_args["title"] == document_data["title"]
            assert call_args["content"] == document_data["content"]
            assert call_args["source"] == document_data["source"]

    @pytest.mark.asyncio
    async def test_ingest_document_missing_fields(self, test_client):
        """Test document ingestion with missing required fields."""
        incomplete_data = {
            "title": "Test Document",
            # Missing content, source, category, severity
        }
        
        response = test_client.post("/api/v1/knowledge/ingest/document", json=incomplete_data)
        
        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_ingest_document_ingestion_failure(self, test_client):
        """Test document ingestion handles ingestion failures."""
        document_data = {
            "title": "Test Document",
            "content": "This is test content.",
            "source": "test",
            "category": "general",
            "severity": "info"
        }
        
        with patch("redis_sre_agent.api.knowledge.ingest_sre_document", new_callable=AsyncMock) as mock_ingest:
            mock_ingest.side_effect = Exception("Ingestion failed")
            
            response = test_client.post("/api/v1/knowledge/ingest/document", json=document_data)
            
            assert response.status_code == 500
            data = response.json()
            assert "error" in data


class TestKnowledgeSearch:
    """Test knowledge search endpoint."""

    @pytest.mark.asyncio
    async def test_search_success(self, test_client):
        """Test successful knowledge search."""
        mock_results = [
            MagicMock(
                title="Test Document 1",
                content="Redis troubleshooting content",
                source="test",
                score=0.95
            ),
            MagicMock(
                title="Test Document 2", 
                content="More Redis content",
                source="test",
                score=0.87
            )
        ]
        
        with patch("redis_sre_agent.api.knowledge.search_knowledge_base", new_callable=AsyncMock) as mock_search:
            mock_search.return_value = mock_results
            
            response = test_client.get("/api/v1/knowledge/search?query=redis&limit=5")
            
            assert response.status_code == 200
            data = response.json()
            
            assert "results" in data
            assert "results_count" in data
            assert data["results_count"] == 2
            assert len(data["results"]) == 2
            
            # Verify search was called with correct parameters
            mock_search.assert_called_once_with("redis", limit=5)

    @pytest.mark.asyncio
    async def test_search_empty_query(self, test_client):
        """Test search with empty query parameter."""
        response = test_client.get("/api/v1/knowledge/search?query=&limit=5")
        
        assert response.status_code == 400
        data = response.json()
        assert "error" in data

    @pytest.mark.asyncio
    async def test_search_no_results(self, test_client):
        """Test search that returns no results."""
        with patch("redis_sre_agent.api.knowledge.search_knowledge_base", new_callable=AsyncMock) as mock_search:
            mock_search.return_value = []
            
            response = test_client.get("/api/v1/knowledge/search?query=nonexistent&limit=5")
            
            assert response.status_code == 200
            data = response.json()
            
            assert data["results_count"] == 0
            assert data["results"] == []
