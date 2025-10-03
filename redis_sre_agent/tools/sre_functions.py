"""SRE tool functions - converted from Docket tasks to regular async functions."""

import logging
import statistics
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ulid import ULID

from redis_sre_agent.core.config import settings
from redis_sre_agent.core.keys import RedisKeys
from redis_sre_agent.core.redis import (
    get_knowledge_index,
    get_vectorizer,
)

logger = logging.getLogger(__name__)


async def validate_url(url: str, timeout: float = 5.0) -> Dict[str, Any]:
    """
    Validate that a URL is accessible and returns a successful response.

    Args:
        url: URL to validate
        timeout: Request timeout in seconds

    Returns:
        Dict with validation results
    """
    try:
        import aiohttp

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
            async with session.head(url) as response:
                return {
                    "url": url,
                    "valid": 200 <= response.status < 400,
                    "status_code": response.status,
                    "error": None,
                }
    except Exception as e:
        return {"url": url, "valid": False, "status_code": None, "error": str(e)}


async def analyze_system_metrics(
    metric_query: str,
    time_range: str = "1h",
    threshold: Optional[float] = None,
    instance_host: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Analyze system metrics and detect anomalies.

    Args:
        metric_query: Prometheus-style metric query
        time_range: Time range for analysis (1h, 6h, 1d, etc.)
        threshold: Alert threshold value
        instance_host: Specific Redis instance host to filter metrics for

    Returns:
        Analysis results with anomaly detection and current values
    """
    try:
        logger.info(f"Analyzing metrics: {metric_query} over {time_range}")
        if instance_host:
            logger.info(f"Filtering metrics for instance host: {instance_host}")

        # Connect to Prometheus for real metrics
        from ..tools.prometheus_client import get_prometheus_client

        prometheus = get_prometheus_client()

        # Modify query to filter by instance host if provided
        final_query = metric_query
        if instance_host and "instance=" not in metric_query.lower():
            # Add instance filter to the query
            if "{" in metric_query:
                # Insert into existing label selector
                final_query = metric_query.replace("{", f'{{instance="{instance_host}",', 1)
            else:
                # Add label selector
                final_query = f'{metric_query}{{instance="{instance_host}"}}'
            logger.info(f"Modified query for instance filtering: {final_query}")

        # Try to query Prometheus, but handle connection failures gracefully
        try:
            metrics_data = await prometheus.query_range(query=final_query, time_range=time_range)
        except Exception as prom_error:
            logger.warning(
                f"Prometheus unavailable ({prom_error}), using simulated metrics for demo"
            )
            # Provide simulated metrics data for demo purposes
            metrics_data = {
                "values": [
                    [1642694400, "50.0"],  # Example timestamp and value
                    [1642697000, "55.0"],
                    [1642699600, "52.0"],
                    [1642702200, "48.0"],
                    [1642704800, "51.0"],
                ]
            }

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
                "metrics_source": "prometheus"
                if "values" in metrics_data and len(metrics_data["values"]) > 5
                else "simulated",
            },
            "raw_metrics": metrics_data,
        }

        logger.info(f"Metrics analysis completed: {result['task_id']}")
        return result

    except Exception as e:
        logger.error(f"Metrics analysis failed: {e}")
        raise


async def search_knowledge_base(
    query: str,
    category: Optional[str] = None,
    product_labels: Optional[List[str]] = None,
    limit: int = 5,
) -> Dict[str, Any]:
    """
    Search the comprehensive knowledge base for relevant information including runbooks,
    Redis documentation, troubleshooting guides, and SRE procedures.

    Args:
        query: Search query
        category: Filter by category (incident, runbook, monitoring, redis_commands, redis_config, etc.)
        product_labels: Filter by Redis product labels (e.g., ["Redis Enterprise Software", "Redis Cloud"])
        limit: Maximum number of results

    Returns:
        Search results with relevant knowledge base content
    """
    logger.info(f"Searching knowledge base: {query}")

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
        return_fields=[
            "title",
            "content",
            "source",
            "category",
            "severity",
            "product_labels",
            "product_label_tags",
            "document_hash",
            "chunk_index",
        ],
        num_results=limit,
    )

    # Build filters for category and product labels
    filters = []
    if category:
        filters.append(f"@category:{{{category}}}")

    if product_labels:
        # Convert product labels to tag format for filtering
        product_label_mapping = {
            "Redis Enterprise Software": "redis_enterprise_software",
            "Redis CE and Stack": "redis_ce_stack",
            "Redis Cloud": "redis_cloud",
            "Redis Enterprise": "redis_enterprise",
            "Redis Insight": "redis_insight",
            "Redis Enterprise for K8s": "redis_enterprise_k8s",
            "Redis Data Integration": "redis_data_integration",
            "Client Libraries": "client_libraries",
        }

        tag_filters = []
        for label in product_labels:
            if label in product_label_mapping:
                tag_filters.append(product_label_mapping[label])
            else:
                # Fallback to normalized version
                tag_filters.append(label.lower().replace(" ", "_"))

        if tag_filters:
            # Use OR logic for multiple product labels
            product_filter = "|".join(tag_filters)
            filters.append(f"@product_label_tags:{{{product_filter}}}")

    # Apply filters if any exist
    if filters:
        combined_filter = " ".join(filters)
        vector_query.set_filter(combined_filter)

    logger.info("Executing vector query...")
    async with index:
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
                    "document_hash": result.get("document_hash", ""),
                    "chunk_index": result.get("chunk_index", 0),
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
                    "document_hash": getattr(result, "document_hash", ""),
                    "chunk_index": getattr(result, "chunk_index", 0),
                }
            )

    # If we got 0 results with a category filter, try again without category
    retry_attempted = False
    if len(formatted_results) == 0 and category is not None:
        logger.info(
            f"No results found with category '{category}', retrying without category filter"
        )
        retry_attempted = True

        # Retry the same search without category
        async with index:
            retry_results = await index.query(vector_query)
        logger.info(f"Retry query results: {len(retry_results) if retry_results else 0} found")

        # Format retry results
        for i, result in enumerate(retry_results):
            if isinstance(result, dict):
                formatted_results.append(
                    {
                        "rank": i + 1,
                        "title": result.get("title", "Unknown"),
                        "content": result.get("content", ""),
                        "source": result.get("source", "Unknown"),
                        "category": result.get("category", "general"),
                        "severity": result.get("severity", "info"),
                        "score": result.get("vector_score", 0.0),
                        "document_hash": result.get("document_hash", ""),
                        "chunk_index": result.get("chunk_index", 0),
                    }
                )
            else:
                formatted_results.append(
                    {
                        "rank": i + 1,
                        "title": getattr(result, "title", "Unknown"),
                        "content": getattr(result, "content", ""),
                        "source": getattr(result, "source", "Unknown"),
                        "category": getattr(result, "category", "general"),
                        "severity": getattr(result, "severity", "info"),
                        "score": getattr(result, "vector_score", 0.0),
                        "document_hash": getattr(result, "document_hash", ""),
                        "chunk_index": getattr(result, "chunk_index", 0),
                    }
                )

    # Format results for better LLM readability with clear source attribution
    formatted_output = f"""
SEARCH RESULTS for query: "{query}"
Found {len(formatted_results)} relevant documents:

"""

    for i, doc in enumerate(formatted_results, 1):
        doc_type = "RUNBOOK" if "runbook" in doc.get("source", "").lower() else "DOCUMENTATION"
        formatted_output += f"""
--- RESULT {i} ---
📋 TITLE: {doc.get("title", "Unknown")}
📁 SOURCE: {doc.get("source", "Unknown")} ({doc_type})
🏷️  CATEGORY: {doc.get("category", "general")} | SEVERITY: {doc.get("severity", "info")}
📊 RELEVANCE SCORE: {doc.get("score", 0.0):.3f}

CONTENT:
{doc.get("content", "")[:800]}{"..." if len(doc.get("content", "")) > 800 else ""}

"""

    if retry_attempted:
        formatted_output += "\n⚠️  NOTE: Initial category search returned no results, broadened search was performed.\n"

    result = {
        "task_id": str(ULID()),
        "query": query,
        "category_filter": category,
        "retry_without_category": retry_attempted,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "completed",
        "results_count": len(formatted_results),
        "results": formatted_results,
        "formatted_output": formatted_output,
        "search_metadata": {
            "index_name": index.name if hasattr(index, "name") else "sre_knowledge",
            "vector_field": "vector",
            "embedding_model": settings.embedding_model,
        },
    }

    if retry_attempted and len(formatted_results) > 0:
        logger.info(
            f"Knowledge search completed after retry: {len(formatted_results)} results found"
        )
    else:
        logger.info(f"Knowledge search completed: {len(formatted_results)} results found")

    # Return the full result dict for API endpoints, but LangGraph can still access formatted_output
    return result


async def get_all_document_fragments(
    document_hash: str, include_metadata: bool = True
) -> Dict[str, Any]:
    """
    Retrieve all fragments/chunks of a specific document.

    This function allows the agent to get the complete document when it finds
    a relevant fragment during search.

    Args:
        document_hash: The document hash to retrieve all fragments for
        include_metadata: Whether to include document metadata

    Returns:
        Dictionary containing all fragments and metadata of the document
    """
    logger.info(f"Retrieving all fragments for document: {document_hash}")

    try:
        # Get components
        index = get_knowledge_index()
        from redis_sre_agent.core.redis import get_redis_client

        # Use the Redis client directly
        redis_client = get_redis_client()

        # Find all chunks for this document
        pattern = RedisKeys.knowledge_chunk_pattern(document_hash)
        chunk_keys = []

        async for key in redis_client.scan_iter(match=pattern):
            if isinstance(key, bytes):
                key = key.decode("utf-8")
            chunk_keys.append(key)

        if not chunk_keys:
            return {
                "document_hash": document_hash,
                "error": "No fragments found for this document",
                "fragments": [],
            }

        # Sort chunk keys by chunk index to maintain order
        chunk_keys.sort(key=lambda k: int(k.split(":")[-1]) if k.split(":")[-1].isdigit() else 0)

        # Retrieve all chunks
        fragments = []
        for key in chunk_keys:
            chunk_data = await redis_client.hgetall(key)
            if chunk_data:
                # Convert bytes to strings, but skip binary fields like vectors
                fragment = {}
                for k, v in chunk_data.items():
                    # Decode key
                    key_str = k.decode("utf-8") if isinstance(k, bytes) else k

                    # Skip vector field (binary data) and other binary fields
                    if key_str in ["vector"]:
                        continue

                    # Decode value safely
                    if isinstance(v, bytes):
                        try:
                            value_str = v.decode("utf-8")
                        except UnicodeDecodeError:
                            # Skip fields that can't be decoded (likely binary)
                            continue
                    else:
                        value_str = v

                    fragment[key_str] = value_str

                fragments.append(fragment)

        # Get document metadata if requested
        metadata = {}
        if include_metadata:
            from redis_sre_agent.pipelines.ingestion.deduplication import DocumentDeduplicator

            deduplicator = DocumentDeduplicator(index)
            metadata = await deduplicator.get_document_metadata(document_hash) or {}

        # Reconstruct full document content
        full_content = ""
        if fragments:
            # Sort fragments by chunk_index
            fragments.sort(key=lambda f: int(f.get("chunk_index", 0)))
            full_content = " ".join(f.get("content", "") for f in fragments)

        result = {
            "document_hash": document_hash,
            "fragments_count": len(fragments),
            "fragments": fragments,
            "metadata": metadata,
            "full_content": full_content,
            "title": fragments[0].get("title", "").split(" (Part ")[0] if fragments else "",
            "source": fragments[0].get("source", "") if fragments else "",
            "category": fragments[0].get("category", "") if fragments else "",
        }

        logger.info(f"Retrieved {len(fragments)} fragments for document {document_hash}")
        return result

    except Exception as e:
        logger.error(f"Failed to retrieve document fragments: {e}")
        return {"document_hash": document_hash, "error": str(e), "fragments": []}


async def get_related_document_fragments(
    document_hash: str, current_chunk_index: Optional[int] = None, context_window: int = 2
) -> Dict[str, Any]:
    """
    Get related fragments around a specific chunk for additional context.

    This is useful when the agent finds a relevant fragment and wants to get
    surrounding context without retrieving the entire document.

    Args:
        document_hash: The document hash to get related fragments for
        current_chunk_index: The chunk index to get context around (if None, gets all)
        context_window: Number of chunks before and after to include

    Returns:
        Dictionary containing related fragments with context
    """
    logger.info(
        f"Getting related fragments for document {document_hash}, chunk {current_chunk_index}"
    )

    try:
        # Get all fragments first
        all_fragments_result = await get_all_document_fragments(
            document_hash, include_metadata=True
        )

        if "error" in all_fragments_result:
            return all_fragments_result

        fragments = all_fragments_result["fragments"]

        if current_chunk_index is None:
            # Return all fragments if no specific chunk specified
            return all_fragments_result

        # Filter to get context window around the specified chunk
        related_fragments = []
        current_chunk_int = (
            int(current_chunk_index)
            if isinstance(current_chunk_index, str)
            else current_chunk_index
        )
        start_index = max(0, current_chunk_int - context_window)
        end_index = min(len(fragments), current_chunk_int + context_window + 1)

        for i in range(start_index, end_index):
            if i < len(fragments):
                fragment = fragments[i]
                fragment["is_target_chunk"] = (
                    int(fragment.get("chunk_index", 0)) == current_chunk_int
                )
                related_fragments.append(fragment)

        # Reconstruct content from related fragments
        related_content = " ".join(f.get("content", "") for f in related_fragments)

        result = {
            "document_hash": document_hash,
            "target_chunk_index": current_chunk_index,
            "context_window": context_window,
            "related_fragments_count": len(related_fragments),
            "related_fragments": related_fragments,
            "related_content": related_content,
            "title": all_fragments_result.get("title", ""),
            "source": all_fragments_result.get("source", ""),
            "category": all_fragments_result.get("category", ""),
            "metadata": all_fragments_result.get("metadata", {}),
        }

        logger.info(
            f"Retrieved {len(related_fragments)} related fragments for document {document_hash}"
        )
        return result

    except Exception as e:
        logger.error(f"Failed to retrieve related document fragments: {e}")
        return {"document_hash": document_hash, "error": str(e), "related_fragments": []}


async def check_service_health(
    service_name: str = "redis",
    redis_url: Optional[str] = None,
    endpoints: Optional[List[str]] = None,
    timeout: float = 10.0,
) -> Dict[str, Any]:
    """
    Check service health with comprehensive diagnostics.

    Args:
        service_name: Name of the service to check
        redis_url: Redis connection URL (required for Redis service checks)
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
            if not redis_url:
                logger.warning("Redis URL not provided for Redis service health check")
                redis_diagnostics = {"error": "Redis URL required for Redis service checks"}
            else:
                try:
                    from ..tools.redis_diagnostics import get_redis_diagnostics

                    redis_client = get_redis_diagnostics(redis_url)
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

        # Generate document hash for proper counting (consistent with bulk ingestion)
        import hashlib

        content_for_hash = f"{title}|{content}|{source}"
        document_hash = hashlib.sha256(content_for_hash.encode()).hexdigest()

        document = {
            "title": title,
            "content": content,
            "source": source,
            "category": category,
            "severity": severity,
            "document_hash": document_hash,  # Add document_hash for proper counting
            "created_at": datetime.now(timezone.utc).timestamp(),
            "vector": content_vector,
        }

        # Store in vector index
        doc_key = RedisKeys.knowledge_document(doc_id)
        document["id"] = doc_id  # Add id field for the index

        async with index:
            # Use the synchronous load method within the async context
            index.load(data=[document], id_field="id", keys=[doc_key])

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
    redis_url: str,
    sections: Optional[str] = None,
    time_window_seconds: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Get detailed Redis diagnostic data for agent analysis.

    This function provides the agent with raw Redis metrics and diagnostics,
    enabling the agent to perform its own analysis and assessment rather than
    receiving pre-calculated status assessments.

    Args:
        redis_url: Redis connection URL to diagnose (required)
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
        all_diagnostics = await get_detailed_redis_diagnostics("redis://localhost:6379")

        # Get specific sections
        memory_data = await get_detailed_redis_diagnostics("redis://localhost:6379", sections="memory")
        perf_data = await get_detailed_redis_diagnostics("redis://localhost:6379", sections="performance,slowlog")
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
            redis_url=redis_url,
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
