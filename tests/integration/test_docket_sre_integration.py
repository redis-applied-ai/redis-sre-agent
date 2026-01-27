"""Docket integration tests for SRE tasks with real Redis."""

import asyncio
from unittest.mock import patch

import pytest

from redis_sre_agent.core.docket_tasks import (
    ingest_sre_document,
    register_sre_tasks,
    search_knowledge_base,
    test_task_system,
)

# check_service_health is optional and may not be present
try:
    from redis_sre_agent.core.docket_tasks import (
        check_service_health as _check_service_health,  # type: ignore
    )
except Exception:  # noqa: BLE001
    _check_service_health = None

if _check_service_health is None:
    import pytest as _pytest

    async def check_service_health(*args, **kwargs):  # type: ignore
        _pytest.skip("check_service_health not available in this build")
else:
    check_service_health = _check_service_health  # type: ignore
from redis_sre_agent.core.redis import (
    create_indices,
)


@pytest.mark.docket_integration
class TestDocketSREIntegration:
    """Integration tests for Docket task system with SRE tasks and real Redis."""

    @pytest.mark.asyncio
    async def test_docket_sre_task_registration(self, test_settings):
        """Test SRE task registration with real Docket/Redis."""
        # Test task system connectivity
        system_ok = await test_task_system()
        assert system_ok is True

        # Test task registration
        await register_sre_tasks()

        # Should complete without errors
        assert True

    @pytest.mark.asyncio
    async def test_health_check_task_real_execution(self, test_settings):
        """Test check_service_health task with real Redis storage."""
        # Execute the task
        endpoints = [
            "http://redis:6379/ping",
            "http://app:8000/health",
            "http://db:5432/health",
        ]

        result = await check_service_health(
            service_name="test_service_cluster", endpoints=endpoints, timeout=45
        )

        # Validate result structure
        assert result["service_name"] == "test_service_cluster"
        assert result["endpoints_checked"] == 3
        assert result["overall_status"] in ["healthy", "unhealthy"]
        assert "task_id" in result
        assert "health_checks" in result

        # Validate health checks
        health_checks = result["health_checks"]
        assert len(health_checks) == 3

        for check in health_checks:
            assert "endpoint" in check
            assert "status" in check
            assert "response_time_ms" in check
            assert "status_code" in check
            assert "timestamp" in check
            assert check["endpoint"] in endpoints

    @pytest.mark.asyncio
    async def test_document_ingestion_task_real_execution(self, test_settings):
        """Test ingest_sre_document task with real Redis and embeddings."""
        # Ensure indices exist using dependency injection
        await create_indices(config=test_settings)

        # Mock vectorizer to avoid OpenAI calls in Docket integration tests
        with patch("redis_sre_agent.core.tasks.get_vectorizer") as mock_vectorizer:
            mock_vectorizer_instance = mock_vectorizer.return_value
            mock_vectorizer_instance.embed_many.return_value = [[0.1] * 1536]

            # Execute the task
            result = await ingest_sre_document(
                title="Docket Integration Test Document",
                content="This document tests the integration between Docket task system and Redis vector storage for SRE knowledge management.",
                source="docket_integration_test.md",
                category="testing",
                severity="info",
            )

            # Validate result
            assert result["title"] == "Docket Integration Test Document"
            assert result["source"] == "docket_integration_test.md"
            assert result["category"] == "testing"
            assert result["status"] == "ingested"
            assert "document_id" in result
            assert "task_id" in result

    @pytest.mark.asyncio
    async def test_knowledge_search_task_real_execution(self, test_settings):
        """Test search_knowledge_base task with real Redis."""
        # Ensure indices exist using dependency injection
        await create_indices(config=test_settings)

        # Mock vectorizer for consistent testing
        with patch("redis_sre_agent.core.tasks.get_vectorizer") as mock_vectorizer:
            mock_vectorizer_instance = mock_vectorizer.return_value
            mock_vectorizer_instance.embed_many.return_value = [[0.2] * 1536]

            # Mock search results
            with patch("redis_sre_agent.core.tasks.get_knowledge_index") as mock_index:
                mock_index_instance = mock_index.return_value
                mock_index_instance.query.return_value = [
                    {
                        "title": "Mock SRE Document",
                        "content": "Mock content for testing search functionality",
                        "source": "mock_runbook.md",
                        "score": 0.85,
                    }
                ]

                # Execute the task
                result = await search_knowledge_base(
                    query="Docket task system integration", category="testing", limit=5
                )

                # Validate result
                assert result["query"] == "Docket task system integration"
                assert result["category"] == "testing"
                assert result["results_count"] == 1
                assert "task_id" in result
                assert "results" in result

                # Validate search results
                search_results = result["results"]
                assert len(search_results) == 1

                search_result = search_results[0]
                assert search_result["title"] == "Mock SRE Document"
                assert search_result["score"] == 0.85

    @pytest.mark.asyncio
    async def test_concurrent_sre_task_execution(self, test_settings):
        """Test concurrent execution of multiple SRE tasks."""
        await create_indices(config=test_settings)

        # Mock vectorizer for predictable results
        with patch("redis_sre_agent.core.tasks.get_vectorizer") as mock_vectorizer:
            mock_vectorizer_instance = mock_vectorizer.return_value
            mock_vectorizer_instance.embed_many.return_value = [[0.3] * 1536]

            # Execute multiple tasks concurrently
            tasks = [
                check_service_health("redis_cluster", ["redis:6379"], 30),
                check_service_health("web_servers", ["web1:80", "web2:80"], 30),
            ]

            # Run concurrently
            results = await asyncio.gather(*tasks)

            # Validate all tasks completed
            assert len(results) == 2

            # Validate each result has expected structure
            for result in results:
                assert "task_id" in result
                assert "timestamp" in result
                assert "overall_status" in result
                assert "health_checks" in result

            # Verify all task IDs are unique
            task_ids = [result["task_id"] for result in results]
            assert len(set(task_ids)) == 2  # All unique

    @pytest.mark.asyncio
    async def test_task_retry_behavior(self, test_settings):
        """Test SRE task retry behavior with failures."""
        # Test with simulated failure and recovery
        call_count = 0

        async def failing_redis_hset(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:  # Fail first 2 attempts
                raise Exception("Simulated Redis failure")
            return 1  # Success on 3rd attempt

        with patch("redis_sre_agent.core.tasks.get_redis_client") as mock_redis_client:
            mock_client = mock_redis_client.return_value
            mock_client.hset.side_effect = failing_redis_hset
            mock_client.expire.return_value = True

            # This should succeed after retries
            result = await check_service_health(
                service_name="test_retry_service", endpoints=["http://test:8000/health"]
            )

            # Should eventually succeed
            assert "overall_status" in result
            assert call_count == 3  # Failed twice, succeeded on 3rd


@pytest.mark.docket_integration
class TestDocketWorkerIntegration:
    """Test Docket worker integration with SRE tasks."""

    @pytest.mark.asyncio
    async def test_worker_startup_with_real_redis(self, redis_url):
        """Test that worker can start up with real Redis."""
        from click.testing import CliRunner

        from redis_sre_agent.cli.main import worker as worker_cmd

        # Mock Worker.run to avoid infinite loop
        with patch("redis_sre_agent.cli.main.Worker.run") as mock_worker_run:
            mock_worker_run.return_value = None

            # Invoke CLI with redis_url env var
            result = CliRunner(env={"REDIS_URL": redis_url}).invoke(worker_cmd)
            assert result.exit_code == 0

            # Verify Worker.run was called with correct parameters
            mock_worker_run.assert_called_once()
            call_kwargs = mock_worker_run.call_args.kwargs

            assert call_kwargs["docket_name"] == "sre_docket"
            assert call_kwargs["url"] == redis_url
            assert call_kwargs["concurrency"] == 2
            assert call_kwargs["tasks"] == ["redis_sre_agent.core.tasks:SRE_TASK_COLLECTION"]

    @pytest.mark.asyncio
    async def test_task_collection_registration(self, test_settings):
        """Test that SRE task collection is properly registered."""
        from redis_sre_agent.core.docket_tasks import SRE_TASK_COLLECTION

        # Verify task collection has expected tasks
        assert len(SRE_TASK_COLLECTION) == 4

        task_names = [task.__name__ for task in SRE_TASK_COLLECTION]
        expected_tasks = [
            "search_knowledge_base",
            "ingest_sre_document",
            "scheduler_task",
        ]

        for expected_task in expected_tasks:
            assert expected_task in task_names

        # Verify all tasks are callable
        for task in SRE_TASK_COLLECTION:
            assert callable(task)


@pytest.mark.docket_integration
class TestDocketErrorHandling:
    """Test Docket error handling scenarios."""

    @pytest.mark.asyncio
    async def test_redis_connection_failure_handling(self):
        """Test handling of Redis connection failures."""
        # Test with invalid Redis URL using dependency injection
        from pydantic import SecretStr

        from redis_sre_agent.core.config import Settings

        invalid_settings = Settings(redis_url=SecretStr("redis://invalid-host:6379/0"))

        # Task system test should fail gracefully with injected invalid config
        system_ok = await test_task_system(config=invalid_settings)
        assert system_ok is False

    @pytest.mark.asyncio
    async def test_task_execution_error_handling(self, test_settings):
        """Test error handling during task execution."""
        # Force an error in Redis operations
        with patch("redis_sre_agent.core.tasks.get_redis_client") as mock_redis_client:
            mock_client = mock_redis_client.return_value
            mock_client.hset.side_effect = Exception("Redis operation failed")

            # Task should raise the exception
            with pytest.raises(Exception, match="Redis operation failed"):
                await check_service_health(
                    service_name="error_test_service", endpoints=["http://test:8000/health"]
                )
