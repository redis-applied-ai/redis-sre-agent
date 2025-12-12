"""Unit tests for Docket task system and SRE tasks."""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from redis_sre_agent.core.docket_tasks import (
    SRE_TASK_COLLECTION,
    register_sre_tasks,
    search_knowledge_base,
    test_task_system,
)


class TestSRETaskCollection:
    """Test SRE task registry."""

    def test_sre_task_collection_populated(self):
        """Test that SRE task collection contains expected tasks."""
        assert len(SRE_TASK_COLLECTION) == 6

        task_names = [task.__name__ for task in SRE_TASK_COLLECTION]
        expected_tasks = [
            "search_knowledge_base",
            "ingest_sre_document",
            "scheduler_task",
            "process_agent_turn",
            "process_chat_turn",  # New: MCP chat task
            "process_knowledge_query",  # New: MCP knowledge query task
        ]

        for expected_task in expected_tasks:
            assert expected_task in task_names


class TestSearchRunbookKnowledge:
    """Test search_knowledge_base task."""

    @pytest.mark.asyncio
    async def test_search_knowledge_success(self, mock_search_index, mock_vectorizer):
        """Test successful knowledge search."""
        # Mock vector embedding
        mock_vectorizer.aembed_many = AsyncMock(return_value=[[0.1] * 1536])

        # Mock search results
        mock_search_results = [
            {
                "title": "Redis Memory Alert",
                "content": "Memory usage troubleshooting guide",
                "source": "runbook.md",
                "score": 0.95,
            }
        ]
        mock_search_index.query.return_value = mock_search_results

        with (
            patch(
                "redis_sre_agent.core.knowledge_helpers.get_knowledge_index",
                return_value=mock_search_index,
            ),
            patch(
                "redis_sre_agent.core.knowledge_helpers.get_vectorizer",
                return_value=mock_vectorizer,
            ),
        ):
            result = await search_knowledge_base(
                query="redis memory issues", category="monitoring", limit=3
            )

        assert result["query"] == "redis memory issues"
        assert result["category"] == "monitoring"
        assert result["results_count"] == 1
        assert len(result["results"]) == 1
        assert result["results"][0]["title"] == "Redis Memory Alert"
        assert "task_id" in result

        # Verify method calls
        mock_vectorizer.aembed_many.assert_called_once_with(["redis memory issues"])
        mock_search_index.query.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_knowledge_no_category(self, mock_search_index, mock_vectorizer):
        """Test knowledge search without category filter."""
        mock_vectorizer.aembed_many = AsyncMock(return_value=[[0.1] * 1536])
        mock_search_index.query.return_value = []

        with (
            patch(
                "redis_sre_agent.core.knowledge_helpers.get_knowledge_index",
                return_value=mock_search_index,
            ),
            patch(
                "redis_sre_agent.core.knowledge_helpers.get_vectorizer",
                return_value=mock_vectorizer,
            ),
        ):
            result = await search_knowledge_base(query="general help", category=None)

        assert result["query"] == "general help"
        assert result["category"] is None
        assert result["results_count"] == 0

    @pytest.mark.asyncio
    async def test_search_knowledge_vectorizer_failure(self, mock_vectorizer):
        """Test knowledge search with vectorizer failure."""
        mock_vectorizer.aembed_many.side_effect = Exception("OpenAI API error")

        with patch(
            "redis_sre_agent.core.knowledge_helpers.get_vectorizer", return_value=mock_vectorizer
        ):
            with pytest.raises(Exception, match="OpenAI API error"):
                await search_knowledge_base("test query")


class TestTaskSystemManagement:
    """Test task system management functions."""

    @pytest.mark.asyncio
    async def test_register_sre_tasks_success(self):
        """Test successful task registration."""
        with (
            patch("redis_sre_agent.core.docket_tasks.Docket") as mock_docket_class,
            patch(
                "redis_sre_agent.core.docket_tasks.get_redis_url",
                return_value="redis://localhost:6379",
            ),
        ):
            # Set up the mock properly
            mock_docket_instance = AsyncMock()
            mock_docket_instance.__aenter__ = AsyncMock(return_value=mock_docket_instance)
            mock_docket_instance.__aexit__ = AsyncMock(return_value=None)
            mock_docket_instance.register = Mock()  # Synchronous, not async
            mock_docket_class.return_value = mock_docket_instance

            await register_sre_tasks()

            # Verify Docket was created and tasks registered
            mock_docket_instance.register.assert_called()
            assert mock_docket_instance.register.call_count == len(SRE_TASK_COLLECTION)

    @pytest.mark.asyncio
    async def test_register_sre_tasks_failure(self):
        """Test task registration failure."""
        with (
            patch("redis_sre_agent.core.docket_tasks.Docket") as mock_docket_class,
            patch(
                "redis_sre_agent.core.docket_tasks.get_redis_url",
                return_value="redis://localhost:6379",
            ),
        ):
            mock_docket_instance = AsyncMock()
            mock_docket_instance.__aenter__ = AsyncMock(side_effect=Exception("Connection failed"))
            mock_docket_class.return_value = mock_docket_instance

            with pytest.raises(Exception, match="Connection failed"):
                await register_sre_tasks()

    @pytest.mark.asyncio
    async def test_task_system_test_success(self):
        """Test task system connectivity test success."""
        with patch("redis_sre_agent.core.docket_tasks.Docket") as mock_docket_class:
            mock_docket_instance = AsyncMock()
            mock_docket_instance.__aenter__ = AsyncMock(return_value=mock_docket_instance)
            mock_docket_instance.__aexit__ = AsyncMock(return_value=None)
            mock_docket_class.return_value = mock_docket_instance

            with patch(
                "redis_sre_agent.core.docket_tasks.get_redis_url",
                return_value="redis://localhost:6379",
            ):
                result = await test_task_system()

        assert result is True

    @pytest.mark.asyncio
    async def test_task_system_test_failure(self):
        """Test task system connectivity test failure."""
        with patch("redis_sre_agent.core.docket_tasks.Docket") as mock_docket_class:
            mock_docket_class.side_effect = Exception("Connection failed")

            with patch(
                "redis_sre_agent.core.docket_tasks.get_redis_url",
                return_value="redis://localhost:6379",
            ):
                result = await test_task_system()

        assert result is False
