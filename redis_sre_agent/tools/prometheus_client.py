"""Prometheus client for metrics queries."""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import aiohttp

from ..core.config import settings

logger = logging.getLogger(__name__)


class PrometheusClient:
    """Client for querying Prometheus metrics."""

    def __init__(self, prometheus_url: Optional[str] = None):
        self.prometheus_url = prometheus_url or getattr(
            settings, "prometheus_url", "http://localhost:9090"
        )
        self.session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session."""
        if self.session is None:
            timeout = aiohttp.ClientTimeout(total=30)
            self.session = aiohttp.ClientSession(timeout=timeout)
        return self.session

    async def close(self):
        """Close HTTP session."""
        if self.session:
            await self.session.close()
            self.session = None

    async def query(self, query: str, time: Optional[datetime] = None) -> Dict[str, Any]:
        """Execute an instant Prometheus query."""
        session = await self._get_session()

        params = {"query": query}
        if time:
            params["time"] = time.timestamp()

        url = urljoin(self.prometheus_url, "/api/v1/query")

        try:
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("status") == "success":
                        return data.get("data", {})
                    else:
                        logger.error(
                            f"Prometheus query failed: {data.get('error', 'Unknown error')}"
                        )
                        return {}
                else:
                    logger.error(f"Prometheus HTTP {response.status}: {await response.text()}")
                    return {}

        except Exception as e:
            logger.error(f"Error querying Prometheus: {e}")
            return {}

    async def query_range(
        self, query: str, time_range: str = "1h", step: str = "15s"
    ) -> Dict[str, Any]:
        """Execute a range Prometheus query."""
        session = await self._get_session()

        # Parse time range to get start/end times
        end_time = datetime.now()
        start_time = self._parse_time_range(time_range, end_time)

        params = {
            "query": query,
            "start": start_time.timestamp(),
            "end": end_time.timestamp(),
            "step": step,
        }

        url = urljoin(self.prometheus_url, "/api/v1/query_range")

        try:
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("status") == "success":
                        result_data = data.get("data", {})

                        # Process results to extract values
                        if result_data.get("resultType") == "matrix" and result_data.get("result"):
                            # Take the first result series
                            series = result_data["result"][0]
                            return {
                                "metric": series.get("metric", {}),
                                "values": series.get("values", []),
                                "query": query,
                                "start_time": start_time.isoformat(),
                                "end_time": end_time.isoformat(),
                            }
                        else:
                            return {"values": [], "query": query}
                    else:
                        logger.error(
                            f"Prometheus range query failed: {data.get('error', 'Unknown error')}"
                        )
                        return {}
                else:
                    logger.error(f"Prometheus HTTP {response.status}: {await response.text()}")
                    return {}

        except Exception as e:
            logger.error(f"Error querying Prometheus range: {e}")
            return {}

    async def get_targets(self) -> List[Dict[str, Any]]:
        """Get Prometheus targets status."""
        session = await self._get_session()
        url = urljoin(self.prometheus_url, "/api/v1/targets")

        try:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("status") == "success":
                        return data.get("data", {}).get("activeTargets", [])
                    else:
                        logger.error(f"Failed to get targets: {data.get('error')}")
                        return []
                else:
                    logger.error(f"Prometheus targets HTTP {response.status}")
                    return []

        except Exception as e:
            logger.error(f"Error getting Prometheus targets: {e}")
            return []

    async def get_labels(self) -> List[str]:
        """Get available metric labels."""
        session = await self._get_session()
        url = urljoin(self.prometheus_url, "/api/v1/labels")

        try:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("status") == "success":
                        return data.get("data", [])
                    else:
                        return []
                else:
                    return []

        except Exception as e:
            logger.error(f"Error getting Prometheus labels: {e}")
            return []

    async def health_check(self) -> Dict[str, Any]:
        """Check Prometheus health and connectivity."""
        try:
            # Test basic connectivity
            session = await self._get_session()
            url = urljoin(self.prometheus_url, "/api/v1/query")
            params = {"query": "up"}

            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("status") == "success":
                        # Count up targets
                        results = data.get("data", {}).get("result", [])
                        up_targets = len(
                            [r for r in results if r.get("value", [None, "0"])[1] == "1"]
                        )

                        return {
                            "status": "healthy",
                            "prometheus_url": self.prometheus_url,
                            "targets_up": up_targets,
                            "total_targets": len(results),
                        }
                    else:
                        return {"status": "error", "error": data.get("error", "Query failed")}
                else:
                    return {"status": "error", "error": f"HTTP {response.status}"}

        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _parse_time_range(self, time_range: str, end_time: datetime) -> datetime:
        """Parse time range string to start datetime."""
        time_range = time_range.lower().strip()

        # Parse format like "1h", "30m", "1d", etc.
        if time_range.endswith("s"):
            seconds = int(time_range[:-1])
            return end_time - timedelta(seconds=seconds)
        elif time_range.endswith("m"):
            minutes = int(time_range[:-1])
            return end_time - timedelta(minutes=minutes)
        elif time_range.endswith("h"):
            hours = int(time_range[:-1])
            return end_time - timedelta(hours=hours)
        elif time_range.endswith("d"):
            days = int(time_range[:-1])
            return end_time - timedelta(days=days)
        else:
            # Default to 1 hour if can't parse
            logger.warning(f"Could not parse time range '{time_range}', using 1h")
            return end_time - timedelta(hours=1)

    async def get_common_redis_metrics(self) -> Dict[str, Any]:
        """Get common Redis metrics from Prometheus."""
        common_queries = {
            "memory_usage": "redis_memory_used_bytes",
            "connected_clients": "redis_connected_clients",
            "ops_per_sec": "rate(redis_commands_processed_total[1m])",
            "keyspace_hits": "redis_keyspace_hits_total",
            "keyspace_misses": "redis_keyspace_misses_total",
            "cpu_usage": "rate(process_cpu_seconds_total{job='redis'}[1m]) * 100",
        }

        results = {}

        for metric_name, query in common_queries.items():
            try:
                result = await self.query(query)
                if result and result.get("result"):
                    # Get the latest value from the first result
                    first_result = result["result"][0]
                    if "value" in first_result:
                        results[metric_name] = {
                            "value": float(first_result["value"][1]),
                            "timestamp": first_result["value"][0],
                            "metric": first_result.get("metric", {}),
                        }
                    else:
                        results[metric_name] = {"error": "No value in result"}
                else:
                    results[metric_name] = {"error": "No results"}

            except Exception as e:
                results[metric_name] = {"error": str(e)}

        return results


# Singleton instance
_prometheus_client: Optional[PrometheusClient] = None


def get_prometheus_client() -> PrometheusClient:
    """Get or create Prometheus client singleton."""
    global _prometheus_client
    if _prometheus_client is None:
        prometheus_url = getattr(settings, "prometheus_url", "http://localhost:9090")
        _prometheus_client = PrometheusClient(prometheus_url)
    return _prometheus_client
