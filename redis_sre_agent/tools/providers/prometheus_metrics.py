"""Prometheus metrics provider implementation.

This provider connects to Prometheus to query time-series metrics data.
It supports both current values and historical time-range queries.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import aiohttp

from ..protocols import MetricDefinition, MetricValue, TimeRange

logger = logging.getLogger(__name__)


class PrometheusMetricsProvider:
    """Prometheus-based metrics provider.

    This provider connects to Prometheus and can query both current values
    and historical time-series data for Redis and system metrics.
    """

    def __init__(self, prometheus_url: str):
        self.prometheus_url = prometheus_url
        self.session: Optional[aiohttp.ClientSession] = None
        self._metric_definitions: Optional[List[MetricDefinition]] = None

    @property
    def provider_name(self) -> str:
        return f"Prometheus ({self.prometheus_url})"

    @property
    def supports_time_queries(self) -> bool:
        return True

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session."""
        if self.session is None:
            timeout = aiohttp.ClientTimeout(total=30)
            self.session = aiohttp.ClientSession(timeout=timeout)
        return self.session

    async def list_metrics(self) -> List[MetricDefinition]:
        """List available Prometheus metrics."""
        if self._metric_definitions is not None:
            return self._metric_definitions

        # Common Redis metrics available in Prometheus (via redis_exporter)
        metrics = [
            # Memory metrics
            MetricDefinition("redis_memory_used_bytes", "Memory used by Redis", "bytes", "gauge"),
            MetricDefinition(
                "redis_memory_max_bytes", "Maximum memory configured", "bytes", "gauge"
            ),
            MetricDefinition(
                "redis_memory_fragmentation_ratio", "Memory fragmentation ratio", "ratio", "gauge"
            ),
            # Connection metrics
            MetricDefinition(
                "redis_connected_clients", "Number of connected clients", "count", "gauge"
            ),
            MetricDefinition(
                "redis_blocked_clients", "Number of blocked clients", "count", "gauge"
            ),
            MetricDefinition(
                "redis_rejected_connections_total", "Total rejected connections", "count", "counter"
            ),
            # Performance metrics
            MetricDefinition(
                "redis_commands_processed_total", "Total commands processed", "count", "counter"
            ),
            MetricDefinition(
                "redis_instantaneous_ops_per_sec", "Operations per second", "ops/sec", "gauge"
            ),
            MetricDefinition(
                "redis_keyspace_hits_total", "Total keyspace hits", "count", "counter"
            ),
            MetricDefinition(
                "redis_keyspace_misses_total", "Total keyspace misses", "count", "counter"
            ),
            MetricDefinition("redis_expired_keys_total", "Total expired keys", "count", "counter"),
            MetricDefinition("redis_evicted_keys_total", "Total evicted keys", "count", "counter"),
            # Database metrics
            MetricDefinition("redis_db_keys", "Number of keys per database", "count", "gauge"),
            MetricDefinition(
                "redis_db_keys_expiring", "Number of expiring keys per database", "count", "gauge"
            ),
            # System metrics (if node_exporter is available)
            MetricDefinition(
                "node_memory_MemAvailable_bytes", "Available system memory", "bytes", "gauge"
            ),
            MetricDefinition("node_memory_MemTotal_bytes", "Total system memory", "bytes", "gauge"),
            MetricDefinition("node_cpu_seconds_total", "CPU time spent", "seconds", "counter"),
            MetricDefinition("node_load1", "1-minute load average", "load", "gauge"),
            # Network metrics
            MetricDefinition(
                "redis_net_input_bytes_total", "Total network input bytes", "bytes", "counter"
            ),
            MetricDefinition(
                "redis_net_output_bytes_total", "Total network output bytes", "bytes", "counter"
            ),
        ]

        self._metric_definitions = metrics
        return metrics

    async def get_current_value(
        self, metric_name: str, labels: Optional[Dict[str, str]] = None
    ) -> Optional[MetricValue]:
        """Get current value of a Prometheus metric."""
        try:
            session = await self._get_session()

            # Build query with labels if provided
            query = metric_name
            if labels:
                label_filters = ",".join([f'{k}="{v}"' for k, v in labels.items()])
                query = f"{metric_name}{{{label_filters}}}"

            params = {"query": query}
            url = urljoin(self.prometheus_url, "/api/v1/query")

            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("status") == "success":
                        result_data = data.get("data", {})
                        results = result_data.get("result", [])

                        if results:
                            # Take the first result
                            result = results[0]
                            value_data = result.get("value", [])
                            if len(value_data) >= 2:
                                timestamp = datetime.fromtimestamp(float(value_data[0]))
                                value = float(value_data[1])
                                result_labels = result.get("metric", {})

                                return MetricValue(value, timestamp, result_labels)

                return None

        except Exception as e:
            logger.error(f"Error getting Prometheus metric {metric_name}: {e}")
            return None

    async def query_time_range(
        self,
        metric_name: str,
        time_range: TimeRange,
        labels: Optional[Dict[str, str]] = None,
        step: Optional[str] = None,
    ) -> List[MetricValue]:
        """Query Prometheus metric values over a time range."""
        try:
            session = await self._get_session()

            # Build query with labels if provided
            query = metric_name
            if labels:
                label_filters = ",".join([f'{k}="{v}"' for k, v in labels.items()])
                query = f"{metric_name}{{{label_filters}}}"

            params = {
                "query": query,
                "start": time_range.start.timestamp(),
                "end": time_range.end.timestamp(),
                "step": step or "15s",
            }

            url = urljoin(self.prometheus_url, "/api/v1/query_range")

            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("status") == "success":
                        result_data = data.get("data", {})
                        results = result_data.get("result", [])

                        metric_values = []
                        for result in results:
                            result_labels = result.get("metric", {})
                            values = result.get("values", [])

                            for value_data in values:
                                if len(value_data) >= 2:
                                    timestamp = datetime.fromtimestamp(float(value_data[0]))
                                    value = float(value_data[1])
                                    metric_values.append(
                                        MetricValue(value, timestamp, result_labels)
                                    )

                        return sorted(metric_values, key=lambda x: x.timestamp)

                return []

        except Exception as e:
            logger.error(f"Error querying Prometheus time range for {metric_name}: {e}")
            return []

    async def health_check(self) -> Dict[str, Any]:
        """Check Prometheus connection health."""
        try:
            session = await self._get_session()
            url = urljoin(self.prometheus_url, "/api/v1/query")
            params = {"query": "up"}

            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("status") == "success":
                        return {
                            "status": "healthy",
                            "provider": self.provider_name,
                            "connected": True,
                            "prometheus_status": "up",
                            "timestamp": datetime.now().isoformat(),
                        }

                return {
                    "status": "unhealthy",
                    "provider": self.provider_name,
                    "error": f"HTTP {response.status}",
                    "connected": False,
                    "timestamp": datetime.now().isoformat(),
                }

        except Exception as e:
            return {
                "status": "unhealthy",
                "provider": self.provider_name,
                "error": str(e),
                "connected": False,
                "timestamp": datetime.now().isoformat(),
            }

    async def close(self):
        """Close HTTP session."""
        if self.session:
            await self.session.close()
            self.session = None


# Helper function to create instances
def create_prometheus_provider(prometheus_url: str) -> PrometheusMetricsProvider:
    """Create a Prometheus metrics provider instance."""
    return PrometheusMetricsProvider(prometheus_url)
