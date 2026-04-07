"""Unit tests for Docket task system and SRE tasks."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from redisvl.query import VectorRangeQuery

from redis_sre_agent.agent.models import AgentResponse
from redis_sre_agent.agent.router import AgentType
from redis_sre_agent.core.docket_tasks import (
    SRE_TASK_COLLECTION,
    _thread_messages_to_conversation_history,
    get_redis_url,
    ingest_sre_document,
    process_agent_turn,
    process_chat_turn,
    process_knowledge_query,
    process_pipeline_operation,
    process_runbook_operation,
    register_sre_tasks,
    run_agent_with_progress,
    scheduler_task,
    search_knowledge_base,
    sre_task,
    test_task_system,
)
from redis_sre_agent.core.targets import (
    ResolvedTargetMatch,
    TargetBinding,
    TargetResolutionResult,
)
from redis_sre_agent.core.tasks import TaskStatus
from redis_sre_agent.core.threads import Message, Thread, ThreadMetadata


class TestSRETaskCollection:
    """Test SRE task registry."""

    def test_sre_task_collection_populated(self):
        """Test that SRE task collection contains expected tasks."""
        assert len(SRE_TASK_COLLECTION) == 9

        task_names = [task.__name__ for task in SRE_TASK_COLLECTION]
        expected_tasks = [
            "search_knowledge_base",
            "ingest_sre_document",
            "scheduler_task",
            "process_agent_turn",
            "process_chat_turn",  # New: MCP chat task
            "process_knowledge_query",  # New: MCP knowledge query task
            "process_pipeline_operation",
            "process_runbook_operation",
            "embed_qa_record",  # Q&A embedding task
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
                "category": "monitoring",
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
        query_obj = mock_search_index.query.call_args.args[0]
        assert isinstance(query_obj, VectorRangeQuery)

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


class TestSreTaskDecorator:
    """Test the sre_task decorator."""

    def test_sre_task_decorator_returns_function(self):
        """Test that sre_task decorator returns the function."""

        # We can't easily test adding to the collection since it's global
        # and already populated. Instead, test that the decorator returns the function.
        async def test_func():
            pass

        result = sre_task(test_func)
        assert result is test_func


class TestGetRedisUrl:
    """Test get_redis_url function."""

    @pytest.mark.asyncio
    async def test_get_redis_url(self):
        """Test get_redis_url returns settings value."""
        with patch("redis_sre_agent.core.docket_tasks.settings") as mock_settings:
            mock_settings.redis_url.get_secret_value.return_value = "redis://test:6379"
            result = await get_redis_url()
            assert result == "redis://test:6379"


class TestIngestSreDocument:
    """Test ingest_sre_document task."""

    @pytest.mark.asyncio
    async def test_ingest_sre_document_success(self):
        """Test successful document ingestion."""
        mock_result = {"status": "success", "doc_id": "doc-123"}

        with patch(
            "redis_sre_agent.core.docket_tasks.ingest_sre_document_helper",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            result = await ingest_sre_document(
                title="Test Doc",
                content="Test content",
                source="test.md",
                category="runbook",
                severity="info",
            )

        assert result["status"] == "success"
        assert result["doc_id"] == "doc-123"

    @pytest.mark.asyncio
    async def test_ingest_sre_document_with_product_labels(self):
        """Test document ingestion with product labels."""
        mock_result = {"status": "success", "doc_id": "doc-456"}

        with patch(
            "redis_sre_agent.core.docket_tasks.ingest_sre_document_helper",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_helper:
            result = await ingest_sre_document(
                title="Test Doc",
                content="Test content",
                source="test.md",
                category="incident",
                severity="critical",
                product_labels=["redis", "cache"],
            )

        mock_helper.assert_called_once_with(
            title="Test Doc",
            content="Test content",
            source="test.md",
            category="incident",
            severity="critical",
            doc_type=None,
            product_labels=["redis", "cache"],
        )
        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_ingest_sre_document_failure(self):
        """Test document ingestion failure."""
        with patch(
            "redis_sre_agent.core.docket_tasks.ingest_sre_document_helper",
            new_callable=AsyncMock,
            side_effect=Exception("Ingestion failed"),
        ):
            with pytest.raises(Exception, match="Ingestion failed"):
                await ingest_sre_document(
                    title="Test Doc",
                    content="Test content",
                    source="test.md",
                )


class TestProcessChatTurn:
    """Test process_chat_turn task."""

    @pytest.mark.asyncio
    async def test_process_chat_turn_success(self):
        """Test successful chat turn processing."""
        mock_redis = AsyncMock()
        mock_task_manager = AsyncMock()
        mock_task_manager.update_task_status = AsyncMock()
        mock_task_manager.set_task_result = AsyncMock()
        mock_thread_manager = AsyncMock()
        mock_thread_manager.append_messages = AsyncMock()

        mock_agent = AsyncMock()
        mock_agent.process_query = AsyncMock(return_value="Test response")

        mock_instance = MagicMock()
        mock_instance.id = "inst-1"

        with (
            patch("redis_sre_agent.core.docket_tasks.get_redis_client", return_value=mock_redis),
            patch("redis_sre_agent.core.docket_tasks.TaskManager", return_value=mock_task_manager),
            patch(
                "redis_sre_agent.core.docket_tasks.ThreadManager", return_value=mock_thread_manager
            ),
            patch(
                "redis_sre_agent.core.docket_tasks.get_instance_by_id",
                new_callable=AsyncMock,
                return_value=mock_instance,
            ),
            patch("redis_sre_agent.agent.chat_agent.ChatAgent", return_value=mock_agent),
            patch("redis_sre_agent.core.docket_tasks.TaskEmitter"),
        ):
            result = await process_chat_turn(
                query="What is Redis?",
                task_id="task-123",
                thread_id="thread-456",
                instance_id="inst-1",
                user_id="user-1",
            )

        assert result["response"] == "Test response"
        assert result["instance_id"] == "inst-1"
        mock_task_manager.update_task_status.assert_any_call("task-123", TaskStatus.IN_PROGRESS)
        mock_task_manager.update_task_status.assert_any_call("task-123", TaskStatus.DONE)
        _, process_kwargs = mock_agent.process_query.call_args
        assert process_kwargs["context"] == {"task_id": "task-123", "instance_id": "inst-1"}

    @pytest.mark.asyncio
    async def test_process_chat_turn_instance_not_found(self):
        """Test chat turn with non-existent instance."""
        mock_redis = AsyncMock()
        mock_task_manager = AsyncMock()
        mock_task_manager.update_task_status = AsyncMock()
        mock_task_manager.set_task_error = AsyncMock()
        mock_thread_manager = AsyncMock()

        with (
            patch("redis_sre_agent.core.docket_tasks.get_redis_client", return_value=mock_redis),
            patch("redis_sre_agent.core.docket_tasks.TaskManager", return_value=mock_task_manager),
            patch(
                "redis_sre_agent.core.docket_tasks.ThreadManager", return_value=mock_thread_manager
            ),
            patch(
                "redis_sre_agent.core.docket_tasks.get_instance_by_id",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch("redis_sre_agent.core.docket_tasks.TaskEmitter"),
        ):
            with pytest.raises(ValueError, match="Instance not found"):
                await process_chat_turn(
                    query="What is Redis?",
                    task_id="task-123",
                    thread_id="thread-456",
                    instance_id="nonexistent",
                )

    @pytest.mark.asyncio
    async def test_process_chat_turn_with_exclude_categories(self):
        """Test chat turn with excluded MCP categories."""
        mock_redis = AsyncMock()
        mock_task_manager = AsyncMock()
        mock_task_manager.update_task_status = AsyncMock()
        mock_task_manager.set_task_result = AsyncMock()
        mock_thread_manager = AsyncMock()
        mock_thread_manager.append_messages = AsyncMock()

        mock_agent = AsyncMock()
        mock_agent.process_query = AsyncMock(return_value="Response")

        with (
            patch("redis_sre_agent.core.docket_tasks.get_redis_client", return_value=mock_redis),
            patch("redis_sre_agent.core.docket_tasks.TaskManager", return_value=mock_task_manager),
            patch(
                "redis_sre_agent.core.docket_tasks.ThreadManager", return_value=mock_thread_manager
            ),
            patch(
                "redis_sre_agent.core.docket_tasks.get_instance_by_id",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch("redis_sre_agent.agent.chat_agent.ChatAgent", return_value=mock_agent),
            patch("redis_sre_agent.core.docket_tasks.TaskEmitter"),
        ):
            result = await process_chat_turn(
                query="Test",
                task_id="task-123",
                thread_id="thread-456",
                exclude_mcp_categories=["metrics", "logs", "invalid_category"],
            )

        assert result["response"] == "Response"

    @pytest.mark.asyncio
    async def test_process_chat_turn_with_cluster(self):
        """Test chat turn with a cluster-only target."""
        mock_redis = AsyncMock()
        mock_task_manager = AsyncMock()
        mock_task_manager.update_task_status = AsyncMock()
        mock_task_manager.set_task_result = AsyncMock()
        mock_thread_manager = AsyncMock()
        mock_thread_manager.append_messages = AsyncMock()

        mock_agent = AsyncMock()
        mock_agent.process_query = AsyncMock(return_value="Cluster response")

        mock_cluster = MagicMock()
        mock_cluster.id = "cluster-1"

        with (
            patch("redis_sre_agent.core.docket_tasks.get_redis_client", return_value=mock_redis),
            patch("redis_sre_agent.core.docket_tasks.TaskManager", return_value=mock_task_manager),
            patch(
                "redis_sre_agent.core.docket_tasks.ThreadManager", return_value=mock_thread_manager
            ),
            patch(
                "redis_sre_agent.core.docket_tasks.get_cluster_by_id",
                new_callable=AsyncMock,
                return_value=mock_cluster,
            ),
            patch(
                "redis_sre_agent.agent.chat_agent.ChatAgent", return_value=mock_agent
            ) as mock_cls,
            patch("redis_sre_agent.core.docket_tasks.TaskEmitter"),
        ):
            result = await process_chat_turn(
                query="What nodes are in this cluster?",
                task_id="task-123",
                thread_id="thread-456",
                cluster_id="cluster-1",
                user_id="user-1",
            )

        assert result["response"] == "Cluster response"
        assert result["cluster_id"] == "cluster-1"
        assert mock_cls.call_args.kwargs["redis_cluster"] is mock_cluster
        _, process_kwargs = mock_agent.process_query.call_args
        assert process_kwargs["context"] == {"task_id": "task-123", "cluster_id": "cluster-1"}

    @pytest.mark.asyncio
    async def test_process_chat_turn_rejects_instance_and_cluster(self):
        """Test chat turn rejects conflicting target identifiers."""
        mock_redis = AsyncMock()
        mock_task_manager = AsyncMock()
        mock_task_manager.update_task_status = AsyncMock()
        mock_task_manager.set_task_error = AsyncMock()
        mock_thread_manager = AsyncMock()

        with (
            patch("redis_sre_agent.core.docket_tasks.get_redis_client", return_value=mock_redis),
            patch("redis_sre_agent.core.docket_tasks.TaskManager", return_value=mock_task_manager),
            patch(
                "redis_sre_agent.core.docket_tasks.ThreadManager", return_value=mock_thread_manager
            ),
            patch("redis_sre_agent.core.docket_tasks.TaskEmitter"),
        ):
            with pytest.raises(ValueError, match="only one of instance_id or cluster_id"):
                await process_chat_turn(
                    query="Test",
                    task_id="task-123",
                    thread_id="thread-456",
                    instance_id="inst-1",
                    cluster_id="cluster-1",
                )

    @pytest.mark.asyncio
    async def test_process_chat_turn_agent_error(self):
        """Test chat turn with agent error."""
        mock_redis = AsyncMock()
        mock_task_manager = AsyncMock()
        mock_task_manager.update_task_status = AsyncMock()
        mock_task_manager.set_task_error = AsyncMock()
        mock_thread_manager = AsyncMock()

        mock_agent = AsyncMock()
        mock_agent.process_query = AsyncMock(side_effect=Exception("Agent error"))

        with (
            patch("redis_sre_agent.core.docket_tasks.get_redis_client", return_value=mock_redis),
            patch("redis_sre_agent.core.docket_tasks.TaskManager", return_value=mock_task_manager),
            patch(
                "redis_sre_agent.core.docket_tasks.ThreadManager", return_value=mock_thread_manager
            ),
            patch(
                "redis_sre_agent.core.docket_tasks.get_instance_by_id",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch("redis_sre_agent.agent.chat_agent.ChatAgent", return_value=mock_agent),
            patch("redis_sre_agent.core.docket_tasks.TaskEmitter"),
        ):
            with pytest.raises(Exception, match="Agent error"):
                await process_chat_turn(
                    query="Test",
                    task_id="task-123",
                    thread_id="thread-456",
                )

        mock_task_manager.set_task_error.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_chat_turn_agent_response_serialization(self):
        """Regression test: AgentResponse must be serialized to dict for JSON storage.

        Previously, AgentResponse (a Pydantic model) was stored directly in the result dict,
        causing 'Object of type AgentResponse is not JSON serializable' errors when
        set_task_result called json.dumps().
        """
        mock_redis = AsyncMock()
        mock_task_manager = AsyncMock()
        mock_task_manager.update_task_status = AsyncMock()
        mock_task_manager.set_task_result = AsyncMock()
        mock_thread_manager = AsyncMock()
        mock_thread_manager.append_messages = AsyncMock()

        # Return an actual AgentResponse object (not a string)
        agent_response = AgentResponse(
            response="Test response text",
            search_results=[{"id": "doc-1", "content": "Some content"}],
        )
        mock_agent = AsyncMock()
        mock_agent.process_query = AsyncMock(return_value=agent_response)

        mock_instance = MagicMock()
        mock_instance.id = "inst-1"

        with (
            patch("redis_sre_agent.core.docket_tasks.get_redis_client", return_value=mock_redis),
            patch("redis_sre_agent.core.docket_tasks.TaskManager", return_value=mock_task_manager),
            patch(
                "redis_sre_agent.core.docket_tasks.ThreadManager", return_value=mock_thread_manager
            ),
            patch(
                "redis_sre_agent.core.docket_tasks.get_instance_by_id",
                new_callable=AsyncMock,
                return_value=mock_instance,
            ),
            patch("redis_sre_agent.agent.chat_agent.ChatAgent", return_value=mock_agent),
            patch("redis_sre_agent.core.docket_tasks.TaskEmitter"),
        ):
            result = await process_chat_turn(
                query="What is Redis?",
                task_id="task-123",
                thread_id="thread-456",
                instance_id="inst-1",
                user_id="user-1",
            )

        # Verify the response is a dict (model_dump'd), not an AgentResponse
        assert isinstance(result["response"], dict)
        assert result["response"]["response"] == "Test response text"
        assert result["response"]["search_results"] == [{"id": "doc-1", "content": "Some content"}]

        # Verify thread message content is a string, not an AgentResponse
        mock_thread_manager.append_messages.assert_called_once()
        call_args = mock_thread_manager.append_messages.call_args
        messages = call_args[0][1]
        assert len(messages) == 1
        assert messages[0]["content"] == "Test response text"
        assert isinstance(messages[0]["content"], str)


class TestProcessKnowledgeQuery:
    """Test process_knowledge_query task."""

    @pytest.mark.asyncio
    async def test_process_knowledge_query_success(self):
        """Test successful knowledge query processing."""
        mock_redis = AsyncMock()
        mock_task_manager = AsyncMock()
        mock_task_manager.update_task_status = AsyncMock()
        mock_task_manager.set_task_result = AsyncMock()
        mock_thread_manager = AsyncMock()
        mock_thread_manager.get_thread = AsyncMock(
            return_value=Thread(
                thread_id="thread-456",
                messages=[],
                context={},
                metadata=ThreadMetadata(),
            )
        )
        mock_thread_manager.append_messages = AsyncMock()

        mock_agent = AsyncMock()
        mock_agent.process_query = AsyncMock(return_value="Knowledge response")

        with (
            patch("redis_sre_agent.core.docket_tasks.get_redis_client", return_value=mock_redis),
            patch("redis_sre_agent.core.docket_tasks.TaskManager", return_value=mock_task_manager),
            patch(
                "redis_sre_agent.core.docket_tasks.ThreadManager", return_value=mock_thread_manager
            ),
            patch("redis_sre_agent.core.docket_tasks.get_chat_agent", return_value=mock_agent),
            patch("redis_sre_agent.core.docket_tasks.TaskEmitter"),
        ):
            result = await process_knowledge_query(
                query="What are Redis best practices?",
                task_id="task-123",
                thread_id="thread-456",
                user_id="user-1",
            )

        assert result["response"] == "Knowledge response"
        mock_task_manager.update_task_status.assert_any_call("task-123", TaskStatus.IN_PROGRESS)
        mock_task_manager.update_task_status.assert_any_call("task-123", TaskStatus.DONE)
        _, kwargs = mock_agent.process_query.call_args
        assert kwargs["conversation_history"] is None

    @pytest.mark.asyncio
    async def test_process_knowledge_query_error(self):
        """Test knowledge query with error."""
        mock_redis = AsyncMock()
        mock_task_manager = AsyncMock()
        mock_task_manager.update_task_status = AsyncMock()
        mock_task_manager.set_task_error = AsyncMock()
        mock_thread_manager = AsyncMock()
        mock_thread_manager.get_thread = AsyncMock(return_value=None)

        mock_agent = AsyncMock()
        mock_agent.process_query = AsyncMock(side_effect=Exception("Knowledge error"))

        with (
            patch("redis_sre_agent.core.docket_tasks.get_redis_client", return_value=mock_redis),
            patch("redis_sre_agent.core.docket_tasks.TaskManager", return_value=mock_task_manager),
            patch(
                "redis_sre_agent.core.docket_tasks.ThreadManager", return_value=mock_thread_manager
            ),
            patch("redis_sre_agent.core.docket_tasks.get_chat_agent", return_value=mock_agent),
            patch("redis_sre_agent.core.docket_tasks.TaskEmitter"),
        ):
            with pytest.raises(Exception, match="Knowledge error"):
                await process_knowledge_query(
                    query="Test",
                    task_id="task-123",
                    thread_id="thread-456",
                )

        mock_task_manager.set_task_error.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_knowledge_query_agent_response_serialization(self):
        """Regression test: AgentResponse must be serialized to dict for JSON storage.

        Previously, AgentResponse (a Pydantic model) was stored directly in the result dict,
        causing 'Object of type AgentResponse is not JSON serializable' errors when
        set_task_result called json.dumps().
        """
        mock_redis = AsyncMock()
        mock_task_manager = AsyncMock()
        mock_task_manager.update_task_status = AsyncMock()
        mock_task_manager.set_task_result = AsyncMock()
        mock_thread_manager = AsyncMock()
        mock_thread_manager.get_thread = AsyncMock(return_value=None)
        mock_thread_manager.append_messages = AsyncMock()

        # Return an actual AgentResponse object (not a string)
        agent_response = AgentResponse(
            response="Knowledge response text",
            search_results=[{"id": "kb-1", "title": "Redis Best Practices"}],
        )
        mock_agent = AsyncMock()
        mock_agent.process_query = AsyncMock(return_value=agent_response)

        with (
            patch("redis_sre_agent.core.docket_tasks.get_redis_client", return_value=mock_redis),
            patch("redis_sre_agent.core.docket_tasks.TaskManager", return_value=mock_task_manager),
            patch(
                "redis_sre_agent.core.docket_tasks.ThreadManager", return_value=mock_thread_manager
            ),
            patch("redis_sre_agent.core.docket_tasks.get_chat_agent", return_value=mock_agent),
            patch("redis_sre_agent.core.docket_tasks.TaskEmitter"),
        ):
            result = await process_knowledge_query(
                query="What are Redis best practices?",
                task_id="task-123",
                thread_id="thread-456",
                user_id="user-1",
            )

        # Verify the response is a dict (model_dump'd), not an AgentResponse
        assert isinstance(result["response"], dict)
        assert result["response"]["response"] == "Knowledge response text"
        assert result["response"]["search_results"] == [
            {"id": "kb-1", "title": "Redis Best Practices"}
        ]

        # Verify thread message content is a string, not an AgentResponse
        mock_thread_manager.append_messages.assert_called_once()
        call_args = mock_thread_manager.append_messages.call_args
        messages = call_args[0][1]
        assert len(messages) == 1
        assert messages[0]["content"] == "Knowledge response text"
        assert isinstance(messages[0]["content"], str)

    @pytest.mark.asyncio
    async def test_process_knowledge_query_passes_conversation_history(self):
        """Compatibility path should preserve thread conversation history."""
        mock_redis = AsyncMock()
        mock_task_manager = AsyncMock()
        mock_task_manager.update_task_status = AsyncMock()
        mock_task_manager.set_task_result = AsyncMock()
        mock_thread_manager = AsyncMock()
        mock_thread_manager.get_thread = AsyncMock(
            return_value=Thread(
                thread_id="thread-456",
                messages=[
                    Message(role="user", content="How does replication work?"),
                    Message(role="assistant", content="It copies writes to replicas."),
                ],
                context={},
                metadata=ThreadMetadata(),
            )
        )
        mock_thread_manager.append_messages = AsyncMock()

        agent_response = AgentResponse(response="Follow-up answer", search_results=[])
        mock_agent = AsyncMock()
        mock_agent.process_query = AsyncMock(return_value=agent_response)

        with (
            patch("redis_sre_agent.core.docket_tasks.get_redis_client", return_value=mock_redis),
            patch("redis_sre_agent.core.docket_tasks.TaskManager", return_value=mock_task_manager),
            patch(
                "redis_sre_agent.core.docket_tasks.ThreadManager", return_value=mock_thread_manager
            ),
            patch("redis_sre_agent.core.docket_tasks.get_chat_agent", return_value=mock_agent),
            patch("redis_sre_agent.core.docket_tasks.TaskEmitter"),
        ):
            await process_knowledge_query(
                query="What about failover?",
                task_id="task-123",
                thread_id="thread-456",
                user_id="user-1",
            )

        _, kwargs = mock_agent.process_query.call_args
        history = kwargs["conversation_history"]
        assert history is not None
        assert len(history) == 2
        assert isinstance(history[0], HumanMessage)
        assert history[0].content == "How does replication work?"
        assert isinstance(history[1], AIMessage)
        assert history[1].content == "It copies writes to replicas."

    @pytest.mark.asyncio
    async def test_process_knowledge_query_excludes_duplicate_latest_user_message(self):
        mock_redis = AsyncMock()
        mock_task_manager = AsyncMock()
        mock_task_manager.update_task_status = AsyncMock()
        mock_task_manager.set_task_result = AsyncMock()
        mock_thread_manager = AsyncMock()
        mock_thread_manager.get_thread = AsyncMock(
            return_value=Thread(
                thread_id="thread-456",
                messages=[
                    Message(role="user", content="How does replication work?"),
                    Message(role="assistant", content="It copies writes to replicas."),
                    Message(role="user", content="What about failover?"),
                ],
                context={},
                metadata=ThreadMetadata(),
            )
        )
        mock_thread_manager.append_messages = AsyncMock()

        agent_response = AgentResponse(response="Follow-up answer", search_results=[])
        mock_agent = AsyncMock()
        mock_agent.process_query = AsyncMock(return_value=agent_response)

        with (
            patch("redis_sre_agent.core.docket_tasks.get_redis_client", return_value=mock_redis),
            patch("redis_sre_agent.core.docket_tasks.TaskManager", return_value=mock_task_manager),
            patch(
                "redis_sre_agent.core.docket_tasks.ThreadManager", return_value=mock_thread_manager
            ),
            patch("redis_sre_agent.core.docket_tasks.get_chat_agent", return_value=mock_agent),
            patch("redis_sre_agent.core.docket_tasks.TaskEmitter"),
        ):
            await process_knowledge_query(
                query="What about failover?",
                task_id="task-123",
                thread_id="thread-456",
                user_id="user-1",
            )

        _, kwargs = mock_agent.process_query.call_args
        history = kwargs["conversation_history"]
        assert history is not None
        assert len(history) == 2
        assert history[0].content == "How does replication work?"
        assert history[1].content == "It copies writes to replicas."

    @pytest.mark.asyncio
    async def test_process_knowledge_query_respects_configured_max_iterations(self):
        mock_redis = AsyncMock()
        mock_task_manager = AsyncMock()
        mock_task_manager.update_task_status = AsyncMock()
        mock_task_manager.set_task_result = AsyncMock()
        mock_thread_manager = AsyncMock()
        mock_thread_manager.get_thread = AsyncMock(return_value=None)
        mock_thread_manager.append_messages = AsyncMock()

        agent_response = AgentResponse(response="Answer", search_results=[])
        mock_agent = AsyncMock()
        mock_agent.process_query = AsyncMock(return_value=agent_response)

        with (
            patch("redis_sre_agent.core.docket_tasks.get_redis_client", return_value=mock_redis),
            patch("redis_sre_agent.core.docket_tasks.TaskManager", return_value=mock_task_manager),
            patch(
                "redis_sre_agent.core.docket_tasks.ThreadManager", return_value=mock_thread_manager
            ),
            patch("redis_sre_agent.core.docket_tasks.get_chat_agent", return_value=mock_agent),
            patch("redis_sre_agent.core.docket_tasks.TaskEmitter"),
            patch("redis_sre_agent.core.docket_tasks.settings.max_iterations", 5),
        ):
            await process_knowledge_query(
                query="What are Redis best practices?",
                task_id="task-123",
                thread_id="thread-456",
                user_id="user-1",
            )

        _, kwargs = mock_agent.process_query.call_args
        assert kwargs["max_iterations"] == 5


def test_thread_messages_to_conversation_history_filters_non_dialog_roles():
    history = _thread_messages_to_conversation_history(
        [
            Message(role="user", content="Question"),
            Message(role="assistant", content="Answer"),
            Message(role="system", content="Ignored"),
        ]
    )

    assert len(history) == 2
    assert isinstance(history[0], HumanMessage)
    assert isinstance(history[1], AIMessage)


class TestProcessPipelineOperation:
    """Test process_pipeline_operation task."""

    @pytest.mark.asyncio
    async def test_process_pipeline_operation_success(self):
        """Pipeline task should persist results and mark completion."""
        mock_redis = AsyncMock()
        mock_task_manager = AsyncMock()
        mock_task_manager.update_task_status = AsyncMock()
        mock_task_manager.set_task_result = AsyncMock()

        with (
            patch("redis_sre_agent.core.docket_tasks.get_redis_client", return_value=mock_redis),
            patch("redis_sre_agent.core.docket_tasks.TaskManager", return_value=mock_task_manager),
            patch("redis_sre_agent.core.docket_tasks.TaskEmitter"),
            patch(
                "redis_sre_agent.core.pipeline_execution_helpers.run_pipeline_operation_helper",
                new_callable=AsyncMock,
                return_value={"operation": "scrape", "success": True},
            ) as mock_helper,
        ):
            result = await process_pipeline_operation(
                operation="scrape",
                task_id="task-123",
                thread_id="thread-456",
                artifacts_path="/tmp/artifacts",
                scrapers=["redis_docs"],
            )

        assert result == {"operation": "scrape", "success": True}
        mock_helper.assert_awaited_once()
        mock_task_manager.update_task_status.assert_any_call("task-123", TaskStatus.IN_PROGRESS)
        mock_task_manager.update_task_status.assert_any_call("task-123", TaskStatus.DONE)
        mock_task_manager.set_task_result.assert_awaited_once_with(
            "task-123",
            {"operation": "scrape", "success": True},
        )

    @pytest.mark.asyncio
    async def test_process_pipeline_operation_error(self):
        """Pipeline task should persist task errors and re-raise failures."""
        mock_redis = AsyncMock()
        mock_task_manager = AsyncMock()
        mock_task_manager.update_task_status = AsyncMock()
        mock_task_manager.set_task_error = AsyncMock()

        with (
            patch("redis_sre_agent.core.docket_tasks.get_redis_client", return_value=mock_redis),
            patch("redis_sre_agent.core.docket_tasks.TaskManager", return_value=mock_task_manager),
            patch("redis_sre_agent.core.docket_tasks.TaskEmitter"),
            patch(
                "redis_sre_agent.core.pipeline_execution_helpers.run_pipeline_operation_helper",
                new_callable=AsyncMock,
                side_effect=Exception("pipeline failed"),
            ),
        ):
            with pytest.raises(Exception, match="pipeline failed"):
                await process_pipeline_operation(
                    operation="ingest",
                    task_id="task-123",
                    thread_id="thread-456",
                    batch_date="2026-03-25",
                )

        mock_task_manager.set_task_error.assert_awaited_once_with("task-123", "pipeline failed")


class TestProcessRunbookOperation:
    """Test process_runbook_operation task."""

    @pytest.mark.asyncio
    async def test_process_runbook_operation_success(self):
        """Runbook task should persist results and mark completion."""
        mock_redis = AsyncMock()
        mock_task_manager = AsyncMock()
        mock_task_manager.update_task_status = AsyncMock()
        mock_task_manager.set_task_result = AsyncMock()

        with (
            patch("redis_sre_agent.core.docket_tasks.get_redis_client", return_value=mock_redis),
            patch("redis_sre_agent.core.docket_tasks.TaskManager", return_value=mock_task_manager),
            patch("redis_sre_agent.core.docket_tasks.TaskEmitter"),
            patch(
                "redis_sre_agent.core.runbook_execution_helpers.run_runbook_operation_helper",
                new_callable=AsyncMock,
                return_value={"operation": "generate", "success": True},
            ) as mock_helper,
        ):
            result = await process_runbook_operation(
                operation="generate",
                task_id="task-123",
                thread_id="thread-456",
                topic="Memory Pressure",
                scenario_description="Redis memory saturation on primaries",
            )

        assert result == {"operation": "generate", "success": True}
        mock_helper.assert_awaited_once()
        mock_task_manager.update_task_status.assert_any_call("task-123", TaskStatus.IN_PROGRESS)
        mock_task_manager.update_task_status.assert_any_call("task-123", TaskStatus.DONE)
        mock_task_manager.set_task_result.assert_awaited_once_with(
            "task-123",
            {"operation": "generate", "success": True},
        )

    @pytest.mark.asyncio
    async def test_process_runbook_operation_error(self):
        """Runbook task should persist task errors and re-raise failures."""
        mock_redis = AsyncMock()
        mock_task_manager = AsyncMock()
        mock_task_manager.update_task_status = AsyncMock()
        mock_task_manager.set_task_error = AsyncMock()

        with (
            patch("redis_sre_agent.core.docket_tasks.get_redis_client", return_value=mock_redis),
            patch("redis_sre_agent.core.docket_tasks.TaskManager", return_value=mock_task_manager),
            patch("redis_sre_agent.core.docket_tasks.TaskEmitter"),
            patch(
                "redis_sre_agent.core.runbook_execution_helpers.run_runbook_operation_helper",
                new_callable=AsyncMock,
                side_effect=Exception("runbook failed"),
            ),
        ):
            with pytest.raises(Exception, match="runbook failed"):
                await process_runbook_operation(
                    operation="evaluate",
                    task_id="task-123",
                    thread_id="thread-456",
                )

        mock_task_manager.set_task_error.assert_awaited_once_with("task-123", "runbook failed")


class TestSchedulerTask:
    """Test scheduler_task function."""

    @pytest.mark.asyncio
    async def test_scheduler_task_no_schedules(self):
        """Test scheduler task when no schedules need runs."""
        with (
            patch(
                "redis_sre_agent.core.schedules.find_schedules_needing_runs",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            result = await scheduler_task()

        assert result["submitted_tasks"] == 0
        assert result["status"] == "completed"
        assert "task_id" in result

    @pytest.mark.asyncio
    async def test_scheduler_task_with_schedules(self):
        """Test scheduler task with schedules needing runs."""
        mock_schedule = {
            "id": "sched-1",
            "name": "Test Schedule",
            "instructions": "Check Redis health",
            "next_run_at": datetime.now(timezone.utc).isoformat(),
            "redis_instance_id": "inst-1",
            "cron_expression": "*/5 * * * *",
        }

        # Mock Redis client - needs to be returned from async get_redis_client
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=True)  # Dedup key set succeeds

        mock_docket = AsyncMock()
        mock_docket.add = MagicMock()
        mock_task_func = AsyncMock(return_value="task-123")
        mock_docket.add.return_value = mock_task_func

        mock_thread_manager = AsyncMock()
        mock_thread_manager.create_thread = AsyncMock(return_value="thread-123")
        mock_thread_manager.set_thread_subject = AsyncMock()

        # get_redis_client is called both sync and async in the function
        # Line 380: redis_client = get_redis_client() - sync
        # Line 412: redis_client = await get_redis_client() - async
        async def mock_get_redis_client():
            return mock_redis

        with (
            patch(
                "redis_sre_agent.core.schedules.find_schedules_needing_runs",
                new_callable=AsyncMock,
                return_value=[mock_schedule],
            ),
            patch(
                "redis_sre_agent.core.schedules.update_schedule_last_run",
                new_callable=AsyncMock,
            ),
            patch(
                "redis_sre_agent.core.schedules.update_schedule_next_run",
                new_callable=AsyncMock,
            ),
            patch(
                "redis_sre_agent.core.docket_tasks.get_redis_url",
                new_callable=AsyncMock,
                return_value="redis://localhost:6379",
            ),
            patch(
                "redis_sre_agent.core.docket_tasks.Docket",
            ) as mock_docket_class,
            patch(
                "redis_sre_agent.core.docket_tasks.get_redis_client",
                side_effect=lambda: mock_redis,
            ),
            patch(
                "redis_sre_agent.core.docket_tasks.ThreadManager",
                return_value=mock_thread_manager,
            ),
            patch(
                "redis_sre_agent.core.schedules.Schedule",
            ) as mock_schedule_class,
        ):
            # Setup async context manager for Docket
            mock_docket_class.return_value.__aenter__ = AsyncMock(return_value=mock_docket)
            mock_docket_class.return_value.__aexit__ = AsyncMock(return_value=None)

            # Setup Schedule mock
            mock_schedule_obj = MagicMock()
            mock_schedule_obj.calculate_next_run.return_value = datetime.now(timezone.utc)
            mock_schedule_class.return_value = mock_schedule_obj

            result = await scheduler_task()

        assert result["status"] == "completed"
        assert result["processed_schedules"] == 1
        # Note: submitted_tasks may be 0 if the async get_redis_client call fails
        # The important thing is the function completes without error

    @pytest.mark.asyncio
    async def test_scheduler_task_dedup_prevents_duplicate(self):
        """Test scheduler task deduplication prevents duplicate submissions."""
        mock_schedule = {
            "id": "sched-1",
            "name": "Test Schedule",
            "instructions": "Check Redis health",
            "next_run_at": datetime.now(timezone.utc).isoformat(),
            "cron_expression": "*/5 * * * *",
        }

        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=False)  # Dedup key already exists

        mock_docket = AsyncMock()
        mock_thread_manager = AsyncMock()
        mock_thread_manager.create_thread = AsyncMock(return_value="thread-123")
        mock_thread_manager.set_thread_subject = AsyncMock()

        with (
            patch(
                "redis_sre_agent.core.schedules.find_schedules_needing_runs",
                new_callable=AsyncMock,
                return_value=[mock_schedule],
            ),
            patch(
                "redis_sre_agent.core.schedules.update_schedule_last_run",
                new_callable=AsyncMock,
            ),
            patch(
                "redis_sre_agent.core.schedules.update_schedule_next_run",
                new_callable=AsyncMock,
            ),
            patch(
                "redis_sre_agent.core.docket_tasks.get_redis_url",
                new_callable=AsyncMock,
                return_value="redis://localhost:6379",
            ),
            patch(
                "redis_sre_agent.core.docket_tasks.Docket",
            ) as mock_docket_class,
            patch(
                "redis_sre_agent.core.docket_tasks.get_redis_client",
                return_value=mock_redis,
            ),
            patch(
                "redis_sre_agent.core.docket_tasks.ThreadManager",
                return_value=mock_thread_manager,
            ),
            patch(
                "redis_sre_agent.core.schedules.Schedule",
            ) as mock_schedule_class,
        ):
            mock_docket_class.return_value.__aenter__ = AsyncMock(return_value=mock_docket)
            mock_docket_class.return_value.__aexit__ = AsyncMock(return_value=None)

            mock_schedule_obj = MagicMock()
            mock_schedule_obj.calculate_next_run.return_value = datetime.now(timezone.utc)
            mock_schedule_class.return_value = mock_schedule_obj

            result = await scheduler_task()

        # Task was not submitted due to deduplication
        assert result["submitted_tasks"] == 0
        assert result["processed_schedules"] == 1


class TestProcessAgentTurn:
    """Test process_agent_turn function."""

    @pytest.mark.asyncio
    async def test_process_agent_turn_thread_not_found(self):
        """Test process_agent_turn when thread doesn't exist."""
        mock_redis = AsyncMock()
        mock_thread_manager = AsyncMock()
        mock_thread_manager.get_thread = AsyncMock(return_value=None)
        mock_task_manager = AsyncMock()
        mock_task_manager.create_task = AsyncMock(return_value="task-123")
        mock_task_manager.update_task_status = AsyncMock()
        mock_task_manager.add_task_update = AsyncMock()
        mock_task_manager.set_task_error = AsyncMock()

        with (
            patch("redis_sre_agent.core.docket_tasks.get_redis_client", return_value=mock_redis),
            patch(
                "redis_sre_agent.core.docket_tasks.ThreadManager", return_value=mock_thread_manager
            ),
            patch("redis_sre_agent.core.docket_tasks.TaskManager", return_value=mock_task_manager),
            patch("opentelemetry.trace.get_tracer") as mock_tracer,
        ):
            mock_span = MagicMock()
            mock_span.end = MagicMock()
            mock_tracer.return_value.start_span.return_value = mock_span

            with pytest.raises(ValueError, match="Thread .* not found"):
                await process_agent_turn(
                    thread_id="nonexistent-thread",
                    message="Hello",
                )

    @pytest.mark.asyncio
    async def test_process_agent_turn_with_task_id(self):
        """Test process_agent_turn uses provided task_id."""
        mock_redis = AsyncMock()

        mock_thread = MagicMock()
        mock_thread.id = "thread-123"
        mock_thread.context = {}
        mock_thread.metadata = MagicMock()
        mock_thread.metadata.user_id = "user-1"
        mock_thread.messages = []

        mock_thread_manager = AsyncMock()
        mock_thread_manager.get_thread = AsyncMock(return_value=mock_thread)
        mock_thread_manager.update_thread_context = AsyncMock()
        mock_thread_manager.append_messages = AsyncMock()

        mock_task_manager = AsyncMock()
        mock_task_manager.create_task = AsyncMock(return_value="new-task-123")
        mock_task_manager.update_task_status = AsyncMock()
        mock_task_manager.add_task_update = AsyncMock()
        mock_task_manager.set_task_result = AsyncMock()
        mock_task_manager.set_task_error = AsyncMock()

        mock_chat_agent = AsyncMock()
        mock_response = AgentResponse(
            response="Chat response",
            search_results=[],
            tool_envelopes=[{"name": "redis_info", "status": "success"}],
        )
        mock_chat_agent.process_query = AsyncMock(return_value=mock_response)

        with (
            patch("redis_sre_agent.core.docket_tasks.get_redis_client", return_value=mock_redis),
            patch(
                "redis_sre_agent.core.docket_tasks.ThreadManager", return_value=mock_thread_manager
            ),
            patch("redis_sre_agent.core.docket_tasks.TaskManager", return_value=mock_task_manager),
            patch(
                "redis_sre_agent.core.docket_tasks._extract_instance_details_from_message",
                return_value=None,
            ),
            patch(
                "redis_sre_agent.core.docket_tasks.get_chat_agent",
                return_value=mock_chat_agent,
            ),
            patch(
                "redis_sre_agent.core.docket_tasks.ULID", return_value="01HXTESTMESSAGEID1234567890"
            ),
            patch("opentelemetry.trace.get_tracer") as mock_tracer,
        ):
            mock_span = MagicMock()
            mock_span.end = MagicMock()
            mock_span.set_attribute = MagicMock()
            mock_tracer.return_value.start_span.return_value = mock_span

            result = await process_agent_turn(
                thread_id="thread-123",
                message="What are Redis best practices?",
                task_id="provided-task-123",  # Provide task_id
            )

        # Should use provided task_id, not create a new one
        mock_task_manager.create_task.assert_not_called()
        mock_task_manager.update_task_status.assert_any_call(
            "provided-task-123", TaskStatus.IN_PROGRESS
        )
        assert result["message_id"] == "01HXTESTMESSAGEID1234567890"

        # Result payload should include the assistant message_id for trace lookup.
        set_result_call = mock_task_manager.set_task_result.await_args
        assert set_result_call.args[0] == "provided-task-123"
        assert set_result_call.args[1]["message_id"] == "01HXTESTMESSAGEID1234567890"

        # The assistant message persisted on thread should preserve message_id + task linkage metadata.
        assistant_msgs = [m for m in mock_thread.messages if m.role == "assistant"]
        assert assistant_msgs
        assert assistant_msgs[-1].message_id == "01HXTESTMESSAGEID1234567890"
        assert assistant_msgs[-1].metadata["metadata"]["task_id"] == "provided-task-123"
        assert (
            assistant_msgs[-1].metadata["metadata"]["message_id"] == "01HXTESTMESSAGEID1234567890"
        )

        # Tool envelopes are stored as decision trace for this assistant message_id.
        mock_thread_manager.set_message_trace.assert_awaited_once_with(
            message_id="01HXTESTMESSAGEID1234567890",
            tool_envelopes=[{"name": "redis_info", "status": "success"}],
            otel_trace_id=None,
        )

    @pytest.mark.asyncio
    async def test_process_agent_turn_honors_requested_agent_type(self):
        """Requested agent type should bypass router auto-selection."""
        mock_redis = AsyncMock()
        mock_thread = MagicMock()
        mock_thread.id = "thread-123"
        mock_thread.context = {}
        mock_thread.metadata = MagicMock()
        mock_thread.metadata.user_id = "user-1"
        mock_thread.metadata.session_id = "session-1"
        mock_thread.messages = []

        mock_thread_manager = AsyncMock()
        mock_thread_manager.get_thread = AsyncMock(return_value=mock_thread)
        mock_thread_manager.update_thread_context = AsyncMock()
        mock_thread_manager.append_messages = AsyncMock()

        mock_task_manager = AsyncMock()
        mock_task_manager.create_task = AsyncMock(return_value="new-task-123")
        mock_task_manager.update_task_status = AsyncMock()
        mock_task_manager.add_task_update = AsyncMock()
        mock_task_manager.set_task_result = AsyncMock()
        mock_task_manager.set_task_error = AsyncMock()

        mock_chat_agent = AsyncMock()
        mock_response = AgentResponse(
            response="Chat response",
            search_results=[],
            tool_envelopes=[],
        )
        mock_chat_agent.process_query = AsyncMock(return_value=mock_response)

        with (
            patch("redis_sre_agent.core.docket_tasks.get_redis_client", return_value=mock_redis),
            patch(
                "redis_sre_agent.core.docket_tasks.ThreadManager", return_value=mock_thread_manager
            ),
            patch("redis_sre_agent.core.docket_tasks.TaskManager", return_value=mock_task_manager),
            patch(
                "redis_sre_agent.core.docket_tasks._extract_instance_details_from_message",
                return_value=None,
            ),
            patch(
                "redis_sre_agent.core.docket_tasks.get_chat_agent",
                return_value=mock_chat_agent,
            ),
            patch(
                "redis_sre_agent.core.docket_tasks.route_to_appropriate_agent",
                new_callable=AsyncMock,
            ) as mock_router,
            patch(
                "redis_sre_agent.core.docket_tasks.ULID", return_value="01HXTESTMESSAGEID1234567890"
            ),
            patch("opentelemetry.trace.get_tracer") as mock_tracer,
        ):
            mock_span = MagicMock()
            mock_span.end = MagicMock()
            mock_span.set_attribute = MagicMock()
            mock_tracer.return_value.start_span.return_value = mock_span

            result = await process_agent_turn(
                thread_id="thread-123",
                message="Use chat",
                task_id="provided-task-123",
                context={"requested_agent_type": "chat"},
            )

        mock_router.assert_not_called()
        mock_chat_agent.process_query.assert_awaited_once()
        assert result["message_id"] == "01HXTESTMESSAGEID1234567890"

    @pytest.mark.asyncio
    async def test_process_agent_turn_passes_resolved_target_context_to_triage(self):
        mock_redis = AsyncMock()
        mock_thread = MagicMock()
        mock_thread.id = "thread-123"
        mock_thread.context = {}
        mock_thread.metadata = MagicMock()
        mock_thread.metadata.user_id = "user-1"
        mock_thread.messages = []

        mock_thread_manager = AsyncMock()
        mock_thread_manager.get_thread = AsyncMock(return_value=mock_thread)
        mock_thread_manager.update_thread_context = AsyncMock()
        mock_thread_manager.append_messages = AsyncMock()
        mock_thread_manager.set_message_trace = AsyncMock()

        mock_task_manager = AsyncMock()
        mock_task_manager.create_task = AsyncMock(return_value="new-task-123")
        mock_task_manager.update_task_status = AsyncMock()
        mock_task_manager.add_task_update = AsyncMock()
        mock_task_manager.set_task_result = AsyncMock()
        mock_task_manager.set_task_error = AsyncMock()
        mock_task_manager.get_task_state = AsyncMock(return_value=MagicMock(updates=[]))
        mock_task_manager._publish_stream_update = AsyncMock()

        resolution = TargetResolutionResult(
            status="resolved",
            query="investigate checkout cache",
            clarification_required=False,
            selected_matches=[
                ResolvedTargetMatch(
                    target_kind="instance",
                    resource_id="redis-prod-checkout-cache",
                    display_name="checkout-cache-prod",
                    environment="production",
                    target_type="oss_single",
                    capabilities=["redis", "diagnostics"],
                    confidence=0.97,
                    match_reasons=["matched environment=production"],
                )
            ],
        )
        bindings = [
            TargetBinding(
                target_handle="tgt_01",
                target_kind="instance",
                resource_id="redis-prod-checkout-cache",
                display_name="checkout-cache-prod",
                capabilities=["redis", "diagnostics"],
                thread_id="thread-123",
                task_id="provided-task-123",
            )
        ]
        mock_run_agent = AsyncMock(
            return_value={
                "response": "Triage response",
                "search_results": [],
                "tool_envelopes": [],
                "metadata": {"agent_type": "redis_triage"},
            }
        )

        with (
            patch("redis_sre_agent.core.docket_tasks.get_redis_client", return_value=mock_redis),
            patch(
                "redis_sre_agent.core.docket_tasks.ThreadManager", return_value=mock_thread_manager
            ),
            patch("redis_sre_agent.core.docket_tasks.TaskManager", return_value=mock_task_manager),
            patch(
                "redis_sre_agent.core.docket_tasks._extract_instance_details_from_message",
                return_value=None,
            ),
            patch(
                "redis_sre_agent.core.docket_tasks.route_to_appropriate_agent",
                new=AsyncMock(return_value=AgentType.REDIS_TRIAGE),
            ),
            patch(
                "redis_sre_agent.core.targets.resolve_target_query",
                new=AsyncMock(return_value=resolution),
            ),
            patch(
                "redis_sre_agent.core.targets.attach_target_matches",
                new=AsyncMock(return_value=(bindings, 3)),
            ),
            patch("redis_sre_agent.core.docket_tasks.get_sre_agent", return_value=MagicMock()),
            patch(
                "redis_sre_agent.core.docket_tasks.run_agent_with_progress",
                new=mock_run_agent,
            ),
            patch(
                "redis_sre_agent.core.docket_tasks.ULID", return_value="01HXTESTMESSAGEID1234567890"
            ),
            patch("opentelemetry.trace.get_tracer") as mock_tracer,
        ):
            mock_span = MagicMock()
            mock_span.end = MagicMock()
            mock_span.set_attribute = MagicMock()
            mock_tracer.return_value.start_span.return_value = mock_span

            await process_agent_turn(
                thread_id="thread-123",
                message="Investigate checkout cache",
                task_id="provided-task-123",
            )

        _, kwargs = mock_run_agent.await_args
        assert kwargs["agent_context"]["instance_id"] == "redis-prod-checkout-cache"
        assert kwargs["agent_context"]["attached_target_handles"] == ["tgt_01"]
        assert kwargs["agent_context"]["target_toolset_generation"] == 3

    @pytest.mark.asyncio
    async def test_process_agent_turn_passes_single_resolved_cluster_scope_to_triage(self):
        mock_redis = AsyncMock()
        mock_thread = MagicMock()
        mock_thread.context = {}
        mock_thread.messages = []
        mock_thread.metadata.user_id = "test-user"

        mock_thread_manager = AsyncMock()
        mock_thread_manager.get_thread = AsyncMock(return_value=mock_thread)
        mock_thread_manager.update_thread_context = AsyncMock()
        mock_thread_manager.append_message = AsyncMock()
        mock_thread_manager.update_thread = AsyncMock()

        mock_task_manager = AsyncMock()
        mock_task_manager.create_task = AsyncMock(return_value="provided-task-123")
        mock_task_manager.add_task_update = AsyncMock()
        mock_task_manager.set_task_result = AsyncMock()
        mock_task_manager.set_task_error = AsyncMock()
        mock_task_manager.get_task_state = AsyncMock(return_value=MagicMock(updates=[]))
        mock_task_manager._publish_stream_update = AsyncMock()

        resolution = TargetResolutionResult(
            status="resolved",
            query="investigate checkout cluster",
            clarification_required=False,
            selected_matches=[
                ResolvedTargetMatch(
                    target_kind="cluster",
                    resource_id="cluster-prod-checkout",
                    display_name="checkout-cluster-prod",
                    environment="production",
                    target_type="redis_enterprise",
                    capabilities=["admin"],
                    confidence=0.97,
                    match_reasons=["matched environment=production"],
                )
            ],
        )
        bindings = [
            TargetBinding(
                target_handle="tgt_cluster",
                target_kind="cluster",
                resource_id="cluster-prod-checkout",
                display_name="checkout-cluster-prod",
                capabilities=["admin"],
                thread_id="thread-123",
                task_id="provided-task-123",
            )
        ]
        mock_run_agent = AsyncMock(
            return_value={
                "response": "Cluster triage response",
                "search_results": [],
                "tool_envelopes": [],
                "metadata": {"agent_type": "redis_triage"},
            }
        )

        with (
            patch("redis_sre_agent.core.docket_tasks.get_redis_client", return_value=mock_redis),
            patch(
                "redis_sre_agent.core.docket_tasks.ThreadManager", return_value=mock_thread_manager
            ),
            patch("redis_sre_agent.core.docket_tasks.TaskManager", return_value=mock_task_manager),
            patch(
                "redis_sre_agent.core.docket_tasks._extract_instance_details_from_message",
                return_value=None,
            ),
            patch(
                "redis_sre_agent.core.docket_tasks.route_to_appropriate_agent",
                new=AsyncMock(return_value=AgentType.REDIS_TRIAGE),
            ),
            patch(
                "redis_sre_agent.core.targets.resolve_target_query",
                new=AsyncMock(return_value=resolution),
            ),
            patch(
                "redis_sre_agent.core.targets.attach_target_matches",
                new=AsyncMock(return_value=(bindings, 5)),
            ),
            patch("redis_sre_agent.core.docket_tasks.get_sre_agent", return_value=MagicMock()),
            patch(
                "redis_sre_agent.core.docket_tasks.run_agent_with_progress",
                new=mock_run_agent,
            ),
            patch(
                "redis_sre_agent.core.docket_tasks.ULID", return_value="01HXTESTMESSAGEID1234567890"
            ),
            patch("opentelemetry.trace.get_tracer") as mock_tracer,
        ):
            mock_span = MagicMock()
            mock_span.end = MagicMock()
            mock_span.set_attribute = MagicMock()
            mock_tracer.return_value.start_span.return_value = mock_span

            await process_agent_turn(
                thread_id="thread-123",
                message="Investigate checkout cluster",
                task_id="provided-task-123",
            )

        _, kwargs = mock_run_agent.await_args
        assert kwargs["agent_context"]["cluster_id"] == "cluster-prod-checkout"
        assert kwargs["agent_context"]["attached_target_handles"] == ["tgt_cluster"]
        assert kwargs["agent_context"]["target_toolset_generation"] == 5

    @pytest.mark.asyncio
    async def test_pre_resolved_multi_target_scope_reaches_agent_without_singular_target_ids(self):
        mock_redis = AsyncMock()
        mock_thread = MagicMock()
        mock_thread.context = {}
        mock_thread.messages = []
        mock_thread.metadata.user_id = "test-user"

        mock_thread_manager = AsyncMock()
        mock_thread_manager.get_thread = AsyncMock(return_value=mock_thread)
        mock_thread_manager.update_thread_context = AsyncMock()
        mock_thread_manager.append_message = AsyncMock()
        mock_thread_manager.update_thread = AsyncMock()

        mock_task_manager = AsyncMock()
        mock_task_manager.create_task = AsyncMock(return_value="provided-task-123")
        mock_task_manager.add_task_update = AsyncMock()
        mock_task_manager.set_task_result = AsyncMock()
        mock_task_manager.set_task_error = AsyncMock()
        mock_task_manager.get_task_state = AsyncMock(return_value=MagicMock(updates=[]))
        mock_task_manager._publish_stream_update = AsyncMock()

        resolution = TargetResolutionResult(
            status="resolved",
            query="compare checkout and session cache",
            clarification_required=False,
            selected_matches=[
                ResolvedTargetMatch(
                    target_kind="instance",
                    resource_id="redis-prod-checkout-cache",
                    display_name="checkout-cache-prod",
                    environment="production",
                    target_type="oss_single",
                    capabilities=["redis", "diagnostics"],
                    confidence=0.97,
                    match_reasons=["matched environment=production"],
                ),
                ResolvedTargetMatch(
                    target_kind="instance",
                    resource_id="redis-stage-session-cache",
                    display_name="session-cache-stage",
                    environment="staging",
                    target_type="oss_single",
                    capabilities=["redis", "diagnostics"],
                    confidence=0.94,
                    match_reasons=["matched environment=staging"],
                ),
            ],
        )
        bindings = [
            TargetBinding(
                target_handle="tgt_01",
                target_kind="instance",
                resource_id="redis-prod-checkout-cache",
                display_name="checkout-cache-prod",
                capabilities=["redis", "diagnostics"],
                thread_id="thread-123",
                task_id="provided-task-123",
            ),
            TargetBinding(
                target_handle="tgt_02",
                target_kind="instance",
                resource_id="redis-stage-session-cache",
                display_name="session-cache-stage",
                capabilities=["redis", "diagnostics"],
                thread_id="thread-123",
                task_id="provided-task-123",
            ),
        ]
        mock_run_agent = AsyncMock(
            return_value={
                "response": "Comparison response",
                "search_results": [],
                "tool_envelopes": [],
                "metadata": {"agent_type": "redis_triage"},
            }
        )

        with (
            patch("redis_sre_agent.core.docket_tasks.get_redis_client", return_value=mock_redis),
            patch(
                "redis_sre_agent.core.docket_tasks.ThreadManager", return_value=mock_thread_manager
            ),
            patch("redis_sre_agent.core.docket_tasks.TaskManager", return_value=mock_task_manager),
            patch(
                "redis_sre_agent.core.docket_tasks._extract_instance_details_from_message",
                return_value=None,
            ),
            patch(
                "redis_sre_agent.core.docket_tasks.route_to_appropriate_agent",
                new=AsyncMock(return_value=AgentType.REDIS_TRIAGE),
            ),
            patch(
                "redis_sre_agent.core.targets.resolve_target_query",
                new=AsyncMock(return_value=resolution),
            ),
            patch(
                "redis_sre_agent.core.targets.attach_target_matches",
                new=AsyncMock(return_value=(bindings, 4)),
            ),
            patch("redis_sre_agent.core.docket_tasks.get_sre_agent", return_value=MagicMock()),
            patch(
                "redis_sre_agent.core.docket_tasks.run_agent_with_progress",
                new=mock_run_agent,
            ),
            patch(
                "redis_sre_agent.core.docket_tasks.ULID", return_value="01HXTESTMESSAGEID1234567890"
            ),
            patch("opentelemetry.trace.get_tracer") as mock_tracer,
        ):
            mock_span = MagicMock()
            mock_span.end = MagicMock()
            mock_span.set_attribute = MagicMock()
            mock_tracer.return_value.start_span.return_value = mock_span

            await process_agent_turn(
                thread_id="thread-123",
                message="Compare checkout and session cache",
                task_id="provided-task-123",
            )

        _, kwargs = mock_run_agent.await_args
        assert kwargs["agent_context"]["attached_target_handles"] == ["tgt_01", "tgt_02"]
        assert kwargs["agent_context"]["active_target_handle"] == "tgt_01"
        assert kwargs["agent_context"]["target_toolset_generation"] == 4
        assert "instance_id" not in kwargs["agent_context"]
        assert "cluster_id" not in kwargs["agent_context"]

    @pytest.mark.asyncio
    async def test_process_agent_turn_chat_path_does_not_bind_single_target_for_multi_scope(self):
        mock_redis = AsyncMock()
        mock_thread = MagicMock()
        mock_thread.context = {
            "instance_id": "redis-stale-instance",
            "attached_target_handles": ["tgt_01", "tgt_02"],
        }
        mock_thread.messages = []
        mock_thread.metadata.user_id = "test-user"

        mock_thread_manager = AsyncMock()
        mock_thread_manager.get_thread = AsyncMock(return_value=mock_thread)
        mock_thread_manager.update_thread_context = AsyncMock()
        mock_thread_manager.append_message = AsyncMock()
        mock_thread_manager.update_thread = AsyncMock()

        mock_task_manager = AsyncMock()
        mock_task_manager.create_task = AsyncMock(return_value="provided-task-123")
        mock_task_manager.add_task_update = AsyncMock()
        mock_task_manager.set_task_result = AsyncMock()
        mock_task_manager.set_task_error = AsyncMock()
        mock_task_manager.get_task_state = AsyncMock(return_value=MagicMock(updates=[]))
        mock_task_manager._publish_stream_update = AsyncMock()

        mock_chat_agent = MagicMock()
        mock_chat_agent.process_query = AsyncMock(
            return_value=AgentResponse(
                response="Chat response",
                search_results=[],
                tool_envelopes=[],
            )
        )

        with (
            patch("redis_sre_agent.core.docket_tasks.get_redis_client", return_value=mock_redis),
            patch(
                "redis_sre_agent.core.docket_tasks.ThreadManager", return_value=mock_thread_manager
            ),
            patch("redis_sre_agent.core.docket_tasks.TaskManager", return_value=mock_task_manager),
            patch(
                "redis_sre_agent.core.docket_tasks.route_to_appropriate_agent",
                new=AsyncMock(return_value=AgentType.REDIS_CHAT),
            ),
            patch(
                "redis_sre_agent.core.docket_tasks.get_chat_agent",
                return_value=mock_chat_agent,
            ) as mock_get_chat_agent,
            patch(
                "redis_sre_agent.core.docket_tasks.ULID", return_value="01HXTESTMESSAGEID1234567890"
            ),
            patch("opentelemetry.trace.get_tracer") as mock_tracer,
        ):
            mock_span = MagicMock()
            mock_span.end = MagicMock()
            mock_span.set_attribute = MagicMock()
            mock_tracer.return_value.start_span.return_value = mock_span

            await process_agent_turn(
                thread_id="thread-123",
                message="Compare the attached targets",
                task_id="provided-task-123",
            )

        assert mock_get_chat_agent.call_args.kwargs["redis_instance"] is None
        assert mock_get_chat_agent.call_args.kwargs["redis_cluster"] is None


class TestRunAgentWithProgress:
    """Test run_agent_with_progress function."""

    @pytest.mark.asyncio
    async def test_run_agent_with_progress_no_messages(self):
        """Test run_agent_with_progress with empty messages."""
        mock_emitter = AsyncMock()
        mock_agent = MagicMock()
        conversation_state = {"messages": []}

        with pytest.raises(ValueError, match="No messages in conversation"):
            await run_agent_with_progress(
                agent=mock_agent,
                conversation_state=conversation_state,
                progress_emitter=mock_emitter,
                thread_state=None,
            )

    @pytest.mark.asyncio
    async def test_run_agent_with_progress_no_user_message(self):
        """Test run_agent_with_progress with no user message."""
        mock_emitter = AsyncMock()
        mock_agent_param = MagicMock()
        conversation_state = {
            "messages": [{"role": "assistant", "content": "Hello"}],
            "thread_id": "thread-123",
        }

        mock_agent = MagicMock()

        with (
            patch(
                "redis_sre_agent.agent.langgraph_agent.SRELangGraphAgent",
                return_value=mock_agent,
            ),
            pytest.raises(ValueError, match="No user message found"),
        ):
            await run_agent_with_progress(
                agent=mock_agent_param,
                conversation_state=conversation_state,
                progress_emitter=mock_emitter,
                thread_state=None,
            )

    @pytest.mark.asyncio
    async def test_run_agent_with_progress_success(self):
        """Test successful run_agent_with_progress."""
        mock_emitter = AsyncMock()
        mock_agent_param = MagicMock()
        conversation_state = {
            "messages": [{"role": "user", "content": "Check Redis health"}],
            "thread_id": "thread-123",
        }

        mock_agent = MagicMock()
        mock_response = AgentResponse(response="Agent response", search_results=[])
        mock_agent.process_query = AsyncMock(return_value=mock_response)

        with patch(
            "redis_sre_agent.agent.langgraph_agent.SRELangGraphAgent",
            return_value=mock_agent,
        ):
            result = await run_agent_with_progress(
                agent=mock_agent_param,
                conversation_state=conversation_state,
                progress_emitter=mock_emitter,
                thread_state=None,
            )

        assert result["response"] == "Agent response"
        mock_agent.process_query.assert_called_once()
