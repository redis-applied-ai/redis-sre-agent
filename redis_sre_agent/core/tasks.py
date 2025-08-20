"""Docket task definitions for SRE operations."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from docket import Docket, Retry
from ulid import ULID

from redis_sre_agent.core.config import settings
from redis_sre_agent.core.redis import (
    get_knowledge_index,
    get_redis_client,
    get_vectorizer,
)

logger = logging.getLogger(__name__)

# SRE-specific task registry
SRE_TASK_COLLECTION = []


def sre_task(func):
    """Decorator to register SRE tasks."""
    SRE_TASK_COLLECTION.append(func)
    return func


@sre_task
async def analyze_system_metrics(
    metric_query: str,
    time_range: str = "1h",
    threshold: Optional[float] = None,
    retry: Retry = Retry(attempts=3, delay=timedelta(seconds=5)),
) -> Dict[str, Any]:
    """
    Analyze system metrics and detect anomalies.

    Args:
        metric_query: Prometheus-style metric query
        time_range: Time range for analysis (1h, 6h, 1d, etc.)
        threshold: Alert threshold value
        retry: Retry configuration
    """
    try:
        logger.info(f"Analyzing metrics: {metric_query} over {time_range}")

        # Connect to Prometheus for real metrics
        from ..tools.prometheus_client import get_prometheus_client

        prometheus = get_prometheus_client()
        metrics_data = await prometheus.query_range(query=metric_query, time_range=time_range)

        # Analyze metrics for anomalies
        current_value = None
        anomalies_detected = False
        threshold_breached = False

        if metrics_data and "values" in metrics_data:
            values = [float(v[1]) for v in metrics_data["values"] if v[1] is not None]
            if values:
                current_value = values[-1]  # Latest value

                # Check threshold if provided
                if threshold is not None:
                    threshold_breached = current_value > threshold

                # Simple anomaly detection (check if current value is >2 std devs from mean)
                if len(values) > 5:
                    import statistics

                    mean_val = statistics.mean(values[:-1])  # Exclude current value
                    try:
                        std_dev = statistics.stdev(values[:-1])
                        if abs(current_value - mean_val) > 2 * std_dev:
                            anomalies_detected = True
                    except statistics.StatisticsError:
                        pass  # Not enough data for stdev

        result = {
            "task_id": str(ULID()),
            "metric_query": metric_query,
            "time_range": time_range,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "analyzed",
            "findings": {
                "anomalies_detected": anomalies_detected,
                "current_value": current_value,
                "threshold_breached": threshold_breached,
                "data_points": len(metrics_data.get("values", [])) if metrics_data else 0,
                "metrics_source": "prometheus",
            },
            "raw_metrics": metrics_data,
        }

        # Store result in Redis for retrieval
        client = get_redis_client()
        result_key = f"sre:metrics:{result['task_id']}"
        await client.hset(result_key, mapping=result)
        await client.expire(result_key, 3600)  # 1 hour TTL

        logger.info(f"Metrics analysis completed: {result['task_id']}")
        return result

    except Exception as e:
        logger.error(f"Metrics analysis failed (attempt {retry.attempt}): {e}")
        raise


@sre_task
async def search_runbook_knowledge(
    query: str,
    category: Optional[str] = None,
    limit: int = 5,
    retry: Retry = Retry(attempts=2, delay=timedelta(seconds=2)),
) -> Dict[str, Any]:
    """
    Search SRE knowledge base and runbooks.

    Args:
        query: Search query text
        category: Optional category filter (incident, maintenance, monitoring, etc.)
        limit: Maximum number of results
        retry: Retry configuration
    """
    try:
        logger.info(f"Searching SRE knowledge: '{query}' in category '{category}'")

        # Get vector search components
        index = get_knowledge_index()
        vectorizer = get_vectorizer()

        # Create vector embedding for the query
        query_vector = await vectorizer.embed_many([query])

        # Build search filters
        filters = []
        if category:
            filters.append(f"@category:{category}")

        # Perform vector search
        # Note: This is a simplified version - real implementation would be more complex
        results = await index.query(
            query_vector[0], num_results=limit, filters=filters if filters else None
        )

        search_result = {
            "task_id": str(ULID()),
            "query": query,
            "category": category,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "results_count": len(results),
            "results": [
                {
                    "title": doc.get("title", ""),
                    "content": doc.get("content", "")[:500],  # Truncate for response
                    "source": doc.get("source", ""),
                    "score": doc.get("score", 0.0),
                }
                for doc in results
            ],
        }

        logger.info(
            f"Knowledge search completed: {search_result['task_id']} ({len(results)} results)"
        )
        return search_result

    except Exception as e:
        logger.error(f"Knowledge search failed (attempt {retry.attempt}): {e}")
        raise


@sre_task
async def check_service_health(
    service_name: str,
    endpoints: List[str],
    timeout: int = 30,
    retry: Retry = Retry(attempts=2, delay=timedelta(seconds=3)),
) -> Dict[str, Any]:
    """
    Check health status of a service and its endpoints.

    Args:
        service_name: Name of the service to check
        endpoints: List of health check endpoints
        timeout: Request timeout in seconds
        retry: Retry configuration
    """
    try:
        logger.info(f"Checking health for service: {service_name}")

        # Check if this is Redis service - use direct diagnostics
        if service_name.lower() in ["redis", "redis-server", "redis-cluster"]:
            from ..tools.redis_diagnostics import get_redis_diagnostics

            redis_diag = get_redis_diagnostics()
            diagnostic_results = await redis_diag.run_diagnostic_suite()

            # Convert diagnostics to health check format
            health_results = [
                {
                    "endpoint": "redis_diagnostics",
                    "status": (
                        "healthy"
                        if diagnostic_results["overall_status"] in ["healthy", "warning"]
                        else "unhealthy"
                    ),
                    "response_time_ms": None,
                    "diagnostic_data": diagnostic_results,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            ]

            await redis_diag.close()
        else:
            # For other services, perform HTTP health checks
            import aiohttp

            health_results = []

            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=timeout)
            ) as session:
                for endpoint in endpoints:
                    start_time = datetime.now()

                    try:
                        async with session.get(endpoint) as response:
                            response_time = (datetime.now() - start_time).total_seconds() * 1000

                            health_check = {
                                "endpoint": endpoint,
                                "status": "healthy" if response.status < 400 else "unhealthy",
                                "response_time_ms": round(response_time, 2),
                                "status_code": response.status,
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                            }

                    except Exception as e:
                        health_check = {
                            "endpoint": endpoint,
                            "status": "unhealthy",
                            "response_time_ms": None,
                            "status_code": None,
                            "error": str(e),
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }

                    health_results.append(health_check)

        overall_status = (
            "healthy"
            if all(result["status"] == "healthy" for result in health_results)
            else "unhealthy"
        )

        result = {
            "task_id": str(ULID()),
            "service_name": service_name,
            "overall_status": overall_status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "endpoints_checked": len(endpoints),
            "health_checks": health_results,
        }

        # Store result in Redis
        client = get_redis_client()
        result_key = f"sre:health:{result['task_id']}"
        await client.hset(result_key, mapping=result)
        await client.expire(result_key, 1800)  # 30 minutes TTL

        logger.info(f"Health check completed: {service_name} is {overall_status}")
        return result

    except Exception as e:
        logger.error(f"Health check failed for {service_name} (attempt {retry.attempt}): {e}")
        raise


@sre_task
async def ingest_sre_document(
    title: str,
    content: str,
    source: str,
    category: str = "general",
    severity: str = "info",
    retry: Retry = Retry(attempts=3, delay=timedelta(seconds=2)),
) -> Dict[str, Any]:
    """
    Ingest a document into the SRE knowledge base.

    Args:
        title: Document title
        content: Document content
        source: Source system or file
        category: Document category (incident, runbook, monitoring, etc.)
        severity: Severity level (info, warning, critical)
        retry: Retry configuration
    """
    try:
        logger.info(f"Ingesting SRE document: {title} from {source}")

        # Get components
        index = get_knowledge_index()
        vectorizer = get_vectorizer()

        # Create document embedding
        content_vector = await vectorizer.embed_many([content])

        # Prepare document data
        doc_id = str(ULID())
        document = {
            "title": title,
            "content": content,
            "source": source,
            "category": category,
            "severity": severity,
            "created_at": datetime.now(timezone.utc).timestamp(),
            "vector": content_vector[0],
        }

        # Store in vector index
        doc_key = f"sre_knowledge:{doc_id}"
        await index.load(data=[document], id_field="id", keys=[doc_key])

        result = {
            "task_id": str(ULID()),
            "document_id": doc_id,
            "title": title,
            "source": source,
            "category": category,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "ingested",
        }

        logger.info(f"Document ingested successfully: {doc_id}")
        return result

    except Exception as e:
        logger.error(f"Document ingestion failed (attempt {retry.attempt}): {e}")
        raise


async def get_redis_url() -> str:
    """Get Redis URL for Docket."""
    return settings.redis_url


async def register_sre_tasks() -> None:
    """Register all SRE tasks with Docket."""
    try:
        async with Docket(url=await get_redis_url()) as docket:
            # Register all SRE tasks
            for task in SRE_TASK_COLLECTION:
                docket.register(task)

            logger.info(f"Registered {len(SRE_TASK_COLLECTION)} SRE tasks with Docket")
    except Exception as e:
        logger.error(f"Failed to register SRE tasks: {e}")
        raise


async def test_task_system() -> bool:
    """Test if the task system is working."""
    try:
        # Try to connect to Docket
        async with Docket(url=await get_redis_url()) as docket:
            # Simple connectivity test
            return True
    except Exception as e:
        logger.error(f"Task system test failed: {e}")
        return False
