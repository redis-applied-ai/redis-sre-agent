"""Prometheus metrics endpoint for the Redis SRE Agent API."""

import logging
import time
from typing import Any, Dict

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from redis_sre_agent.core.config import settings
from redis_sre_agent.core.redis import get_redis_client, test_redis_connection

logger = logging.getLogger(__name__)

router = APIRouter()


def format_prometheus_metric(
    name: str, value: float, labels: Dict[str, str] = None, help_text: str = None
) -> str:
    """Format a metric in Prometheus exposition format."""
    lines = []

    if help_text:
        lines.append(f"# HELP {name} {help_text}")
        lines.append(f"# TYPE {name} gauge")

    if labels:
        label_str = ",".join([f'{k}="{v}"' for k, v in labels.items()])
        lines.append(f"{name}{{{label_str}}} {value}")
    else:
        lines.append(f"{name} {value}")

    return "\n".join(lines)


async def get_application_metrics() -> Dict[str, Any]:
    """Get application-specific metrics."""
    metrics = {}

    # Basic application info
    metrics["sre_agent_info"] = {
        "value": 1,
        "labels": {
            "version": "0.1.0",
            "app_name": settings.app_name,
            "embedding_model": settings.embedding_model,
        },
        "help": "SRE Agent application information",
    }

    # Redis connection status
    try:
        redis_ok = await test_redis_connection()
        metrics["sre_agent_redis_connection_status"] = {
            "value": 1 if redis_ok else 0,
            "help": "Redis connection status (1=connected, 0=disconnected)",
        }
    except Exception as e:
        logger.error(f"Error checking Redis connection: {e}")
        metrics["sre_agent_redis_connection_status"] = {
            "value": 0,
            "help": "Redis connection status (1=connected, 0=disconnected)",
        }

    # Vector index status
    try:
        from redis_sre_agent.core.redis import get_knowledge_index

        knowledge_index = get_knowledge_index()
        index_exists = await knowledge_index.exists()
        metrics["sre_agent_vector_index_status"] = {
            "value": 1 if index_exists else 0,
            "help": "Vector index status (1=exists, 0=missing)",
        }
    except Exception as e:
        logger.error(f"Error checking vector index: {e}")
        metrics["sre_agent_vector_index_status"] = {
            "value": 0,
            "help": "Vector index status (1=exists, 0=missing)",
        }

    # Knowledge base document count
    try:
        redis_client = get_redis_client()
        # Count documents in the knowledge base
        doc_count = await redis_client.hlen("sre_knowledge:documents")
        metrics["sre_agent_knowledge_documents_total"] = {
            "value": doc_count,
            "help": "Total number of documents in knowledge base",
        }
    except Exception as e:
        logger.error(f"Error counting knowledge documents: {e}")
        metrics["sre_agent_knowledge_documents_total"] = {
            "value": 0,
            "help": "Total number of documents in knowledge base",
        }

    # Task queue status
    try:
        from docket.docket import Docket

        async with Docket(url=settings.redis_url, name="sre_docket") as docket:
            workers = await docket.workers()
            metrics["sre_agent_workers_total"] = {
                "value": len(workers),
                "help": "Number of active task workers",
            }
    except Exception as e:
        logger.warning(f"Error checking workers: {e}")
        metrics["sre_agent_workers_total"] = {"value": 0, "help": "Number of active task workers"}

    # Application uptime (simple timestamp)
    metrics["sre_agent_start_time_seconds"] = {
        "value": time.time(),
        "help": "Unix timestamp when the application started",
    }

    return metrics


@router.get("/metrics", response_class=PlainTextResponse)
async def prometheus_metrics():
    """
    Prometheus metrics endpoint.

    Returns application metrics in Prometheus exposition format.
    """
    try:
        metrics = await get_application_metrics()

        # Format metrics in Prometheus format
        metric_lines = []

        for metric_name, metric_data in metrics.items():
            formatted = format_prometheus_metric(
                name=metric_name,
                value=metric_data["value"],
                labels=metric_data.get("labels"),
                help_text=metric_data.get("help"),
            )
            metric_lines.append(formatted)

        # Add a final newline
        return "\n".join(metric_lines) + "\n"

    except Exception as e:
        logger.error(f"Error generating metrics: {e}")
        # Return minimal metrics on error
        error_metric = format_prometheus_metric(
            name="sre_agent_metrics_error",
            value=1,
            help_text="Error occurred while generating metrics",
        )
        return error_metric + "\n"


@router.get("/metrics/health", response_class=PlainTextResponse)
async def metrics_health():
    """
    Simple health check for metrics endpoint.

    Returns a simple metric indicating the metrics endpoint is working.
    """
    metric = format_prometheus_metric(
        name="sre_agent_metrics_up", value=1, help_text="Metrics endpoint is responding"
    )
    return metric + "\n"
