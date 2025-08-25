"""SRE tool functions - converted from Docket tasks to regular async functions."""

import logging
import statistics
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ulid import ULID

from redis_sre_agent.core.config import settings
from redis_sre_agent.core.redis import (
    get_knowledge_index,
    get_vectorizer,
)

logger = logging.getLogger(__name__)


async def analyze_system_metrics(
    metric_query: str,
    time_range: str = "1h",
    threshold: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Analyze system metrics and detect anomalies.

    Args:
        metric_query: Prometheus-style metric query
        time_range: Time range for analysis (1h, 6h, 1d, etc.)
        threshold: Alert threshold value

    Returns:
        Analysis results with anomaly detection and current values
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

        logger.info(f"Metrics analysis completed: {result['task_id']}")
        return result

    except Exception as e:
        logger.error(f"Metrics analysis failed: {e}")
        raise


async def search_runbook_knowledge(
    query: str,
    category: Optional[str] = None,
    limit: int = 5,
) -> Dict[str, Any]:
    """
    Search the SRE knowledge base for relevant information.

    Args:
        query: Search query
        category: Filter by category (incident, runbook, monitoring, etc.)
        limit: Maximum number of results

    Returns:
        Search results with relevant SRE knowledge
    """
    logger.info(f"Searching runbook knowledge: {query}")

    # Get components
    index = get_knowledge_index()
    vectorizer = get_vectorizer()

    # Create query embedding (awaitable shim provided by core.redis.get_vectorizer)
    logger.info("Creating query embedding...")
    vectors = await vectorizer.embed_many([query])
    query_vector = vectors[0]

    # Perform vector search
    from redisvl.query import VectorQuery

    logger.info("Creating VectorQuery...")
    vector_query = VectorQuery(
        vector=query_vector,
        vector_field_name="vector",
        return_fields=["title", "content", "source", "category", "severity"],
        num_results=limit,
    )

    # Note: Category filtering disabled as knowledge base uses oss/enterprise/shared categories
    # Future enhancement: map search categories to actual knowledge base categories
    # if category:
    #     vector_query.set_filter(f"@category:{{{category}}}")

    logger.info("Executing vector query...")
    results = await index.query(vector_query)
    logger.info(
        f"Query results received, type: {type(results)}, count: {len(results) if results else 'None'}"
    )

    # Format results
    formatted_results = []
    for i, result in enumerate(results):
        # Debug: check what type of object result is
        logger.debug(f"Result {i} type: {type(result)}, content: {result}")

        # Handle different result formats
        if isinstance(result, dict):
            # Redis dict format
            formatted_results.append(
                {
                    "rank": i + 1,
                    "title": result.get("title", "Unknown"),
                    "content": result.get("content", ""),
                    "source": result.get("source", "Unknown"),
                    "category": result.get("category", "general"),
                    "severity": result.get("severity", "info"),
                    "score": result.get("vector_score", 0.0),
                }
            )
        else:
            # Object format with attributes
            formatted_results.append(
                {
                    "rank": i + 1,
                    "title": getattr(result, "title", "Unknown"),
                    "content": getattr(result, "content", ""),
                    "source": getattr(result, "source", "Unknown"),
                    "category": getattr(result, "category", "general"),
                    "severity": getattr(result, "severity", "info"),
                    "score": getattr(result, "vector_score", 0.0),
                }
            )

    result = {
        "task_id": str(ULID()),
        "query": query,
        "category_filter": category,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "completed",
        "results_count": len(formatted_results),
        "results": formatted_results,
        "search_metadata": {
            "index_name": index.name if hasattr(index, "name") else "sre_knowledge",
            "vector_field": "vector",
            "embedding_model": settings.embedding_model,
        },
    }

    logger.info(f"Knowledge search completed: {len(formatted_results)} results found")
    return result


async def check_service_health(
    service_name: str = "redis",
    endpoints: Optional[List[str]] = None,
    timeout: float = 10.0,
) -> Dict[str, Any]:
    """
    Check service health with comprehensive diagnostics.

    Args:
        service_name: Name of the service to check
        endpoints: List of health check endpoints
        timeout: Request timeout in seconds

    Returns:
        Comprehensive health check results
    """
    try:
        logger.info(f"Checking health for service: {service_name}")

        if endpoints is None:
            endpoints = ["http://localhost:8000/health"]

        health_results = []
        overall_status = "healthy"

        # Check HTTP endpoints
        import asyncio

        import aiohttp

        async def check_endpoint(url: str) -> Dict[str, Any]:
            try:
                start_time = datetime.now()
                async with aiohttp.ClientSession(
                    timeout=aiohttp.ClientTimeout(total=timeout)
                ) as session:
                    async with session.get(url) as response:
                        end_time = datetime.now()
                        response_time = (end_time - start_time).total_seconds() * 1000

                        return {
                            "endpoint": url,
                            "status": "healthy" if response.status == 200 else "unhealthy",
                            "status_code": response.status,
                            "response_time_ms": round(response_time, 2),
                            "timestamp": start_time.isoformat(),
                        }
            except Exception as e:
                return {
                    "endpoint": url,
                    "status": "failed",
                    "error": str(e),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }

        # Check all endpoints concurrently
        endpoint_tasks = [check_endpoint(url) for url in endpoints]
        health_results = await asyncio.gather(*endpoint_tasks, return_exceptions=True)

        # Handle exceptions in results
        processed_results = []
        for result in health_results:
            if isinstance(result, Exception):
                processed_results.append(
                    {
                        "status": "error",
                        "error": str(result),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                )
                overall_status = "unhealthy"
            else:
                processed_results.append(result)
                if result.get("status") != "healthy":
                    overall_status = "unhealthy"

        # Run Redis-specific diagnostics if this is a Redis service
        redis_diagnostics = None
        if service_name.lower() == "redis":
            try:
                from ..tools.redis_diagnostics import get_redis_diagnostics

                redis_client = get_redis_diagnostics()
                redis_diagnostics = await redis_client.run_diagnostic_suite()

                # Update overall status based on Redis diagnostics
                if redis_diagnostics.get("overall_status") == "critical":
                    overall_status = "critical"
                elif (
                    redis_diagnostics.get("overall_status") == "warning"
                    and overall_status == "healthy"
                ):
                    overall_status = "warning"

            except Exception as e:
                logger.warning(f"Redis diagnostics failed: {e}")
                redis_diagnostics = {"error": str(e)}

        result = {
            "task_id": str(ULID()),
            "service_name": service_name,
            "overall_status": overall_status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "endpoints_checked": len(endpoints),
            "health_checks": processed_results,
            "redis_diagnostics": redis_diagnostics,
        }

        logger.info(f"Health check completed: {service_name} is {overall_status}")
        return result

    except Exception as e:
        logger.error(f"Health check failed for {service_name}: {e}")
        raise


async def ingest_sre_document(
    title: str,
    content: str,
    source: str,
    category: str = "general",
    severity: str = "info",
) -> Dict[str, Any]:
    """
    Ingest a document into the SRE knowledge base.

    Args:
        title: Document title
        content: Document content
        source: Source system or file
        category: Document category (incident, runbook, monitoring, etc.)
        severity: Severity level (info, warning, critical)

    Returns:
        Ingestion result with document ID
    """
    try:
        logger.info(f"Ingesting SRE document: {title} from {source}")

        # Get components
        index = get_knowledge_index()
        vectorizer = get_vectorizer()

        # Create document embedding (awaitable shim provided)
        vectors = await vectorizer.embed_many([content])
        content_vector = vectors[0]

        # Prepare document data
        doc_id = str(ULID())
        document = {
            "title": title,
            "content": content,
            "source": source,
            "category": category,
            "severity": severity,
            "created_at": datetime.now(timezone.utc).timestamp(),
            "vector": content_vector,
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
        logger.error(f"Document ingestion failed: {e}")
        raise


async def get_detailed_redis_diagnostics(
    sections: Optional[str] = None,
    time_window_seconds: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Get detailed Redis diagnostic data for agent analysis.

    This function provides the agent with raw Redis metrics and diagnostics,
    enabling the agent to perform its own analysis and assessment rather than
    receiving pre-calculated status assessments.

    Args:
        sections: Comma-separated diagnostic sections to capture:
            - "memory": Memory usage and fragmentation metrics
            - "performance": Hit rates, ops/sec, command statistics
            - "clients": Connection analysis and client patterns
            - "slowlog": Slow query log analysis
            - "configuration": Current Redis configuration
            - "keyspace": Database and key statistics
            - "replication": Master/slave replication status
            - "persistence": RDB/AOF persistence status
            - "cpu": CPU usage statistics
            - None or "all": Capture all sections

        time_window_seconds: Time window for time-series analysis (future enhancement)

    Returns:
        Dict containing raw diagnostic metrics without pre-calculated assessments.
        Agent is responsible for analysis, calculations, and severity determination.

    Example:
        # Get comprehensive diagnostics
        all_diagnostics = await get_detailed_redis_diagnostics()

        # Get specific sections
        memory_data = await get_detailed_redis_diagnostics(sections="memory")
        perf_data = await get_detailed_redis_diagnostics(sections="performance,slowlog")
    """
    try:
        logger.info(
            f"Getting detailed Redis diagnostics: sections={sections}, time_window={time_window_seconds}"
        )

        # Import the shared diagnostic function
        from ..tools.redis_diagnostics import capture_redis_diagnostics

        # Parse sections parameter
        sections_list = None
        if sections and sections != "all":
            sections_list = [s.strip() for s in sections.split(",") if s.strip()]

        # Capture diagnostic data using shared function
        diagnostic_data = await capture_redis_diagnostics(
            sections=sections_list,
            time_window_seconds=time_window_seconds,
            include_raw_data=True,  # Include raw Redis INFO for comprehensive analysis
        )

        # Add task metadata for consistency with other SRE functions
        result = {
            "task_id": str(ULID()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": diagnostic_data.get("capture_status", "unknown"),
            "sections_requested": sections or "all",
            "sections_captured": diagnostic_data.get("sections_captured", []),
            "redis_url": diagnostic_data.get("redis_url"),
            "capture_timestamp": diagnostic_data.get("timestamp"),
            "diagnostics": diagnostic_data.get("diagnostics", {}),
            "metadata": {
                "function": "get_detailed_redis_diagnostics",
                "data_format": "raw_metrics_only",
                "agent_analysis_required": True,
                "no_pre_calculated_status": True,
            },
        }

        # Check if capture was successful
        if result["status"] != "success":
            error_msg = diagnostic_data.get("diagnostics", {}).get("error", "Unknown capture error")
            logger.error(f"Redis diagnostics capture failed: {error_msg}")
            result["error"] = error_msg

        logger.info(f"Redis diagnostics completed: {result['task_id']} - {result['status']}")
        return result

    except Exception as e:
        logger.error(f"Failed to get detailed Redis diagnostics: {e}")
        raise
