"""Unit tests for Knowledge API endpoints."""

from unittest.mock import AsyncMock, patch

import pytest


class TestKnowledgeStatsEdgeCases:
    """Test knowledge stats endpoint edge cases."""

    @pytest.mark.asyncio
    async def test_knowledge_stats_aggregation_error(self, test_client):
        """Test stats when aggregation fails but search succeeds."""
        mock_index = AsyncMock()
        mock_index.name = "sre_knowledge"
        mock_index.__aenter__ = AsyncMock(return_value=mock_index)
        mock_index.__aexit__ = AsyncMock(return_value=None)

        mock_redis_client = AsyncMock()
        mock_index.client = mock_redis_client

        # FT.SEARCH succeeds, FT.AGGREGATE fails
        mock_redis_client.execute_command.side_effect = [
            [10],  # FT.SEARCH returns 10 chunks
            Exception("Aggregation error"),  # FT.AGGREGATE fails
        ]

        with (
            patch("redis_sre_agent.core.redis.get_knowledge_index", return_value=mock_index),
            patch(
                "redis_sre_agent.core.redis.get_redis_client",
                new_callable=AsyncMock,
                return_value=mock_redis_client,
            ),
        ):
            response = test_client.get("/api/v1/knowledge/stats")

            assert response.status_code == 200
            data = response.json()
            # Should fallback to estimating documents from chunks
            assert data["total_chunks"] == 10
            assert data["total_documents"] > 0  # Estimated from chunks

    @pytest.mark.asyncio
    async def test_knowledge_stats_with_running_jobs(self, test_client):
        """Test stats when jobs are running."""
        from datetime import datetime, timezone

        from redis_sre_agent.api.knowledge import _active_jobs

        _active_jobs.clear()
        _active_jobs["running_job"] = {
            "job_id": "running_job",
            "operation": "scrape",
            "status": "running",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "started_at": datetime.now(timezone.utc).isoformat(),
            "completed_at": None,
            "progress": {},
            "results": None,
            "error": None,
        }

        mock_index = AsyncMock()
        mock_index.name = "sre_knowledge"
        mock_index.__aenter__ = AsyncMock(return_value=mock_index)
        mock_index.__aexit__ = AsyncMock(return_value=None)

        mock_redis_client = AsyncMock()
        mock_index.client = mock_redis_client
        mock_redis_client.execute_command.side_effect = [
            [5],  # FT.SEARCH
            [2],  # FT.AGGREGATE
        ]

        with (
            patch("redis_sre_agent.core.redis.get_knowledge_index", return_value=mock_index),
            patch(
                "redis_sre_agent.core.redis.get_redis_client",
                new_callable=AsyncMock,
                return_value=mock_redis_client,
            ),
        ):
            response = test_client.get("/api/v1/knowledge/stats")

            assert response.status_code == 200
            data = response.json()
            assert data["ingestion_status"] == "running"

    @pytest.mark.asyncio
    async def test_knowledge_stats_with_completed_jobs(self, test_client):
        """Test stats with completed jobs to get last ingestion time."""
        from datetime import datetime, timezone

        from redis_sre_agent.api.knowledge import _active_jobs

        _active_jobs.clear()
        completed_time = datetime.now(timezone.utc).isoformat()
        _active_jobs["completed_job"] = {
            "job_id": "completed_job",
            "operation": "ingest",
            "status": "completed",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "started_at": datetime.now(timezone.utc).isoformat(),
            "completed_at": completed_time,
            "progress": {},
            "results": {"documents": 10},
            "error": None,
        }

        mock_index = AsyncMock()
        mock_index.name = "sre_knowledge"
        mock_index.__aenter__ = AsyncMock(return_value=mock_index)
        mock_index.__aexit__ = AsyncMock(return_value=None)

        mock_redis_client = AsyncMock()
        mock_index.client = mock_redis_client
        mock_redis_client.execute_command.side_effect = [
            [5],  # FT.SEARCH
            [2],  # FT.AGGREGATE
        ]

        with (
            patch("redis_sre_agent.core.redis.get_knowledge_index", return_value=mock_index),
            patch(
                "redis_sre_agent.core.redis.get_redis_client",
                new_callable=AsyncMock,
                return_value=mock_redis_client,
            ),
        ):
            response = test_client.get("/api/v1/knowledge/stats")

            assert response.status_code == 200
            data = response.json()
            assert data["last_ingestion"] == completed_time
            assert data["ingestion_status"] == "idle"

    @pytest.mark.asyncio
    async def test_knowledge_stats_complete_failure(self, test_client):
        """Test stats when everything fails."""
        with patch("redis_sre_agent.core.redis.get_knowledge_index") as mock_get_index:
            mock_get_index.side_effect = Exception("Complete failure")

            response = test_client.get("/api/v1/knowledge/stats")

            assert response.status_code == 200
            data = response.json()
            # Should return zeros on complete failure
            assert data["total_documents"] == 0
            assert data["total_chunks"] == 0


class TestKnowledgeStats:
    """Test knowledge stats endpoint."""

    @pytest.mark.asyncio
    async def test_knowledge_stats_success(self, test_client):
        """Test knowledge stats endpoint returns correct data."""
        mock_index = AsyncMock()
        mock_index.name = "sre_knowledge"
        mock_index.__aenter__ = AsyncMock(return_value=mock_index)
        mock_index.__aexit__ = AsyncMock(return_value=None)

        # Mock Redis client for FT.SEARCH and FT.AGGREGATE commands
        mock_redis_client = AsyncMock()
        mock_index.client = mock_redis_client

        # Mock FT.SEARCH response for total chunks (returns [count, ...])
        mock_redis_client.execute_command.side_effect = [
            [12],  # FT.SEARCH returns 12 total chunks
            [3],  # FT.AGGREGATE returns 3 unique documents
        ]

        with (
            patch("redis_sre_agent.core.redis.get_knowledge_index", return_value=mock_index),
            patch(
                "redis_sre_agent.core.redis.get_redis_client",
                new_callable=AsyncMock,
                return_value=mock_redis_client,
            ),
        ):
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
            assert data["total_documents"] == 3  # From FT.AGGREGATE unique document_hash count
            assert data["total_chunks"] == 12  # From FT.SEARCH total entries count
            assert data["storage_size_mb"] == 0.024  # 12 chunks * 0.002 MB per chunk

            # Verify Redis commands were called correctly
            calls = mock_redis_client.execute_command.call_args_list
            assert len(calls) == 2

            # First call: FT.SEARCH for total chunks
            assert calls[0][0] == ("FT.SEARCH", "sre_knowledge", "*", "LIMIT", "0", "0")

            # Second call: FT.AGGREGATE for unique documents
            assert calls[1][0] == (
                "FT.AGGREGATE",
                "sre_knowledge",
                "*",
                "GROUPBY",
                "1",
                "@document_hash",
                "REDUCE",
                "COUNT",
                "0",
                "AS",
                "count",
            )

    @pytest.mark.asyncio
    async def test_knowledge_stats_empty_index(self, test_client):
        """Test knowledge stats endpoint with empty index."""
        mock_index = AsyncMock()
        mock_index.name = "sre_knowledge"
        mock_index.__aenter__ = AsyncMock(return_value=mock_index)
        mock_index.__aexit__ = AsyncMock(return_value=None)

        # Mock Redis client for empty index
        mock_redis_client = AsyncMock()
        mock_index.client = mock_redis_client

        # Mock FT.SEARCH and FT.AGGREGATE responses for empty index
        mock_redis_client.execute_command.side_effect = [
            [0],  # FT.SEARCH returns 0 total chunks
            [0],  # FT.AGGREGATE returns 0 unique documents
        ]

        with (
            patch("redis_sre_agent.core.redis.get_knowledge_index", return_value=mock_index),
            patch(
                "redis_sre_agent.core.redis.get_redis_client",
                new_callable=AsyncMock,
                return_value=mock_redis_client,
            ),
        ):
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
        mock_index.name = "sre_knowledge"
        mock_index.__aenter__ = AsyncMock(return_value=mock_index)
        mock_index.__aexit__ = AsyncMock(return_value=None)

        # Mock Redis client that fails
        mock_redis_client = AsyncMock()
        mock_redis_client.execute_command.side_effect = Exception("Query failed")

        with (
            patch("redis_sre_agent.core.redis.get_knowledge_index", return_value=mock_index),
            patch(
                "redis_sre_agent.core.redis.get_redis_client",
                new_callable=AsyncMock,
                return_value=mock_redis_client,
            ),
        ):
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
            "severity": "info",
        }

        mock_result = {"document_id": "test_doc_123"}

        with patch(
            "redis_sre_agent.tools.sre_functions.ingest_sre_document", new_callable=AsyncMock
        ) as mock_ingest:
            mock_ingest.return_value = mock_result

            response = test_client.post("/api/v1/knowledge/ingest/document", json=document_data)

            assert response.status_code == 200
            data = response.json()

            assert data["success"] is True
            assert data["document_id"] == "test_doc_123"
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
            "severity": "info",
        }

        with patch(
            "redis_sre_agent.tools.sre_functions.ingest_sre_document", new_callable=AsyncMock
        ) as mock_ingest:
            mock_ingest.side_effect = Exception("Ingestion failed")

            response = test_client.post("/api/v1/knowledge/ingest/document", json=document_data)

            assert response.status_code == 500
            data = response.json()
            assert "detail" in data


class TestKnowledgeJobs:
    """Test knowledge job management endpoints."""

    @pytest.mark.asyncio
    async def test_list_jobs_empty(self, test_client):
        """Test listing jobs when none exist."""
        # Clear any existing jobs
        from redis_sre_agent.api.knowledge import _active_jobs

        _active_jobs.clear()

        response = test_client.get("/api/v1/knowledge/jobs")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 0

    @pytest.mark.asyncio
    async def test_list_jobs_with_data(self, test_client):
        """Test listing jobs when some exist."""
        from datetime import datetime, timezone

        from redis_sre_agent.api.knowledge import _active_jobs

        _active_jobs.clear()
        _active_jobs["job1"] = {
            "job_id": "job1",
            "operation": "scrape",
            "status": "completed",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "started_at": None,
            "completed_at": None,
            "progress": {},
            "results": None,
            "error": None,
        }

        response = test_client.get("/api/v1/knowledge/jobs")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["job_id"] == "job1"

    @pytest.mark.asyncio
    async def test_get_job_status_success(self, test_client):
        """Test getting status for existing job."""
        from datetime import datetime, timezone

        from redis_sre_agent.api.knowledge import _active_jobs

        _active_jobs.clear()
        _active_jobs["job2"] = {
            "job_id": "job2",
            "operation": "ingest",
            "status": "running",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "started_at": datetime.now(timezone.utc).isoformat(),
            "completed_at": None,
            "progress": {"processed": 10},
            "results": None,
            "error": None,
        }

        response = test_client.get("/api/v1/knowledge/jobs/job2")

        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == "job2"
        assert data["status"] == "running"

    @pytest.mark.asyncio
    async def test_get_job_status_not_found(self, test_client):
        """Test getting status for non-existent job."""
        from redis_sre_agent.api.knowledge import _active_jobs

        _active_jobs.clear()

        response = test_client.get("/api/v1/knowledge/jobs/nonexistent")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_cancel_job_success(self, test_client):
        """Test canceling an existing job."""
        from datetime import datetime, timezone

        from redis_sre_agent.api.knowledge import _active_jobs

        _active_jobs.clear()
        _active_jobs["job3"] = {
            "job_id": "job3",
            "operation": "scrape",
            "status": "running",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "started_at": datetime.now(timezone.utc).isoformat(),
            "completed_at": None,
            "progress": {},
            "results": None,
            "error": None,
        }

        response = test_client.delete("/api/v1/knowledge/jobs/job3")

        assert response.status_code == 200
        data = response.json()
        assert "cancelled" in data["message"].lower() or "removed" in data["message"].lower()

    @pytest.mark.asyncio
    async def test_cancel_job_not_found(self, test_client):
        """Test canceling non-existent job."""
        from redis_sre_agent.api.knowledge import _active_jobs

        _active_jobs.clear()

        response = test_client.delete("/api/v1/knowledge/jobs/nonexistent")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


class TestKnowledgeSettings:
    """Test knowledge settings endpoints."""

    @pytest.mark.asyncio
    async def test_get_settings_defaults(self, test_client):
        """Test getting default settings."""
        # Reset settings to None to test defaults
        import redis_sre_agent.api.knowledge as knowledge_module

        knowledge_module._knowledge_settings = None

        response = test_client.get("/api/v1/knowledge/settings")

        assert response.status_code == 200
        data = response.json()
        assert "chunk_size" in data
        assert "chunk_overlap" in data
        assert "embedding_model" in data

    @pytest.mark.asyncio
    async def test_reset_settings(self, test_client):
        """Test resetting settings to defaults."""
        response = test_client.post("/api/v1/knowledge/settings/reset")

        assert response.status_code == 200
        data = response.json()
        assert "chunk_size" in data
        assert "chunk_overlap" in data


class TestKnowledgeSettingsUpdate:
    """Test knowledge settings update endpoint."""

    @pytest.mark.asyncio
    async def test_update_settings_success(self, test_client):
        """Test updating knowledge settings."""
        response = test_client.put(
            "/api/v1/knowledge/settings",
            json={
                "chunk_size": 1000,
                "chunk_overlap": 100,
                "embedding_model": "text-embedding-3-small",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["chunk_size"] == 1000
        assert data["chunk_overlap"] == 100

    @pytest.mark.asyncio
    async def test_update_settings_partial(self, test_client):
        """Test updating only some settings."""
        response = test_client.put("/api/v1/knowledge/settings", json={"chunk_size": 2000})

        assert response.status_code == 200
        data = response.json()
        assert data["chunk_size"] == 2000

    @pytest.mark.asyncio
    async def test_update_settings_when_none(self, test_client):
        """Test updating settings when they are None (initializes defaults)."""
        # Reset settings to None
        import redis_sre_agent.api.knowledge as knowledge_module

        knowledge_module._knowledge_settings = None

        response = test_client.put("/api/v1/knowledge/settings", json={"chunk_size": 1500})

        assert response.status_code == 200
        data = response.json()
        assert data["chunk_size"] == 1500


class TestKnowledgeSearchErrors:
    """Test knowledge search error handling."""

    @pytest.mark.asyncio
    async def test_search_index_error(self, test_client):
        """Test search when index raises an error."""
        mock_index = AsyncMock()
        mock_index.__aenter__ = AsyncMock(side_effect=Exception("Index error"))
        mock_index.__aexit__ = AsyncMock(return_value=None)

        with patch("redis_sre_agent.core.redis.get_knowledge_index", return_value=mock_index):
            response = test_client.get("/api/v1/knowledge/search?query=test")

            assert response.status_code == 500
            assert "Search failed" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_search_query_error(self, test_client):
        """Test search when query execution fails."""
        mock_index = AsyncMock()
        mock_index.name = "sre_knowledge"
        mock_index.__aenter__ = AsyncMock(return_value=mock_index)
        mock_index.__aexit__ = AsyncMock(return_value=None)
        mock_index.search = AsyncMock(side_effect=Exception("Query error"))

        with patch("redis_sre_agent.core.redis.get_knowledge_index", return_value=mock_index):
            response = test_client.get("/api/v1/knowledge/search?query=test")

            assert response.status_code == 500
            assert "Search failed" in response.json()["detail"]


class TestKnowledgeSearch:
    """Test knowledge search endpoint."""

    @pytest.mark.asyncio
    async def test_search_success(self, test_client):
        """Test successful knowledge search."""
        mock_result = {
            "query": "redis",
            "category_filter": None,
            "results_count": 2,
            "results": [
                {
                    "title": "Test Document 1",
                    "content": "Redis troubleshooting content",
                    "source": "test",
                    "score": 0.95,
                },
                {
                    "title": "Test Document 2",
                    "content": "More Redis content",
                    "source": "test",
                    "score": 0.87,
                },
            ],
            "formatted_output": "Found 2 results for redis",
        }

        with patch(
            "redis_sre_agent.api.knowledge.search_knowledge_base", new_callable=AsyncMock
        ) as mock_search:
            mock_search.return_value = mock_result

            response = test_client.get("/api/v1/knowledge/search?query=redis&limit=5")

            assert response.status_code == 200
            data = response.json()

            assert "results" in data
            assert "results_count" in data
            assert data["results_count"] == 2
            assert len(data["results"]) == 2

            # Verify search was called with correct parameters
            mock_search.assert_called_once_with(
                "redis", category=None, product_labels=None, limit=5
            )

    @pytest.mark.asyncio
    async def test_search_empty_query(self, test_client):
        """Test search with empty query parameter."""
        response = test_client.get("/api/v1/knowledge/search?query=&limit=5")

        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        assert "empty" in data["detail"].lower()

    @pytest.mark.asyncio
    async def test_search_no_results(self, test_client):
        """Test search that returns no results."""
        with patch(
            "redis_sre_agent.api.knowledge.search_knowledge_base", new_callable=AsyncMock
        ) as mock_search:
            mock_search.return_value = []

            response = test_client.get("/api/v1/knowledge/search?query=nonexistent&limit=5")

            assert response.status_code == 200
            data = response.json()

            assert data["results_count"] == 0
            assert data["results"] == []

    @pytest.mark.asyncio
    async def test_search_with_product_labels(self, test_client):
        """Test search with product labels filter."""
        with patch(
            "redis_sre_agent.api.knowledge.search_knowledge_base", new_callable=AsyncMock
        ) as mock_search:
            mock_search.return_value = []

            response = test_client.get(
                "/api/v1/knowledge/search?query=test&product_labels=redis,valkey"
            )

            assert response.status_code == 200
            # Verify product_labels were parsed and passed
            mock_search.assert_called_once()
            call_args = mock_search.call_args
            assert call_args[1]["product_labels"] == ["redis", "valkey"]

    @pytest.mark.asyncio
    async def test_search_string_result_format(self, test_client):
        """Test search when result is a string (formatted output)."""
        with patch(
            "redis_sre_agent.api.knowledge.search_knowledge_base", new_callable=AsyncMock
        ) as mock_search:
            # Return a string instead of list/dict
            mock_search.return_value = "Formatted search results as string"

            response = test_client.get("/api/v1/knowledge/search?query=test")

            assert response.status_code == 200
            data = response.json()
            assert data["formatted_output"] == "Formatted search results as string"
            assert data["results_count"] == 0
            assert data["results"] == []
