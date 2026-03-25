"""Tests for MCP server tools."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from redis_sre_agent.mcp_server.server import (
    mcp,
    redis_sre_create_instance,
    redis_sre_database_chat,
    redis_sre_deep_triage,
    redis_sre_delete_support_package,
    redis_sre_delete_task,
    redis_sre_extract_support_package,
    redis_sre_general_chat,
    redis_sre_get_knowledge_fragments,
    redis_sre_get_pipeline_batch,
    redis_sre_get_pipeline_status,
    redis_sre_get_related_knowledge_fragments,
    redis_sre_get_support_package_info,
    redis_sre_get_support_ticket,
    redis_sre_get_task_citations,
    redis_sre_get_task_status,
    redis_sre_get_thread,
    redis_sre_knowledge_query,
    redis_sre_knowledge_search,
    redis_sre_list_instances,
    redis_sre_list_support_packages,
    redis_sre_list_threads,
    redis_sre_search_support_tickets,
    redis_sre_upload_support_package,
)


class TestMCPServerSetup:
    """Test MCP server configuration."""

    def test_mcp_server_name(self):
        """Test that the MCP server has correct name."""
        assert mcp.name == "redis-sre-agent"

    def test_mcp_server_has_instructions(self):
        """Test that the MCP server has instructions."""
        assert mcp.instructions is not None
        assert "Redis SRE Agent" in mcp.instructions

    def test_mcp_server_has_tools(self):
        """Test that all expected tools are registered."""
        tool_names = [t.name for t in mcp._tool_manager._tools.values()]
        assert "redis_sre_deep_triage" in tool_names
        assert "redis_sre_general_chat" in tool_names
        assert "redis_sre_database_chat" in tool_names
        assert "redis_sre_knowledge_search" in tool_names
        assert "redis_sre_get_knowledge_fragments" in tool_names
        assert "redis_sre_get_related_knowledge_fragments" in tool_names
        assert "redis_sre_get_pipeline_status" in tool_names
        assert "redis_sre_get_pipeline_batch" in tool_names
        assert "redis_sre_upload_support_package" in tool_names
        assert "redis_sre_list_support_packages" in tool_names
        assert "redis_sre_extract_support_package" in tool_names
        assert "redis_sre_delete_support_package" in tool_names
        assert "redis_sre_get_support_package_info" in tool_names
        assert "redis_sre_search_support_tickets" in tool_names
        assert "redis_sre_get_support_ticket" in tool_names
        assert "redis_sre_knowledge_query" in tool_names
        assert "redis_sre_get_thread" in tool_names
        assert "redis_sre_list_threads" in tool_names
        assert "redis_sre_get_task_status" in tool_names
        assert "redis_sre_get_task_citations" in tool_names
        assert "redis_sre_delete_task" in tool_names
        assert "redis_sre_list_instances" in tool_names
        assert "redis_sre_create_instance" in tool_names


class TestDeepTriageTool:
    """Test the redis_sre_deep_triage MCP tool."""

    @pytest.mark.asyncio
    async def test_deep_triage_success(self):
        """Test successful deep triage request."""
        mock_result = {
            "thread_id": "thread-123",
            "task_id": "task-456",
            "status": "queued",
            "message": "Task created",
        }

        with (
            patch("redis_sre_agent.core.redis.get_redis_client"),
            patch("redis_sre_agent.core.tasks.create_task", new_callable=AsyncMock) as mock_create,
        ):
            mock_create.return_value = mock_result

            result = await redis_sre_deep_triage(
                query="High memory usage on Redis",
                instance_id="redis-prod-1",
                user_id="user-123",
            )

            assert result["thread_id"] == "thread-123"
            assert result["task_id"] == "task-456"
            assert "status" in result
            mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_deep_triage_with_cluster_id(self):
        """Test deep triage accepts cluster_id and forwards context."""
        mock_result = {
            "thread_id": "thread-123",
            "task_id": "task-456",
            "status": "queued",
            "message": "Task created",
        }

        with (
            patch("redis_sre_agent.core.redis.get_redis_client"),
            patch("redis_sre_agent.core.tasks.create_task", new_callable=AsyncMock) as mock_create,
        ):
            mock_create.return_value = mock_result

            result = await redis_sre_deep_triage(
                query="Cluster check",
                cluster_id="cluster-prod-1",
            )

            assert result["task_id"] == "task-456"
            call_kwargs = mock_create.call_args.kwargs
            assert call_kwargs["context"]["cluster_id"] == "cluster-prod-1"

    @pytest.mark.asyncio
    async def test_deep_triage_rejects_instance_and_cluster_together(self):
        """Test deep triage rejects conflicting target identifiers."""
        result = await redis_sre_deep_triage(
            query="Cluster check",
            instance_id="redis-prod-1",
            cluster_id="cluster-prod-1",
        )

        assert result["status"] == "failed"
        assert "only one of instance_id or cluster_id" in result["message"]

    @pytest.mark.asyncio
    async def test_deep_triage_error_handling(self):
        """Test deep triage error handling."""
        with (
            patch("redis_sre_agent.core.redis.get_redis_client"),
            patch("redis_sre_agent.core.tasks.create_task", new_callable=AsyncMock) as mock_create,
        ):
            mock_create.side_effect = Exception("Redis connection failed")

            result = await redis_sre_deep_triage(query="Test query")

            assert result["status"] == "failed"
            assert "error" in result


class TestGeneralChatTool:
    """Test the redis_sre_general_chat MCP tool.

    Note: The chat tool creates a task and returns task_id/thread_id
    instead of running synchronously. This matches the triage pattern.
    """

    @pytest.mark.asyncio
    async def test_general_chat_creates_task(self):
        """Test that general_chat creates a task and returns task_id."""
        mock_result = {
            "thread_id": "thread-123",
            "task_id": "task-456",
            "status": "queued",
            "message": "Task created",
        }

        with (
            patch("redis_sre_agent.core.redis.get_redis_client"),
            patch("redis_sre_agent.core.tasks.create_task", new_callable=AsyncMock) as mock_create,
        ):
            mock_create.return_value = mock_result

            result = await redis_sre_general_chat(query="What's the memory usage?")

            assert result["thread_id"] == "thread-123"
            assert result["task_id"] == "task-456"
            assert "status" in result
            mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_general_chat_with_instance_id(self):
        """Test general_chat with a specific instance includes it in context."""
        mock_result = {
            "thread_id": "thread-123",
            "task_id": "task-456",
            "status": "queued",
        }

        with (
            patch("redis_sre_agent.core.redis.get_redis_client"),
            patch("redis_sre_agent.core.tasks.create_task", new_callable=AsyncMock) as mock_create,
        ):
            mock_create.return_value = mock_result

            result = await redis_sre_general_chat(query="Check status", instance_id="redis-prod-1")

            assert result["task_id"] == "task-456"
            # Verify instance_id was passed in context
            call_kwargs = mock_create.call_args.kwargs
            assert call_kwargs["context"]["instance_id"] == "redis-prod-1"

    @pytest.mark.asyncio
    async def test_general_chat_with_cluster_id(self):
        """Test general_chat with a specific cluster includes it in context."""
        mock_result = {
            "thread_id": "thread-123",
            "task_id": "task-456",
            "status": "queued",
        }

        with (
            patch("redis_sre_agent.core.redis.get_redis_client"),
            patch("redis_sre_agent.core.tasks.create_task", new_callable=AsyncMock) as mock_create,
        ):
            mock_create.return_value = mock_result

            result = await redis_sre_general_chat(
                query="Check cluster", cluster_id="cluster-prod-1"
            )

            assert result["task_id"] == "task-456"
            call_kwargs = mock_create.call_args.kwargs
            assert call_kwargs["context"]["cluster_id"] == "cluster-prod-1"

    @pytest.mark.asyncio
    async def test_general_chat_rejects_instance_and_cluster_together(self):
        """Test general_chat rejects conflicting target identifiers."""
        result = await redis_sre_general_chat(
            query="Check status",
            instance_id="redis-prod-1",
            cluster_id="cluster-prod-1",
        )

        assert result["status"] == "failed"
        assert "only one of instance_id or cluster_id" in result["message"]

    @pytest.mark.asyncio
    async def test_general_chat_error_handling(self):
        """Test general_chat error handling."""
        with (
            patch("redis_sre_agent.core.redis.get_redis_client"),
            patch("redis_sre_agent.core.tasks.create_task", new_callable=AsyncMock) as mock_create,
        ):
            mock_create.side_effect = Exception("Redis connection failed")

            result = await redis_sre_general_chat(query="Test query")

            assert result["status"] == "failed"
            assert "error" in result


class TestDatabaseChatTool:
    """Test the redis_sre_database_chat MCP tool with category exclusion."""

    @pytest.mark.asyncio
    async def test_database_chat_excludes_all_mcp_by_default(self):
        """Test that database_chat excludes all MCP categories by default."""
        mock_result = {
            "thread_id": "thread-123",
            "task_id": "task-456",
            "status": "queued",
        }

        with (
            patch("redis_sre_agent.core.redis.get_redis_client"),
            patch("redis_sre_agent.core.tasks.create_task", new_callable=AsyncMock) as mock_create,
        ):
            mock_create.return_value = mock_result

            result = await redis_sre_database_chat(query="What's the memory usage?")

            assert result["task_id"] == "task-456"
            # Verify that exclude_mcp_categories is set in context
            call_kwargs = mock_create.call_args.kwargs
            assert "exclude_mcp_categories" in call_kwargs["context"]

    @pytest.mark.asyncio
    async def test_database_chat_with_selective_exclusion(self):
        """Test database_chat with selective category exclusion."""
        mock_result = {
            "thread_id": "thread-123",
            "task_id": "task-456",
            "status": "queued",
        }

        with (
            patch("redis_sre_agent.core.redis.get_redis_client"),
            patch("redis_sre_agent.core.tasks.create_task", new_callable=AsyncMock) as mock_create,
        ):
            mock_create.return_value = mock_result

            # Only exclude tickets and repos
            result = await redis_sre_database_chat(
                query="Check status",
                exclude_mcp_categories=["tickets", "repos"],
            )

            assert result["task_id"] == "task-456"
            call_kwargs = mock_create.call_args.kwargs
            assert call_kwargs["context"]["exclude_mcp_categories"] == ["tickets", "repos"]

    @pytest.mark.asyncio
    async def test_database_chat_with_cluster_id(self):
        """Test database_chat forwards cluster_id in context."""
        mock_result = {
            "thread_id": "thread-123",
            "task_id": "task-456",
            "status": "queued",
        }

        with (
            patch("redis_sre_agent.core.redis.get_redis_client"),
            patch("redis_sre_agent.core.tasks.create_task", new_callable=AsyncMock) as mock_create,
        ):
            mock_create.return_value = mock_result

            result = await redis_sre_database_chat(
                query="Check cluster", cluster_id="cluster-prod-1"
            )

            assert result["task_id"] == "task-456"
            call_kwargs = mock_create.call_args.kwargs
            assert call_kwargs["context"]["cluster_id"] == "cluster-prod-1"

    @pytest.mark.asyncio
    async def test_database_chat_rejects_instance_and_cluster_together(self):
        """Test database_chat rejects conflicting target identifiers."""
        result = await redis_sre_database_chat(
            query="Check status",
            instance_id="redis-prod-1",
            cluster_id="cluster-prod-1",
        )

        assert result["status"] == "failed"
        assert "only one of instance_id or cluster_id" in result["message"]


class TestKnowledgeSearchTool:
    """Test the redis_sre_knowledge_search MCP tool."""

    @pytest.mark.asyncio
    async def test_knowledge_search_success(self):
        """Test successful knowledge search."""
        mock_result = {
            "results": [
                {
                    "title": "Redis Memory Management",
                    "content": "Redis uses memory...",
                    "source": "docs",
                    "category": "documentation",
                }
            ]
        }

        with patch(
            "redis_sre_agent.core.knowledge_helpers.search_knowledge_base_helper",
            new_callable=AsyncMock,
        ) as mock_search:
            mock_search.return_value = mock_result

            result = await redis_sre_knowledge_search(query="memory management", limit=5)

            assert result["query"] == "memory management"
            assert len(result["results"]) == 1
            assert result["results"][0]["title"] == "Redis Memory Management"
            mock_search.assert_called_once()

    @pytest.mark.asyncio
    async def test_knowledge_search_limit_clamped(self):
        """Test that limit is clamped to valid range."""
        with patch(
            "redis_sre_agent.core.knowledge_helpers.search_knowledge_base_helper",
            new_callable=AsyncMock,
        ) as mock_search:
            mock_search.return_value = {"results": []}

            # Test with too high limit (max is 50)
            await redis_sre_knowledge_search(query="test", limit=100)
            call_args = mock_search.call_args
            assert call_args.kwargs["limit"] == 50

            # Test with too low limit
            await redis_sre_knowledge_search(query="test", limit=0)
            call_args = mock_search.call_args
            assert call_args.kwargs["limit"] == 1

    @pytest.mark.asyncio
    async def test_knowledge_search_error_handling(self):
        """Test knowledge search error handling."""
        with patch(
            "redis_sre_agent.core.knowledge_helpers.search_knowledge_base_helper",
            new_callable=AsyncMock,
        ) as mock_search:
            mock_search.side_effect = Exception("Search failed")

            result = await redis_sre_knowledge_search(query="test")

            assert "error" in result
            assert result["results"] == []
            assert result["total_results"] == 0


class TestKnowledgeFragmentTools:
    """Test document fragment MCP tools."""

    @pytest.mark.asyncio
    async def test_get_knowledge_fragments_success(self):
        """Full fragment retrieval returns helper payload."""
        mock_result = {
            "document_hash": "doc-123",
            "fragments_count": 2,
            "fragments": [{"chunk_index": 0}, {"chunk_index": 1}],
        }

        with patch(
            "redis_sre_agent.core.knowledge_helpers.get_all_document_fragments",
            new_callable=AsyncMock,
        ) as mock_helper:
            mock_helper.return_value = mock_result

            result = await redis_sre_get_knowledge_fragments(document_hash="doc-123")

            assert result["document_hash"] == "doc-123"
            assert result["fragments_count"] == 2
            mock_helper.assert_awaited_once_with(
                "doc-123",
                include_metadata=True,
                index_type="knowledge",
                version=None,
            )

    @pytest.mark.asyncio
    async def test_get_knowledge_fragments_error_payload_passthrough(self):
        """Fragment retrieval preserves helper error payload."""
        with patch(
            "redis_sre_agent.core.knowledge_helpers.get_all_document_fragments",
            new_callable=AsyncMock,
        ) as mock_helper:
            mock_helper.return_value = {
                "document_hash": "doc-123",
                "error": "No fragments found for this document",
                "fragments": [],
            }

            result = await redis_sre_get_knowledge_fragments(document_hash="doc-123")

            assert result["document_hash"] == "doc-123"
            assert result["error"] == "No fragments found for this document"

    @pytest.mark.asyncio
    async def test_get_related_knowledge_fragments_success(self):
        """Related fragment retrieval returns helper payload."""
        mock_result = {
            "document_hash": "doc-123",
            "target_chunk_index": 4,
            "related_fragments_count": 3,
            "related_fragments": [{"chunk_index": 3}, {"chunk_index": 4}, {"chunk_index": 5}],
        }

        with patch(
            "redis_sre_agent.core.knowledge_helpers.get_related_document_fragments",
            new_callable=AsyncMock,
        ) as mock_helper:
            mock_helper.return_value = mock_result

            result = await redis_sre_get_related_knowledge_fragments(
                document_hash="doc-123",
                chunk_index=4,
                window=1,
            )

            assert result["target_chunk_index"] == 4
            assert result["related_fragments_count"] == 3
            mock_helper.assert_awaited_once_with(
                "doc-123",
                current_chunk_index=4,
                context_window=1,
            )

    @pytest.mark.asyncio
    async def test_get_related_knowledge_fragments_error_payload_passthrough(self):
        """Related fragment retrieval preserves helper error payload."""
        with patch(
            "redis_sre_agent.core.knowledge_helpers.get_related_document_fragments",
            new_callable=AsyncMock,
        ) as mock_helper:
            mock_helper.return_value = {
                "document_hash": "doc-123",
                "error": "lookup failed",
                "related_fragments": [],
            }

            result = await redis_sre_get_related_knowledge_fragments(
                document_hash="doc-123",
                chunk_index=4,
            )

            assert result["document_hash"] == "doc-123"
            assert result["error"] == "lookup failed"


class TestPipelineInspectionTools:
    """Test pipeline inspection MCP tools."""

    @pytest.mark.asyncio
    async def test_get_pipeline_status_success(self):
        """Pipeline status returns helper payload."""
        mock_result = {
            "artifacts_path": "/tmp/artifacts",
            "current_batch_date": "2026-03-25",
            "available_batches": ["2026-03-24", "2026-03-25"],
            "scrapers": {"redis_docs": {"source": "redis.io"}},
            "ingestion": {"batches_ingested": 1},
        }

        with patch(
            "redis_sre_agent.core.pipeline_helpers.get_pipeline_status_helper",
            new_callable=AsyncMock,
        ) as mock_helper:
            mock_helper.return_value = mock_result

            result = await redis_sre_get_pipeline_status()

            assert result["current_batch_date"] == "2026-03-25"
            assert result["available_batches"] == ["2026-03-24", "2026-03-25"]
            mock_helper.assert_called_once_with(artifacts_path="./artifacts")

    @pytest.mark.asyncio
    async def test_get_pipeline_status_error_handling(self):
        """Pipeline status returns structured error payload on failure."""
        with patch(
            "redis_sre_agent.core.pipeline_helpers.get_pipeline_status_helper",
            new_callable=AsyncMock,
        ) as mock_helper:
            mock_helper.side_effect = Exception("status failed")

            result = await redis_sre_get_pipeline_status(artifacts_path="/tmp/artifacts")

            assert result["artifacts_path"] == "/tmp/artifacts"
            assert result["available_batches"] == []
            assert "error" in result

    @pytest.mark.asyncio
    async def test_get_pipeline_batch_success(self):
        """Pipeline batch returns helper payload."""
        mock_result = {
            "batch_date": "2026-03-25",
            "artifacts_path": "/tmp/artifacts",
            "total_documents": 12,
            "categories": {"oss": 10},
            "document_types": {"documentation": 8},
            "ingestion": {"available": True, "status": "success", "chunks_indexed": 42},
        }

        with patch(
            "redis_sre_agent.core.pipeline_helpers.get_pipeline_batch_helper",
            new_callable=AsyncMock,
        ) as mock_helper:
            mock_helper.return_value = mock_result

            result = await redis_sre_get_pipeline_batch(batch_date="2026-03-25")

            assert result["batch_date"] == "2026-03-25"
            assert result["ingestion"]["status"] == "success"
            mock_helper.assert_called_once_with(
                batch_date="2026-03-25", artifacts_path="./artifacts"
            )

    @pytest.mark.asyncio
    async def test_get_pipeline_batch_error_handling(self):
        """Pipeline batch returns structured error payload on failure."""
        with patch(
            "redis_sre_agent.core.pipeline_helpers.get_pipeline_batch_helper",
            new_callable=AsyncMock,
        ) as mock_helper:
            mock_helper.side_effect = Exception("batch failed")

            result = await redis_sre_get_pipeline_batch(
                batch_date="2026-03-25",
                artifacts_path="/tmp/artifacts",
            )

            assert result["batch_date"] == "2026-03-25"
            assert result["artifacts_path"] == "/tmp/artifacts"
            assert "error" in result


class TestSupportPackageManagementTools:
    """Test support-package management MCP tools."""

    @pytest.mark.asyncio
    async def test_upload_support_package_success(self, tmp_path):
        """Upload returns package id and status."""
        archive = tmp_path / "support-package.tar.gz"
        archive.write_bytes(b"dummy")

        mock_manager = AsyncMock()
        mock_manager.upload.return_value = "pkg-123"

        with patch(
            "redis_sre_agent.core.support_package_helpers.get_support_package_manager",
            return_value=mock_manager,
        ):
            result = await redis_sre_upload_support_package(file_path=str(archive))

            assert result == {
                "package_id": "pkg-123",
                "filename": "support-package.tar.gz",
                "status": "uploaded",
            }
            mock_manager.upload.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_upload_support_package_missing_file(self):
        """Upload validates file existence."""
        result = await redis_sre_upload_support_package(file_path="/tmp/does-not-exist.tar.gz")

        assert result["status"] == "failed"
        assert "error" in result

    @pytest.mark.asyncio
    async def test_list_support_packages_success(self):
        """List support packages returns serialized metadata."""
        from datetime import datetime, timezone

        from redis_sre_agent.tools.support_package.storage.protocols import PackageMetadata

        mock_manager = AsyncMock()
        mock_manager.list_packages.return_value = [
            PackageMetadata(
                package_id="pkg-123",
                filename="support-package.tar.gz",
                size_bytes=1024,
                uploaded_at=datetime(2026, 3, 25, tzinfo=timezone.utc),
                storage_path="/tmp/pkg-123",
                checksum="abc123",
            )
        ]

        with patch(
            "redis_sre_agent.core.support_package_helpers.get_support_package_manager",
            return_value=mock_manager,
        ):
            result = await redis_sre_list_support_packages()

            assert result["total"] == 1
            assert result["packages"][0]["package_id"] == "pkg-123"
            assert result["packages"][0]["size_bytes"] == 1024

    @pytest.mark.asyncio
    async def test_extract_support_package_success(self):
        """Extract returns output path."""
        from pathlib import Path

        mock_manager = AsyncMock()
        mock_manager.extract.return_value = Path("/tmp/extracted/pkg-123")

        with patch(
            "redis_sre_agent.core.support_package_helpers.get_support_package_manager",
            return_value=mock_manager,
        ):
            result = await redis_sre_extract_support_package(package_id="pkg-123")

            assert result == {
                "package_id": "pkg-123",
                "path": "/tmp/extracted/pkg-123",
                "status": "extracted",
            }

    @pytest.mark.asyncio
    async def test_delete_support_package_requires_confirm(self):
        """Delete is gated by explicit confirmation."""
        result = await redis_sre_delete_support_package(package_id="pkg-123")

        assert result["status"] == "failed"
        assert "confirm" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_delete_support_package_success(self):
        """Delete returns deleted status."""
        mock_manager = AsyncMock()

        with patch(
            "redis_sre_agent.core.support_package_helpers.get_support_package_manager",
            return_value=mock_manager,
        ):
            result = await redis_sre_delete_support_package(package_id="pkg-123", confirm=True)

            assert result == {"package_id": "pkg-123", "status": "deleted"}
            mock_manager.delete.assert_awaited_once_with("pkg-123")

    @pytest.mark.asyncio
    async def test_get_support_package_info_success(self):
        """Info returns metadata plus extraction state."""
        from datetime import datetime, timezone

        from redis_sre_agent.tools.support_package.storage.protocols import PackageMetadata

        mock_manager = AsyncMock()
        mock_manager.get_metadata.return_value = PackageMetadata(
            package_id="pkg-123",
            filename="support-package.tar.gz",
            size_bytes=2048,
            uploaded_at=datetime(2026, 3, 25, tzinfo=timezone.utc),
            storage_path="/tmp/pkg-123",
            checksum="abc123",
        )
        mock_manager.is_extracted.return_value = True

        with patch(
            "redis_sre_agent.core.support_package_helpers.get_support_package_manager",
            return_value=mock_manager,
        ):
            result = await redis_sre_get_support_package_info(package_id="pkg-123")

            assert result["package_id"] == "pkg-123"
            assert result["is_extracted"] is True
            assert result["checksum"] == "abc123"

    @pytest.mark.asyncio
    async def test_get_support_package_info_not_found(self):
        """Info returns not_found payload when metadata is missing."""
        mock_manager = AsyncMock()
        mock_manager.get_metadata.return_value = None

        with patch(
            "redis_sre_agent.core.support_package_helpers.get_support_package_manager",
            return_value=mock_manager,
        ):
            result = await redis_sre_get_support_package_info(package_id="pkg-123")

            assert result["status"] == "not_found"
            assert result["package_id"] == "pkg-123"


class TestKnowledgeQueryTool:
    """Test the redis_sre_knowledge_query MCP tool.

    The knowledge_query tool creates a task that uses the KnowledgeOnlyAgent
    to answer questions about SRE practices and Redis.
    """

    @pytest.mark.asyncio
    async def test_knowledge_query_creates_task(self):
        """Test that knowledge_query creates a task and returns task_id."""
        mock_result = {
            "thread_id": "thread-123",
            "task_id": "task-456",
            "status": "queued",
            "message": "Task created",
        }

        with (
            patch("redis_sre_agent.core.redis.get_redis_client"),
            patch("redis_sre_agent.core.tasks.create_task", new_callable=AsyncMock) as mock_create,
        ):
            mock_create.return_value = mock_result

            result = await redis_sre_knowledge_query(query="What are Redis eviction policies?")

            assert result["thread_id"] == "thread-123"
            assert result["task_id"] == "task-456"
            assert "status" in result
            mock_create.assert_called_once()
            # Verify agent_type is set in context
            call_kwargs = mock_create.call_args.kwargs
            assert call_kwargs["context"]["agent_type"] == "knowledge"

    @pytest.mark.asyncio
    async def test_knowledge_query_error_handling(self):
        """Test knowledge_query error handling."""
        with (
            patch("redis_sre_agent.core.redis.get_redis_client"),
            patch("redis_sre_agent.core.tasks.create_task", new_callable=AsyncMock) as mock_create,
        ):
            mock_create.side_effect = Exception("Redis connection failed")

            result = await redis_sre_knowledge_query(query="Test query")

            assert result["status"] == "failed"
            assert "error" in result


class TestSupportTicketTools:
    """Test support-ticket MCP tools."""

    @pytest.mark.asyncio
    async def test_search_support_tickets_success(self):
        """Support-ticket search returns ticket-scoped results."""
        mock_result = {
            "tickets": [
                {
                    "ticket_id": "ticket-123",
                    "title": "Connection reset incidents",
                    "summary": "Intermittent resets under load",
                }
            ],
            "results": [
                {
                    "ticket_id": "ticket-123",
                    "title": "Connection reset incidents",
                    "summary": "Intermittent resets under load",
                }
            ],
            "ticket_count": 1,
            "results_count": 1,
        }

        with patch(
            "redis_sre_agent.core.knowledge_helpers.search_support_tickets_helper",
            new_callable=AsyncMock,
        ) as mock_search:
            mock_search.return_value = mock_result

            result = await redis_sre_search_support_tickets(query="connection reset", limit=5)

            assert result["query"] == "connection reset"
            assert result["ticket_count"] == 1
            assert result["tickets"][0]["ticket_id"] == "ticket-123"
            mock_search.assert_called_once()
            assert mock_search.call_args.kwargs["distance_threshold"] == pytest.approx(0.8)

    @pytest.mark.asyncio
    async def test_search_support_tickets_limit_clamped(self):
        """Support-ticket search limit is clamped to [1, 50]."""
        with patch(
            "redis_sre_agent.core.knowledge_helpers.search_support_tickets_helper",
            new_callable=AsyncMock,
        ) as mock_search:
            mock_search.return_value = {"tickets": [], "results": [], "ticket_count": 0}

            await redis_sre_search_support_tickets(query="x", limit=100)
            assert mock_search.call_args.kwargs["limit"] == 50

            await redis_sre_search_support_tickets(query="x", limit=0)
            assert mock_search.call_args.kwargs["limit"] == 1

    @pytest.mark.asyncio
    async def test_search_support_tickets_error_handling(self):
        """Support-ticket search returns error payload on failure."""
        with patch(
            "redis_sre_agent.core.knowledge_helpers.search_support_tickets_helper",
            new_callable=AsyncMock,
        ) as mock_search:
            mock_search.side_effect = Exception("Search failed")

            result = await redis_sre_search_support_tickets(query="test")

            assert "error" in result
            assert result["tickets"] == []
            assert result["total_results"] == 0

    @pytest.mark.asyncio
    async def test_get_support_ticket_success(self):
        """Get support ticket returns full ticket payload."""
        mock_result = {
            "ticket_id": "ticket-123",
            "title": "Connection reset incidents",
            "doc_type": "support_ticket",
            "full_content": "full ticket content",
        }

        with patch(
            "redis_sre_agent.core.knowledge_helpers.get_support_ticket_helper",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_get.return_value = mock_result

            result = await redis_sre_get_support_ticket(ticket_id="ticket-123")

            assert result["ticket_id"] == "ticket-123"
            assert result["doc_type"] == "support_ticket"
            mock_get.assert_called_once_with(ticket_id="ticket-123")

    @pytest.mark.asyncio
    async def test_get_support_ticket_error_payload_passthrough(self):
        """Get support ticket returns helper error payload."""
        with patch(
            "redis_sre_agent.core.knowledge_helpers.get_support_ticket_helper",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_get.return_value = {
                "ticket_id": "ticket-123",
                "error": "not found",
                "doc_type": "support_ticket",
            }

            result = await redis_sre_get_support_ticket(ticket_id="ticket-123")

            assert result["ticket_id"] == "ticket-123"
            assert result["error"] == "not found"

    @pytest.mark.asyncio
    async def test_get_support_ticket_exception_handling(self):
        """Get support ticket returns error payload on exception."""
        with patch(
            "redis_sre_agent.core.knowledge_helpers.get_support_ticket_helper",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_get.side_effect = Exception("Lookup failed")

            result = await redis_sre_get_support_ticket(ticket_id="ticket-123")

            assert result["ticket_id"] == "ticket-123"
            assert "error" in result


class TestListInstancesTool:
    """Test the redis_sre_list_instances MCP tool."""

    @pytest.mark.asyncio
    async def test_list_instances_success(self):
        """Test successful instance listing."""
        from redis_sre_agent.core.instances import InstanceQueryResult

        mock_instance = MagicMock()
        mock_instance.id = "redis-prod-1"
        mock_instance.name = "Production Redis"
        mock_instance.environment = "production"
        mock_instance.usage = "cache"
        mock_instance.description = "Main cache"
        mock_instance.instance_type = "redis_cloud"
        mock_instance.repo_url = "https://github.com/example/repo"

        mock_result = InstanceQueryResult(
            instances=[mock_instance],
            total=1,
            limit=100,
            offset=0,
        )

        with patch(
            "redis_sre_agent.core.instances.query_instances",
            new_callable=AsyncMock,
        ) as mock_query:
            mock_query.return_value = mock_result

            result = await redis_sre_list_instances()

            assert result["total"] == 1
            assert result["instances"][0]["id"] == "redis-prod-1"
            assert result["instances"][0]["name"] == "Production Redis"
            assert result["instances"][0]["repo_url"] == "https://github.com/example/repo"

    @pytest.mark.asyncio
    async def test_list_instances_empty(self):
        """Test empty instance list."""
        from redis_sre_agent.core.instances import InstanceQueryResult

        mock_result = InstanceQueryResult(
            instances=[],
            total=0,
            limit=100,
            offset=0,
        )

        with patch(
            "redis_sre_agent.core.instances.query_instances",
            new_callable=AsyncMock,
        ) as mock_query:
            mock_query.return_value = mock_result

            result = await redis_sre_list_instances()

            assert result["total"] == 0
            assert result["instances"] == []

    @pytest.mark.asyncio
    async def test_list_instances_with_filters(self):
        """Test instance listing with filter parameters."""
        from redis_sre_agent.core.instances import InstanceQueryResult

        mock_instance = MagicMock()
        mock_instance.id = "redis-prod-1"
        mock_instance.name = "Production Redis"
        mock_instance.environment = "production"
        mock_instance.usage = "cache"
        mock_instance.description = "Main cache"
        mock_instance.instance_type = "redis_cloud"
        mock_instance.repo_url = None

        mock_result = InstanceQueryResult(
            instances=[mock_instance],
            total=1,
            limit=100,
            offset=0,
        )

        with patch(
            "redis_sre_agent.core.instances.query_instances",
            new_callable=AsyncMock,
        ) as mock_query:
            mock_query.return_value = mock_result

            result = await redis_sre_list_instances(
                environment="production",
                usage="cache",
                status="healthy",
            )

            # Verify query_instances was called with the correct parameters
            mock_query.assert_called_once()
            call_kwargs = mock_query.call_args[1]
            assert call_kwargs["environment"] == "production"
            assert call_kwargs["usage"] == "cache"
            assert call_kwargs["status"] == "healthy"

            assert result["total"] == 1
            assert result["instances"][0]["environment"] == "production"

    @pytest.mark.asyncio
    async def test_list_instances_with_search(self):
        """Test instance listing with search parameter."""
        from redis_sre_agent.core.instances import InstanceQueryResult

        mock_instance = MagicMock()
        mock_instance.id = "redis-prod-1"
        mock_instance.name = "Production Redis"
        mock_instance.environment = "production"
        mock_instance.usage = "cache"
        mock_instance.description = "Main cache"
        mock_instance.instance_type = "redis_cloud"
        mock_instance.repo_url = None

        mock_result = InstanceQueryResult(
            instances=[mock_instance],
            total=1,
            limit=100,
            offset=0,
        )

        with patch(
            "redis_sre_agent.core.instances.query_instances",
            new_callable=AsyncMock,
        ) as mock_query:
            mock_query.return_value = mock_result

            result = await redis_sre_list_instances(search="Production")

            # Verify query_instances was called with the search parameter
            mock_query.assert_called_once()
            call_kwargs = mock_query.call_args[1]
            assert call_kwargs["search"] == "Production"

            assert result["total"] == 1
            assert result["instances"][0]["name"] == "Production Redis"

    @pytest.mark.asyncio
    async def test_list_instances_error(self):
        """Test list instances error handling."""
        with patch(
            "redis_sre_agent.core.instances.query_instances",
            new_callable=AsyncMock,
        ) as mock_query:
            mock_query.side_effect = Exception("Connection failed")

            result = await redis_sre_list_instances()

            assert "error" in result
            assert result["instances"] == []


class TestCreateInstanceTool:
    """Test the redis_sre_create_instance MCP tool."""

    @pytest.mark.asyncio
    async def test_create_instance_success(self):
        """Test successful instance creation."""
        with (
            patch(
                "redis_sre_agent.core.instances.get_instances",
                new_callable=AsyncMock,
            ) as mock_get,
            patch(
                "redis_sre_agent.core.instances.save_instances",
                new_callable=AsyncMock,
            ) as mock_save,
        ):
            mock_get.return_value = []
            mock_save.return_value = True

            result = await redis_sre_create_instance(
                name="test-redis",
                connection_url="redis://localhost:6379",
                environment="development",
                usage="cache",
                description="Test instance",
            )

            assert result["status"] == "created"
            assert result["name"] == "test-redis"
            assert "id" in result

    @pytest.mark.asyncio
    async def test_create_instance_invalid_environment(self):
        """Test create instance with invalid environment."""
        result = await redis_sre_create_instance(
            name="test-redis",
            connection_url="redis://localhost:6379",
            environment="invalid",
            usage="cache",
            description="Test",
        )

        assert result["status"] == "failed"
        assert "error" in result
        assert "environment" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_create_instance_invalid_usage(self):
        """Test create instance with invalid usage."""
        result = await redis_sre_create_instance(
            name="test-redis",
            connection_url="redis://localhost:6379",
            environment="development",
            usage="invalid",
            description="Test",
        )

        assert result["status"] == "failed"
        assert "error" in result
        assert "usage" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_create_instance_duplicate_name(self):
        """Test create instance with duplicate name."""
        from unittest.mock import MagicMock

        existing = MagicMock()
        existing.name = "test-redis"

        with patch(
            "redis_sre_agent.core.instances.get_instances",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_get.return_value = [existing]

            result = await redis_sre_create_instance(
                name="test-redis",
                connection_url="redis://localhost:6379",
                environment="development",
                usage="cache",
                description="Test",
            )

            assert result["status"] == "failed"
            assert "already exists" in result["error"]


class TestGetThreadTool:
    """Test the redis_sre_get_thread MCP tool."""

    @pytest.mark.asyncio
    async def test_get_thread_success(self):
        """Test successful thread retrieval."""
        from redis_sre_agent.core.threads import Message, Thread, ThreadMetadata

        # Create a proper Thread object with messages
        mock_thread = Thread(
            thread_id="thread-123",
            messages=[
                Message(role="user", content="Check memory"),
                Message(role="assistant", content="Analyzing..."),
            ],
            context={},
            metadata=ThreadMetadata(),
        )

        mock_redis = AsyncMock()
        mock_redis.zrevrange = AsyncMock(return_value=[])  # No tasks

        with (
            patch("redis_sre_agent.core.redis.get_redis_client", return_value=mock_redis),
            patch(
                "redis_sre_agent.core.threads.ThreadManager.get_thread",
                new_callable=AsyncMock,
            ) as mock_get,
        ):
            mock_get.return_value = mock_thread

            result = await redis_sre_get_thread(thread_id="thread-123")

            assert result["thread_id"] == "thread-123"
            assert result["message_count"] == 2
            assert result["messages"][0]["role"] == "user"

    @pytest.mark.asyncio
    async def test_get_thread_not_found(self):
        """Test thread not found."""
        with (
            patch("redis_sre_agent.core.redis.get_redis_client"),
            patch(
                "redis_sre_agent.core.threads.ThreadManager.get_thread",
                new_callable=AsyncMock,
            ) as mock_get,
        ):
            mock_get.return_value = None

            result = await redis_sre_get_thread(thread_id="nonexistent")

            assert "error" in result
            assert "not found" in result["error"]


class TestListThreadsTool:
    """Test the redis_sre_list_threads MCP tool."""

    @pytest.mark.asyncio
    async def test_list_threads_success(self):
        """Test successful thread listing."""
        from redis_sre_agent.core.threads import Message, Thread, ThreadMetadata

        # Mock thread summaries returned by ThreadManager.list_threads
        mock_summaries = [
            {
                "thread_id": "thread-123",
                "subject": "High memory usage",
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-01T01:00:00Z",
                "user_id": "user-1",
                "instance_id": "redis-prod-1",
                "tags": [],
                "priority": 0,
            },
            {
                "thread_id": "thread-456",
                "subject": "Slow queries",
                "created_at": "2024-01-02T00:00:00Z",
                "updated_at": "2024-01-02T02:00:00Z",
                "user_id": "user-1",
                "instance_id": "redis-prod-2",
                "tags": [],
                "priority": 0,
            },
        ]

        # Mock Thread objects for enrichment
        mock_thread_123 = Thread(
            thread_id="thread-123",
            messages=[
                Message(role="user", content="Check memory"),
                Message(role="assistant", content="Analyzing memory usage..."),
            ],
            metadata=ThreadMetadata(),
        )
        mock_thread_456 = Thread(
            thread_id="thread-456",
            messages=[
                Message(role="user", content="Why slow?"),
            ],
            metadata=ThreadMetadata(),
        )

        async def mock_get_thread(thread_id):
            if thread_id == "thread-123":
                return mock_thread_123
            elif thread_id == "thread-456":
                return mock_thread_456
            return None

        with (
            patch("redis_sre_agent.core.redis.get_redis_client"),
            patch(
                "redis_sre_agent.core.threads.ThreadManager.list_threads",
                new_callable=AsyncMock,
            ) as mock_list,
            patch(
                "redis_sre_agent.core.threads.ThreadManager.get_thread",
                new_callable=AsyncMock,
            ) as mock_get,
        ):
            mock_list.return_value = mock_summaries
            mock_get.side_effect = mock_get_thread

            result = await redis_sre_list_threads()

            assert result["total"] == 2
            assert len(result["threads"]) == 2
            assert result["threads"][0]["thread_id"] == "thread-123"
            assert result["threads"][0]["subject"] == "High memory usage"
            assert result["threads"][0]["message_count"] == 2
            assert result["threads"][1]["message_count"] == 1
            assert result["limit"] == 50
            assert result["offset"] == 0

    @pytest.mark.asyncio
    async def test_list_threads_with_user_filter(self):
        """Test listing threads filtered by user_id."""
        mock_summaries = [
            {
                "thread_id": "thread-123",
                "subject": "User 1 thread",
                "user_id": "user-1",
                "instance_id": None,
                "tags": [],
                "priority": 0,
            }
        ]

        with (
            patch("redis_sre_agent.core.redis.get_redis_client"),
            patch(
                "redis_sre_agent.core.threads.ThreadManager.list_threads",
                new_callable=AsyncMock,
            ) as mock_list,
            patch(
                "redis_sre_agent.core.threads.ThreadManager.get_thread",
                new_callable=AsyncMock,
            ) as mock_get,
        ):
            mock_list.return_value = mock_summaries
            mock_get.return_value = None

            result = await redis_sre_list_threads(user_id="user-1")

            # Verify user_id was passed to list_threads
            mock_list.assert_called_once()
            call_kwargs = mock_list.call_args.kwargs
            assert call_kwargs["user_id"] == "user-1"

            assert result["total"] == 1
            assert result["threads"][0]["user_id"] == "user-1"

    @pytest.mark.asyncio
    async def test_list_threads_with_instance_filter(self):
        """Test listing threads filtered by instance_id."""
        # Return threads with different instance_ids
        mock_summaries = [
            {
                "thread_id": "thread-123",
                "subject": "Prod issue",
                "user_id": None,
                "instance_id": "redis-prod-1",
                "tags": [],
                "priority": 0,
            },
            {
                "thread_id": "thread-456",
                "subject": "Staging issue",
                "user_id": None,
                "instance_id": "redis-staging-1",
                "tags": [],
                "priority": 0,
            },
        ]

        with (
            patch("redis_sre_agent.core.redis.get_redis_client"),
            patch(
                "redis_sre_agent.core.threads.ThreadManager.list_threads",
                new_callable=AsyncMock,
            ) as mock_list,
            patch(
                "redis_sre_agent.core.threads.ThreadManager.get_thread",
                new_callable=AsyncMock,
            ) as mock_get,
        ):
            mock_list.return_value = mock_summaries
            mock_get.return_value = None

            # Filter to only redis-prod-1
            result = await redis_sre_list_threads(instance_id="redis-prod-1")

            # Should filter in-memory to only matching instance
            assert result["total"] == 1
            assert result["threads"][0]["instance_id"] == "redis-prod-1"

    @pytest.mark.asyncio
    async def test_list_threads_pagination(self):
        """Test thread listing with pagination parameters."""
        mock_summaries = []

        with (
            patch("redis_sre_agent.core.redis.get_redis_client"),
            patch(
                "redis_sre_agent.core.threads.ThreadManager.list_threads",
                new_callable=AsyncMock,
            ) as mock_list,
        ):
            mock_list.return_value = mock_summaries

            result = await redis_sre_list_threads(limit=10, offset=20)

            # Verify pagination params passed correctly
            mock_list.assert_called_once()
            call_kwargs = mock_list.call_args.kwargs
            assert call_kwargs["limit"] == 10
            assert call_kwargs["offset"] == 20

            assert result["limit"] == 10
            assert result["offset"] == 20

    @pytest.mark.asyncio
    async def test_list_threads_limit_clamped(self):
        """Test that limit is clamped to valid range (1-100)."""
        with (
            patch("redis_sre_agent.core.redis.get_redis_client"),
            patch(
                "redis_sre_agent.core.threads.ThreadManager.list_threads",
                new_callable=AsyncMock,
            ) as mock_list,
        ):
            mock_list.return_value = []

            # Test with too high limit (max is 100)
            result = await redis_sre_list_threads(limit=200)
            call_kwargs = mock_list.call_args.kwargs
            assert call_kwargs["limit"] == 100
            assert result["limit"] == 100

            # Test with too low limit (min is 1)
            result = await redis_sre_list_threads(limit=0)
            call_kwargs = mock_list.call_args.kwargs
            assert call_kwargs["limit"] == 1
            assert result["limit"] == 1

            # Test with negative offset (clamped to 0)
            result = await redis_sre_list_threads(offset=-5)
            call_kwargs = mock_list.call_args.kwargs
            assert call_kwargs["offset"] == 0
            assert result["offset"] == 0

    @pytest.mark.asyncio
    async def test_list_threads_empty(self):
        """Test empty thread list."""
        with (
            patch("redis_sre_agent.core.redis.get_redis_client"),
            patch(
                "redis_sre_agent.core.threads.ThreadManager.list_threads",
                new_callable=AsyncMock,
            ) as mock_list,
        ):
            mock_list.return_value = []

            result = await redis_sre_list_threads()

            assert result["total"] == 0
            assert result["threads"] == []
            assert result["has_more"] is False

    @pytest.mark.asyncio
    async def test_list_threads_has_more_pagination_hint(self):
        """Test has_more is True when result count equals limit."""
        # When we get exactly `limit` results, there may be more
        mock_summaries = [
            {"thread_id": f"thread-{i}", "subject": f"Thread {i}", "tags": [], "priority": 0}
            for i in range(5)
        ]

        with (
            patch("redis_sre_agent.core.redis.get_redis_client"),
            patch(
                "redis_sre_agent.core.threads.ThreadManager.list_threads",
                new_callable=AsyncMock,
            ) as mock_list,
            patch(
                "redis_sre_agent.core.threads.ThreadManager.get_thread",
                new_callable=AsyncMock,
            ) as mock_get,
        ):
            mock_list.return_value = mock_summaries
            mock_get.return_value = None

            result = await redis_sre_list_threads(limit=5)

            assert result["has_more"] is True

    @pytest.mark.asyncio
    async def test_list_threads_error_handling(self):
        """Test list threads error handling."""
        with (
            patch("redis_sre_agent.core.redis.get_redis_client"),
            patch(
                "redis_sre_agent.core.threads.ThreadManager.list_threads",
                new_callable=AsyncMock,
            ) as mock_list,
        ):
            mock_list.side_effect = Exception("Redis connection failed")

            result = await redis_sre_list_threads()

            assert "error" in result
            assert result["threads"] == []
            assert result["total"] == 0

    @pytest.mark.asyncio
    async def test_list_threads_enrichment_error_fallback(self):
        """Test that enrichment errors don't fail the entire listing."""
        from redis_sre_agent.core.threads import Message, Thread, ThreadMetadata

        mock_summaries = [
            {
                "thread_id": "thread-ok",
                "subject": "Works",
                "tags": [],
                "priority": 0,
            },
            {
                "thread_id": "thread-fail",
                "subject": "Fails enrichment",
                "tags": [],
                "priority": 0,
            },
        ]

        mock_thread_ok = Thread(
            thread_id="thread-ok",
            messages=[Message(role="user", content="Hi")],
            metadata=ThreadMetadata(),
        )

        async def mock_get_thread(thread_id):
            if thread_id == "thread-ok":
                return mock_thread_ok
            elif thread_id == "thread-fail":
                raise Exception("Enrichment failed")
            return None

        with (
            patch("redis_sre_agent.core.redis.get_redis_client"),
            patch(
                "redis_sre_agent.core.threads.ThreadManager.list_threads",
                new_callable=AsyncMock,
            ) as mock_list,
            patch(
                "redis_sre_agent.core.threads.ThreadManager.get_thread",
                new_callable=AsyncMock,
            ) as mock_get,
        ):
            mock_list.return_value = mock_summaries
            mock_get.side_effect = mock_get_thread

            result = await redis_sre_list_threads()

            # Both threads should be in results
            assert result["total"] == 2
            # First thread enriched successfully
            assert result["threads"][0]["message_count"] == 1
            # Second thread fell back to 0
            assert result["threads"][1]["message_count"] == 0

    @pytest.mark.asyncio
    async def test_list_threads_latest_message_truncation(self):
        """Test that latest_message is truncated to 100 chars."""
        from redis_sre_agent.core.threads import Message, Thread, ThreadMetadata

        long_content = "A" * 200  # 200 character message

        mock_summaries = [
            {"thread_id": "thread-123", "subject": "Long message", "tags": [], "priority": 0}
        ]

        mock_thread = Thread(
            thread_id="thread-123",
            messages=[
                Message(role="user", content="Hello"),
                Message(role="assistant", content=long_content),
            ],
            metadata=ThreadMetadata(),
        )

        with (
            patch("redis_sre_agent.core.redis.get_redis_client"),
            patch(
                "redis_sre_agent.core.threads.ThreadManager.list_threads",
                new_callable=AsyncMock,
            ) as mock_list,
            patch(
                "redis_sre_agent.core.threads.ThreadManager.get_thread",
                new_callable=AsyncMock,
            ) as mock_get,
        ):
            mock_list.return_value = mock_summaries
            mock_get.return_value = mock_thread

            result = await redis_sre_list_threads()

            # Latest message should be truncated
            latest = result["threads"][0]["latest_message"]
            assert len(latest) == 103  # 100 chars + "..."
            assert latest.endswith("...")


class TestGetTaskStatusTool:
    """Test the redis_sre_get_task_status MCP tool."""

    @pytest.mark.asyncio
    async def test_get_task_status_success(self):
        """Test successful task status retrieval."""
        # Mock returns data in the format that get_task_by_id actually returns
        mock_task = {
            "task_id": "task-123",
            "thread_id": "thread-456",
            "status": "done",
            "updates": [
                {"timestamp": "2024-01-01T00:00:30Z", "message": "Processing", "type": "progress"}
            ],
            "result": {"summary": "Complete"},
            "tool_calls": [{"name": "redis_info", "args": {"section": "memory"}}],
            "error_message": None,
            "metadata": {
                "subject": "Health check",
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-01T00:01:00Z",
                "user_id": None,
            },
            "context": {},
        }

        with patch(
            "redis_sre_agent.core.tasks.get_task_by_id",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_get.return_value = mock_task

            result = await redis_sre_get_task_status(task_id="task-123")

            assert result["task_id"] == "task-123"
            assert result["status"] == "done"
            assert result["thread_id"] == "thread-456"
            assert result["subject"] == "Health check"
            assert result["created_at"] == "2024-01-01T00:00:00Z"
            assert result["updated_at"] == "2024-01-01T00:01:00Z"
            assert result["updates"] == mock_task["updates"]
            assert result["result"] == {"summary": "Complete"}
            assert "tool_calls" not in result

    @pytest.mark.asyncio
    async def test_get_task_status_not_found(self):
        """Test task not found."""
        with patch(
            "redis_sre_agent.core.tasks.get_task_by_id",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_get.side_effect = ValueError("Task task-999 not found")

            result = await redis_sre_get_task_status(task_id="task-999")

            assert result["status"] == "not_found"
            assert "error" in result


class TestGetTaskCitationsTool:
    """Test the redis_sre_get_task_citations MCP tool."""

    @pytest.mark.asyncio
    async def test_get_task_citations_success(self):
        """Test successful citation retrieval."""
        mock_task = {
            "task_id": "task-123",
            "thread_id": "thread-456",
            "status": "done",
            "tool_calls": [{"name": "redis_info", "args": {"section": "memory"}}],
        }

        with patch(
            "redis_sre_agent.core.tasks.get_task_by_id",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_get.return_value = mock_task

            result = await redis_sre_get_task_citations(task_id="task-123")

            assert result["task_id"] == "task-123"
            assert result["thread_id"] == "thread-456"
            assert result["status"] == "done"
            assert result["citation_count"] == 1
            assert result["tool_calls"] == mock_task["tool_calls"]

    @pytest.mark.asyncio
    async def test_get_task_citations_not_found(self):
        """Test citation lookup for missing task."""
        with patch(
            "redis_sre_agent.core.tasks.get_task_by_id",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_get.side_effect = ValueError("Task task-999 not found")

            result = await redis_sre_get_task_citations(task_id="task-999")

            assert result["status"] == "not_found"
            assert "error" in result


class TestDeleteTaskTool:
    """Test the redis_sre_delete_task MCP tool."""

    @pytest.mark.asyncio
    async def test_delete_task_success(self):
        """Task delete should cancel via Docket and call core delete."""

        mock_client = AsyncMock()

        with (
            patch("redis_sre_agent.core.redis.get_redis_client", return_value=mock_client),
            patch(
                "redis_sre_agent.core.tasks.delete_task",
                new_callable=AsyncMock,
            ) as mock_delete,
            patch(
                "redis_sre_agent.core.docket_tasks.get_redis_url", new_callable=AsyncMock
            ) as mock_url,
            patch("docket.Docket") as mock_docket,
        ):
            mock_url.return_value = "redis://test"

            # Configure Docket context manager with async cancel
            docket_instance = AsyncMock()
            docket_instance.__aenter__.return_value = docket_instance
            docket_instance.__aexit__.return_value = False
            mock_docket.return_value = docket_instance

            result = await redis_sre_delete_task(task_id="task-123")

            mock_delete.assert_awaited_once_with(task_id="task-123", redis_client=mock_client)
            docket_instance.cancel.assert_awaited_once_with("task-123")
            assert result["status"] == "deleted"
            assert result["task_id"] == "task-123"

    @pytest.mark.asyncio
    async def test_delete_task_failure(self):
        """If core delete fails, tool should return error payload."""

        mock_client = AsyncMock()

        with (
            patch("redis_sre_agent.core.redis.get_redis_client", return_value=mock_client),
            patch(
                "redis_sre_agent.core.tasks.delete_task",
                new_callable=AsyncMock,
            ) as mock_delete,
            patch("redis_sre_agent.core.docket_tasks.get_redis_url", new_callable=AsyncMock),
            patch("docket.Docket") as mock_docket,
        ):
            mock_delete.side_effect = Exception("boom")

            docket_instance = AsyncMock()
            docket_instance.__aenter__.return_value = docket_instance
            docket_instance.__aexit__.return_value = False
            mock_docket.return_value = docket_instance

            result = await redis_sre_delete_task(task_id="task-err")

            mock_delete.assert_awaited_once()
            assert result["status"] == "error"
            assert result["task_id"] == "task-err"
            assert "boom" in result["error"]
