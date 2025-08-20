"""Docket integration tests for SRE tasks with real Redis."""

import asyncio
import os
from unittest.mock import patch

import pytest

from redis_sre_agent.core.redis import (
    cleanup_redis_connections,
    create_indices,
)
from redis_sre_agent.core.tasks import (
    analyze_system_metrics,
    check_service_health,
    ingest_sre_document,
    register_sre_tasks,
    search_runbook_knowledge,
    test_task_system,
)


@pytest.mark.docket_integration
class TestDocketSREIntegration:
    """Integration tests for Docket task system with SRE tasks and real Redis."""

    @pytest.fixture(autouse=True)
    def check_docket_integration_enabled(self):
        """Skip if Docket integration tests are not enabled."""
        if not os.environ.get("DOCKET_INTEGRATION_TESTS"):
            pytest.skip("Docket integration tests not enabled. Set DOCKET_INTEGRATION_TESTS=true")

    @pytest.mark.asyncio
    async def test_docket_sre_task_registration(self, redis_container):
        """Test SRE task registration with real Docket/Redis."""
        if not redis_container:
            pytest.skip("Integration tests not enabled")

        try:
            # Test task system connectivity
            system_ok = await test_task_system()
            assert system_ok is True

            # Test task registration
            await register_sre_tasks()

            # Should complete without errors
            assert True

        finally:
            await cleanup_redis_connections()

    @pytest.mark.asyncio
    async def test_analyze_metrics_task_real_execution(self, redis_container):
        """Test analyze_system_metrics task with real Redis storage."""
        if not redis_container:
            pytest.skip("Integration tests not enabled")

        try:
            # Execute the task
            result = await analyze_system_metrics(
                metric_query="cpu_usage{instance='server1'} > 80", time_range="30m", threshold=85.0
            )

            # Validate result structure
            assert result["metric_query"] == "cpu_usage{instance='server1'} > 80"
            assert result["time_range"] == "30m"
            assert result["status"] == "analyzed"
            assert "task_id" in result
            assert "timestamp" in result
            assert "findings" in result

            # Validate findings structure
            findings = result["findings"]
            assert "anomalies_detected" in findings
            assert "current_value" in findings
            assert "threshold_breached" in findings

            # Task ID should be a valid ULID
            assert len(result["task_id"]) == 26  # ULID length

        finally:
            await cleanup_redis_connections()

    @pytest.mark.asyncio
    async def test_health_check_task_real_execution(self, redis_container):
        """Test check_service_health task with real Redis storage."""
        if not redis_container:
            pytest.skip("Integration tests not enabled")

        try:
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

        finally:
            await cleanup_redis_connections()

    @pytest.mark.asyncio
    async def test_document_ingestion_task_real_execution(self, redis_container):
        """Test ingest_sre_document task with real Redis and embeddings."""
        if not redis_container:
            pytest.skip("Integration tests not enabled")

        try:
            # Ensure indices exist
            await create_indices()

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

        finally:
            await cleanup_redis_connections()

    @pytest.mark.asyncio
    async def test_knowledge_search_task_real_execution(self, redis_container):
        """Test search_runbook_knowledge task with real Redis."""
        if not redis_container:
            pytest.skip("Integration tests not enabled")

        try:
            # Ensure indices exist
            await create_indices()

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
                    result = await search_runbook_knowledge(
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

        finally:
            await cleanup_redis_connections()

    @pytest.mark.asyncio
    async def test_concurrent_sre_task_execution(self, redis_container):
        """Test concurrent execution of multiple SRE tasks."""
        if not redis_container:
            pytest.skip("Integration tests not enabled")

        try:
            await create_indices()

            # Mock vectorizer for predictable results
            with patch("redis_sre_agent.core.tasks.get_vectorizer") as mock_vectorizer:
                mock_vectorizer_instance = mock_vectorizer.return_value
                mock_vectorizer_instance.embed_many.return_value = [[0.3] * 1536]

                # Execute multiple tasks concurrently
                tasks = [
                    analyze_system_metrics("cpu_usage", "1h", 80.0),
                    analyze_system_metrics("memory_usage", "30m", 90.0),
                    check_service_health("redis_cluster", ["redis:6379"], 30),
                    check_service_health("web_servers", ["web1:80", "web2:80"], 30),
                ]

                # Run concurrently
                results = await asyncio.gather(*tasks)

                # Validate all tasks completed
                assert len(results) == 4

                # Validate each result has expected structure
                for i, result in enumerate(results):
                    assert "task_id" in result
                    assert "timestamp" in result

                    if i < 2:  # Metrics tasks
                        assert result["status"] == "analyzed"
                        assert "findings" in result
                    else:  # Health check tasks
                        assert "overall_status" in result
                        assert "health_checks" in result

                # Verify all task IDs are unique
                task_ids = [result["task_id"] for result in results]
                assert len(set(task_ids)) == 4  # All unique

        finally:
            await cleanup_redis_connections()

    @pytest.mark.asyncio
    async def test_task_retry_behavior(self, redis_container):
        """Test SRE task retry behavior with failures."""
        if not redis_container:
            pytest.skip("Integration tests not enabled")

        try:
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
                result = await analyze_system_metrics(
                    metric_query="test_retry_metric", time_range="5m"
                )

                # Should eventually succeed
                assert result["status"] == "analyzed"
                assert call_count == 3  # Failed twice, succeeded on 3rd

        finally:
            await cleanup_redis_connections()


@pytest.mark.docket_integration
class TestDocketWorkerIntegration:
    """Test Docket worker integration with SRE tasks."""

    @pytest.fixture(autouse=True)
    def check_docket_integration_enabled(self):
        """Skip if Docket integration tests are not enabled."""
        if not os.environ.get("DOCKET_INTEGRATION_TESTS"):
            pytest.skip("Docket integration tests not enabled")

    @pytest.mark.asyncio
    async def test_worker_startup_with_real_redis(self, redis_container):
        """Test that worker can start up with real Redis."""
        if not redis_container:
            pytest.skip("Integration tests not enabled")

        redis_url = redis_container.get_connection_url()

        # Test worker main function imports and basic setup
        with patch.dict(os.environ, {"REDIS_URL": redis_url}):
            from redis_sre_agent.worker import main

            # Mock Worker.run to avoid infinite loop
            with patch("redis_sre_agent.worker.Worker.run") as mock_worker_run:
                mock_worker_run.return_value = None

                # Should start without errors
                await main()

                # Verify Worker.run was called with correct parameters
                mock_worker_run.assert_called_once()
                call_kwargs = mock_worker_run.call_args.kwargs

                assert call_kwargs["docket_name"] == "sre_docket"
                assert call_kwargs["url"] == redis_url
                assert call_kwargs["concurrency"] == 2
                assert call_kwargs["tasks"] == ["redis_sre_agent.core.tasks:SRE_TASK_COLLECTION"]

    @pytest.mark.asyncio
    async def test_task_collection_registration(self, redis_container):
        """Test that SRE task collection is properly registered."""
        if not redis_container:
            pytest.skip("Integration tests not enabled")

        from redis_sre_agent.core.tasks import SRE_TASK_COLLECTION

        # Verify task collection has expected tasks
        assert len(SRE_TASK_COLLECTION) == 4

        task_names = [task.__name__ for task in SRE_TASK_COLLECTION]
        expected_tasks = [
            "analyze_system_metrics",
            "search_runbook_knowledge",
            "check_service_health",
            "ingest_sre_document",
        ]

        for expected_task in expected_tasks:
            assert expected_task in task_names

        # Verify all tasks are callable
        for task in SRE_TASK_COLLECTION:
            assert callable(task)


@pytest.mark.docket_integration
class TestDocketErrorHandling:
    """Test Docket error handling scenarios."""

    @pytest.fixture(autouse=True)
    def check_docket_integration_enabled(self):
        """Skip if Docket integration tests are not enabled."""
        if not os.environ.get("DOCKET_INTEGRATION_TESTS"):
            pytest.skip("Docket integration tests not enabled")

    @pytest.mark.asyncio
    async def test_redis_connection_failure_handling(self):
        """Test handling of Redis connection failures."""
        # Test with invalid Redis URL
        invalid_redis_url = "redis://invalid-host:6379/0"

        with patch.dict(os.environ, {"REDIS_URL": invalid_redis_url}):
            # Task system test should fail gracefully
            system_ok = await test_task_system()
            assert system_ok is False

    @pytest.mark.asyncio
    async def test_task_execution_error_handling(self, redis_container):
        """Test error handling during task execution."""
        if not redis_container:
            pytest.skip("Integration tests not enabled")

        try:
            # Force an error in Redis operations
            with patch("redis_sre_agent.core.tasks.get_redis_client") as mock_redis_client:
                mock_client = mock_redis_client.return_value
                mock_client.hset.side_effect = Exception("Redis operation failed")

                # Task should raise the exception
                with pytest.raises(Exception, match="Redis operation failed"):
                    await analyze_system_metrics(metric_query="error_test_metric", time_range="1m")

        finally:
            await cleanup_redis_connections()


# Helper function to run Docket integration tests
def run_docket_integration_tests():
    """Run Docket integration tests with proper environment setup."""
    if not os.environ.get("DOCKET_INTEGRATION_TESTS"):
        print("ℹ️  Set DOCKET_INTEGRATION_TESTS=true to run Docket integration tests.")
        return

    print("🚀 Running Docket SRE integration tests...")

    # Set environment for tests
    os.environ["INTEGRATION_TESTS"] = "true"
    os.environ["DOCKET_INTEGRATION_TESTS"] = "true"

    # Run the tests
    import subprocess

    result = subprocess.run(
        [
            "uv",
            "run",
            "pytest",
            "tests/integration/test_docket_sre_integration.py",
            "-v",
            "-m",
            "docket_integration",
        ]
    )

    return result.returncode == 0


if __name__ == "__main__":
    run_docket_integration_tests()
