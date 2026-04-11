"""Tests for unified query MCP helpers."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from redis_sre_agent.core.query_helpers import (
    _get_query_task_callable,
    _normalize_agent_selection,
    get_redis_url,
    queue_query_task_helper,
)
from redis_sre_agent.core.tasks import TaskStatus


class TestNormalizeAgentSelection:
    """Test query agent normalization."""

    def test_normalize_agent_selection_accepts_supported_values(self):
        assert _normalize_agent_selection(None) == "auto"
        assert _normalize_agent_selection("AUTO") == "auto"
        assert _normalize_agent_selection("chat") == "chat"
        assert _normalize_agent_selection("triage") == "triage"
        assert _normalize_agent_selection("knowledge") == "knowledge"

    def test_normalize_agent_selection_rejects_invalid_values(self):
        with pytest.raises(ValueError, match="Invalid agent"):
            _normalize_agent_selection("bogus")


class TestHelperShims:
    """Test import-cycle shims used by query helpers."""

    @pytest.mark.asyncio
    async def test_get_redis_url_delegates(self):
        with patch(
            "redis_sre_agent.core.docket_tasks.get_redis_url",
            new_callable=AsyncMock,
            return_value="redis://localhost:6379/0",
        ) as mock_get_redis_url:
            result = await get_redis_url()

        assert result == "redis://localhost:6379/0"
        mock_get_redis_url.assert_awaited_once_with()

    def test_get_query_task_callable_returns_process_agent_turn(self):
        from redis_sre_agent.core.docket_tasks import process_agent_turn

        assert _get_query_task_callable() is process_agent_turn


class TestQueueQueryTaskHelper:
    """Test unified query task queuing."""

    @pytest.mark.asyncio
    async def test_queue_query_task_helper_creates_and_submits_task(self):
        redis_client = AsyncMock()
        mock_manager = AsyncMock()
        mock_manager.get_metadata = AsyncMock(return_value=SimpleNamespace(filename="pkg.tar.gz"))
        mock_manager.extract = AsyncMock(return_value=Path("/tmp/extracted/pkg-1"))
        task_callable = AsyncMock()
        docket_instance = AsyncMock()
        docket_instance.__aenter__.return_value = docket_instance
        docket_instance.__aexit__.return_value = False
        docket_instance.add.return_value = task_callable

        with (
            patch("redis_sre_agent.core.query_helpers.get_redis_client", return_value=redis_client),
            patch(
                "redis_sre_agent.core.query_helpers.get_instance_by_id",
                new_callable=AsyncMock,
                return_value=SimpleNamespace(id="redis-prod-1"),
            ),
            patch(
                "redis_sre_agent.core.query_helpers.get_support_package_manager",
                return_value=mock_manager,
            ),
            patch(
                "redis_sre_agent.core.query_helpers.create_task",
                new_callable=AsyncMock,
                return_value={
                    "thread_id": "thread-123",
                    "task_id": "task-123",
                    "status": TaskStatus.QUEUED,
                },
            ) as mock_create_task,
            patch(
                "redis_sre_agent.core.query_helpers.get_redis_url",
                new_callable=AsyncMock,
                return_value="redis://localhost:6379/0",
            ),
            patch(
                "redis_sre_agent.core.query_helpers._get_query_task_callable",
                return_value="process-agent-turn",
            ),
            patch("redis_sre_agent.core.query_helpers.Docket", return_value=docket_instance),
        ):
            result = await queue_query_task_helper(
                query="Investigate memory usage",
                instance_id="redis-prod-1",
                support_package_id="pkg-1",
                user_id="user-1",
                agent="auto",
            )

        assert result == {
            "thread_id": "thread-123",
            "task_id": "task-123",
            "status": "queued",
            "message": "Query task queued for processing",
            "agent": "auto",
        }
        create_kwargs = mock_create_task.await_args.kwargs
        assert create_kwargs["message"] == "Investigate memory usage"
        assert create_kwargs["thread_id"] is None
        assert create_kwargs["redis_client"] is redis_client
        context = create_kwargs["context"]
        assert context["instance_id"] == "redis-prod-1"
        assert context["support_package_id"] == "pkg-1"
        assert context["support_package_path"] == "/tmp/extracted/pkg-1"
        assert context["user_id"] == "user-1"
        assert context["resolution_policy"] == "require_target"
        assert context["target_bindings"][0]["target_kind"] == "instance"
        assert context["target_bindings"][0]["target_handle"]
        assert context["target_bindings"][0]["resource_id"] == "redis-prod-1"
        assert context["turn_scope"]["seed_hints"] == {"instance_id": "redis-prod-1"}

        task_kwargs = task_callable.await_args.kwargs
        assert task_kwargs["thread_id"] == "thread-123"
        assert task_kwargs["message"] == "Investigate memory usage"
        assert task_kwargs["task_id"] == "task-123"
        assert task_kwargs["context"] == context

    @pytest.mark.asyncio
    async def test_queue_query_task_helper_supports_thread_continuation_and_agent_override(self):
        redis_client = AsyncMock()
        thread_manager = AsyncMock()
        thread_manager.get_thread = AsyncMock(return_value=SimpleNamespace(thread_id="thread-123"))
        task_callable = AsyncMock()
        docket_instance = AsyncMock()
        docket_instance.__aenter__.return_value = docket_instance
        docket_instance.__aexit__.return_value = False
        docket_instance.add.return_value = task_callable

        with (
            patch("redis_sre_agent.core.query_helpers.get_redis_client", return_value=redis_client),
            patch(
                "redis_sre_agent.core.query_helpers.ThreadManager",
                return_value=thread_manager,
            ),
            patch(
                "redis_sre_agent.core.query_helpers.create_task",
                new_callable=AsyncMock,
                return_value={
                    "thread_id": "thread-123",
                    "task_id": "task-123",
                    "status": TaskStatus.QUEUED,
                },
            ) as mock_create_task,
            patch(
                "redis_sre_agent.core.query_helpers.get_redis_url",
                new_callable=AsyncMock,
                return_value="redis://localhost:6379/0",
            ),
            patch(
                "redis_sre_agent.core.query_helpers._get_query_task_callable",
                return_value="process-agent-turn",
            ),
            patch("redis_sre_agent.core.query_helpers.Docket", return_value=docket_instance),
        ):
            result = await queue_query_task_helper(
                query="Follow up",
                thread_id="thread-123",
                agent="knowledge",
            )

        assert result["agent"] == "knowledge"
        create_kwargs = mock_create_task.await_args.kwargs
        assert create_kwargs["message"] == "Follow up"
        assert create_kwargs["thread_id"] == "thread-123"
        assert create_kwargs["redis_client"] is redis_client
        context = create_kwargs["context"]
        assert context["requested_agent_type"] == "knowledge"
        assert context["resolution_policy"] == "allow_zero_scope"
        assert context["turn_scope"]["scope_kind"] == "zero_scope"

        task_kwargs = task_callable.await_args.kwargs
        assert task_kwargs["thread_id"] == "thread-123"
        assert task_kwargs["message"] == "Follow up"
        assert task_kwargs["task_id"] == "task-123"
        assert task_kwargs["context"] == context

    @pytest.mark.asyncio
    async def test_queue_query_task_helper_supports_cluster_context_and_awaitable_docket_add(self):
        redis_client = AsyncMock()
        task_callable = AsyncMock()
        docket_instance = AsyncMock()
        docket_instance.__aenter__.return_value = docket_instance
        docket_instance.__aexit__.return_value = False
        docket_instance.add = AsyncMock(return_value=task_callable)

        with (
            patch("redis_sre_agent.core.query_helpers.get_redis_client", return_value=redis_client),
            patch(
                "redis_sre_agent.core.query_helpers.get_cluster_by_id",
                new_callable=AsyncMock,
                return_value=SimpleNamespace(id="cluster-1"),
            ),
            patch(
                "redis_sre_agent.core.query_helpers.create_task",
                new_callable=AsyncMock,
                return_value={
                    "thread_id": "thread-123",
                    "task_id": "task-123",
                    "status": TaskStatus.QUEUED,
                },
            ) as mock_create_task,
            patch(
                "redis_sre_agent.core.query_helpers.get_redis_url",
                new_callable=AsyncMock,
                return_value="redis://localhost:6379/0",
            ),
            patch(
                "redis_sre_agent.core.query_helpers._get_query_task_callable",
                return_value="process-agent-turn",
            ),
            patch("redis_sre_agent.core.query_helpers.Docket", return_value=docket_instance),
        ):
            result = await queue_query_task_helper(
                query="Check cluster",
                cluster_id="cluster-1",
            )

        assert result["agent"] == "auto"
        create_kwargs = mock_create_task.await_args.kwargs
        assert create_kwargs["message"] == "Check cluster"
        assert create_kwargs["thread_id"] is None
        assert create_kwargs["redis_client"] is redis_client
        context = create_kwargs["context"]
        assert context["cluster_id"] == "cluster-1"
        assert context["resolution_policy"] == "require_target"
        assert context["target_bindings"][0]["target_kind"] == "cluster"
        assert context["target_bindings"][0]["target_kind"] == "cluster"
        assert context["target_bindings"][0]["resource_id"] == "cluster-1"
        assert context["turn_scope"]["seed_hints"] == {"cluster_id": "cluster-1"}

        task_kwargs = task_callable.await_args.kwargs
        assert task_kwargs["thread_id"] == "thread-123"
        assert task_kwargs["message"] == "Check cluster"
        assert task_kwargs["task_id"] == "task-123"
        assert task_kwargs["context"] == context

    @pytest.mark.asyncio
    async def test_queue_query_task_helper_preserves_instance_hint_with_agent_override(self):
        redis_client = AsyncMock()
        task_callable = AsyncMock()
        docket_instance = AsyncMock()
        docket_instance.__aenter__.return_value = docket_instance
        docket_instance.__aexit__.return_value = False
        docket_instance.add.return_value = task_callable

        with (
            patch("redis_sre_agent.core.query_helpers.get_redis_client", return_value=redis_client),
            patch(
                "redis_sre_agent.core.query_helpers.get_instance_by_id",
                new_callable=AsyncMock,
                return_value=SimpleNamespace(id="redis-prod-1"),
            ),
            patch(
                "redis_sre_agent.core.query_helpers.create_task",
                new_callable=AsyncMock,
                return_value={
                    "thread_id": "thread-123",
                    "task_id": "task-123",
                    "status": TaskStatus.QUEUED,
                },
            ) as mock_create_task,
            patch(
                "redis_sre_agent.core.query_helpers.get_redis_url",
                new_callable=AsyncMock,
                return_value="redis://localhost:6379/0",
            ),
            patch(
                "redis_sre_agent.core.query_helpers._get_query_task_callable",
                return_value="process-agent-turn",
            ),
            patch("redis_sre_agent.core.query_helpers.Docket", return_value=docket_instance),
        ):
            await queue_query_task_helper(
                query="Investigate with chat",
                instance_id="redis-prod-1",
                agent="chat",
            )

        create_kwargs = mock_create_task.await_args.kwargs
        assert create_kwargs["message"] == "Investigate with chat"
        assert create_kwargs["thread_id"] is None
        assert create_kwargs["redis_client"] is redis_client
        context = create_kwargs["context"]
        assert context["instance_id"] == "redis-prod-1"
        assert context["requested_agent_type"] == "chat"
        assert context["target_bindings"][0]["target_kind"] == "instance"
        assert context["target_bindings"][0]["resource_id"] == "redis-prod-1"
        assert context["turn_scope"]["seed_hints"] == {"instance_id": "redis-prod-1"}
        assert "thread_id" not in context
        assert "session_id" not in context

        task_kwargs = task_callable.await_args.kwargs
        assert task_kwargs["thread_id"] == "thread-123"
        assert task_kwargs["message"] == "Investigate with chat"
        assert task_kwargs["task_id"] == "task-123"
        assert task_kwargs["context"] == context

    @pytest.mark.asyncio
    async def test_queue_query_task_helper_rejects_multiple_targets(self):
        with pytest.raises(ValueError, match="only one of instance_id or cluster_id"):
            await queue_query_task_helper(
                query="Investigate",
                instance_id="redis-prod-1",
                cluster_id="cluster-1",
            )

    @pytest.mark.asyncio
    async def test_queue_query_task_helper_rejects_missing_thread(self):
        redis_client = AsyncMock()
        thread_manager = AsyncMock()
        thread_manager.get_thread = AsyncMock(return_value=None)

        with (
            patch("redis_sre_agent.core.query_helpers.get_redis_client", return_value=redis_client),
            patch(
                "redis_sre_agent.core.query_helpers.ThreadManager",
                return_value=thread_manager,
            ),
            pytest.raises(ValueError, match="Thread thread-404 not found"),
        ):
            await queue_query_task_helper(query="Follow up", thread_id="thread-404")

    @pytest.mark.asyncio
    async def test_queue_query_task_helper_rejects_missing_instance(self):
        with (
            patch(
                "redis_sre_agent.core.query_helpers.get_instance_by_id",
                new_callable=AsyncMock,
                return_value=None,
            ),
            pytest.raises(ValueError, match="Instance not found: redis-missing"),
        ):
            await queue_query_task_helper(query="Investigate", instance_id="redis-missing")

    @pytest.mark.asyncio
    async def test_queue_query_task_helper_rejects_missing_cluster(self):
        with (
            patch(
                "redis_sre_agent.core.query_helpers.get_cluster_by_id",
                new_callable=AsyncMock,
                return_value=None,
            ),
            pytest.raises(ValueError, match="Cluster not found: cluster-missing"),
        ):
            await queue_query_task_helper(query="Investigate", cluster_id="cluster-missing")

    @pytest.mark.asyncio
    async def test_queue_query_task_helper_rejects_missing_support_package(self):
        mock_manager = AsyncMock()
        mock_manager.get_metadata = AsyncMock(return_value=None)

        with (
            patch(
                "redis_sre_agent.core.query_helpers.get_support_package_manager",
                return_value=mock_manager,
            ),
            pytest.raises(ValueError, match="Support package not found: pkg-missing"),
        ):
            await queue_query_task_helper(query="Investigate", support_package_id="pkg-missing")
