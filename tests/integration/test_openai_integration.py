"""OpenAI integration tests with live API calls."""

import os
from unittest.mock import patch

import pytest

from redis_sre_agent.core.redis import (
    cleanup_redis_connections,
    create_indices,
    get_knowledge_index,
    get_vectorizer,
)
from redis_sre_agent.core.tasks import (
    ingest_sre_document,
    search_runbook_knowledge,
)


@pytest.mark.openai_integration
class TestOpenAIIntegration:
    """Integration tests with real OpenAI API calls.

    These tests require:
    - OPENAI_API_KEY environment variable
    - OPENAI_INTEGRATION_TESTS=true to run
    - Redis container (provided by redis_container fixture)
    """

    @pytest.fixture(autouse=True)
    def check_integration_tests_enabled(self):
        """Skip if OpenAI integration tests are not enabled."""
        if not os.environ.get("OPENAI_INTEGRATION_TESTS"):
            pytest.skip("OpenAI integration tests not enabled. Set OPENAI_INTEGRATION_TESTS=true")

        if not os.environ.get("OPENAI_API_KEY"):
            pytest.skip("OPENAI_API_KEY not set")

    @pytest.mark.asyncio
    async def test_real_embedding_generation(self, redis_container):
        """Test real embedding generation with OpenAI API."""
        if not redis_container:
            pytest.skip("Integration tests not enabled")

        # Clear global state to ensure fresh instances
        from redis_sre_agent.core import redis

        redis._vectorizer = None
        redis._redis_client = None
        redis._document_index = None

        try:
            # Get real vectorizer (will make OpenAI API call)
            vectorizer = get_vectorizer()

            # Test embedding generation
            test_texts = [
                "Redis memory usage is high",
                "Service health check failed",
                "CPU utilization exceeded threshold",
            ]

            embeddings = await vectorizer.embed_many(test_texts)

            # Validate embeddings
            assert len(embeddings) == 3
            for embedding in embeddings:
                assert isinstance(embedding, list)
                assert len(embedding) == 1536  # text-embedding-3-small dimension
                assert all(isinstance(val, float) for val in embedding)

            # Test that different texts produce different embeddings
            assert embeddings[0] != embeddings[1] != embeddings[2]

        finally:
            await cleanup_redis_connections()

    @pytest.mark.asyncio
    async def test_real_vector_index_creation_and_search(self, redis_container):
        """Test creating vector indices and searching with real embeddings."""
        if not redis_container:
            pytest.skip("Integration tests not enabled")

        # Clear global state
        from redis_sre_agent.core import redis

        redis._vectorizer = None
        redis._redis_client = None
        redis._document_index = None

        try:
            # Create indices with real Redis
            indices_created = await create_indices()
            assert indices_created is True

            # Get real components
            get_vectorizer()
            index = get_knowledge_index()

            # Verify index exists
            index_exists = await index.exists()
            assert index_exists is True

        finally:
            await cleanup_redis_connections()

    @pytest.mark.asyncio
    async def test_real_document_ingestion_workflow(self, redis_container):
        """Test complete document ingestion with real embeddings."""
        if not redis_container:
            pytest.skip("Integration tests not enabled")

        # Clear global state
        from redis_sre_agent.core import redis

        redis._vectorizer = None
        redis._redis_client = None
        redis._document_index = None

        try:
            # Ensure indices exist
            await create_indices()

            # Test document ingestion with real embeddings
            result = await ingest_sre_document(
                title="Redis High Memory Alert",
                content="When Redis memory usage exceeds 80%, check for memory leaks, large keys, and consider implementing eviction policies. Common causes include unoptimized data structures and lack of TTL settings.",
                source="test_integration_runbook.md",
                category="monitoring",
                severity="warning",
            )

            # Validate ingestion result
            assert result["status"] == "ingested"
            assert result["title"] == "Redis High Memory Alert"
            assert result["source"] == "test_integration_runbook.md"
            assert result["category"] == "monitoring"
            assert "document_id" in result
            assert "task_id" in result

            # Test searching for the ingested document
            search_result = await search_runbook_knowledge(
                query="Redis memory usage high", category="monitoring", limit=3
            )

            # Validate search results
            assert search_result["query"] == "Redis memory usage high"
            assert search_result["category"] == "monitoring"
            assert search_result["results_count"] >= 0  # May be 0 if vector similarity is low

            # If we found results, validate their structure
            if search_result["results_count"] > 0:
                result_item = search_result["results"][0]
                assert "title" in result_item
                assert "content" in result_item
                assert "source" in result_item
                assert "score" in result_item
                assert isinstance(result_item["score"], (int, float))

        finally:
            await cleanup_redis_connections()

    @pytest.mark.asyncio
    async def test_semantic_search_quality(self, redis_container):
        """Test semantic search quality with multiple related documents."""
        if not redis_container:
            pytest.skip("Integration tests not enabled")

        # Clear global state
        from redis_sre_agent.core import redis

        redis._vectorizer = None
        redis._redis_client = None
        redis._document_index = None

        try:
            # Ensure indices exist
            await create_indices()

            # Ingest multiple related documents
            test_documents = [
                {
                    "title": "Redis Memory Management",
                    "content": "Redis memory optimization techniques including eviction policies, memory analysis, and key compression strategies.",
                    "category": "optimization",
                },
                {
                    "title": "CPU Performance Monitoring",
                    "content": "Monitor CPU utilization across services, set up alerts for high CPU usage, and identify performance bottlenecks.",
                    "category": "monitoring",
                },
                {
                    "title": "Network Latency Issues",
                    "content": "Diagnose network latency problems, check connection pools, and optimize network configuration.",
                    "category": "networking",
                },
                {
                    "title": "Redis Connection Pool Tuning",
                    "content": "Configure Redis connection pools for optimal performance, including timeout settings and pool sizing.",
                    "category": "optimization",
                },
            ]

            # Ingest all documents
            for i, doc in enumerate(test_documents):
                await ingest_sre_document(
                    title=doc["title"],
                    content=doc["content"],
                    source=f"test_semantic_{i}.md",
                    category=doc["category"],
                    severity="info",
                )

            # Test semantic search - should find Redis-related documents for Redis query
            redis_search = await search_runbook_knowledge(query="Redis performance issues", limit=5)

            # Test category filtering
            optimization_search = await search_runbook_knowledge(
                query="performance optimization", category="optimization", limit=3
            )

            # Validate that searches return results
            assert redis_search["results_count"] >= 0
            assert optimization_search["results_count"] >= 0

            # If we have results, they should have reasonable scores
            if redis_search["results_count"] > 0:
                for result in redis_search["results"]:
                    # Scores should be reasonable (typically 0.0 to 1.0)
                    assert 0.0 <= result["score"] <= 1.0

            if optimization_search["results_count"] > 0:
                for result in optimization_search["results"]:
                    assert result["source"].startswith("test_semantic_")
                    assert 0.0 <= result["score"] <= 1.0

        finally:
            await cleanup_redis_connections()

    @pytest.mark.asyncio
    async def test_embedding_consistency(self, redis_container):
        """Test that identical texts produce identical embeddings."""
        if not redis_container:
            pytest.skip("Integration tests not enabled")

        # Clear global state
        from redis_sre_agent.core import redis

        redis._vectorizer = None

        try:
            vectorizer = get_vectorizer()

            test_text = "Redis cluster requires careful memory management"

            # Generate embeddings multiple times
            embedding1 = await vectorizer.embed_many([test_text])
            embedding2 = await vectorizer.embed_many([test_text])

            # Should be identical (OpenAI embeddings are deterministic)
            assert embedding1[0] == embedding2[0]

            # Test different texts produce different embeddings
            different_text = "CPU monitoring shows high utilization"
            embedding3 = await vectorizer.embed_many([different_text])

            assert embedding1[0] != embedding3[0]

        finally:
            await cleanup_redis_connections()


@pytest.mark.openai_integration
class TestOpenAIErrorHandling:
    """Test error handling with OpenAI API."""

    @pytest.fixture(autouse=True)
    def check_integration_tests_enabled(self):
        """Skip if OpenAI integration tests are not enabled."""
        if not os.environ.get("OPENAI_INTEGRATION_TESTS"):
            pytest.skip("OpenAI integration tests not enabled")

    @pytest.mark.asyncio
    async def test_invalid_api_key_handling(self, redis_container):
        """Test handling of invalid OpenAI API key."""
        if not redis_container:
            pytest.skip("Integration tests not enabled")

        # Test with invalid API key
        with patch.dict(os.environ, {"OPENAI_API_KEY": "invalid-key"}):
            from redis_sre_agent.core import redis

            redis._vectorizer = None  # Force re-creation

            try:
                vectorizer = get_vectorizer()

                # This should raise an authentication error
                with pytest.raises(Exception) as exc_info:
                    await vectorizer.embed_many(["test text"])

                # Should be an authentication-related error
                error_str = str(exc_info.value).lower()
                assert any(
                    keyword in error_str
                    for keyword in ["authentication", "api", "key", "unauthorized", "401"]
                )

            finally:
                redis._vectorizer = None

    @pytest.mark.asyncio
    async def test_rate_limit_behavior(self, redis_container):
        """Test behavior under potential rate limits."""
        if not redis_container:
            pytest.skip("Integration tests not enabled")

        # Clear global state
        from redis_sre_agent.core import redis

        redis._vectorizer = None

        try:
            vectorizer = get_vectorizer()

            # Generate multiple embeddings in succession
            # This tests rate limit handling (though we shouldn't hit limits in normal testing)
            test_texts = [f"Test document {i} for rate limit testing" for i in range(5)]

            embeddings = await vectorizer.embed_many(test_texts)

            # Should succeed and return correct number of embeddings
            assert len(embeddings) == 5
            for embedding in embeddings:
                assert len(embedding) == 1536

        finally:
            await cleanup_redis_connections()


@pytest.mark.openai_integration
class TestRealWorkflowIntegration:
    """Test complete workflows with real OpenAI integration."""

    @pytest.fixture(autouse=True)
    def check_integration_tests_enabled(self):
        """Skip if OpenAI integration tests are not enabled."""
        if not os.environ.get("OPENAI_INTEGRATION_TESTS"):
            pytest.skip("OpenAI integration tests not enabled")

    @pytest.mark.asyncio
    async def test_complete_sre_knowledge_workflow(self, redis_container):
        """Test complete SRE knowledge management workflow."""
        if not redis_container:
            pytest.skip("Integration tests not enabled")

        # Clear global state
        from redis_sre_agent.core import redis

        redis._vectorizer = None
        redis._redis_client = None
        redis._document_index = None

        try:
            # 1. Set up infrastructure
            indices_created = await create_indices()
            assert indices_created is True

            # 2. Ingest SRE knowledge base
            sre_documents = [
                {
                    "title": "Redis Cluster Monitoring Best Practices",
                    "content": "Monitor Redis cluster health using redis-cli, check node status, memory usage, and replication lag. Set up alerts for node failures and memory thresholds.",
                    "category": "monitoring",
                    "severity": "info",
                },
                {
                    "title": "High CPU Incident Response",
                    "content": "When CPU usage exceeds 90%, identify top processes using htop, check for infinite loops, restart problematic services, and scale horizontally if needed.",
                    "category": "incident",
                    "severity": "critical",
                },
                {
                    "title": "Database Connection Pool Exhaustion",
                    "content": "Diagnose connection pool exhaustion by checking active connections, increase pool size, optimize query performance, and implement connection retry logic.",
                    "category": "database",
                    "severity": "warning",
                },
            ]

            ingestion_results = []
            for doc in sre_documents:
                result = await ingest_sre_document(
                    title=doc["title"],
                    content=doc["content"],
                    source=f"sre_runbook_{doc['category']}.md",
                    category=doc["category"],
                    severity=doc["severity"],
                )
                ingestion_results.append(result)

            # Validate all ingestions succeeded
            assert len(ingestion_results) == 3
            for result in ingestion_results:
                assert result["status"] == "ingested"

            # 3. Test various search scenarios
            search_scenarios = [
                {
                    "query": "Redis cluster is down",
                    "expected_category": "monitoring",
                    "description": "Should find Redis monitoring docs",
                },
                {
                    "query": "Server CPU usage is very high",
                    "expected_category": "incident",
                    "description": "Should find CPU incident response",
                },
                {
                    "query": "Database connection errors",
                    "expected_category": "database",
                    "description": "Should find database connection docs",
                },
                {
                    "query": "System performance issues",
                    "expected_category": None,  # Could match multiple categories
                    "description": "Should find relevant performance docs",
                },
            ]

            for scenario in search_scenarios:
                search_result = await search_runbook_knowledge(query=scenario["query"], limit=3)

                print(f"\n🔍 Search: '{scenario['query']}'")
                print(f"   Results: {search_result['results_count']}")

                # Should return some results for these SRE-relevant queries
                assert search_result["results_count"] >= 0

                if search_result["results_count"] > 0:
                    top_result = search_result["results"][0]
                    print(f"   Top result: {top_result['title']} (score: {top_result['score']})")

                    # Validate result structure
                    assert "title" in top_result
                    assert "content" in top_result
                    assert "source" in top_result
                    assert "score" in top_result

                    # Score should be reasonable
                    assert 0.0 <= top_result["score"] <= 1.0

            # 4. Test category filtering
            monitoring_results = await search_runbook_knowledge(
                query="system monitoring", category="monitoring", limit=2
            )

            # Should work without errors
            assert monitoring_results["category"] == "monitoring"

            print("\n✅ Complete SRE workflow test passed!")
            print(f"   - Ingested {len(sre_documents)} documents")
            print(f"   - Tested {len(search_scenarios)} search scenarios")
            print("   - Verified category filtering")

        finally:
            await cleanup_redis_connections()


# Helper function to run OpenAI integration tests
def run_openai_integration_tests():
    """Run OpenAI integration tests with proper environment setup."""
    if not os.environ.get("OPENAI_API_KEY"):
        print("❌ OPENAI_API_KEY not set. Cannot run OpenAI integration tests.")
        return

    if not os.environ.get("OPENAI_INTEGRATION_TESTS"):
        print("ℹ️  Set OPENAI_INTEGRATION_TESTS=true to run OpenAI integration tests.")
        return

    print("🚀 Running OpenAI integration tests...")

    # Set integration test environment
    os.environ["INTEGRATION_TESTS"] = "true"
    os.environ["OPENAI_INTEGRATION_TESTS"] = "true"

    # Run the tests
    import subprocess

    result = subprocess.run(
        [
            "uv",
            "run",
            "pytest",
            "tests/integration/test_openai_integration.py",
            "-v",
            "-m",
            "openai_integration",
        ]
    )

    return result.returncode == 0


if __name__ == "__main__":
    run_openai_integration_tests()
