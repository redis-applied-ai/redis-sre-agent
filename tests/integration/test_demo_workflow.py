"""Integration tests for complete demo workflow."""

import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from redis_sre_agent.agent.langgraph_agent import get_sre_agent
from redis_sre_agent.pipelines.orchestrator import PipelineOrchestrator
from redis_sre_agent.pipelines.scraper.base import (
    DocumentCategory,
    DocumentType,
    ScrapedDocument,
    SeverityLevel,
)
from redis_sre_agent.pipelines.scraper.runbook_generator import RunbookGenerator
from redis_sre_agent.tools.prometheus_client import PrometheusClient


class TestDemoWorkflow:
    """Test complete demo workflow integration."""

    def setup_method(self):
        """Clear agent singleton before each test."""
        import redis_sre_agent.agent.langgraph_agent as agent_module

        agent_module._sre_agent = None

    def teardown_method(self):
        """Clear agent singleton after each test."""
        import redis_sre_agent.agent.langgraph_agent as agent_module

        agent_module._sre_agent = None

    @pytest.fixture
    async def demo_environment(self):
        """Set up demo environment with all components."""
        with tempfile.TemporaryDirectory() as temp_dir:
            artifacts_path = Path(temp_dir) / "artifacts"
            artifacts_path.mkdir()

            # Create orchestrator
            orchestrator = PipelineOrchestrator(str(artifacts_path))

            # Create Prometheus client
            prometheus_client = PrometheusClient("http://test-prometheus:9090")

            # Mock Redis components to avoid real connections
            with patch("redis_sre_agent.core.redis.get_knowledge_index") as mock_index_func:
                with patch(
                    "redis_sre_agent.pipelines.ingestion.processor.get_knowledge_index"
                ) as mock_index_func2:
                    with patch(
                        "redis_sre_agent.pipelines.ingestion.processor.get_vectorizer"
                    ) as mock_vectorizer_func:
                        # Create mock instances
                        mock_index = AsyncMock()
                        mock_index.load = AsyncMock()
                        mock_index.query = AsyncMock(return_value=[])
                        mock_index.add_many = AsyncMock()
                        mock_index.clear = AsyncMock()
                        # Mock all potential Redis operations
                        mock_index.create = AsyncMock()
                        mock_index.exists = AsyncMock(return_value=True)
                        mock_index.info = AsyncMock(return_value={})
                        # Make both mock functions return the same mock instance
                        mock_index_func.return_value = mock_index
                        mock_index_func2.return_value = mock_index

                        mock_vectorizer = AsyncMock()
                        mock_vectorizer.embed_many = AsyncMock(return_value=[[0.1, 0.2, 0.3]])
                        mock_vectorizer_func.return_value = mock_vectorizer

                        yield {
                            "orchestrator": orchestrator,
                            "prometheus_client": prometheus_client,
                            "artifacts_path": artifacts_path,
                            "mock_index": mock_index,
                            "mock_vectorizer": mock_vectorizer,
                        }

    @pytest.mark.asyncio
    async def test_complete_pipeline_workflow(self, demo_environment):
        """Test complete pipeline from scraping to ingestion."""
        orchestrator = demo_environment["orchestrator"]

        # Mock successful runbook generation
        sample_runbook = """
# Redis Memory Management

## Overview
This runbook covers Redis memory optimization procedures.

## Symptoms
- High memory usage alerts
- OOM killer activation

## Diagnostic Steps
1. Run INFO memory command
2. Check memory usage patterns

## Resolution Procedures
1. Analyze memory usage with MEMORY USAGE
2. Optimize data structures
3. Configure memory limits

## Prevention
- Monitor memory metrics continuously
- Set appropriate maxmemory policies

## Escalation
Contact Redis DBA team for persistent issues
        """

        # Mock scraper to return standardized runbook
        for scraper_name, scraper in orchestrator.scrapers.items():
            if isinstance(scraper, RunbookGenerator):
                # Mock the entire runbook generation workflow
                mock_doc = ScrapedDocument(
                    title="Redis Memory Management",
                    content=sample_runbook,
                    source_url="https://redis.io/docs/memory-optimization",
                    category=DocumentCategory.SHARED,
                    doc_type=DocumentType.RUNBOOK,
                    severity=SeverityLevel.HIGH,
                    metadata={
                        "generated_by": "runbook_generator",
                        "source_type": "redis_official_docs",
                    },
                )

                scraper.scraped_documents = [mock_doc]

                # Create an async function that saves the document to the file system
                async def mock_scraping_job():
                    # Actually save the document using the storage system
                    scraper.storage.save_document(mock_doc)
                    return {
                        "source": "runbook_generator",
                        "documents_scraped": 1,
                        "success": True,
                    }

                scraper.run_scraping_job = mock_scraping_job
            else:
                # Mock other scrapers to return empty results
                scraper.scraped_documents = []
                scraper.run_scraping_job = AsyncMock(
                    return_value={
                        "source": scraper.get_source_name(),
                        "documents_scraped": 0,
                        "success": True,
                    }
                )

        # Run complete pipeline
        result = await orchestrator.run_full_pipeline()

        # Verify scraping phase
        assert result["success"] is True
        assert result["scraping"]["success"] is True
        assert result["scraping"]["total_documents"] == 1

        # Verify ingestion phase
        assert result["ingestion"]["success"] is True
        assert result["ingestion"]["documents_processed"] == 1
        assert result["ingestion"]["chunks_indexed"] > 0

        # Verify artifacts were created
        batch_date = result["scraping"]["batch_date"]
        batch_path = demo_environment["artifacts_path"] / batch_date

        assert batch_path.exists()
        # Check for batch manifest (created during scraping phase)
        assert (batch_path / "batch_manifest.json").exists()
        assert (batch_path / "ingestion_manifest.json").exists()

    @pytest.mark.asyncio
    async def test_runbook_generator_with_redis_urls(self, demo_environment):
        """Test runbook generator specifically with Redis documentation URLs."""
        orchestrator = demo_environment["orchestrator"]
        runbook_generator = orchestrator.scrapers["runbook_generator"]

        # Verify Redis URLs are configured
        redis_urls = [
            "https://redis.io/docs/latest/operate/oss_and_stack/management/replication/",
            "https://redis.io/docs/latest/operate/oss_and_stack/management/optimization/latency/",
            "https://redis.io/docs/latest/operate/oss_and_stack/management/debugging/",
        ]

        for url in redis_urls:
            assert url in runbook_generator.config["runbook_urls"]

        # Mock URL content extraction for Redis docs
        mock_redis_content = """
        <html>
        <body>
        <article>
            <h1>Redis Latency Optimization</h1>
            <p>This guide covers Redis latency optimization techniques.</p>
            <h2>Common Latency Issues</h2>
            <ul>
                <li>Slow queries blocking operations</li>
                <li>Memory swapping</li>
                <li>Network congestion</li>
            </ul>
            <h2>Diagnostic Commands</h2>
            <pre>redis-cli --latency-history -i 15</pre>
            <pre>INFO commandstats</pre>
        </article>
        </body>
        </html>
        """

        # Mock OpenAI standardization
        standardized_runbook = """
# Redis Latency Optimization

## Overview
Comprehensive guide to identifying and resolving Redis latency issues.

## Symptoms
- Increased response times
- Application timeouts
- Performance degradation alerts

## Diagnostic Steps
1. Monitor latency with redis-cli --latency-history -i 15
2. Check command statistics with INFO commandstats
3. Analyze slow query log

## Resolution Procedures
1. Identify slow operations causing blocking
2. Optimize query patterns
3. Configure appropriate timeout values
4. Monitor memory usage patterns

## Prevention
- Implement latency monitoring
- Use appropriate data structures
- Configure memory policies

## Escalation
Escalate to Redis performance team if latency exceeds SLA thresholds
        """

        with patch.object(runbook_generator, "_scrape_url_content") as mock_scrape:
            with patch.object(runbook_generator, "_generate_standardized_runbook") as mock_generate:
                mock_scrape.return_value = mock_redis_content
                mock_generate.return_value = standardized_runbook

                # Test URL extraction for Redis docs
                result = await runbook_generator.test_url_extraction(
                    redis_urls[1]
                )  # Latency optimization

                assert result["success"] is True
                assert result["source_type"] == "redis_official_docs"
                assert result["content_length"] > 0

                # Test full scraping with single URL
                runbook_generator.config["runbook_urls"] = [redis_urls[1]]  # Test just one URL

                documents = await runbook_generator.scrape()

                assert len(documents) == 1
                document = documents[0]

                assert document.title == "Redis Latency Optimization"
                assert document.doc_type == DocumentType.RUNBOOK
                assert "Diagnostic Steps" in document.content
                assert "redis-cli --latency-history" in document.content

    @pytest.mark.asyncio
    async def test_prometheus_integration_with_agent(self, demo_environment):
        """Test Prometheus integration with SRE agent."""
        prometheus_client = demo_environment["prometheus_client"]

        # Mock Prometheus responses for Redis metrics
        mock_metrics_responses = {
            "redis_memory_used_bytes": {"result": [{"value": [1642694400, "268435456"]}]},  # 256MB
            "redis_connected_clients": {"result": [{"value": [1642694400, "25"]}]},
            "rate(redis_commands_processed_total[1m])": {
                "result": [{"value": [1642694400, "1500"]}]
            },
        }

        def mock_query_response(query):
            return mock_metrics_responses.get(query, {"result": []})

        with patch.object(prometheus_client, "query", side_effect=mock_query_response):
            # Test individual metric queries
            memory_result = await prometheus_client.query("redis_memory_used_bytes")
            assert len(memory_result["result"]) == 1
            assert memory_result["result"][0]["value"][1] == "268435456"

            # Test common Redis metrics
            common_metrics = await prometheus_client.get_common_redis_metrics()

            assert "memory_usage" in common_metrics
            assert common_metrics["memory_usage"]["value"] == 268435456.0

            assert "connected_clients" in common_metrics
            assert common_metrics["connected_clients"]["value"] == 25.0

            assert "ops_per_sec" in common_metrics
            assert common_metrics["ops_per_sec"]["value"] == 1500.0

    @pytest.mark.asyncio
    async def test_agent_with_knowledge_base(self, demo_environment):
        """Test SRE agent querying ingested knowledge base."""
        # First, populate knowledge base with sample runbook
        orchestrator = demo_environment["orchestrator"]

        sample_doc = ScrapedDocument(
            title="Redis Connection Troubleshooting",
            content="""
# Redis Connection Issues

## Overview
Guide for diagnosing and resolving Redis connection problems.

## Symptoms
- Connection timeouts
- "Connection refused" errors
- High connection latency

## Diagnostic Steps
1. Check Redis server status with INFO server
2. Verify network connectivity
3. Check connection limits with CONFIG GET maxclients
4. Monitor connection pool usage

## Resolution Procedures
1. Restart Redis service if unresponsive
2. Increase connection limits if needed
3. Optimize connection pool configuration
4. Check firewall and network settings

## Prevention
- Monitor connection metrics
- Set appropriate connection timeouts
- Use connection pooling effectively

## Escalation
Contact infrastructure team for persistent connectivity issues
            """,
            source_url="https://redis.io/docs/troubleshooting/connections",
            category=DocumentCategory.OSS,
            doc_type=DocumentType.RUNBOOK,
            severity=SeverityLevel.HIGH,
        )

        # Mock successful ingestion
        batch_date = orchestrator.storage.current_date
        batch_path = demo_environment["artifacts_path"] / batch_date
        batch_path.mkdir(exist_ok=True)

        # Create category directory and document
        oss_path = batch_path / "oss"
        oss_path.mkdir(exist_ok=True)

        doc_path = oss_path / "connection_troubleshooting.json"
        with open(doc_path, "w") as f:
            json.dump(sample_doc.to_dict(), f)

        # Mock successful ingestion
        with patch.object(orchestrator.ingestion, "ingest_batch") as mock_ingest:
            mock_ingest.return_value = {
                "batch_date": batch_date,
                "documents_processed": 1,
                "chunks_indexed": 3,
                "success": True,
            }

            ingestion_result = await orchestrator.run_ingestion_pipeline(batch_date)
            assert ingestion_result["success"] is True

        # Now test agent querying the knowledge base
        with patch("redis_sre_agent.agent.langgraph_agent.SRELangGraphAgent") as mock_agent_class:
            with patch("redis_sre_agent.agent.langgraph_agent.get_sre_agent") as mock_get_agent:
                mock_agent = AsyncMock()

                # Mock knowledge search results

                # Mock agent processing
                mock_agent.process_query = AsyncMock(
                    return_value="""
Based on the knowledge base search, I found a comprehensive Redis connection troubleshooting guide. Here's how to diagnose your connection issues:

**Immediate Steps:**
1. Check Redis server status with `INFO server`
2. Verify network connectivity to Redis host
3. Check connection limits with `CONFIG GET maxclients`

**Common Causes:**
- Connection timeouts due to network issues
- Maxclients limit exceeded
- Redis server unresponsive

**Resolution:**
- Restart Redis service if unresponsive
- Increase connection limits if needed: `CONFIG SET maxclients 1000`
- Check firewall and network settings

Would you like me to help you run specific diagnostic commands or check your current Redis configuration?
                """
                )

                mock_agent_class.return_value = mock_agent
                mock_get_agent.return_value = mock_agent

                # Test agent query
                agent = get_sre_agent()
                response = await agent.process_query(
                    query="I'm having Redis connection issues, can you help troubleshoot?",
                    session_id="test_session",
                    user_id="test_user",
                )

                assert "connection troubleshooting" in response.lower()
                assert "info server" in response.lower()
                assert "maxclients" in response.lower()

            mock_agent.process_query.assert_called_once()

    @pytest.mark.asyncio
    async def test_end_to_end_monitoring_scenario(self, demo_environment):
        """Test complete monitoring scenario from alert to resolution."""
        demo_environment["orchestrator"]
        prometheus_client = demo_environment["prometheus_client"]

        # Scenario: High Redis memory usage alert

        # 1. Prometheus detects high memory usage
        high_memory_response = {
            "result": [{"value": [1642694400, "1073741824"]}]  # 1GB memory usage
        }

        with patch.object(prometheus_client, "query", return_value=high_memory_response):
            memory_result = await prometheus_client.query("redis_memory_used_bytes")
            memory_value = float(memory_result["result"][0]["value"][1])

            assert memory_value == 1073741824.0  # 1GB

            # 2. SRE receives alert and queries agent
            alert_query = (
                f"Redis memory usage is at {memory_value / (1024**3):.1f}GB, what should I check?"
            )

            # 3. Agent should search knowledge base for memory troubleshooting
            with patch("redis_sre_agent.core.tasks.search_knowledge_base") as mock_search:
                mock_search.return_value = {
                    "task_id": "search_456",
                    "query": alert_query,
                    "results": [
                        {
                            "title": "Redis Memory Management",
                            "content": "Steps to diagnose and resolve Redis memory issues...",
                            "source": "redis_memory_runbook",
                            "score": 0.92,
                        }
                    ],
                }

                # 4. Agent provides actionable guidance
                with patch(
                    "redis_sre_agent.agent.langgraph_agent.SRELangGraphAgent"
                ) as mock_agent_class:
                    with patch(
                        "redis_sre_agent.agent.langgraph_agent.get_sre_agent"
                    ) as mock_get_agent:
                        mock_agent = AsyncMock()
                        mock_agent.process_query = AsyncMock(
                            return_value="""
I see Redis memory usage is at 1.0GB. Let me help you investigate:

**Immediate Checks:**
1. Run `INFO memory` to get detailed memory breakdown
2. Check `MEMORY USAGE` on largest keys
3. Verify maxmemory policy with `CONFIG GET maxmemory-policy`

**Key Metrics to Monitor:**
- used_memory vs used_memory_rss
- Number of keys and their types
- Memory fragmentation ratio

**Common Resolutions:**
- Enable key eviction if not set: `CONFIG SET maxmemory-policy allkeys-lru`
- Identify and optimize large keys
- Consider memory defragmentation

Would you like me to help analyze specific Redis INFO output or run diagnostic commands?
                        """
                        )

                        mock_agent_class.return_value = mock_agent
                        mock_get_agent.return_value = mock_agent

                        agent = get_sre_agent()
                        response = await agent.process_query(
                            query=alert_query, session_id="alert_session", user_id="sre_engineer"
                        )

                        # Verify agent provides actionable guidance
                        assert "INFO memory" in response
                        assert "MEMORY USAGE" in response
                        assert "maxmemory-policy" in response
                        assert "allkeys-lru" in response

    @pytest.mark.asyncio
    async def test_pipeline_status_and_monitoring(self, demo_environment):
        """Test pipeline status monitoring and batch management."""
        orchestrator = demo_environment["orchestrator"]

        # Create sample batch structure
        batch_dates = ["2025-01-20", "2025-01-19", "2025-01-18"]

        for batch_date in batch_dates:
            batch_path = demo_environment["artifacts_path"] / batch_date
            batch_path.mkdir()

            # Create manifest
            manifest = {
                "batch_date": batch_date,
                "total_documents": 5,
                "scrapers": ["runbook_generator", "redis_docs"],
            }

            with open(batch_path / "manifest.json", "w") as f:
                json.dump(manifest, f)

            # Create ingestion manifest for some batches
            if batch_date != "2025-01-18":  # Skip last batch
                ingestion_manifest = {
                    "batch_date": batch_date,
                    "documents_processed": 5,
                    "chunks_indexed": 15,
                    "success": True,
                }

                with open(batch_path / "ingestion_manifest.json", "w") as f:
                    json.dump(ingestion_manifest, f)

        # Test pipeline status
        status = await orchestrator.get_pipeline_status()

        assert "artifacts_path" in status
        assert "current_batch_date" in status
        assert len(status["available_batches"]) >= 3
        assert "scrapers" in status
        assert (
            len(status["scrapers"]) == 4
        )  # redis_docs, redis_kb, redis_runbooks, runbook_generator

        # Test ingestion status
        assert "ingestion" in status
        assert status["ingestion"]["batches_ingested"] >= 2  # Two batches have ingestion manifests

        # Test cleanup functionality
        cleanup_result = await orchestrator.cleanup_old_batches(
            keep_days=1
        )  # Aggressive cleanup for testing

        assert "batches_removed" in cleanup_result
        assert "batches_kept" in cleanup_result
        assert "errors" in cleanup_result
